from __future__ import annotations

import logging

from playwright.async_api import Browser

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")


async def run(browser: Browser, spec: dict) -> list[str]:
    site = spec["site"]
    category = spec["category"]
    start_url = spec["start_url"]
    page_from = spec.get("page_from")
    page_to = spec.get("page_to")

    logger.info(
        "[marfy] STUB start_url=%s page_from=%s page_to=%s",
        start_url,
        page_from,
        page_to,
    )
    runlog.info(
        "STUB marfy %s page_from=%s page_to=%s",
        category,
        page_from,
        page_to,
    )
    return []