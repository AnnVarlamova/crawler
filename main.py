from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import httpx


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


from dotenv import load_dotenv
from pydantic import BaseModel, Field

from browser_use import Agent, Browser, ChatOpenAI
import tempfile
import shutil
import atexit


# =========================
# CONFIG
# =========================

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
ITEMS_DIR = DATA_DIR / "items"

DISCOVERED_FILE = STATE_DIR / "discovered_urls.jsonl"
PROCESSED_FILE = STATE_DIR / "processed_urls.jsonl"
SAVED_ITEMS_FILE = STATE_DIR / "saved_items.jsonl"
DOWNLOADED_IMAGES_FILE = STATE_DIR / "downloaded_images.jsonl"
ERRORS_FILE = STATE_DIR / "errors.jsonl"
IN_PROGRESS_FILE = STATE_DIR / "in_progress_urls.jsonl"

DEFAULT_LIMIT_PER_SITE = 3
DEFAULT_MAX_IMAGES = 8
DEFAULT_CONCURRENCY = 1

STOP_REQUESTED = False


# =========================
# SIGNALS
# =========================

def _handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("\n[!] Stop requested. Waiting for current tasks to finish safely...", flush=True)


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


# =========================
# MODELS
# =========================

class ListingLinks(BaseModel):
    listing_urls: list[str] = Field(default_factory=list)


class ProductImage(BaseModel):
    url: str
    alt: Optional[str] = None


class ProductCard(BaseModel):
    source_site: str = ""
    product_url: str = ""
    title: str

    gender: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None

    season: list[str] = Field(default_factory=list)
    garment_elements: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)

    short_description: str = ""
    pattern_info: str = ""
    raw_text: str = ""

    adult_only: bool = True
    is_accessory: bool = False
    is_child_item: bool = False

    images: list[ProductImage] = Field(default_factory=list)


class GeneratedTags(BaseModel):
    tags: list[str] = Field(default_factory=list)


# =========================
# TAGS
# =========================

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


# =========================
# UTILS
# =========================

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, row: dict) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl_keyset(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    result = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                val = obj.get(key)
                if isinstance(val, str) and val:
                    result.add(val)
            except Exception:
                continue
    return result


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_tag(tag: str) -> str:
    return re.sub(r"[-\s]+", "-", tag.strip().lower())


def merge_tags(*groups: list[str]) -> list[str]:
    seen = set()
    out = []
    for group in groups:
        for tag in group:
            t = normalize_tag(tag)
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def slugify(text: str, max_len: int = 120) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text, flags=re.UNICODE).strip("-")
    return text[:max_len] or "item"


