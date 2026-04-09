from __future__ import annotations

import asyncio
import atexit
import logging
import os
import random
import shutil
import tempfile
from typing import Awaitable, Callable, Optional, TypeVar

from dotenv import load_dotenv

from browser_use import Agent, Browser, ChatOpenAI

from app.cache import load_cached_model, save_cached_model
from app.config import (
    AGENT_MAX_RETRIES,
    AGENT_RETRY_BASE_DELAY_SEC,
    AGENT_RETRY_MAX_DELAY_SEC,
    BASE_TAGS,
    DEFAULT_BROWSER_MODEL,
    DEFAULT_TAGS_MODEL,
)
from app.models import AgentProductCard, DiscoveryBatch, GeneratedTags, ProductCard, ProductImage
from app.prompts import (
    make_discovery_prompt,
    make_pattern_vault_prompt,
    make_product_prompt,
    make_tags_prompt,
)
from app.utils import (
    dedupe_preserve_order,
    get_structured_output,
    is_allowed_product_url,
    is_allowed_section_url,
    merge_tags,
    normalize_tag,
)

logger = logging.getLogger(__name__)

_TEMP_BROWSER_DIRS: list[str] = []
_ALLOWED_TAGS = {normalize_tag(tag) for tag in BASE_TAGS}
T = TypeVar("T")


def _cleanup_temp_browser_dirs() -> None:
    for d in _TEMP_BROWSER_DIRS:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


atexit.register(_cleanup_temp_browser_dirs)


def build_llm(model_name: str | None = None) -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env")

    return ChatOpenAI(
        model=model_name or DEFAULT_BROWSER_MODEL,
        api_key=api_key,
    )


def build_browser() -> Browser:
    profile_dir = tempfile.mkdtemp(prefix="browseruse_profile_")
    _TEMP_BROWSER_DIRS.append(profile_dir)

    logger.debug("Created browser profile dir: %s", profile_dir)

    return Browser(
        headless=True,
        channel="chromium",
        user_data_dir=profile_dir,
        enable_default_extensions=False,
        args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )


async def _close_browser(browser: Browser) -> None:
    maybe_close = getattr(browser, "close", None)
    if callable(maybe_close):
        maybe = maybe_close()
        if asyncio.iscoroutine(maybe):
            await maybe


async def _run_with_retry(
    phase: str,
    target: str,
    op: Callable[[], Awaitable[T]],
    max_retries: int = AGENT_MAX_RETRIES,
) -> T:
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await op()
        except Exception as e:
            last_error = e
            retryable = attempt < max_retries
            logger.warning(
                "[RETRY] phase=%s target=%s attempt=%s/%s error=%s",
                phase,
                target,
                attempt,
                max_retries,
                e,
            )
            if not retryable:
                break

            delay = min(
                AGENT_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)),
                AGENT_RETRY_MAX_DELAY_SEC,
            )
            delay += random.uniform(0, 0.5)
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _normalized_allowed_or_short_tag(value: str | None) -> str | None:
    text = _clean_value(value)
    if not text:
        return None

    tag = normalize_tag(text)
    if not tag:
        return None

    if tag in _ALLOWED_TAGS:
        return tag

    if len(tag) <= 32 and tag.count("-") <= 3:
        return tag

    return None


def _expand_gender_tags(gender: str | None) -> list[str]:
    tag = _normalized_allowed_or_short_tag(gender)
    if not tag:
        return []

    mapping = {
        "woman": "women",
        "women": "women",
        "female": "women",
        "lady": "women",
        "man": "men",
        "men": "men",
        "male": "men",
        "unisex": "unisex",
    }
    mapped = mapping.get(tag, tag)
    return [mapped] if mapped else []


def _deterministic_tags(card: ProductCard) -> list[str]:
    tags: list[str] = []

    if card.source_site:
        tags.append(normalize_tag(card.source_site))

    tags.extend(_expand_gender_tags(card.gender))

    for value in [card.category, card.subcategory]:
        tag = _normalized_allowed_or_short_tag(value)
        if tag:
            tags.append(tag)

    for group in [card.season, card.garment_elements, card.materials]:
        for value in group:
            tag = _normalized_allowed_or_short_tag(value)
            if tag:
                tags.append(tag)

    if card.pattern_info:
        text = card.pattern_info.lower()
        if "pdf" in text:
            tags.append("pdf-pattern")
        if "pattern" in text or "выкрой" in text:
            tags.append("sewing-pattern")

    return merge_tags(tags)


def _should_skip_llm_tags(base_tags: list[str], card: ProductCard) -> bool:
    informative_fields = sum(
        1 for value in [card.gender, card.category, card.subcategory] if _clean_value(value)
    )
    informative_groups = sum(
        1 for group in [card.season, card.garment_elements, card.materials] if group
    )

    if len(base_tags) >= 8:
        return True

    if len(base_tags) >= 5 and (informative_fields + informative_groups) >= 3:
        return True

    return False


def _is_pattern_vault_page(url: str) -> bool:
    normalized = url.lower()
    return "pattern-vault.com/free-designer-patterns" in normalized


def _make_discovery_task(page_url: str, product_limit: int, section_limit: int) -> tuple[str, str]:
    if _is_pattern_vault_page(page_url):
        return (
            "pattern_vault",
            make_pattern_vault_prompt(page_url, product_limit),
        )

    return (
        "default",
        make_discovery_prompt(page_url, product_limit, section_limit),
    )


