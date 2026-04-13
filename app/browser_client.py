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
    DEFAULT_BROWSER_MODEL,
)
from app.models import DiscoveryBatch
from app.prompts import make_discovery_prompt, make_discovery_via_parent_prompt
from app.utils import (
    dedupe_preserve_order,
    get_structured_output,
    is_allowed_product_url,
    is_allowed_section_url,
)

logger = logging.getLogger(__name__)

_TEMP_BROWSER_DIRS: list[str] = []
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


def _coerce_batch(raw, product_limit: int, section_limit: int) -> DiscoveryBatch:
    if isinstance(raw, DiscoveryBatch):
        data = raw
    elif isinstance(raw, dict):
        data = DiscoveryBatch.model_validate(raw)
    else:
        raise RuntimeError(f"unexpected structured output type: {type(raw)!r}")

    data.product_urls = [
        u for u in dedupe_preserve_order(data.product_urls)
        if is_allowed_product_url(u)
    ][:product_limit]

    data.next_section_urls = [
        u for u in dedupe_preserve_order(data.next_section_urls)
        if is_allowed_section_url(u)
    ][:section_limit]

    return data


def _normalize_batch(
    data: DiscoveryBatch,
    product_limit: int,
    section_limit: int,
    current_url: str | None = None,
    target_url: str | None = None,
    parent_url: str | None = None,
) -> DiscoveryBatch:
    data.product_urls = [
        u for u in dedupe_preserve_order(data.product_urls)
        if is_allowed_product_url(u)
    ][:product_limit]

    excluded_sections = {u for u in [current_url, target_url] if u}
    used = set(data.product_urls)

    normalized_sections: list[str] = []
    for u in dedupe_preserve_order(data.next_section_urls):
        if u in used:
            continue
        if u in excluded_sections:
            continue
        if parent_url and u == parent_url:
            continue
        if not is_allowed_section_url(u):
            continue
        normalized_sections.append(u)

    data.next_section_urls = normalized_sections[:section_limit]
    return data


async def _discover_direct(
    page_url: str,
    product_limit: int,
    section_limit: int,
) -> DiscoveryBatch:
    cache_payload = {
        "mode": "direct",
        "page_url": page_url,
        "product_limit": product_limit,
        "section_limit": section_limit,
    }
    cached = load_cached_model("discover_page", cache_payload, DiscoveryBatch)
    if cached is not None:
        logger.info("Discovery cache hit (direct): %s", page_url)
        return _normalize_batch(
            cached,
            product_limit,
            section_limit,
            current_url=page_url,
            target_url=page_url,
        )

    async def _op() -> DiscoveryBatch:
        browser = build_browser()
        try:
            logger.info(
                "Discovering direct: page_url=%s product_limit=%s section_limit=%s",
                page_url,
                product_limit,
                section_limit,
            )

            agent = Agent(
                task=make_discovery_prompt(
                    page_url=page_url,
                    product_limit=product_limit,
                    section_limit=section_limit,
                ),
                llm=build_llm(DEFAULT_BROWSER_MODEL),
                browser=browser,
                use_vision=False,
                output_model_schema=DiscoveryBatch,
                max_failures=2,
            )
            result = await agent.run()
            raw = get_structured_output(result)
            if raw is None:
                raise RuntimeError("no structured discovery output")

            data = _coerce_batch(raw, product_limit, section_limit)
            data = _normalize_batch(
                data,
                product_limit,
                section_limit,
                current_url=page_url,
                target_url=page_url,
            )
            save_cached_model("discover_page", cache_payload, data)
            return data
        finally:
            await _close_browser(browser)

    return await _run_with_retry("discover_direct", page_url, _op)


async def _discover_via_parent(
    parent_url: str,
    target_url: str,
    product_limit: int,
    section_limit: int,
) -> DiscoveryBatch:
    cache_payload = {
        "mode": "via_parent",
        "parent_url": parent_url,
        "target_url": target_url,
        "product_limit": product_limit,
        "section_limit": section_limit,
    }
    cached = load_cached_model("discover_page", cache_payload, DiscoveryBatch)
    if cached is not None:
        logger.info("Discovery cache hit (via_parent): parent=%s target=%s", parent_url, target_url)
        return _normalize_batch(
            cached,
            product_limit,
            section_limit,
            current_url=target_url,
            target_url=target_url,
            parent_url=parent_url,
        )

    async def _op() -> DiscoveryBatch:
        browser = build_browser()
        try:
            logger.info(
                "Discovering via parent: parent_url=%s target_url=%s product_limit=%s section_limit=%s",
                parent_url,
                target_url,
                product_limit,
                section_limit,
            )

            agent = Agent(
                task=make_discovery_via_parent_prompt(
                    parent_url=parent_url,
                    target_url=target_url,
                    product_limit=product_limit,
                    section_limit=section_limit,
                ),
                llm=build_llm(DEFAULT_BROWSER_MODEL),
                browser=browser,
                use_vision=False,
                output_model_schema=DiscoveryBatch,
                max_failures=2,
            )
            result = await agent.run()
            raw = get_structured_output(result)
            if raw is None:
                raise RuntimeError("no structured discovery output via parent")

            data = _coerce_batch(raw, product_limit, section_limit)
            data = _normalize_batch(
                data,
                product_limit,
                section_limit,
                current_url=target_url,
                target_url=target_url,
                parent_url=parent_url,
            )
            save_cached_model("discover_page", cache_payload, data)
            return data
        finally:
            await _close_browser(browser)

    return await _run_with_retry("discover_via_parent", target_url, _op)


async def discover_batch_for_section(
    page_url: str,
    parent_url: Optional[str],
    product_limit: int,
    section_limit: int,
) -> DiscoveryBatch:
    direct_error: Exception | None = None

    try:
        direct = await _discover_direct(
            page_url=page_url,
            product_limit=product_limit,
            section_limit=section_limit,
        )

        if direct.product_urls:
            logger.info(
                "Discovered direct: product_urls=%s next_section_urls=%s from %s",
                len(direct.product_urls),
                len(direct.next_section_urls),
                page_url,
            )
            return direct

        if not parent_url:
            logger.info(
                "Direct open returned 0 products and no parent fallback is available: %s",
                page_url,
            )
            return direct

        logger.info(
            "Direct open returned 0 products, trying via parent: parent=%s target=%s",
            parent_url,
            page_url,
        )

    except Exception as e:
        direct_error = e

        if not parent_url:
            logger.warning(
                "Direct open failed and no parent fallback is available: page=%s error=%s",
                page_url,
                e,
            )
            raise

        logger.warning(
            "Direct open failed, trying via parent: parent=%s target=%s error=%s",
            parent_url,
            page_url,
            e,
        )

    via_parent = await _discover_via_parent(
        parent_url=parent_url,
        target_url=page_url,
        product_limit=product_limit,
        section_limit=section_limit,
    )

    if via_parent.product_urls:
        logger.info(
            "Discovered via parent: product_urls=%s next_section_urls=%s target=%s",
            len(via_parent.product_urls),
            len(via_parent.next_section_urls),
            page_url,
        )
        return via_parent

    logger.info(
        "Via-parent fallback also returned 0 products: target=%s direct_error=%s",
        page_url,
        direct_error,
    )
    return via_parent