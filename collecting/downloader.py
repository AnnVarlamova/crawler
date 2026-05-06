from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image

from collecting.config import (
    DOWNLOAD_TIMEOUT_SECONDS,
    IMAGE_INDEX_FILE,
    IMAGE_MAX_HEIGHT,
    IMAGE_MAX_WIDTH,
    JPEG_QUALITY,
    MAX_IMAGES_PER_PRODUCT,
    WEBP_QUALITY,
)
from collecting.models import (
    IMAGE_MANNEQUIN,
    IMAGE_PHOTO,
    IMAGE_TECHNICAL,
    CollectedImage,
    CollectedProduct,
)

logger = logging.getLogger("collecting")

_IMAGE_INDEX_LOCK = threading.Lock()


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


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(unquote(path)).name
    return name or "image.jpg"


def stem_from_url(url: str) -> str:
    return Path(filename_from_url(url)).stem.lower()


def safe_filename_part(value: str, max_len: int = 80) -> str:
    value = unquote(value).lower().strip()
    value = re.sub(r"[^a-zа-яё0-9]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-")
    return (value or "image")[:max_len]


def is_digits_only_filename(url: str) -> bool:
    stem = Path(filename_from_url(url)).stem
    return bool(re.fullmatch(r"\d+", stem))


def photo_number(url: str) -> int | None:
    name = Path(filename_from_url(url)).stem.lower()

    match = re.search(r"фото[-_\s]?(\d+)", name, flags=re.IGNORECASE)
    if not match:
        return None

    return int(match.group(1))


def classify_image(
    *,
    product: CollectedProduct,
    image: CollectedImage,
    max_photo_number: int | None,
) -> str | None:
    """
    Возвращает тип картинки или None, если картинку надо пропустить.

    Типы:
      photo
      mannequin
      technical
    """
    site = product.site
    url = image.url
    name = filename_from_url(url)
    name_lower = name.lower()
    stem_lower = stem_from_url(url)
    alt_lower = (image.alt or "").lower()
    source_lower = (image.source or "").lower()

    joined = " ".join([url.lower(), name_lower, alt_lower, source_lower])

    # Общий мусор.
    bad_parts = [
        "logo",
        "sprite",
        "icon",
        "placeholder",
        "avatar",
        "banner",
        "payment",
        "social",
        "loader",
        "preloader",
        "rating",
        "star",
        "favicon",
    ]

    if any(part in joined for part in bad_parts):
        return None

    # Vikisews.
    if site == "vikisews":
        if name.startswith("Обложка_") or stem_lower.startswith("обложка"):
            return None

        if "тех_рисунок" in stem_lower or "техрисунок" in stem_lower:
            return IMAGE_TECHNICAL

        if "эскиз" in stem_lower:
            return IMAGE_MANNEQUIN

        return IMAGE_PHOTO

    # Grasser.
    if site == "grasser":
        if (
            "tekhrisunok" in stem_lower
            or "tehrisunok" in stem_lower
            or "техрисунок" in stem_lower
            or "тех_рисунок" in stem_lower
        ):
            return IMAGE_TECHNICAL

        return IMAGE_PHOTO

    # Helpersew — пока без автоопределения техрисунка.
    if site == "helpersew":
        return IMAGE_PHOTO

    # Simplicity.
    if site == "simplicity":
        if "front of envelope" in joined or "front envelope" in joined or "envelope front" in joined:
            return None

        if (
            "back of envelope" in joined
            or "back envelope" in joined
            or "envelope back" in joined
            or "lineart" in joined
            or "line art" in joined
            or "#tab-lineart" in joined
        ):
            return IMAGE_TECHNICAL

        return IMAGE_PHOTO

    # Shkatulka.
    if site == "shkatulka":
        if "техрисунок" in stem_lower or "тех_рисунок" in stem_lower:
            return IMAGE_TECHNICAL

        # Обложки и аватарки: 1.jpg, 2.jpg, 123.jpg и т.п.
        if is_digits_only_filename(url):
            return None

        n = photo_number(url)

        # Последнюю фото-N не берём, потому что там часто коллаж фото+рисунок.
        if n is not None and max_photo_number is not None and n == max_photo_number:
            return None

        if n is not None:
            return IMAGE_PHOTO

        return IMAGE_PHOTO

    # BurdaStyle.
    if site == "burdastyle":
        if "техрисунок" in joined or "технический" in joined or "lineart" in joined or "line art" in joined:
            return IMAGE_TECHNICAL

        if (
            "манекен" in joined
            or "сшитое" in joined
            or "сшитый" in joined
            or "сшитая" in joined
            or "сшитые" in joined
        ):
            return IMAGE_MANNEQUIN

        return IMAGE_PHOTO

    # Marfy.
    if site == "marfy":
        return IMAGE_PHOTO

    return IMAGE_PHOTO


