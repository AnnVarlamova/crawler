from __future__ import annotations

import logging

from playwright.async_api import Browser

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


async def _wait_for_listing(page) -> None:
    try:
        await page.locator("a.grid-product__title[href]").first.wait_for(timeout=10000)
    except Exception:
        await wait_ms(page, 1500)


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser)

    try:
        site = spec["site"]
        category = spec["category"]
        start_url = spec["start_url"]

        logger.info("[shkatulka] open %s", start_url)
        runlog.info("START shkatulka %s", category)

        await safe_goto(
            page,
            "https://shkatulka-sew.ru/",
            primary_wait_until="domcontentloaded",
            fallback_wait_until="commit",
        )
        await wait_ms(page, 1200)
        await safe_goto(page, start_url, primary_wait_until="domcontentloaded", fallback_wait_until="commit")
        await wait_ms(page, 1200)
        await _wait_for_listing(page)

        all_links: list[str] = []
        seen = set()

        stagnant_rounds = 0
        last_count = 0

        while stagnant_rounds < 4:
            links = await collect_unique_links(
                page=page,
                selector="a.grid-product__title[href]",
                href_filter=lambda href: href.startswith("https://shkatulka-sew.ru/pattern/"),
            )

            fresh_links: list[str] = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    all_links.append(link)
                    fresh_links.append(link)

            written = 0
            if fresh_links:
                written = save_dataset_links(
                    site=site,
                    category=category,
                    source_page=start_url,
                    links=fresh_links,
                )

            current_count = len(all_links)
            logger.info(
                "[shkatulka] category=%s total=%s fresh=%s written=%s stagnant_rounds=%s",
                category,
                current_count,
                len(fresh_links),
                written,
                stagnant_rounds,
            )

            if current_count == last_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            last_count = current_count

            await page.evaluate("window.scrollBy(0, 1200)")
            await wait_ms(page, 250)

        runlog.info("DONE  shkatulka %s total=%s", category, len(all_links))
        return all_links

    finally:
        await safe_close_context(context)