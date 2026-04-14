from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, row: dict) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl_keyset(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()

    result = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
                val = obj.get(key)
                if isinstance(val, str) and val:
                    result.add(val)
            except Exception:
                continue

    return result


def append_jsonl_unique(path: Path, row: dict, key: str, existing_keys: set[str] | None = None) -> bool:
    val = row.get(key)
    if not isinstance(val, str) or not val:
        return False

    if existing_keys is None:
        existing_keys = read_jsonl_keyset(path, key)

    if val in existing_keys:
        return False

    append_jsonl(path, row)
    existing_keys.add(val)
    return True


def get_site_host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def slugify(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
    )