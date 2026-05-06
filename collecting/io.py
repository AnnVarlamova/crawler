from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from collecting.config import SUPPORTED_SITES
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

    for path in sorted(links_dir.glob("**/products.jsonl")):
        rows = read_jsonl(path)

        for row in rows:
            row_site = row.get("site")
            url = row.get("url")
            category = row.get("category")
            source_page = row.get("source_page")

            if not row_site or row_site not in SUPPORTED_SITES:
                continue

            if site and row_site != site:
                continue

            if not url or not category:
                continue

            records.append(
                LinkRecord(
                    url=url,
                    site=row_site,
                    category=category,
                )
            )

    return records


def round_robin_records(records: list[LinkRecord]) -> list[LinkRecord]:
    """
    Перемешивает очередь по сайтам:

      burda_1, grasser_1, helpersew_1,
      burda_2, grasser_2, helpersew_2,
      ...

    Это мягче для сайтов, чем собирать один домен подряд.
    """
    grouped: dict[str, deque[LinkRecord]] = defaultdict(deque)

    for record in records:
        grouped[record.site].append(record)

    site_order = sorted(grouped.keys())
    result: list[LinkRecord] = []

    while grouped:
        empty_sites: list[str] = []

        for site in site_order:
            queue = grouped.get(site)

            if not queue:
                empty_sites.append(site)
                continue

            result.append(queue.popleft())

            if not queue:
                empty_sites.append(site)

        for site in empty_sites:
            grouped.pop(site, None)

        site_order = [site for site in site_order if site in grouped]

    return result


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


def product_to_metadata(product: CollectedProduct) -> dict:
    return {
        "url": product.url,
        "site": product.site,
        "category": product.category,
        "source_page": product.source_page,
        "title": product.title,
        "description": product.description,
        "similar_patterns": product.similar_patterns,
        "collection": product.collection,
        "season": product.season,
        "style": product.style,
    }


def save_product(collected_dir: Path, product: CollectedProduct) -> Path:
    product_dir = get_product_dir(collected_dir, product)
    metadata_path = product_dir / "metadata.json"

    write_json(metadata_path, product_to_metadata(product))

    return metadata_path