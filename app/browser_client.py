from __future__ import annotations

import asyncio
import atexit
import os
import shutil
import tempfile
from typing import Optional

from dotenv import load_dotenv

from browser_use import Agent, Browser, ChatOpenAI

from app.models import GeneratedTags, ListingLinks, ProductCard
from app.prompts import make_discovery_prompt, make_product_prompt, make_tags_prompt
from app.utils import dedupe_preserve_order, get_structured_output, is_allowed_product_url


_TEMP_BROWSER_DIRS: list[str] = []


def _cleanup_temp_browser_dirs() -> None:
    for d in _TEMP_BROWSER_DIRS:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


atexit.register(_cleanup_temp_browser_dirs)


def build_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env")

    return ChatOpenAI(
        model="gpt-4.1",
        api_key=api_key,
    )


def build_browser() -> Browser:
    profile_dir = tempfile.mkdtemp(prefix="browseruse_profile_")
    _TEMP_BROWSER_DIRS.append(profile_dir)

    return Browser(
        headless=True,
        channel="chromium",
        user_data_dir=profile_dir,
        enable_default_extensions=False,
    )


async def _close_browser(browser: Browser) -> None:
    maybe_close = getattr(browser, "close", None)
    if callable(maybe_close):
        maybe = maybe_close()
        if asyncio.iscoroutine(maybe):
            await maybe


async def discover_urls_for_site(start_url: str, limit: int) -> list[str]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_discovery_prompt(start_url, limit),
            llm=build_llm(),
            browser=browser,
            use_vision=True,
            output_model_schema=ListingLinks,
            max_failures=3,
        )
        result = await agent.run()
        data = get_structured_output(result)
        if not data:
            return []

        urls = dedupe_preserve_order(data.listing_urls)
        urls = [u for u in urls if is_allowed_product_url(u)]
        return urls[:limit]
    finally:
        await _close_browser(browser)


async def extract_product(product_url: str) -> Optional[ProductCard]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_product_prompt(product_url),
            llm=build_llm(),
            browser=browser,
            use_vision=True,
            output_model_schema=ProductCard,
            max_failures=3,
        )
        result = await agent.run()
        return get_structured_output(result)
    finally:
        await _close_browser(browser)


async def generate_tags(card: ProductCard) -> list[str]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_tags_prompt(card),
            llm=build_llm(),
            browser=browser,
            use_vision=False,
            output_model_schema=GeneratedTags,
            max_failures=2,
        )
        result = await agent.run()
        data = get_structured_output(result)
        if not data:
            return []
        return dedupe_preserve_order(data.tags)
    finally:
        await _close_browser(browser)