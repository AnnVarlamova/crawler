from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_HTML_DIR = DATA_DIR / "raw_html"
TEXT_DIR = DATA_DIR / "text"
IMAGES_DIR = DATA_DIR / "images"
FILES_DIR = DATA_DIR / "files"
JSONL_DIR = DATA_DIR / "jsonl"
STATE_DIR = DATA_DIR / "state"

ITEMS_JSONL = JSONL_DIR / "items.jsonl"
CANDIDATES_JSONL = JSONL_DIR / "candidates.jsonl"

HEADLESS = True

# 🚀 Чуть ускоряем, но не ломаем сайты
MAX_CONCURRENCY = 4
MAX_PAGES_PER_SITE = 250
MAX_DEPTH = 4

NAV_TIMEOUT_MS = 45000
WAIT_AFTER_LOAD_MS = 900
REQUEST_TIMEOUT_SEC = 45

# ⏱️ мягкий delay
RESPECT_DELAY_SEC = 1.2
RESPECT_JITTER_MIN = 0.3
RESPECT_JITTER_MAX = 0.9

DOWNLOAD_IMAGES = True
DOWNLOAD_FILES = True
SAVE_HTML = True
SAVE_TEXT = True

# ⚡ ускорение Playwright
BLOCK_BROWSER_IMAGES = True
BLOCK_BROWSER_FONTS = True
BLOCK_BROWSER_MEDIA = True
BLOCK_BROWSER_STYLESHEETS = True

USE_ROBOTS_TXT = False

# 🌐 домены (оставляем как есть, но можно потом чистить)
ALLOWED_DOMAINS = {
    "simplicity.com", "www.simplicity.com",
    "vikisews.com",
    "grasser.ru",
    "blog.pattern-vault.com",
    "thecuttingclass.com", "www.thecuttingclass.com",
    "shkatulka-sew.ru",
    "korfiati.ru",
    "etsy.com", "www.etsy.com",
    "thefoldline.com", "www.thefoldline.com",
    "lekala.co", "www.lekala.co",
    "sewist.com", "www.sewist.com",
    "marfy.it", "www.marfy.it",
    "bootstrapfashion.com", "patterns.bootstrapfashion.com",
    "tianascloset.com",
    "burdastyle.ru",
    "tessuti-shop.com", "www.tessuti-shop.com",
    "stylearc.com", "www.stylearc.com",
}

# 🔥 НОВЫЙ БАЗОВЫЙ ВХОД
ENTRY_POINTS = [
    # Korfiati
    "https://korfiati.ru/vyikroyki-odezhdyi/vyikroyki-zhenskoy-odezhdyi/",
    "https://korfiati.ru/vyikroyki-odezhdyi/vyikroyki-iz-trikotaga/",
    "https://korfiati.ru/vyikroyki-odezhdyi/vyikroyki-muzhskoy-odezhdyi/",

    # The Fold Line
    "https://thefoldline.com/collections/womens-sewing-patterns",
    "https://thefoldline.com/collections/mens-sewing-patterns",

    # Lekala
    "https://www.lekala.co/catalog/women",
    "https://www.lekala.co/catalog/men",

    # Bootstrap
    "https://patterns.bootstrapfashion.com/exclusive-designer-sewing-patterns.html?limit=all",

    # Tiana
    "https://tianascloset.com/index.php/product-category/womens-collection/",
    "https://tianascloset.com/index.php/product-category/mens-collection/",

    # Burda
    "https://burdastyle.ru/vikroyki/dlya-zhenshhin/",
    "https://burdastyle.ru/vikroyki/dlya-muzhchin/",

    # StyleArc
    "https://www.stylearc.com/shop-category/sewing-patterns/",

    # Pattern Vault
    "https://blog.pattern-vault.com/free-designer-patterns/"
]

# ❗ Старые seed убираем полностью
SEED_URLS = ENTRY_POINTS