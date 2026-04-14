from __future__ import annotations

from playwright.async_api import async_playwright

from discovery.config import PLAYWRIGHT_HEADLESS
from discovery.browser_sites import shkatulka, simplicity, vikisews


async def run_browser_spec(spec_name: str, spec: dict) -> list[str]:
    handler_name = spec["handler"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        try:
            if handler_name == "simplicity":
                return await simplicity.run(browser, spec)
            if handler_name == "vikisews":
                return await vikisews.run(browser, spec)
            if handler_name == "shkatulka":
                return await shkatulka.run(browser, spec)

            raise RuntimeError(f"unknown browser handler: {handler_name}")
        finally:
            await browser.close()