def stable_item_id(url: str, title: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return f"{slugify(host)}__{slugify(title or url)}"


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def is_probably_image_url(url: str) -> bool:
    u = url.lower()
    return any(ext in u for ext in [".jpg", ".jpeg", ".png", ".webp", ".avif"])


def filename_from_url(url: str, fallback: str) -> str:
    name = Path(urlparse(url).path).name or fallback
    if "." not in name:
        name += ".jpg"
    return name[:180]


def detect_site_key(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    for key, base in SITE_URLS.items():
        base_host = urlparse(base).netloc.lower().replace("www.", "")
        if base_host in host:
            return key
    return host


def get_structured_output(result):
    if hasattr(result, "output") and result.output is not None:
        return result.output
    if hasattr(result, "structured_output") and result.structured_output is not None:
        return result.structured_output
    if hasattr(result, "final_result") and result.final_result is not None:
        return result.final_result
    return None


# =========================
# STATE
# =========================

@dataclass
class State:
    discovered_urls: set[str]
    processed_urls: set[str]
    saved_item_ids: set[str]
    downloaded_image_urls: set[str]
    in_progress_urls: set[str]


def load_state() -> State:
    ensure_dir(STATE_DIR)
    return State(
        discovered_urls=read_jsonl_keyset(DISCOVERED_FILE, "url"),
        processed_urls=read_jsonl_keyset(PROCESSED_FILE, "url"),
        saved_item_ids=read_jsonl_keyset(SAVED_ITEMS_FILE, "item_id"),
        downloaded_image_urls=read_jsonl_keyset(DOWNLOADED_IMAGES_FILE, "url"),
        in_progress_urls=read_jsonl_keyset(IN_PROGRESS_FILE, "url"),
    )


# =========================
# BROWSER-USE
# =========================

def build_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env")

    return ChatOpenAI(
        model="gpt-4.1",
        api_key=api_key,
    )


_TEMP_BROWSER_DIRS: list[str] = []


def _cleanup_temp_browser_dirs() -> None:
    for d in _TEMP_BROWSER_DIRS:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


atexit.register(_cleanup_temp_browser_dirs)


def build_browser() -> Browser:
    profile_dir = tempfile.mkdtemp(prefix="browseruse_profile_")
    _TEMP_BROWSER_DIRS.append(profile_dir)

    return Browser(
        headless=True,
        channel="chromium",
        user_data_dir=profile_dir,
        enable_default_extensions=False,
    )

def is_allowed_product_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().replace("www.", "")
    allowed_hosts = {
        "simplicity.com",
        "vikisews.com",
        "burdastyle.ru",
        "helpersew.com",
        "grasser.ru",
        "shkatulka-sew.ru",
        "korfiati.ru",
        "marfy.it",
    }
    return any(host == d or host.endswith("." + d) for d in allowed_hosts)

def make_discovery_prompt(start_url: str, limit: int) -> str:
    return f"""
Open this site: {start_url}

Your goal:
Find individual product pages for adult sewing/clothing patterns.

Important constraints:
- Work ONLY inside the allowed domain.
- Return ONLY concrete product/item pages, not category pages.
- Focus on WOMEN'S and MEN'S clothing.
- Exclude:
  - children / kids / baby / teen
  - accessories
  - bags, hats, scarves, belts, gloves, socks
  - toys, dolls, pets
  - home decor, quilts, crafts
  - articles/blog/editorial pages unless they clearly correspond to one concrete garment pattern page
- Prefer pages with finished garment photos and product/pattern description.
- Return up to {limit} unique absolute URLs.

Output only the structured result.
""".strip()


def make_product_prompt(product_url: str) -> str:
    return f"""
Open this exact product page: {product_url}

Extract structured information for this item.

Rules:
- This should be an adult clothing item or clothing pattern page.
- Exclude children items and accessories.
- product_url must be exactly "{product_url}".
- source_site should be the site key inferred from the domain.
- Collect URLs of finished garment photos from different angles if available.
- Prefer photos of the garment, not technical drawings only.
- Put useful readable page text into raw_text.
- Leave unknown fields empty rather than inventing data.

Output only the structured result.
""".strip()


def make_tags_prompt(card: ProductCard) -> str:
    payload = json.dumps(card.model_dump(mode="json"), ensure_ascii=False, indent=2)
    vocab = ", ".join(BASE_TAGS)
    return f"""
Generate tags for this clothing item.

Allowed tag vocabulary:
{vocab}

Input item:
{payload}

Rules:
- Return 5 to 20 tags.
- lowercase
- hyphen-separated
- no duplicates
- prioritize garment type, fit, details, gender, season, style
- use vocabulary above whenever possible
- if a necessary tag is not in vocabulary, you may add a short normalized tag

Output only the structured result.
""".strip()


async def discover_urls_for_site(start_url: str, limit: int) -> list[str]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_discovery_prompt(start_url, limit),
            llm=build_llm(),
            browser=browser,
            use_vision=True,
            output_model_schema=ListingLinks,
            max_failures=3,
        )
        result = await agent.run()
        data = get_structured_output(result)
        if not data:
            return []
        urls = dedupe_preserve_order(data.listing_urls)
        urls = [u for u in urls if is_allowed_product_url(u)]
        return urls[:limit]
    finally:
        maybe_close = getattr(browser, "close", None)
        if callable(maybe_close):
            maybe = maybe_close()
            if asyncio.iscoroutine(maybe):
                await maybe


async def extract_product(product_url: str) -> Optional[ProductCard]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_product_prompt(product_url),
            llm=build_llm(),
            browser=browser,
            use_vision=True,
            output_model_schema=ProductCard,
            max_failures=3,
        )
        result = await agent.run()
        return get_structured_output(result)
    finally:
        maybe_close = getattr(browser, "close", None)
        if callable(maybe_close):
            maybe = maybe_close()
            if asyncio.iscoroutine(maybe):
                await maybe


