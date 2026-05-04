from __future__ import annotations

import os
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

DATASET_DIR = Path(os.getenv("DATASET_DIR", "dataset"))

LINKS_DIR = DATASET_DIR / "links"
COLLECTED_DIR = DATASET_DIR / "collected"

DATA_DIR = Path("data")
STATE_DIR = DATA_DIR / "_state_collecting"

PROCESSED_FILE = STATE_DIR / "processed_collecting.jsonl"
ERRORS_FILE = STATE_DIR / "errors_collecting.jsonl"
SKIPPED_FILE = STATE_DIR / "skipped_collecting.jsonl"

DETAILED_LOG_DIR = PACKAGE_DIR / "logs"
GENERAL_LOG_DIR = PROJECT_ROOT / "logs"

DETAILED_LOG_FILE = DETAILED_LOG_DIR / "collecting.log"
GENERAL_LOG_FILE = GENERAL_LOG_DIR / "collecting.log"

PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))

DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "30"))
MAX_IMAGES_PER_PRODUCT = int(os.getenv("MAX_IMAGES_PER_PRODUCT", "30"))

RETRY_COUNT = int(os.getenv("RETRY_COUNT", "2"))

SUPPORTED_SITES = {
    "burdastyle",
    "etsy",
    "grasser",
    "helpersew",
    "marfy",
    "shkatulka",
    "simplicity",
    "vikisews",
}