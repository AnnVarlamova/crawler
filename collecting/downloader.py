from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx

from collecting.config import DOWNLOAD_TIMEOUT_SECONDS, MAX_IMAGES_PER_PRODUCT
from collecting.models import CollectedProduct

logger = logging.getLogger("collecting")


def guess_extension(url: str, content_type: str | None = None) -> str:
    if content_type:
        content_type = content_type.split(";")[0].strip()
        ext = mimetypes.guess_extension(content_type)

        if ext:
            if ext == ".jpe":
                return ".jpg"
            return ext

    path = urlparse(url).path.lower()

    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        if path.endswith(ext):
            return ext

    return ".jpg"


async def download_images(product: CollectedProduct, product_dir: Path) -> CollectedProduct:
    images_dir = product_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": product.url,
    }


    logger.debug(
        "Start image downloading product=%s images=%s dir=%s",
        product.url,
        len(product.images),
        images_dir,
    )

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        headers=headers,
    ) as client:
        for index, image in enumerate(product.images[:MAX_IMAGES_PER_PRODUCT]):
            try:
                logger.debug("Downloading image %s -> index=%s", image.url, index)

                response = await client.get(image.url)
                response.raise_for_status()

                content_type = response.headers.get("content-type")
                ext = guess_extension(image.url, content_type)

                path = images_dir / f"{index:03d}{ext}"
                path.write_bytes(response.content)

                image.local_path = str(path)

                logger.debug("Image downloaded url=%s path=%s", image.url, path)

            except Exception as e:
                image.local_path = None


                logger.warning(
                    "Image download failed product=%s image=%s error=%r",
                    product.url,
                    image.url,
                    e,
                )

    downloaded_count = len([image for image in product.images if image.local_path])

    logger.debug(
        "Finished image downloading product=%s downloaded=%s/%s",
        product.url,
        downloaded_count,
        len(product.images),
    )

    return product