async def generate_tags(card: ProductCard) -> list[str]:
    browser = build_browser()
    try:
        agent = Agent(
            task=make_tags_prompt(card),
            llm=build_llm(),
            browser=browser,
            use_vision=False,
            output_model_schema=GeneratedTags,
            max_failures=2,
        )
        result = await agent.run()
        data = get_structured_output(result)
        if not data:
            return []
        return dedupe_preserve_order(data.tags)
    finally:
        maybe_close = getattr(browser, "close", None)
        if callable(maybe_close):
            maybe = maybe_close()
            if asyncio.iscoroutine(maybe):
                await maybe


# =========================
# FILTERING
# =========================

def is_valid_product(card: ProductCard) -> bool:
    if card.is_accessory or card.is_child_item:
        return False

    text = " ".join([
        card.title or "",
        card.category or "",
        card.subcategory or "",
        card.short_description or "",
        card.pattern_info or "",
        card.raw_text or "",
    ]).lower()

    banned = [
        "kids", "child", "children", "baby", "teen",
        "аксессуар", "accessory", "bag", "hat", "cap", "scarf",
        "glove", "sock", "toy", "doll", "pet",
        "сумк", "шапк", "шарф", "перчат",
    ]
    if any(x in text for x in banned):
        return False

    positive = [
        "dress", "blouse", "shirt", "top", "skirt",
        "trousers", "pants", "jeans", "shorts",
        "jacket", "blazer", "coat", "vest", "hoodie",
        "sweater", "cardigan", "jumpsuit", "bodysuit",
        "плать", "блуз", "рубаш", "топ", "юбк",
        "брюк", "брюки", "джинс", "шорт", "жакет",
        "пиджак", "пальто", "жилет", "худи", "свитер",
        "кардиган", "комбинез",
    ]
    if not any(x in text for x in positive):
        return False

    if not card.images:
        return False

    return True


# =========================
# DOWNLOADS
# =========================

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


# =========================
# SAVE ITEM
# =========================

def save_item(card: ProductCard, tags: list[str], downloaded_images: list[str]) -> str:
    item_id = stable_item_id(card.product_url, card.title)
    item_dir = ITEMS_DIR / item_id
    ensure_dir(item_dir)

    metadata = {
        "item_id": item_id,
        "source_site": card.source_site,
        "product_url": card.product_url,
        "title": card.title,
        "gender": card.gender,
        "category": card.category,
        "subcategory": card.subcategory,
        "season": card.season,
        "garment_elements": card.garment_elements,
        "materials": card.materials,
        "short_description": card.short_description,
        "pattern_info": card.pattern_info,
        "adult_only": card.adult_only,
        "is_accessory": card.is_accessory,
        "is_child_item": card.is_child_item,
        "image_source_urls": [img.url for img in card.images],
        "downloaded_images": downloaded_images,
    }

    write_json(item_dir / "metadata.json", metadata)
    write_json(item_dir / "tags.json", {"tags": tags})
    (item_dir / "raw_text.txt").write_text(card.raw_text or "", encoding="utf-8")

    return item_id


# =========================
# PIPELINE
# =========================

async def discover_phase(state: State, limit_per_site: int) -> None:
    for site_key, start_url in SITE_URLS.items():
        if STOP_REQUESTED:
            return

        print(f"[DISCOVER] {site_key} -> {start_url}", flush=True)
        try:
            urls = await discover_urls_for_site(start_url, limit_per_site)
            added = 0
            for url in urls:
                if url not in state.discovered_urls:
                    state.discovered_urls.add(url)
                    append_jsonl(DISCOVERED_FILE, {"url": url, "site": site_key})
                    added += 1
            print(f"[DISCOVER] {site_key}: found={len(urls)} new={added}", flush=True)
        except Exception as e:
            append_jsonl(ERRORS_FILE, {"phase": "discover", "site": site_key, "error": str(e)})
            print(f"[DISCOVER] {site_key}: error={e}", flush=True)


