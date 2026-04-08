from __future__ import annotations

import os
from pathlib import Path


def _merge_no_proxy(existing: str | None) -> str:
    required = ["127.0.0.1", "localhost", "::1"]
    current = [x.strip() for x in (existing or "").split(",") if x.strip()]
    seen = {x.lower() for x in current}
    for item in required:
        if item.lower() not in seen:
            current.append(item)
    return ",".join(current)


os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1"


SITE_URLS = {
    "simplicity": "https://simplicity.com/",
    "vikisews": "https://vikisews.com/",
    "burdastyle": "https://burdastyle.ru/",
    "helpersew": "https://helpersew.com/",
    "grasser": "https://grasser.ru/",
    "shkatulka": "https://shkatulka-sew.ru/",
    "korfiati": "https://korfiati.ru/",
    "marfy": "https://www.marfy.it/",
}

ALLOWED_DOMAINS = [
    "*.simplicity.com",
    "*.vikisews.com",
    "*.burdastyle.ru",
    "*.helpersew.com",
    "*.grasser.ru",
    "*.shkatulka-sew.ru",
    "*.korfiati.ru",
    "*.marfy.it",
]

DATA_DIR = Path("data")
STATE_DIR = DATA_DIR / "_state"
CACHE_DIR = DATA_DIR / "_cache"


# =========================
# DATASET PATH (REQUIRED)
# =========================

ITEMS_DIR_ENV = os.getenv("ITEMS_DIR")

if not ITEMS_DIR_ENV:
    raise RuntimeError(
        "ITEMS_DIR is not set.\n"
        "Please set environment variable ITEMS_DIR to your dataset path.\n"
        "Example:\n"
        "  Windows (PowerShell):\n"
        "    $env:ITEMS_DIR=\"D:\\Yandex.Disk\\pics\"\n"
        "  or in .env:\n"
        "    ITEMS_DIR=D:\\Yandex.Disk\\pics"
    )

ITEMS_DIR = Path(ITEMS_DIR_ENV)

if not ITEMS_DIR.exists():
    raise RuntimeError(
        f"ITEMS_DIR does not exist: {ITEMS_DIR}\n"
        "Please create this directory before running the script."
    )

if not ITEMS_DIR.is_dir():
    raise RuntimeError(
        f"ITEMS_DIR is not a directory: {ITEMS_DIR}"
    )


DISCOVERED_FILE = STATE_DIR / "discovered_urls.jsonl"
PROCESSED_FILE = STATE_DIR / "processed_urls.jsonl"
SAVED_ITEMS_FILE = STATE_DIR / "saved_items.jsonl"
DOWNLOADED_IMAGES_FILE = STATE_DIR / "downloaded_images.jsonl"
ERRORS_FILE = STATE_DIR / "errors.jsonl"
IN_PROGRESS_FILE = STATE_DIR / "in_progress_urls.jsonl"

PENDING_SECTION_URLS_FILE = STATE_DIR / "pending_section_urls.json"
VISITED_SECTION_URLS_FILE = STATE_DIR / "visited_section_urls.json"

DEFAULT_LIMIT_PER_SITE = 3
DEFAULT_MAX_IMAGES = 8
DEFAULT_CONCURRENCY = 1

DEFAULT_SECTIONS_PER_SITE = 1
DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION = 24
DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION = 12

CACHE_VERSION = "v2"
DEFAULT_BROWSER_MODEL = os.getenv("OPENAI_BROWSER_MODEL", "gpt-4.1")
DEFAULT_TAGS_MODEL = os.getenv("OPENAI_TAGS_MODEL", "gpt-4.1-mini")

BASE_TAGS = [
    "women", "men", "unisex",
    "dress", "blouse", "shirt", "top", "tshirt", "skirt",
    "trousers", "pants", "jeans", "shorts",
    "jacket", "blazer", "coat", "trench", "vest",
    "hoodie", "sweatshirt", "sweater", "cardigan",
    "jumpsuit", "bodysuit", "loungewear", "sleepwear", "swimwear",
    "fitted", "relaxed", "oversized", "straight", "a-line", "wrap",
    "slim-fit", "wide-leg", "cropped", "maxi", "midi", "mini",
    "sleeveless", "short-sleeve", "long-sleeve", "puff-sleeve",
    "raglan", "dropped-shoulder",
    "v-neck", "crew-neck", "boat-neck", "turtleneck",
    "collar", "lapel", "hood", "zipper", "buttons",
    "pleats", "darts", "pockets", "belt", "lining",
    "casual", "office", "formal", "evening", "classic", "minimalist",
    "spring", "summer", "autumn", "winter", "demi-season",
    "beginner", "intermediate", "advanced",
    "pdf-pattern", "sewing-pattern",
]