def _to_product_card(data: AgentProductCard) -> ProductCard:
    image_urls = dedupe_preserve_order(data.image_urls)
    images = [ProductImage(url=url) for url in image_urls if url]
    return ProductCard(
        source_site=data.source_site,
        product_url=data.product_url,
        title=data.title,
        gender=data.gender,
        category=data.category,
        subcategory=data.subcategory,
        season=data.season,
        garment_elements=data.garment_elements,
        materials=data.materials,
        short_description=data.short_description,
        pattern_info=data.pattern_info,
        raw_text=data.raw_text,
        adult_only=data.adult_only,
        is_accessory=data.is_accessory,
        is_child_item=data.is_child_item,
        images=images,
    )


async def discover_batch_for_page(
    page_url: str,
    product_limit: int,
    section_limit: int,
) -> DiscoveryBatch:
    prompt_kind, task = _make_discovery_task(page_url, product_limit, section_limit)

    cache_payload = {
        "page_url": page_url,
        "product_limit": product_limit,
        "section_limit": section_limit,
        "prompt_kind": prompt_kind,
    }
    cached = load_cached_model("discover_page", cache_payload, DiscoveryBatch)
    if cached is not None:
        logger.info("Discovery cache hit: %s", page_url)
        cached.product_urls = [
            u for u in dedupe_preserve_order(cached.product_urls)
            if is_allowed_product_url(u)
        ][:product_limit]
        cached.next_section_urls = [
            u for u in dedupe_preserve_order(cached.next_section_urls)
            if is_allowed_section_url(u)
        ][:section_limit]
        return cached

    async def _op() -> DiscoveryBatch:
        browser = build_browser()
        try:
            logger.info(
                "Discovering from page: page_url=%s product_limit=%s section_limit=%s prompt_kind=%s",
                page_url,
                product_limit,
                section_limit,
                prompt_kind,
            )

            agent = Agent(
                task=task,
                llm=build_llm(DEFAULT_BROWSER_MODEL),
                browser=browser,
                use_vision=False,
                output_model_schema=DiscoveryBatch,
                max_failures=3,
            )
            result = await agent.run()
            data = get_structured_output(result)
            if not data:
                raise RuntimeError("no structured discovery output")

            data.product_urls = [
                u for u in dedupe_preserve_order(data.product_urls)
                if is_allowed_product_url(u)
            ][:product_limit]
            used = set(data.product_urls)
            data.next_section_urls = [
                u for u in dedupe_preserve_order(data.next_section_urls)
                if u not in used and is_allowed_section_url(u)
            ][:section_limit]

            save_cached_model("discover_page", cache_payload, data)
            return data
        finally:
            await _close_browser(browser)

    data = await _run_with_retry("discover", page_url, _op)
    logger.info(
        "Discovered product_urls=%s next_section_urls=%s from %s",
        len(data.product_urls),
        len(data.next_section_urls),
        page_url,
    )
    return data


async def extract_product(product_url: str) -> Optional[ProductCard]:
    cache_payload = {"product_url": product_url}
    cached = load_cached_model("extract_product", cache_payload, ProductCard)
    if cached is not None:
        logger.info("Product cache hit: %s", product_url)
        return cached

    async def _op() -> ProductCard:
        browser = build_browser()
        try:
            logger.info("Extracting product: %s", product_url)
            agent = Agent(
                task=make_product_prompt(product_url),
                llm=build_llm(DEFAULT_BROWSER_MODEL),
                browser=browser,
                use_vision=True,
                output_model_schema=AgentProductCard,
                max_failures=3,
            )
            result = await agent.run()
            data = get_structured_output(result)
            if data is None:
                raise RuntimeError("no structured product output")

            card = _to_product_card(data)
            save_cached_model("extract_product", cache_payload, card)
            return card
        finally:
            await _close_browser(browser)

    return await _run_with_retry("extract", product_url, _op)


async def _generate_tags_llm(card: ProductCard) -> list[str]:
    async def _op() -> list[str]:
        browser = build_browser()
        try:
            logger.info("Generating LLM tags for: %s", card.product_url or card.title)
            agent = Agent(
                task=make_tags_prompt(card),
                llm=build_llm(DEFAULT_TAGS_MODEL),
                browser=browser,
                use_vision=False,
                output_model_schema=GeneratedTags,
                max_failures=2,
            )
            result = await agent.run()
            data = get_structured_output(result)
            if not data:
                raise RuntimeError("no structured tags output")

            return dedupe_preserve_order(data.tags)
        finally:
            await _close_browser(browser)

    return await _run_with_retry("tags", card.product_url or card.title, _op)


async def generate_tags(card: ProductCard) -> list[str]:
    payload = card.model_dump(mode="json")
    cached = load_cached_model("generate_tags", payload, GeneratedTags)
    if cached is not None:
        logger.info("Tags cache hit: %s", card.product_url or card.title)
        return dedupe_preserve_order(cached.tags)

    base_tags = _deterministic_tags(card)
    logger.info(
        "Base tags for %s: count=%s tags=%s",
        card.product_url or card.title,
        len(base_tags),
        base_tags,
    )

    if _should_skip_llm_tags(base_tags, card):
        logger.info("Skipping LLM tags for %s", card.product_url or card.title)
        result = GeneratedTags(tags=base_tags)
        save_cached_model("generate_tags", payload, result)
        return result.tags

    llm_tags = await _generate_tags_llm(card)
    final_tags = merge_tags(base_tags, llm_tags)

    result = GeneratedTags(tags=final_tags)
    save_cached_model("generate_tags", payload, result)
    return result.tags