async def process_one_url(url: str, state: State, max_images: int, lock: asyncio.Lock) -> None:
    if STOP_REQUESTED:
        return

    # Reserve URL first so another concurrent worker does not take it.
    async with lock:
        if url in state.processed_urls or url in state.in_progress_urls:
            return
        state.in_progress_urls.add(url)
        append_jsonl(IN_PROGRESS_FILE, {"url": url})

    try:
        print(f"[PROCESS] {url}", flush=True)

        card = await extract_product(url)
        if not card:
            append_jsonl(ERRORS_FILE, {"phase": "extract", "url": url, "error": "no structured output"})
            return

        if not card.source_site:
            card.source_site = detect_site_key(url)
        if not card.product_url:
            card.product_url = url

        item_id = stable_item_id(card.product_url, card.title)

        async with lock:
            if item_id in state.saved_item_ids:
                state.processed_urls.add(url)
                append_jsonl(PROCESSED_FILE, {"url": url, "status": "already_saved"})
                return

        if not is_valid_product(card):
            async with lock:
                state.processed_urls.add(url)
                append_jsonl(PROCESSED_FILE, {"url": url, "status": "filtered_out"})
            return

        item_dir = ITEMS_DIR / item_id
        downloaded = await download_images(card, item_dir, state, max_images=max_images)
        tags = merge_tags(await generate_tags(card))
        saved_item_id = save_item(card, tags, downloaded)

        async with lock:
            state.saved_item_ids.add(saved_item_id)
            append_jsonl(SAVED_ITEMS_FILE, {"item_id": saved_item_id, "url": url})
            state.processed_urls.add(url)
            append_jsonl(PROCESSED_FILE, {"url": url, "status": "saved"})
            print(f"[SAVED] {saved_item_id}", flush=True)

    except Exception as e:
        append_jsonl(ERRORS_FILE, {"phase": "process", "url": url, "error": str(e)})
        print(f"[ERROR] {url} -> {e}", flush=True)

    finally:
        async with lock:
            state.in_progress_urls.discard(url)


async def process_phase_concurrent(state: State, max_images: int, concurrency: int) -> None:
    queue = [
        url for url in state.discovered_urls
        if url not in state.processed_urls and url not in state.in_progress_urls
    ]
    print(f"[PROCESS] queued={len(queue)} concurrency={concurrency}", flush=True)

    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def runner(url: str):
        async with semaphore:
            if STOP_REQUESTED:
                return
            await process_one_url(url, state, max_images, lock)

    tasks = []
    for url in queue:
        if STOP_REQUESTED:
            break
        tasks.append(asyncio.create_task(runner(url)))

    if not tasks:
        return

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass


async def async_main():
    ensure_dir(DATA_DIR)
    ensure_dir(STATE_DIR)
    ensure_dir(ITEMS_DIR)

    limit_per_site = DEFAULT_LIMIT_PER_SITE
    max_images = DEFAULT_MAX_IMAGES
    concurrency = DEFAULT_CONCURRENCY

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--limit-per-site" and i + 1 < len(argv):
            limit_per_site = int(argv[i + 1])
            i += 2
        elif argv[i] == "--max-images" and i + 1 < len(argv):
            max_images = int(argv[i + 1])
            i += 2
        elif argv[i] == "--concurrency" and i + 1 < len(argv):
            concurrency = int(argv[i + 1])
            i += 2
        else:
            i += 1

    state = load_state()

    print("[START] Discovery phase", flush=True)
    await discover_phase(state, limit_per_site=limit_per_site)

    if STOP_REQUESTED:
        print("[STOP] Interrupted after discovery.", flush=True)
        return

    print("[START] Concurrent process phase", flush=True)
    await process_phase_concurrent(state, max_images=max_images, concurrency=concurrency)

    print("[DONE]", flush=True)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()