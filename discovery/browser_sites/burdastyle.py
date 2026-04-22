from __future__ import annotations

import logging

from playwright.async_api import Browser

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")


async def run(browser: Browser, spec: dict) -> list[str]:
    site = spec["site"]
    category = spec["category"]
    start_url = spec["start_url"]

    logger.info(
        "[burdastyle] STUB start_url=%s category=%s",
        start_url,
        category,
    )
    runlog.info(
        "STUB burdastyle %s",
        category,
    )
    return []