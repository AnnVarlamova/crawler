from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app import runtime
from app.browser_client import discover_batch_for_page, extract_product, generate_tags
from app.config import (
    DATA_DIR,
    DEFAULT_CONCURRENCY,
    DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION,
    DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION,
    DEFAULT_MAX_IMAGES,
    DEFAULT_SECTIONS_PER_SITE,
    DISCOVERED_FILE,
    ERRORS_FILE,
    ITEMS_DIR,
    PENDING_SECTION_URLS_FILE,
    PROCESSED_FILE,
    SAVED_ITEMS_FILE,
    SITE_PRIORITY,
    SITE_URLS,
    STATE_DIR,
    VISITED_SECTION_URLS_FILE,
)
from app.downloads import download_images
from app.filtering import is_valid_product
from app.models import ProductCard, State
from app.state import load_state
from app.utils import (
    append_jsonl,
    detect_site_key,
    ensure_dir,
    is_allowed_section_url,
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


def persist_section_state(state: State) -> None:
    write_json(PENDING_SECTION_URLS_FILE, {"urls": sorted(state.pending_section_urls)})
    write_json(VISITED_SECTION_URLS_FILE, {"urls": sorted(state.visited_section_urls)})


def seed_pending_sections(state: State) -> None:
    changed = False
    for start_url in SITE_URLS.values():
        if start_url not in state.pending_section_urls and start_url not in state.visited_section_urls:
            state.pending_section_urls.add(start_url)
            changed = True
    if changed:
        persist_section_state(state)


def get_ordered_site_keys() -> list[str]:
    return sorted(
        SITE_URLS.keys(),
        key=lambda site_key: (-SITE_PRIORITY.get(site_key, 0), site_key),
    )


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


async def discover_iteration(
    state: State,
    sections_per_site: int,
    product_limit_per_section: int,
    next_sections_limit_per_section: int,
) -> int:
    seed_pending_sections(state)

    visited_this_iteration = 0
    ordered_site_keys = get_ordered_site_keys()

    logger.info(
        "[DISCOVER] site priority order: %s",
        ", ".join(f"{site}({SITE_PRIORITY.get(site, 0)})" for site in ordered_site_keys),
    )

    for site_key in ordered_site_keys:
        if runtime.STOP_REQUESTED:
            break

        site_pending = [
            url for url in state.pending_section_urls
            if detect_site_key(url) == site_key
        ]
        if not site_pending:
            continue

        for page_url in site_pending[:sections_per_site]:
            if runtime.STOP_REQUESTED:
                break

            logger.info(
                "[DISCOVER] site=%s priority=%s page=%s",
                site_key,
                SITE_PRIORITY.get(site_key, 0),
                page_url,
            )

            state.pending_section_urls.discard(page_url)
            persist_section_state(state)

            try:
                batch = await discover_batch_for_page(
                    page_url=page_url,
                    product_limit=product_limit_per_section,
                    section_limit=next_sections_limit_per_section,
                )

                state.visited_section_urls.add(page_url)

                added_products = 0
                added_sections = 0

                for product_url in batch.product_urls:
                    if product_url not in state.discovered_urls:
                        state.discovered_urls.add(product_url)
                        append_jsonl(DISCOVERED_FILE, {"url": product_url, "site": site_key, "source_page": page_url})
                        added_products += 1

                for section_url in batch.next_section_urls:
                    if not is_allowed_section_url(section_url):
                        continue
                    if section_url in state.visited_section_urls or section_url in state.pending_section_urls:
                        continue
                    state.pending_section_urls.add(section_url)
                    added_sections += 1

                persist_section_state(state)
                visited_this_iteration += 1

                logger.info(
                    "[DISCOVER] site=%s priority=%s page=%s new_products=%s new_sections=%s remaining_pending_for_site=%s",
                    site_key,
                    SITE_PRIORITY.get(site_key, 0),
                    page_url,
                    added_products,
                    added_sections,
                    len([u for u in state.pending_section_urls if detect_site_key(u) == site_key]),
                )
            except Exception as e:
                state.pending_section_urls.add(page_url)
                persist_section_state(state)
                append_jsonl(ERRORS_FILE, {"phase": "discover", "site": site_key, "page_url": page_url, "error": str(e)})
                logger.exception("[DISCOVER] failed for page %s", page_url)

    return visited_this_iteration


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


async def process_phase_concurrent(state: State, max_images: int, concurrency: int) -> int:
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
        return 0

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.warning("Processing tasks were cancelled")

    return len(tasks)


async def async_main():
    ensure_dir(DATA_DIR)
    ensure_dir(STATE_DIR)
    ensure_dir(ITEMS_DIR)

    max_images = DEFAULT_MAX_IMAGES
    concurrency = DEFAULT_CONCURRENCY
    sections_per_site = DEFAULT_SECTIONS_PER_SITE
    discovery_products_per_section = DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION
    discovery_next_sections_per_section = DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--limit-per-site" and i + 1 < len(argv):
            sections_per_site = int(argv[i + 1])
            i += 2
        elif argv[i] == "--max-images" and i + 1 < len(argv):
            max_images = int(argv[i + 1])
            i += 2
        elif argv[i] == "--concurrency" and i + 1 < len(argv):
            concurrency = int(argv[i + 1])
            i += 2
        elif argv[i] == "--sections-per-site" and i + 1 < len(argv):
            sections_per_site = int(argv[i + 1])
            i += 2
        elif argv[i] == "--discovery-products-per-section" and i + 1 < len(argv):
            discovery_products_per_section = int(argv[i + 1])
            i += 2
        elif argv[i] == "--discovery-next-sections-per-section" and i + 1 < len(argv):
            discovery_next_sections_per_section = int(argv[i + 1])
            i += 2
        else:
            i += 1

    logger.info("Log level = %s", logging.getLevelName(logger.level))
    logger.info("Starting pipeline")
    logger.info("DATA_DIR=%s", DATA_DIR)
    logger.info("STATE_DIR=%s", STATE_DIR)
    logger.info("ITEMS_DIR=%s", ITEMS_DIR)
    logger.info(
        "Parameters: sections_per_site=%s, max_images=%s, concurrency=%s, discovery_products_per_section=%s, discovery_next_sections_per_section=%s",
        sections_per_site,
        max_images,
        concurrency,
        discovery_products_per_section,
        discovery_next_sections_per_section,
    )
    logger.info(
        "Site priority order: %s",
        ", ".join(f"{site}({SITE_PRIORITY.get(site, 0)})" for site in get_ordered_site_keys()),
    )

    state = load_state()
    seed_pending_sections(state)

    while not runtime.STOP_REQUESTED:
        logger.info("[START] Discovery iteration")
        visited_sections = await discover_iteration(
            state=state,
            sections_per_site=sections_per_site,
            product_limit_per_section=discovery_products_per_section,
            next_sections_limit_per_section=discovery_next_sections_per_section,
        )

        if runtime.STOP_REQUESTED:
            logger.warning("[STOP] Interrupted after discovery iteration")
            return

        logger.info("[START] Process phase")
        processed_count = await process_phase_concurrent(
            state=state,
            max_images=max_images,
            concurrency=concurrency,
        )

        remaining_products = len([
            url for url in state.discovered_urls
            if url not in state.processed_urls and url not in state.in_progress_urls
        ])
        remaining_sections = len(state.pending_section_urls)

        logger.info(
            "[LOOP] visited_sections=%s processed_count=%s remaining_sections=%s remaining_products=%s",
            visited_sections,
            processed_count,
            remaining_sections,
            remaining_products,
        )

        if visited_sections == 0 and processed_count == 0:
            break

        if remaining_sections == 0 and remaining_products == 0:
            break

    logger.info("[DONE]")


def main():
    asyncio.run(async_main())