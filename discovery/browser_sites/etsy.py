from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus, urlsplit, urlunsplit

from playwright.async_api import Browser, Page

from discovery.browser_sites.common import (
    new_page,
    safe_close_context,
    safe_goto,
    save_dataset_links,
    wait_ms,
)

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")

GOOGLE_URL = "https://www.google.com/search?q={query}&start={start}"

RESULT_SELECTOR = "a[href]"


def normalize_etsy_listing_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _is_etsy_listing(url: str) -> bool:
    return "/listing/" in url and "etsy.com" in url


def _extract_real_url(href: str) -> str | None:
    # Google часто даёт ссылки вида /url?q=...
    if href.startswith("/url?q="):
        try:
            return href.split("/url?q=")[1].split("&")[0]
        except Exception:
            return None
    return href


async def _wait_google_results(page: Page):
    for _ in range(30):
        try:
            count = await page.locator(RESULT_SELECTOR).count()
            if count > 20:
                return
        except:
            pass
        await wait_ms(page, 500)


async def _collect_links(page: Page) -> list[str]:
    loc = page.locator(RESULT_SELECTOR)
    count = await loc.count()

    result = []
    seen = set()

    for i in range(count):
        try:
            href = await loc.nth(i).get_attribute("href")
        except:
            continue

        if not href:
            continue

        real = _extract_real_url(href)
        if not real:
            continue

        if not _is_etsy_listing(real):
            continue

        clean = normalize_etsy_listing_url(real)

        if clean in seen:
            continue

        seen.add(clean)
        result.append(clean)

    return result


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser, height=1400)

    try:
        site = spec["site"]
        category = spec["category"]
        query = spec["query"]

        runlog.info("START etsy via google %s", category)

        # формируем запрос
        search_query = f"site:etsy.com/listing {query}"
        encoded = quote_plus(search_query)

        all_links = []
        seen = set()

        # 5 страниц гугла
        for i in range(5):
            start = i * 10
            url = GOOGLE_URL.format(query=encoded, start=start)

            logger.info("[etsy-google] open %s", url)

            await safe_goto(page, url)
            await wait_ms(page, 2000)

            await _wait_google_results(page)

            links = await _collect_links(page)

            fresh = []
            for l in links:
                if l not in seen:
                    seen.add(l)
                    all_links.append(l)
                    fresh.append(l)

            if fresh:
                save_dataset_links(
                    site=site,
                    category=category,
                    source_page=url,
                    links=fresh,
                )

            logger.info(
                "[etsy-google] page=%s found=%s fresh=%s total=%s",
                i,
                len(links),
                len(fresh),
                len(all_links),
            )

            await wait_ms(page, 2000)

        runlog.info("DONE etsy total=%s", len(all_links))
        return all_links

    finally:
        await safe_close_context(context)