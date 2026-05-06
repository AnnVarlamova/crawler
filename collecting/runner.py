from __future__ import annotations

import asyncio
import traceback
from collections import defaultdict

from collecting.browser import light_scroll, new_browser, new_page, safe_goto
from collecting.config import (
    COLLECTED_DIR,
    DEBUG_DIR,
    ERRORS_FILE,
    LINKS_DIR,
    MAX_CONCURRENT_PRODUCTS,
    MAX_PER_SITE,
    PROCESSED_FILE,
    RETRY_COUNT,
)
from collecting.downloader import download_images
from collecting.handlers import HANDLERS
from collecting.io import (
    append_jsonl,
    get_product_dir,
    load_link_records,
    product_id_from_url,
    read_jsonl,
    round_robin_records,
    save_product,
)
from collecting.logging_utils import setup_logging
from collecting.models import LinkRecord

logger = setup_logging()


def load_processed_urls() -> set[str]:
    rows = read_jsonl(PROCESSED_FILE)
    return {row["url"] for row in rows if row.get("url")}


async def save_debug_html(record: LinkRecord, page, attempt: int) -> None:
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        debug_path = (
            DEBUG_DIR
            / f"{record.site}_{product_id_from_url(record.url)}_attempt_{attempt}.html"
        )
        debug_path.write_text(await page.content(), encoding="utf-8")
        logger.error("Saved debug html: %s", debug_path)
    except Exception:
        logger.exception("Failed to save debug html for url=%s", record.url)


async def process_one(record: LinkRecord, browser) -> None:
    handler_cls = HANDLERS.get(record.site)

    if handler_cls is None:
        logger.warning(
            "No collecting handler for site=%s url=%s",
            record.site,
            record.url,
        )

        append_jsonl(
            ERRORS_FILE,
            {
                "url": record.url,
                "site": record.site,
                "category": record.category,
                "error": f"No collecting handler for site: {record.site}",
            },
        )
        return

    handler = handler_cls()
    last_error: Exception | None = None
    last_traceback: str | None = None

    for attempt in range(RETRY_COUNT + 1):
        page = None

        try:
            logger.debug(
                "Collect attempt=%s/%s site=%s category=%s url=%s",
                attempt + 1,
                RETRY_COUNT + 1,
                record.site,
                record.category,
                record.url,
            )

            page = await new_page(browser)

            await safe_goto(page, record.url)
            await light_scroll(page)

            product = await handler.collect(page, record)

            product_dir = get_product_dir(COLLECTED_DIR, product)
            product = await download_images(product, product_dir)

            metadata_path = save_product(COLLECTED_DIR, product)

            downloaded_images_count = len(
                [image for image in product.images if image.local_path]
            )

            append_jsonl(
                PROCESSED_FILE,
                {
                    "url": record.url,
                    "site": record.site,
                    "category": record.category,
                    "product_id": product_id_from_url(record.url),
                    "metadata_path": str(metadata_path),
                    "title": product.title,
                    "images_count": len(product.images),
                    "downloaded_images_count": downloaded_images_count,
                },
            )

            logger.info(
                "Collected ok site=%s category=%s title=%r images=%s downloaded=%s url=%s",
                record.site,
                record.category,
                product.title,
                len(product.images),
                downloaded_images_count,
                record.url,
            )

            return

        except Exception as e:
            last_error = e
            last_traceback = traceback.format_exc()

            if page is not None:
                await save_debug_html(record, page, attempt + 1)

            logger.exception(
                "Collect failed attempt=%s/%s site=%s category=%s url=%s",
                attempt + 1,
                RETRY_COUNT + 1,
                record.site,
                record.category,
                record.url,
            )

        finally:
            if page is not None:
                await page.context.close()

    append_jsonl(
        ERRORS_FILE,
        {
            "url": record.url,
            "site": record.site,
            "category": record.category,
            "error": repr(last_error),
            "traceback": last_traceback,
        },
    )

    logger.error(
        "Collect finally failed site=%s category=%s url=%s error=%r",
        record.site,
        record.category,
        record.url,
        last_error,
    )


async def worker(
    *,
    worker_id: int,
    queue: asyncio.Queue[LinkRecord],
    browser,
    site_locks: dict[str, asyncio.Semaphore],
) -> None:
    while True:
        try:
            record = queue.get_nowait()
        except asyncio.QueueEmpty:
            logger.info("Worker %s finished: queue is empty", worker_id)
            return

        try:
            site_lock = site_locks[record.site]

            async with site_lock:
                logger.info(
                    "Worker %s processing site=%s url=%s",
                    worker_id,
                    record.site,
                    record.url,
                )
                await process_one(record, browser)

        finally:
            queue.task_done()


async def run(
    site: str | None = None,
    limit: int | None = None,
    round_robin: bool = False,
    parallel: bool = False,
    max_concurrent: int | None = None,
) -> None:
    records = load_link_records(LINKS_DIR, site=site)

    processed = load_processed_urls()
    records = [record for record in records if record.url not in processed]

    if round_robin and site is None:
        records = round_robin_records(records)

    if limit is not None:
        records = records[:limit]

    logger.info(
        "To collect: %s site=%s round_robin=%s parallel=%s",
        len(records),
        site,
        round_robin,
        parallel,
    )

    if not records:
        logger.info("Nothing to collect")
        return

    playwright, browser = await new_browser()

    try:
        if not parallel:
            for index, record in enumerate(records, start=1):
                logger.info(
                    "[%s/%s] %s: %s",
                    index,
                    len(records),
                    record.site,
                    record.url,
                )

                await process_one(record, browser)

            return

        concurrency = max_concurrent or MAX_CONCURRENT_PRODUCTS
        concurrency = max(1, concurrency)

        logger.info(
            "Parallel collecting started: max_concurrent=%s max_per_site=%s",
            concurrency,
            MAX_PER_SITE,
        )

        queue: asyncio.Queue[LinkRecord] = asyncio.Queue()

        for record in records:
            queue.put_nowait(record)

        site_locks: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(MAX_PER_SITE)
        )

        workers = [
            asyncio.create_task(
                worker(
                    worker_id=i + 1,
                    queue=queue,
                    browser=browser,
                    site_locks=site_locks,
                )
            )
            for i in range(concurrency)
        ]

        await queue.join()

        for task in workers:
            task.cancel()

        await asyncio.gather(*workers, return_exceptions=True)

    finally:
        await browser.close()
        await playwright.stop()
        logger.info("Collecting finished")


def run_sync(
    site: str | None = None,
    limit: int | None = None,
    round_robin: bool = False,
    parallel: bool = False,
    max_concurrent: int | None = None,
) -> None:
    asyncio.run(
        run(
            site=site,
            limit=limit,
            round_robin=round_robin,
            parallel=parallel,
            max_concurrent=max_concurrent,
        )
    )