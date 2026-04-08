from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app import runtime
from app.browser_client import discover_urls_for_site, extract_product, generate_tags
from app.config import (
    DATA_DIR,
    DEFAULT_CONCURRENCY,
    DEFAULT_LIMIT_PER_SITE,
    DEFAULT_MAX_IMAGES,
    DISCOVERED_FILE,
    ERRORS_FILE,
    ITEMS_DIR,
    PROCESSED_FILE,
    SAVED_ITEMS_FILE,
    SITE_URLS,
    STATE_DIR,
)
from app.downloads import download_images
from app.filtering import is_valid_product
from app.models import ProductCard, State
from app.state import load_state
from app.utils import (
    append_jsonl,
    detect_site_key,
    ensure_dir,
    merge_tags,
    stable_item_id,
    write_json,
)

logger = logging.getLogger(__name__)


def _handle_stop(signum, frame):
    runtime.STOP_REQUESTED = True
    logger.warning("Stop requested. Waiting for current tasks to finish safely...")


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


def save_item(card: ProductCard, tags: list[str], downloaded_images: list[str]) -> str:
    item_id = stable_item_id(card.product_url, card.title)
    item_dir = ITEMS_DIR / item_id
    ensure_dir(item_dir)

    metadata = {
        "item_id": item_id,
        "source_site": card.source_site,
        "product_url": card.product_url,
        "title": card.title,
        "gender": card.gender,
        "category": card.category,
        "subcategory": card.subcategory,
        "season": card.season,
        "garment_elements": card.garment_elements,
        "materials": card.materials,
        "short_description": card.short_description,
        "pattern_info": card.pattern_info,
        "adult_only": card.adult_only,
        "is_accessory": card.is_accessory,
        "is_child_item": card.is_child_item,
        "image_source_urls": [img.url for img in card.images],
        "downloaded_images": downloaded_images,
    }

    write_json(item_dir / "metadata.json", metadata)
    write_json(item_dir / "tags.json", {"tags": tags})
    (item_dir / "raw_text.txt").write_text(card.raw_text or "", encoding="utf-8")

    return item_id


async def discover_phase(state: State, limit_per_site: int) -> None:
    for site_key, start_url in SITE_URLS.items():
        if runtime.STOP_REQUESTED:
            return

        logger.info("[DISCOVER] %s -> %s", site_key, start_url)
        try:
            urls = await discover_urls_for_site(start_url, limit_per_site)
            added = 0
            for url in urls:
                if url not in state.discovered_urls:
                    state.discovered_urls.add(url)
                    append_jsonl(DISCOVERED_FILE, {"url": url, "site": site_key})
                    added += 1

            logger.info("[DISCOVER] %s: found=%s new=%s", site_key, len(urls), added)
        except Exception as e:
            append_jsonl(ERRORS_FILE, {"phase": "discover", "site": site_key, "error": str(e)})
            logger.exception("[DISCOVER] %s failed", site_key)


