from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app import runtime
from app.browser_client import discover_batch_for_section
from app.config import (
    DATA_DIR,
    DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION,
    DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION,
    DEFAULT_SECTIONS_PER_SITE,
    DISCOVERED_FILE,
    ERRORS_FILE,
    MAX_SECTION_RETRIES_WITHOUT_PRODUCTS,
    REVISIT_MIGRATION_DONE_FILE,
    SITE_ERROR_LIMIT,
    SITE_PARENT_URLS,
    SITE_PRIORITY,
    SITE_URLS,
    STATE_DIR,
)
from app.models import State
from app.state import load_state, persist_section_state
from app.utils import (
    append_jsonl,
    detect_site_key,
    ensure_dir,
    get_site_host,
    is_allowed_product_url,
    is_allowed_section_url,
    read_json,
    write_json,
)

logger = logging.getLogger(__name__)

# Поднимаем версию миграции, чтобы уже "пройденные" в прошлых вариантах
# страницы ещё раз вернулись в pending и дошлись по новой логике.
REVISIT_MIGRATION_VERSION = 2


def _handle_stop(signum, frame):
    runtime.STOP_REQUESTED = True
    logger.warning("Stop requested. Waiting for current page to finish safely...")


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


def _requeue_old_visited_once(state: State) -> None:
    """
    Одноразово возвращаем старые visited-страницы обратно в pending,
    чтобы они прошлись по новой логике.

    Важно:
    - не трогаем уже существующие pending
    - visited НЕ очищаем полностью; просто даём страницам шанс снова оказаться в очереди
    - маркер версионирован, чтобы можно было повторно включить миграцию при изменении логики
    """
    marker = read_json(REVISIT_MIGRATION_DONE_FILE)
    marker_version = 0
    if isinstance(marker, dict):
        value = marker.get("version")
        if isinstance(value, int):
            marker_version = value

    if marker_version >= REVISIT_MIGRATION_VERSION:
        return

    moved = 0
    for url in list(state.visited_section_urls):
        if url not in state.pending_sections:
            state.pending_sections[url] = None
            moved += 1

    write_json(
        REVISIT_MIGRATION_DONE_FILE,
        {
            "done": True,
            "version": REVISIT_MIGRATION_VERSION,
            "moved": moved,
        },
    )
    persist_section_state(state)
    logger.info("[MIGRATION] requeued old visited pages once: moved=%s", moved)


def seed_pending_sections(state: State) -> None:
    changed = False
    for site_key, start_url in SITE_URLS.items():
        if start_url not in state.pending_sections and start_url not in state.visited_section_urls:
            parent_url = SITE_PARENT_URLS.get(site_key)
            if parent_url == start_url:
                parent_url = None
            state.pending_sections[start_url] = parent_url
            changed = True

    if changed:
        persist_section_state(state)


def get_ordered_site_keys() -> list[str]:
    return sorted(
        SITE_URLS.keys(),
        key=lambda site_key: (-SITE_PRIORITY.get(site_key, 0), site_key),
    )


def is_site_blocked(state: State, site_host: str) -> bool:
    return state.site_error_counts.get(site_host, 0) >= SITE_ERROR_LIMIT


def record_site_success(state: State, site_host: str) -> None:
    if state.site_error_counts.get(site_host, 0):
        state.site_error_counts[site_host] = 0


