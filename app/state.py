from __future__ import annotations

from app.config import (
    DISCOVERED_FILE,
    DOWNLOADED_IMAGES_FILE,
    PENDING_SECTION_URLS_FILE,
    PROCESSED_FILE,
    SAVED_ITEMS_FILE,
    STATE_DIR,
    VISITED_SECTION_URLS_FILE,
)
from app.models import State
from app.utils import ensure_dir, read_json_string_list, read_jsonl_keyset


def load_state() -> State:
    ensure_dir(STATE_DIR)
    return State(
        discovered_urls=read_jsonl_keyset(DISCOVERED_FILE, "url"),
        processed_urls=read_jsonl_keyset(PROCESSED_FILE, "url"),
        saved_item_ids=read_jsonl_keyset(SAVED_ITEMS_FILE, "item_id"),
        downloaded_image_urls=read_jsonl_keyset(DOWNLOADED_IMAGES_FILE, "url"),
        in_progress_urls=set(),
        reserved_item_ids=set(),
        pending_section_urls=set(read_json_string_list(PENDING_SECTION_URLS_FILE)),
        visited_section_urls=set(read_json_string_list(VISITED_SECTION_URLS_FILE)),
        site_error_counts={},
    )