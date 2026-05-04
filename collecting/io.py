from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from collecting.models import LinkRecord, CollectedProduct


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []

    rows: list[dict] = []

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}: {e}") from e

    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_link_records(links_dir: Path, site: str | None = None) -> list[LinkRecord]:
    records: list[LinkRecord] = []

    for path in links_dir.glob("**/products.jsonl"):
        rows = read_jsonl(path)

        for row in rows:
            row_site = row.get("site")
            url = row.get("url")
            category = row.get("category")

            if site and row_site != site:
                continue

            if not url or not row_site or not category:
                continue

            records.append(
                LinkRecord(
                    url=url,
                    site=row_site,
                    category=category,
                    source_page=row.get("source_page"),
                )
            )

    return records


def slugify(value: str, max_len: int = 90) -> str:
    value = value.lower().strip()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-zа-яё0-9]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-")

    if not value:
        value = "item"

    return value[:max_len].strip("-")


def product_id_from_url(url: str) -> str:
    readable = slugify(url)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"


def get_product_dir(collected_dir: Path, product: CollectedProduct) -> Path:
    product_id = product_id_from_url(product.url)
    return collected_dir / product.site / product.category / product_id


def save_product(collected_dir: Path, product: CollectedProduct) -> Path:
    product_dir = get_product_dir(collected_dir, product)
    metadata_path = product_dir / "metadata.json"

    write_json(metadata_path, asdict(product))

    return metadata_path