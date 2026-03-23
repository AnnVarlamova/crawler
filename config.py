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

# Safe crawler defaults
MAX_CONCURRENCY = 3
MAX_PAGES_PER_SITE = 180
MAX_DEPTH = 3

NAV_TIMEOUT_MS = 45000
WAIT_AFTER_LOAD_MS = 1400
REQUEST_TIMEOUT_SEC = 45

# Base polite delay; real delay uses jitter on top
RESPECT_DELAY_SEC = 2.5
RESPECT_JITTER_MIN = 0.5
RESPECT_JITTER_MAX = 1.5

DOWNLOAD_IMAGES = True
DOWNLOAD_FILES = True
SAVE_HTML = True
SAVE_TEXT = True

# Abort heavy resources inside Playwright to reduce load
BLOCK_BROWSER_IMAGES = True
BLOCK_BROWSER_FONTS = True
BLOCK_BROWSER_MEDIA = True
BLOCK_BROWSER_STYLESHEETS = False

USE_ROBOTS_TXT = False

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
    "lekala.co",
    "sewist.com", "www.sewist.com",
    "marfy.it",
    "bootstrapfashion.com",
    "tianascloset.com",
    "burdastyle.ru",
    "tessuti-shop.com",
    "stylearc.com",
    "moodfabrics.com",
}

SEED_URLS = [
    "https://www.thecuttingclass.com/",
    "https://blog.pattern-vault.com/",
    "https://vikisews.com/vykrojki/dresses/",
    "https://grasser.ru/vykrojki/",
    "https://sewist.com/",
    "https://bootstrapfashion.com/",
    "https://moodfabrics.com/collections/free-sewing-patterns",
    "https://tessuti-shop.com/collections/patterns",
    "https://stylearc.com/shop/",
    "https://marfy.it/en/product-category/sewing-patterns/",
    "https://thefoldline.com/collections/sewing-patterns",
    "https://lekala.co/catalog",
    "https://korfiati.ru/",
    "https://shkatulka-sew.ru/",
    "https://burdastyle.ru/vikroyki/",
    "https://tianascloset.com/",
    "https://www.etsy.com/",
    "https://www.simplicity.com/",
]