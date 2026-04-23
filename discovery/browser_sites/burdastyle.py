from __future__ import annotations

import logging
from urllib.parse import urlencode

from playwright.async_api import Browser, Page

from discovery.browser_sites.common import (
    collect_unique_links,
    new_page,
    safe_close_context,
    safe_goto,
    save_dataset_links,
    wait_ms,
)

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")

BURDA_PRODUCT_SELECTOR = "a.system-pattern-url.js-pattern-item-list__click[href]"


def _build_page_url(base_url: str, page_num: int) -> str:
    if page_num <= 1:
        return base_url
    query = urlencode({"page": page_num, "per-page": 24})
    return f"{base_url}?{query}"


async def _wait_for_listing(page: Page) -> None:
    try:
        await page.locator(BURDA_PRODUCT_SELECTOR).first.wait_for(timeout=15000)
        logger.info("[burdastyle] listing appeared")
        return
    except Exception:
        await wait_ms(page, 2500)


async def _get_page_links(page: Page) -> list[str]:
    return await collect_unique_links(
        page=page,
        selector=BURDA_PRODUCT_SELECTOR,
        href_filter=lambda href: isinstance(href, str) and "/vikroyki/" in href,
    )


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser, height=1300)

    try:
        site = spec["site"]
        category = spec["category"]
        start_url = spec["start_url"]
        page_from = spec.get("page_from", 1)
        page_to = spec.get("page_to", 999)

        runlog.info("START burdastyle %s", category)

        all_links: list[str] = []
        seen = set()
        stagnant_rounds = 0

        for page_num in range(page_from, page_to + 1):
            page_url = _build_page_url(start_url, page_num)
            logger.info("[burdastyle] open page=%s url=%s", page_num, page_url)

            await safe_goto(page, page_url, primary_wait_until="domcontentloaded", fallback_wait_until="commit")
            await wait_ms(page, 1600)
            await _wait_for_listing(page)

            links = await _get_page_links(page)

            fresh_links: list[str] = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    all_links.append(link)
                    fresh_links.append(link)

            if fresh_links:
                save_dataset_links(
                    site=site,
                    category=category,
                    source_page=page_url,
                    links=fresh_links,
                )

            logger.info(
                "[burdastyle] page=%s found=%s fresh=%s total=%s",
                page_num,
                len(links),
                len(fresh_links),
                len(all_links),
            )

            if not fresh_links:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 2:
                logger.info("[burdastyle] stop by stagnant pages at page=%s", page_num)
                break

        runlog.info("DONE burdastyle %s total=%s", category, len(all_links))
        return all_links

    finally:
        await safe_close_context(context)