from __future__ import annotations

import logging

from playwright.async_api import Browser, Page, async_playwright

from collecting.config import PLAYWRIGHT_HEADLESS, PLAYWRIGHT_TIMEOUT_MS

logger = logging.getLogger("collecting")


async def new_browser():
    logger.debug("Starting Playwright browser headless=%s", PLAYWRIGHT_HEADLESS)

    playwright = await async_playwright().start()

    browser = await playwright.chromium.launch(
        headless=PLAYWRIGHT_HEADLESS,
        args=[
            "--disable-quic",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    return playwright, browser


async def new_page(browser: Browser) -> Page:
    context = await browser.new_context(
        viewport={"width": 1440, "height": 1600},
        locale="ru-RU",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )

    page = await context.new_page()
    page.set_default_timeout(PLAYWRIGHT_TIMEOUT_MS)

    return page


async def safe_goto(page: Page, url: str) -> None:
    logger.debug("Open url with domcontentloaded: %s", url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
        return
    except Exception:
        logger.debug("domcontentloaded failed, trying commit: %s", url, exc_info=True)

    try:
        await page.goto(url, wait_until="commit", timeout=PLAYWRIGHT_TIMEOUT_MS)
        return
    except Exception:
        logger.debug("commit failed, trying load: %s", url, exc_info=True)

    await page.goto(url, wait_until="load", timeout=PLAYWRIGHT_TIMEOUT_MS)


async def light_scroll(page: Page) -> None:
    """
    Небольшой скролл нужен, чтобы lazy-картинки и нижние блоки карточки
    успели появиться в DOM.
    """
    await page.mouse.wheel(0, 900)
    await page.wait_for_timeout(500)
    await page.mouse.wheel(0, -500)
    await page.wait_for_timeout(300)