from __future__ import annotations

from typing import Optional

from app.config import (
    DISCOVERED_FILE,
    LEGACY_PENDING_SECTION_URLS_FILE,
    PENDING_SECTIONS_FILE,
    SECTION_ATTEMPTS_FILE,
    STATE_DIR,
    VISITED_SECTION_URLS_FILE,
)
from app.models import SectionTask, State
from app.utils import ensure_dir, read_json, read_jsonl_keyset, write_json


def _load_pending_sections_new() -> dict[str, Optional[str]]:
    raw = read_json(PENDING_SECTIONS_FILE)
    if raw is None:
        return {}

    result: dict[str, Optional[str]] = {}

    if isinstance(raw, dict):
        items = raw.get("items")
        if isinstance(items, list):
            for item in items:
                try:
                    task = SectionTask.model_validate(item)
                    if task.url:
                        result[task.url] = task.parent_url
                except Exception:
                    continue

    return result


def _load_pending_sections_legacy() -> dict[str, Optional[str]]:
    raw = read_json(LEGACY_PENDING_SECTION_URLS_FILE)
    if raw is None:
        return {}

    result: dict[str, Optional[str]] = {}

    if isinstance(raw, dict):
        urls = raw.get("urls")
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url:
                    result[url] = None

    return result


def _load_pending_sections() -> dict[str, Optional[str]]:
    new_items = _load_pending_sections_new()
    if new_items:
        return new_items

    return _load_pending_sections_legacy()


def _load_visited_sections() -> set[str]:
    raw = read_json(VISITED_SECTION_URLS_FILE)
    if raw is None:
        return set()

    result: set[str] = set()

    if isinstance(raw, dict):
        urls = raw.get("urls", [])
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url:
                    result.add(url)

    return result


def _load_section_attempts() -> dict[str, int]:
    raw = read_json(SECTION_ATTEMPTS_FILE)
    if raw is None:
        return {}

    result: dict[str, int] = {}

    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, int) and value >= 0:
                result[key] = value

    return result


def load_state() -> State:
    ensure_dir(STATE_DIR)
    return State(
        discovered_urls=read_jsonl_keyset(DISCOVERED_FILE, "url"),
        pending_sections=_load_pending_sections(),
        visited_section_urls=_load_visited_sections(),
        section_attempts=_load_section_attempts(),
        site_error_counts={},
    )


def persist_section_state(state: State) -> None:
    items = [
        {"url": url, "parent_url": parent_url}
        for url, parent_url in sorted(state.pending_sections.items(), key=lambda x: x[0])
    ]
    write_json(PENDING_SECTIONS_FILE, {"items": items})
    write_json(VISITED_SECTION_URLS_FILE, {"urls": sorted(state.visited_section_urls)})
    write_json(SECTION_ATTEMPTS_FILE, state.section_attempts)