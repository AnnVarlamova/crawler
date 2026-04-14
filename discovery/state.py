from __future__ import annotations

from discovery.config import DISCOVERED_FILE, STATE_DIR
from discovery.models import State
from discovery.utils import ensure_dir, read_jsonl_keyset


def load_state() -> State:
    ensure_dir(STATE_DIR)
    return State(
        discovered_urls=read_jsonl_keyset(DISCOVERED_FILE, "url"),
        site_error_counts={},
    )