async def process_one_url(url: str, state: State, max_images: int, lock: asyncio.Lock) -> None:
    if runtime.STOP_REQUESTED:
        return

    item_id: str | None = None
    item_reserved = False

    async with lock:
        if url in state.processed_urls or url in state.in_progress_urls:
            return
        state.in_progress_urls.add(url)

    try:
        logger.info("[PROCESS] %s", url)

        card = await extract_product(url)
        if not card:
            append_jsonl(ERRORS_FILE, {"phase": "extract", "url": url, "error": "no structured output"})
            logger.warning("[PROCESS] no structured output for %s", url)
            return

        if not card.source_site:
            card.source_site = detect_site_key(url)
        if not card.product_url:
            card.product_url = url

        item_id = stable_item_id(card.product_url, card.title)

        async with lock:
            if item_id in state.saved_item_ids:
                state.processed_urls.add(url)
                append_jsonl(PROCESSED_FILE, {"url": url, "status": "already_saved"})
                logger.info("[PROCESS] already saved: %s", item_id)
                return

            if item_id in state.reserved_item_ids:
                state.processed_urls.add(url)
                append_jsonl(PROCESSED_FILE, {"url": url, "status": "duplicate_in_progress"})
                logger.info("[PROCESS] duplicate in progress: %s", item_id)
                return

            state.reserved_item_ids.add(item_id)
            item_reserved = True
            logger.debug("[PROCESS] reserved item_id=%s for url=%s", item_id, url)

        if not is_valid_product(card):
            async with lock:
                state.processed_urls.add(url)
                append_jsonl(PROCESSED_FILE, {"url": url, "status": "filtered_out"})
            logger.info("[PROCESS] filtered out: %s", url)
            return

        item_dir = ITEMS_DIR / item_id
        downloaded = await download_images(card, item_dir, state, max_images=max_images)
        tags = merge_tags(await generate_tags(card))
        saved_item_id = save_item(card, tags, downloaded)

        async with lock:
            state.saved_item_ids.add(saved_item_id)
            append_jsonl(SAVED_ITEMS_FILE, {"item_id": saved_item_id, "url": url})
            state.processed_urls.add(url)
            append_jsonl(PROCESSED_FILE, {"url": url, "status": "saved"})

        logger.info("[SAVED] %s", saved_item_id)

    except Exception as e:
        append_jsonl(ERRORS_FILE, {"phase": "process", "url": url, "error": str(e)})
        logger.exception("[ERROR] processing failed for %s", url)

    finally:
        async with lock:
            state.in_progress_urls.discard(url)
            if item_reserved and item_id is not None:
                state.reserved_item_ids.discard(item_id)


async def process_phase_concurrent(state: State, max_images: int, concurrency: int) -> None:
    queue = [
        url for url in state.discovered_urls
        if url not in state.processed_urls and url not in state.in_progress_urls
    ]
    logger.info("[PROCESS] queued=%s concurrency=%s", len(queue), concurrency)

    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def runner(url: str):
        async with semaphore:
            if runtime.STOP_REQUESTED:
                return
            await process_one_url(url, state, max_images, lock)

    tasks = []
    for url in queue:
        if runtime.STOP_REQUESTED:
            break
        tasks.append(asyncio.create_task(runner(url)))

    if not tasks:
        return

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.warning("Processing tasks were cancelled")


async def async_main():
    ensure_dir(DATA_DIR)
    ensure_dir(STATE_DIR)
    ensure_dir(ITEMS_DIR)

    limit_per_site = DEFAULT_LIMIT_PER_SITE
    max_images = DEFAULT_MAX_IMAGES
    concurrency = DEFAULT_CONCURRENCY

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--limit-per-site" and i + 1 < len(argv):
            limit_per_site = int(argv[i + 1])
            i += 2
        elif argv[i] == "--max-images" and i + 1 < len(argv):
            max_images = int(argv[i + 1])
            i += 2
        elif argv[i] == "--concurrency" and i + 1 < len(argv):
            concurrency = int(argv[i + 1])
            i += 2
        else:
            i += 1
    logger.info("Log level = %s", logging.getLevelName(logger.level))
    logger.info("Starting pipeline")
    logger.info("DATA_DIR=%s", DATA_DIR)
    logger.info("STATE_DIR=%s", STATE_DIR)
    logger.info("ITEMS_DIR=%s", ITEMS_DIR)
    logger.info(
        "Parameters: limit_per_site=%s, max_images=%s, concurrency=%s",
        limit_per_site,
        max_images,
        concurrency,
    )

    state = load_state()

    logger.info("[START] Discovery phase")
    await discover_phase(state, limit_per_site=limit_per_site)

    if runtime.STOP_REQUESTED:
        logger.warning("[STOP] Interrupted after discovery")
        return

    logger.info("[START] Concurrent process phase")
    await process_phase_concurrent(state, max_images=max_images, concurrency=concurrency)

    logger.info("[DONE]")


def main():
    asyncio.run(async_main())