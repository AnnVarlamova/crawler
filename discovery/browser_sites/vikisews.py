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


async def _scroll_step(page, step_px: int = 650) -> None:
    await page.evaluate(
        """(step) => {
            const y = window.scrollY || document.documentElement.scrollTop || 0;
            window.scrollTo({ top: y + step, behavior: 'instant' });
        }""",
        step_px,
    )


async def _wait_for_listing(page) -> None:
    selectors = [
        "#upload-content a.slide-link[href]",
        "a.slide-link[href]",
    ]

    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(timeout=12000)
            return
        except Exception:
            continue

    await wait_ms(page, 2500)


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser)

    try:
        site = spec["site"]
        category = spec["category"]
        start_url = spec["start_url"]

        logger.info("[vikisews] open %s", start_url)
        runlog.info("START vikisews %s", category)

        await safe_goto(
            page,
            start_url,
            primary_wait_until="commit",
            fallback_wait_until="load",
            primary_timeout_ms=45000,
            fallback_timeout_ms=60000,
        )
        await wait_ms(page, 2500)
        await _wait_for_listing(page)

        all_links: list[str] = []
        seen = set()

        stagnant_rounds = 0
        last_count = 0

        while stagnant_rounds < 5:
            links = await collect_unique_links(
                page=page,
                selector="#upload-content a.slide-link[href], a.slide-link[href]",
                href_filter=lambda href: href.startswith("https://vikisews.com/vykrojki/"),
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
                "[vikisews] category=%s total=%s fresh=%s written=%s stagnant_rounds=%s",
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

            await _scroll_step(page, step_px=650)
            await wait_ms(page, 1000)

        runlog.info("DONE  vikisews %s total=%s", category, len(all_links))
        return all_links

    finally:
        await safe_close_context(context)