def record_site_error(state: State, site_host: str) -> int:
    current = state.site_error_counts.get(site_host, 0) + 1
    state.site_error_counts[site_host] = current
    return current


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

        start_url = SITE_URLS[site_key]
        site_host = get_site_host(start_url)

        if is_site_blocked(state, site_host):
            logger.warning(
                "[DISCOVER] skipping blocked site=%s host=%s errors=%s",
                site_key,
                site_host,
                state.site_error_counts.get(site_host, 0),
            )
            continue

        site_pending = [
            (url, parent_url)
            for url, parent_url in state.pending_sections.items()
            if detect_site_key(url) == site_key or get_site_host(url) == site_host
        ]
        if not site_pending:
            continue

        for page_url, parent_url in site_pending[:sections_per_site]:
            if runtime.STOP_REQUESTED:
                break

            attempt_no = state.section_attempts.get(page_url, 0) + 1

            logger.info(
                "[DISCOVER] site=%s priority=%s page=%s parent=%s attempt=%s",
                site_key,
                SITE_PRIORITY.get(site_key, 0),
                page_url,
                parent_url,
                attempt_no,
            )

            state.pending_sections.pop(page_url, None)
            persist_section_state(state)

            try:
                batch = await discover_batch_for_section(
                    page_url=page_url,
                    parent_url=parent_url,
                    product_limit=product_limit_per_section,
                    section_limit=next_sections_limit_per_section,
                )

                state.section_attempts[page_url] = attempt_no

                added_products = 0
                added_sections = 0

                # PRODUCT URLS:
                # Пишем в discovered_urls.jsonl всегда, даже если это дубликат.
                # Но внутренний set всё равно обновляем, чтобы понимать,
                # появились ли реально НОВЫЕ product links для решения "закрывать/не закрывать страницу".
                for product_url in batch.product_urls:
                    if not is_allowed_product_url(product_url):
                        continue

                    append_jsonl(
                        DISCOVERED_FILE,
                        {
                            "url": product_url,
                            "site": site_key,
                            "source_page": page_url,
                        },
                    )

                    if product_url not in state.discovered_urls:
                        state.discovered_urls.add(product_url)
                        added_products += 1

                # NEXT SECTIONS:
                # Ничего "заново писать" не пытаемся.
                # Добавляем только действительно новые section pages.
                for section_url in batch.next_section_urls:
                    if not is_allowed_section_url(section_url):
                        continue
                    if section_url in state.visited_section_urls:
                        continue
                    if section_url in state.pending_sections:
                        continue

                    state.pending_sections[section_url] = page_url
                    added_sections += 1

                # Ключевая логика:
                # страницу держим активной ТОЛЬКО если она дала новые product links.
                #
                # Новые section links можно забрать, но они НЕ считаются причиной
                # снова проходить ту же самую страницу.
                if added_products > 0:
                    state.pending_sections[page_url] = parent_url
                    logger.info(
                        "[DISCOVER] keep page active=%s attempt=%s new_products=%s new_sections=%s",
                        page_url,
                        attempt_no,
                        added_products,
                        added_sections,
                    )
                else:
                    state.visited_section_urls.add(page_url)
                    logger.info(
                        "[DISCOVER] finalize page=%s attempt=%s reason=no_new_products new_sections=%s",
                        page_url,
                        attempt_no,
                        added_sections,
                    )

                persist_section_state(state)
                visited_this_iteration += 1
                record_site_success(state, site_host)

                logger.info(
                    "[DISCOVER] site=%s page=%s new_products=%s new_sections=%s remaining_pending_for_site=%s total_unique_discovered=%s",
                    site_key,
                    page_url,
                    added_products,
                    added_sections,
                    len([u for u in state.pending_sections if get_site_host(u) == site_host]),
                    len(state.discovered_urls),
                )

            except Exception as e:
                state.section_attempts[page_url] = attempt_no

                if attempt_no >= MAX_SECTION_RETRIES_WITHOUT_PRODUCTS:
                    state.visited_section_urls.add(page_url)
                    logger.warning(
                        "[DISCOVER] finalize page=%s attempt=%s reason=error_limit_reached",
                        page_url,
                        attempt_no,
                    )
                else:
                    state.pending_sections[page_url] = parent_url
                    logger.warning(
                        "[DISCOVER] requeue page=%s attempt=%s/%s after error",
                        page_url,
                        attempt_no,
                        MAX_SECTION_RETRIES_WITHOUT_PRODUCTS,
                    )

                persist_section_state(state)

                count = record_site_error(state, site_host)
                append_jsonl(
                    ERRORS_FILE,
                    {
                        "phase": "discover",
                        "site": site_key,
                        "page_url": page_url,
                        "parent_url": parent_url,
                        "error": str(e),
                    },
                )
                logger.exception("[DISCOVER] failed for page %s", page_url)

                if count >= SITE_ERROR_LIMIT:
                    logger.warning(
                        "[DISCOVER] site blocked for this run: site=%s host=%s errors=%s",
                        site_key,
                        site_host,
                        count,
                    )
                    break

    return visited_this_iteration


async def async_main() -> None:
    ensure_dir(DATA_DIR)
    ensure_dir(STATE_DIR)

    sections_per_site = DEFAULT_SECTIONS_PER_SITE
    discovery_products_per_section = DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION
    discovery_next_sections_per_section = DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--sections-per-site" and i + 1 < len(argv):
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

    logger.info("Starting discovery pipeline")
    logger.info("DATA_DIR=%s", DATA_DIR)
    logger.info("STATE_DIR=%s", STATE_DIR)
    logger.info(
        "Parameters: sections_per_site=%s, discovery_products_per_section=%s, discovery_next_sections_per_section=%s, max_section_retries_without_products=%s",
        sections_per_site,
        discovery_products_per_section,
        discovery_next_sections_per_section,
        MAX_SECTION_RETRIES_WITHOUT_PRODUCTS,
    )
    logger.info(
        "Site priority order: %s",
        ", ".join(f"{site}({SITE_PRIORITY.get(site, 0)})" for site in get_ordered_site_keys()),
    )

    state = load_state()
    _requeue_old_visited_once(state)
    seed_pending_sections(state)

    while not runtime.STOP_REQUESTED:
        logger.info("[START] Discovery iteration")

        visited_sections = await discover_iteration(
            state=state,
            sections_per_site=sections_per_site,
            product_limit_per_section=discovery_products_per_section,
            next_sections_limit_per_section=discovery_next_sections_per_section,
        )

        remaining_sections = len([
            url for url in state.pending_sections
            if not is_site_blocked(state, get_site_host(url))
        ])

        logger.info(
            "[LOOP] visited_sections=%s remaining_sections=%s total_unique_discovered=%s blocked_sites=%s",
            visited_sections,
            remaining_sections,
            len(state.discovered_urls),
            {k: v for k, v in state.site_error_counts.items() if v >= SITE_ERROR_LIMIT},
        )

        if visited_sections == 0:
            break

        if remaining_sections == 0:
            break

    logger.info("[DONE] discovery finished")


def main() -> None:
    asyncio.run(async_main())