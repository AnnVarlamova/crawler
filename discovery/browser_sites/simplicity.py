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


BRANDS = [
    "Butterick",
    "Know Me",
    "McCall's",
    "New Look",
    "Simplicity",
    "Vogue Patterns",
]


async def _dismiss_cookie_if_present(page: Page) -> None:
    for text in ["Accept", "I Agree", "Got it"]:
        try:
            locator = page.get_by_role("button", name=text)
            if await locator.count():
                await locator.first.click(timeout=1500)
                await wait_ms(page, 700)
                return
        except Exception:
            continue


async def _wait_for_products_or_filters(page: Page) -> None:
    selectors = [
        "li.product h3.card-title a[href]",
        "a.navList-action--checkbox",
        "button[aria-label='next']",
    ]

    for selector in selectors:
        try:
            await page.locator(selector).first.wait_for(timeout=12000)
            return
        except Exception:
            continue

    await wait_ms(page, 2500)


async def _select_single_brand(page: Page, brand_name: str) -> None:
    locator = page.locator(
        f'a.navList-action--checkbox[data-name="{brand_name}"]'
    )

    count = await locator.count()
    logger.info("[simplicity] select brand=%s found=%s", brand_name, count)

    if count == 0:
        logger.warning("[simplicity] brand not found: %s", brand_name)
        return

    item = locator.first

    # 👇 текущий список до применения фильтра
    before = await _get_first_product_href(page)

    # 👇 скроллим (иногда обязательно)
    await item.scroll_into_view_if_needed()

    # 👇 жёсткое применение через DOM
    await item.evaluate("""
        (el) => {
            // пробуем найти input внутри
            const input = el.querySelector('input[type="checkbox"]');

            if (input) {
                input.checked = true;

                // триггерим все события которые обычно слушают такие сайты
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('click', { bubbles: true }));
            } else {
                // fallback — кликаем сам элемент
                el.click();
            }
        }
    """)

    # 👇 ждём обновления товаров
    for _ in range(20):
        await wait_ms(page, 300)
        after = await _get_first_product_href(page)
        if after and after != before:
            logger.info("[simplicity] brand applied=%s", brand_name)
            return

    logger.warning("[simplicity] brand NOT applied=%s", brand_name)


async def _clear_all_brands(page: Page) -> None:
    locators = page.locator("a.navList-action--checkbox input[type='checkbox']")

    count = await locators.count()
    logger.info("[simplicity] clearing brands count=%s", count)

    for i in range(count):
        el = locators.nth(i)

        try:
            checked = await el.is_checked()
        except Exception:
            checked = False

        if checked:
            await el.evaluate("""
                (input) => {
                    input.checked = false;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """)


async def _scroll_current_page(page: Page) -> None:
    prev_height = -1
    stable_rounds = 0

    while stable_rounds < 3:
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
        prev_height = height

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await wait_ms(page, 900)


async def _get_page_links(page: Page) -> list[str]:
    return await collect_unique_links(
        page=page,
        selector="li.product h3.card-title a[href]",
        href_filter=lambda href: href.startswith("https://simplicity.com/"),
    )


async def _get_first_product_href(page: Page) -> str | None:
    links = await _get_page_links(page)
    return links[0] if links else None


async def _click_next_and_wait_for_new_products(page: Page) -> bool:
    next_btn = page.locator("button[aria-label='next']")

    if not await next_btn.count():
        logger.info("[simplicity] next button not found")
        return False

    if await next_btn.first.is_disabled():
        logger.info("[simplicity] next button is disabled")
        return False

    before_first = await _get_first_product_href(page)

    await next_btn.first.click()
    await wait_ms(page, 1200)

    for _ in range(15):
        after_first = await _get_first_product_href(page)
        if after_first and after_first != before_first:
            return True
        await wait_ms(page, 400)

    logger.warning("[simplicity] next click did not change product list")
    return False


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser)

    try:
        site = spec["site"]
        category = spec["category"]
        start_url = spec["start_url"]

        logger.info("[simplicity] open %s", start_url)
        runlog.info("START simplicity %s", category)

        all_links: list[str] = []
        seen = set()

        # 🔥 идём по каждому бренду отдельно
        for brand in BRANDS:
            logger.info("[simplicity] processing brand=%s", brand)

            # 🔥 НОВАЯ страница вместо переиспользования старой
            await safe_close_context(context)
            context, page = await new_page(browser)

            await safe_goto(
                page,
                start_url,
                primary_wait_until="domcontentloaded",
                fallback_wait_until="commit",
            )
            await wait_ms(page, 2500)

            await _dismiss_cookie_if_present(page)
            await _wait_for_products_or_filters(page)

            await _clear_all_brands(page)
            await _select_single_brand(page, brand)
            await _wait_for_products_or_filters(page)

            page_index = 1

            while True:
                logger.info(
                    "[simplicity] brand=%s page=%s scroll before collect",
                    brand,
                    page_index,
                )

                await _scroll_current_page(page)

                links = await _get_page_links(page)
                first_href = links[0] if links else None

                new_on_page = 0
                fresh_links: list[str] = []

                for link in links:
                    if link not in seen:
                        seen.add(link)
                        all_links.append(link)
                        fresh_links.append(link)
                        new_on_page += 1

                written = 0
                if fresh_links:
                    written = save_dataset_links(
                        site=site,
                        category=category,
                        source_page=f"{start_url}#brand={brand}",
                        links=fresh_links,
                    )

                logger.info(
                    "[simplicity] brand=%s page=%s first_href=%s found=%s new_on_page=%s written=%s total=%s",
                    brand,
                    page_index,
                    first_href,
                    len(links),
                    new_on_page,
                    written,
                    len(all_links),
                )

                moved = await _click_next_and_wait_for_new_products(page)
                if not moved:
                    logger.info("[simplicity] brand=%s stop at page=%s", brand, page_index)
                    break

                page_index += 1

        runlog.info("DONE  simplicity %s total=%s", category, len(all_links))
        return all_links

    finally:
        await safe_close_context(context)