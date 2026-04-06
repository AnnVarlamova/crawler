from __future__ import annotations

from pathlib import Path

import httpx

from app.config import DOWNLOADED_IMAGES_FILE
from app.models import ProductCard, State
from app.runtime import STOP_REQUESTED
from app.utils import (
    append_jsonl,
    dedupe_preserve_order,
    ensure_dir,
    filename_from_url,
    is_probably_image_url,
)


async def download_one_image(client: httpx.AsyncClient, url: str, target: Path) -> bool:
    try:
        r = await client.get(url, timeout=60.0, follow_redirects=True)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").lower()
        if "image" not in ctype and not is_probably_image_url(url):
            return False
        target.write_bytes(r.content)
        return True
    except Exception:
        return False


async def download_images(card: ProductCard, item_dir: Path, state: State, max_images: int) -> list[str]:
    images_dir = item_dir / "images"
    ensure_dir(images_dir)

    image_urls = dedupe_preserve_order([img.url for img in card.images if img.url])[:max_images]
    saved_paths: list[str] = []

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        for idx, url in enumerate(image_urls, start=1):
            if STOP_REQUESTED:
                break

            target = images_dir / filename_from_url(url, f"image_{idx}.jpg")

            if target.exists():
                saved_paths.append(str(target))
                if url not in state.downloaded_image_urls:
                    state.downloaded_image_urls.add(url)
                    append_jsonl(DOWNLOADED_IMAGES_FILE, {"url": url, "path": str(target)})
                continue

            if url in state.downloaded_image_urls:
                continue

            ok = await download_one_image(client, url, target)
            if ok:
                saved_paths.append(str(target))
                state.downloaded_image_urls.add(url)
                append_jsonl(DOWNLOADED_IMAGES_FILE, {"url": url, "path": str(target)})

    return saved_paths