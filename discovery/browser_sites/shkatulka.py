from __future__ import annotations

import logging

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


WOMEN_ROOT_URL = "https://shkatulka-sew.ru/category/jenskie-vykroyki/"
MEN_ROOT_URL = "https://shkatulka-sew.ru/category/mujskie-vykroyki/"


def _get_parent_section_url(spec: dict) -> str:
    return MEN_ROOT_URL if spec.get("section_gender") == "men" else WOMEN_ROOT_URL


async def _wait_for_listing(page: Page) -> None:
    selectors = [
        "a.grid-product__title[href]",
        ".grid-product",
        ".product-grid",
    ]

    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(timeout=15000)
            logger.info("[shkatulka] listing appeared via selector=%s", selector)
            return
        except Exception:
            continue

    logger.warning("[shkatulka] listing not detected, fallback wait")
    await wait_ms(page, 3000)


async def _get_page_links(page: Page) -> list[str]:
    return await collect_unique_links(
        page=page,
        selector="a.grid-product__title[href]",
        href_filter=lambda href: href.startswith("https://shkatulka-sew.ru/pattern/"),
    )


async def _get_product_count(page: Page) -> int:
    try:
        return await page.locator("a.grid-product__title[href]").count()
    except Exception:
        return 0


async def _scroll_step(page: Page, step_px: int) -> None:
    await page.evaluate(
        """(step) => {
            window.scrollBy(0, step);
        }""",
        step_px,
    )


async def _scroll_burst(page: Page) -> None:
    for step in (900, 1100, 1300):
        await _scroll_step(page, step_px=step)
        await wait_ms(page, 700)


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser)

    try:
        site = spec["site"]
        category = spec["category"]
        start_url = spec["start_url"]
        parent_url = _get_parent_section_url(spec)

        logger.info("[shkatulka] open %s", start_url)
        logger.info("[shkatulka] parent=%s", parent_url)
        runlog.info("START shkatulka %s", category)

        await safe_goto(
            page,
            "https://shkatulka-sew.ru/",
            primary_wait_until="domcontentloaded",
            fallback_wait_until="commit",
        )
        await wait_ms(page, 1800)

        await safe_goto(
            page,
            parent_url,
            primary_wait_until="domcontentloaded",
            fallback_wait_until="commit",
        )
        await wait_ms(page, 1800)

        await safe_goto(
            page,
            start_url,
            primary_wait_until="domcontentloaded",
            fallback_wait_until="commit",
        )
        await wait_ms(page, 2500)

        await _wait_for_listing(page)

        # стартовый прогрев скролла
        await _scroll_burst(page)
        await wait_ms(page, 2000)

        all_links: list[str] = []
        seen = set()

        stagnant_rounds = 0
        last_total = 0
        last_product_count = 0
        round_index = 1

        while stagnant_rounds < 8:
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
                    source_page=start_url,
                    links=fresh_links,
                )

            current_total = len(all_links)
            current_product_count = await _get_product_count(page)

            logger.info(
                "[shkatulka] category=%s round=%s product_count=%s total=%s fresh=%s stagnant=%s",
                category,
                round_index,
                current_product_count,
                current_total,
                len(fresh_links),
                stagnant_rounds,
            )

            no_growth = (
                current_total == last_total
                and current_product_count == last_product_count
            )

            if no_growth:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            last_total = current_total
            last_product_count = current_product_count

            await _scroll_burst(page)
            await wait_ms(page, 2000)
            round_index += 1

        runlog.info("DONE shkatulka %s total=%s", category, len(all_links))
        return all_links

    finally:
        try:
            await page.close()
        except Exception:
            pass
        await safe_close_context(context)