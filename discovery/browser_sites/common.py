from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page

from discovery.config import DATASET_DIR, PLAYWRIGHT_TIMEOUT_MS
from discovery.utils import append_jsonl_unique, ensure_dir, read_jsonl_keyset, slugify

logger = logging.getLogger(__name__)


def dataset_file(site: str, category: str) -> Path:
    return DATASET_DIR/ "links" / slugify(site) / slugify(category) / "products.jsonl"


async def new_page(browser: Browser, height=900) -> tuple[BrowserContext, Page]:
    context = await browser.new_context(viewport={"width": 1440, "height": height})
    page = await context.new_page()
    page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)
    return context, page


async def safe_close_context(context: BrowserContext) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def safe_goto(
    page: Page,
    url: str,
    *,
    primary_wait_until: str = "domcontentloaded",
    fallback_wait_until: str = "commit",
    primary_timeout_ms: int | None = None,
    fallback_timeout_ms: int | None = None,
) -> None:
    primary_timeout_ms = primary_timeout_ms or PLAYWRIGHT_TIMEOUT_MS
    fallback_timeout_ms = fallback_timeout_ms or max(45000, PLAYWRIGHT_TIMEOUT_MS)

    try:
        await page.goto(url, wait_until=primary_wait_until, timeout=primary_timeout_ms)
        return
    except Exception as e:
        logger.warning(
            "safe_goto primary failed for %s wait_until=%s error=%s",
            url,
            primary_wait_until,
            e,
        )

    await page.goto(url, wait_until=fallback_wait_until, timeout=fallback_timeout_ms)


async def collect_unique_links(
    page: Page,
    selector: str,
    href_filter: Callable[[str], bool],
) -> list[str]:
    hrefs = await page.eval_on_selector_all(
        selector,
        """
        (els) => els
          .map(e => e.href || e.getAttribute('href'))
          .filter(Boolean)
        """,
    )

    result: list[str] = []
    seen = set()

    for href in hrefs:
        if not isinstance(href, str):
            continue
        if href in seen:
            continue
        if not href_filter(href):
            continue
        seen.add(href)
        result.append(href)

    return result


async def wait_ms(page: Page, ms: int) -> None:
    await page.wait_for_timeout(ms)


def save_dataset_links(
    *,
    site: str,
    category: str,
    source_page: str,
    links: list[str],
) -> int:
    out = dataset_file(site, category)
    ensure_dir(out.parent)

    existing_urls = read_jsonl_keyset(out, "url")
    written = 0

    for link in links:
        added = append_jsonl_unique(
            out,
            {
                "url": link,
                "site": site,
                "category": category,
                "source_page": source_page,
            },
            key="url",
            existing_keys=existing_urls,
        )
        if added:
            written += 1

    return written