def classify_and_limit_images(product: CollectedProduct) -> list[CollectedImage]:
    candidates = list(product.images)

    photo_numbers = [photo_number(img.url) for img in candidates]
    photo_numbers = [n for n in photo_numbers if n is not None]
    max_photo_number = max(photo_numbers) if photo_numbers else None

    classified: list[CollectedImage] = []

    for image in candidates:
        image_type = classify_image(
            product=product,
            image=image,
            max_photo_number=max_photo_number,
        )

        if image_type is None:
            logger.debug(
                "Skip image site=%s product=%s url=%s",
                product.site,
                product.url,
                image.url,
            )
            continue

        image.image_type = image_type
        classified.append(image)

    priority = {
        IMAGE_TECHNICAL: 0,
        IMAGE_MANNEQUIN: 1,
        IMAGE_PHOTO: 2,
    }

    classified.sort(
        key=lambda img: (
            priority.get(img.image_type or IMAGE_PHOTO, 99),
            img.url,
        )
    )

    if len(classified) > MAX_IMAGES_PER_PRODUCT:
        logger.info(
            "Limit images product=%s site=%s before=%s after=%s",
            product.url,
            product.site,
            len(classified),
            MAX_IMAGES_PER_PRODUCT,
        )

    return classified[:MAX_IMAGES_PER_PRODUCT]


def resize_image_in_place(path: Path) -> None:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")

            width, height = img.size

            if width <= IMAGE_MAX_WIDTH and height <= IMAGE_MAX_HEIGHT:
                return

            img.thumbnail((IMAGE_MAX_WIDTH, IMAGE_MAX_HEIGHT), Image.Resampling.LANCZOS)

            suffix = path.suffix.lower()

            if suffix in {".jpg", ".jpeg"}:
                img.save(path, quality=JPEG_QUALITY, optimize=True)
            elif suffix == ".webp":
                img.save(path, quality=WEBP_QUALITY, optimize=True)
            elif suffix == ".png":
                img.save(path, optimize=True)
            else:
                img.save(path)

            logger.debug(
                "Resized image %s from %sx%s to %sx%s",
                path,
                width,
                height,
                img.size[0],
                img.size[1],
            )

    except Exception:
        logger.exception("Failed to resize image: %s", path)


def append_image_index(row: dict) -> None:
    IMAGE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(row, ensure_ascii=False)

    with _IMAGE_INDEX_LOCK:
        with IMAGE_INDEX_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


async def download_images(product: CollectedProduct, product_dir: Path) -> CollectedProduct:
    images_dir = product_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    selected_images = classify_and_limit_images(product)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": product.url,
    }

    logger.debug(
        "Start image downloading product=%s selected=%s original=%s dir=%s",
        product.url,
        len(selected_images),
        len(product.images),
        images_dir,
    )

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        headers=headers,
    ) as client:
        for index, image in enumerate(selected_images):
            try:
                response = await client.get(image.url)
                response.raise_for_status()

                content_type = response.headers.get("content-type")
                ext = guess_extension(image.url, content_type)

                type_part = image.image_type or IMAGE_PHOTO
                name_part = safe_filename_part(stem_from_url(image.url))

                path = images_dir / f"{index:03d}_{type_part}_{name_part}{ext}"
                path.write_bytes(response.content)

                resize_image_in_place(path)

                image.local_path = str(path)

                append_image_index(
                    {
                        "site": product.site,
                        "product_url": product.url,
                        "original_image_url": image.url,
                        "image_type": type_part,
                        "local_path": str(path),
                    }
                )

                logger.debug(
                    "Image downloaded product=%s type=%s url=%s path=%s",
                    product.url,
                    type_part,
                    image.url,
                    path,
                )

            except Exception as e:
                image.local_path = None

                logger.warning(
                    "Image download failed product=%s image=%s error=%r",
                    product.url,
                    image.url,
                    e,
                )

    product.images = selected_images
    product.review_images = []

    downloaded_count = len([image for image in product.images if image.local_path])

    logger.info(
        "Images saved product=%s selected=%s downloaded=%s",
        product.url,
        len(selected_images),
        downloaded_count,
    )

    return product