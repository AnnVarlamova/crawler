from __future__ import annotations

import os
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

DETAILED_LOG_DIR = PACKAGE_DIR / "logs"
GENERAL_LOG_DIR = PROJECT_ROOT / "logs"

DATA_DIR = Path("data")
STATE_DIR = DATA_DIR / "_state"
DATASET_DIR = Path(os.getenv("DATASET_DIR", "dataset"))

DISCOVERED_FILE = STATE_DIR / "discovered_urls.jsonl"
ERRORS_FILE = STATE_DIR / "errors.jsonl"

SITE_ERROR_LIMIT = int(os.getenv("SITE_ERROR_LIMIT", "4"))

PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))

SITE_SPECS: dict[str, dict] = {
    "simplicity_women": {
        "type": "browser",
        "handler": "simplicity",
        "site": "simplicity",
        "start_url": "https://simplicity.com/women-patterns/",
        "category": "women-patterns",
    },
    "simplicity_men": {
        "type": "browser",
        "handler": "simplicity",
        "site": "simplicity",
        "start_url": "https://simplicity.com/men-patterns/",
        "category": "men-patterns",
    },
    "vikisews_dresses": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/platja-i-sarafany/",
        "category": "platja-i-sarafany",
    },
    "vikisews_tops": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/khudi-futbolki-longslivy/",
        "category": "khudi-futbolki-longslivy",
    },
    "vikisews_pants": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/bryuki-dzhinsy-shorty/",
        "category": "bryuki-dzhinsy-shorty",
    },
    "vikisews_shirts": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/rubashki-bluzki-korsazhi/",
        "category": "rubashki-bluzki-korsazhi",
    },
    "vikisews_skirts": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/jubki/",
        "category": "jubki",
    },
    "vikisews_jackets": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/zhakety-kardigany-zhilety/",
        "category": "zhakety-kardigany-zhilety",
    },
    "vikisews_overalls": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/kombinezony/",
        "category": "kombinezony",
    },
    "vikisews_outerwear": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/verhnjaja-odezhda/",
        "category": "verhnjaja-odezhda",
    },
    "vikisews_homewear": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/belye-domashnyaya-odezhda/",
        "category": "belye-domashnyaya-odezhda",
    },
    "vikisews_men": {
        "type": "browser",
        "handler": "vikisews",
        "site": "vikisews",
        "start_url": "https://vikisews.com/vykrojki/muzhskie-vykrojki/",
        "category": "muzhskie-vykrojki",
    },
    "shkatulka_dresses": {
    "type": "browser",
    "handler": "shkatulka",
    "site": "shkatulka",
    "start_url": "https://shkatulka-sew.ru/category/platya/",
    "category": "platya",
    "section_gender": "women",
    },
    "shkatulka_tops": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/bluzki-topy/",
        "category": "bluzki-topy",
        "section_gender": "women",
    },
    "shkatulka_pants": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/bryuki1/",
        "category": "bryuki1",
        "section_gender": "women",
    },
    "shkatulka_skirts": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/yubki-2/",
        "category": "yubki-2",
        "section_gender": "women",
    },
    "shkatulka_hoodies": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/tolstovki-svitshoty-hudi/",
        "category": "tolstovki-svitshoty-hudi",
        "section_gender": "women",
    },
    "shkatulka_outerwear": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/verhnyaya-odejda/",
        "category": "verhnyaya-odejda",
        "section_gender": "women",
    },
    "shkatulka_jackets": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/jakety-jilety/",
        "category": "jakety-jilety",
        "section_gender": "women",
    },
    "shkatulka_overalls": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/kombinezony-polukombinezony/",
        "category": "kombinezony-polukombinezony",
        "section_gender": "women",
    },
    "shkatulka_homewear_women": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/bele-kupalniki-domashnyaya-odejda/",
        "category": "bele-kupalniki-domashnyaya-odezhda",
        "section_gender": "women",
    },
    "shkatulka_homewear_men": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/bele-domashnyaya-odejda/",
        "category": "bele-domashnyaya-odezhda",
        "section_gender": "men",
    },
    "shkatulka_men_shirts": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/rubashki-futbolki/",
        "category": "rubashki-futbolki",
        "section_gender": "men",
    },
    "shkatulka_men_hoodies": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/tolstovki-hudi-2/",
        "category": "tolstovki-hudi-2",
        "section_gender": "men",
    },
    "shkatulka_men_pants": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/bryuki-shorty/",
        "category": "bryuki-shorty",
        "section_gender": "men",
    },
    "shkatulka_men_outerwear": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/verhnyaya-odejda-3/",
        "category": "verhnyaya-odejda-3",
        "section_gender": "men",
    },
    "shkatulka_men_jackets": {
        "type": "browser",
        "handler": "shkatulka",
        "site": "shkatulka",
        "start_url": "https://shkatulka-sew.ru/category/jilety-pidjaki/",
        "category": "jilety-pidjaki",
        "section_gender": "men",
    },
}