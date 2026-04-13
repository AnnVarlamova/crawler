from __future__ import annotations

import os
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1"

SITE_URLS = {
    "vikisews": "https://vikisews.com/vykrojki/",
    "simplicity": "https://simplicity.com/",
    "grasser_women": "https://grasser.ru/vykrojki/vykroyki-dlya-zhenshchin/",
    "grasser_men": "https://grasser.ru/vykrojki/muzhskie-vykrojki/",
    "helpersew_women": "https://helpersew.com/catalog/zhenskie/",
    "helpersew_men": "https://helpersew.com/catalog/muzhskie/",
    "burdastyle_women": "https://burdastyle.ru/vikroyki/dlya-zhenshhin/",
    "burdastyle_men": "https://burdastyle.ru/vikroyki/dlya-muzhchin/",
    "pattern_vault": "https://blog.pattern-vault.com/free-designer-patterns/",
    "shkatulka_women": "https://shkatulka-sew.ru/category/jenskie-vykroyki/",
    "shkatulka_men": "https://shkatulka-sew.ru/category/mujskie-vykroyki/",
    "marfy": "https://www.marfy.it/en/the-marfy-hand-made-pre-cut-sewing-pattern/",
    "marfy_pdf": "https://www.marfy.it/en/sewing-pattern/digital-pdf-sewing-patterns/",
}

SITE_PARENT_URLS = {
    "grasser_women": "https://grasser.ru/vykrojki/",
    "grasser_men": "https://grasser.ru/vykrojki/",
    "simplicity": "https://simplicity.com/new-sewing-patterns/",
    "marfy": "https://www.marfy.it/en/",
    "marfy_pdf": "https://www.marfy.it/en/sewing-pattern/",
}

SITE_PRIORITY = {
    "vikisews": 100,
    "simplicity": 90,
    "grasser_women": 80,
    "grasser_men": 80,
    "helpersew_women": 70,
    "helpersew_men": 70,
    "burdastyle_women": 60,
    "burdastyle_men": 60,
    "pattern_vault": 50,
    "shkatulka_women": 40,
    "shkatulka_men": 40,
    "marfy": 30,
    "marfy_pdf": 30,
}

DATA_DIR = Path("data")
STATE_DIR = DATA_DIR / "_state"
CACHE_DIR = DATA_DIR / "_cache"

DISCOVERED_FILE = STATE_DIR / "discovered_urls.jsonl"
ERRORS_FILE = STATE_DIR / "errors.jsonl"

PENDING_SECTIONS_FILE = STATE_DIR / "pending_sections.json"
LEGACY_PENDING_SECTION_URLS_FILE = STATE_DIR / "pending_section_urls.json"

VISITED_SECTION_URLS_FILE = STATE_DIR / "visited_section_urls.json"
SECTION_ATTEMPTS_FILE = STATE_DIR / "section_attempts.json"

# Маркер одноразовой миграции: старые visited -> pending
REVISIT_MIGRATION_DONE_FILE = STATE_DIR / "revisit_migration_done.json"

DEFAULT_SECTIONS_PER_SITE = 1
DEFAULT_DISCOVERY_PRODUCTS_PER_SECTION = 24
DEFAULT_DISCOVERY_NEXT_SECTIONS_PER_SECTION = 12

CACHE_VERSION = "v5"
DEFAULT_BROWSER_MODEL = os.getenv("OPENAI_BROWSER_MODEL", "gpt-4.1")

AGENT_MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "3"))
AGENT_RETRY_BASE_DELAY_SEC = float(os.getenv("AGENT_RETRY_BASE_DELAY_SEC", "2.0"))
AGENT_RETRY_MAX_DELAY_SEC = float(os.getenv("AGENT_RETRY_MAX_DELAY_SEC", "20.0"))
SITE_ERROR_LIMIT = int(os.getenv("SITE_ERROR_LIMIT", "4"))
MAX_SECTION_RETRIES_WITHOUT_PRODUCTS = int(
    os.getenv("MAX_SECTION_RETRIES_WITHOUT_PRODUCTS", "2")
)