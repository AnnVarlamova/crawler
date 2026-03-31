import argparse
import asyncio
import hashlib
import json
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import requests
from browser_use import Agent, Browser, Controller
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()

SEED_SITES = [
    "https://www.simplicity.com",
    "https://vikisews.com",
    "https://burdastyle.ru",
    "https://helpersew.com",
    "https://grasser.ru",
    "https://shkatulka-sew.ru",
    "https://korfiati.ru",
    "https://www.marfy.it",
]


class ProductUrlItem(BaseModel):
    url: str = Field(description="Absolute URL to a single product/pattern page")


class ProductUrlBatch(BaseModel):
    items: list[ProductUrlItem] = Field(default_factory=list)


class PatternData(BaseModel):
    title: str = ""
    gender: Literal["womenswear", "menswear", "unknown"] = "unknown"
    short_description: str = ""
    details: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    pattern_info: str = ""
    image_urls: list[str] = Field(default_factory=list)


class StopFlag:
    def __init__(self) -> None:
        self.stop_requested = False

    def request_stop(self, *_args) -> None:
        self.stop_requested = True


@dataclass
class CrawlerPaths:
    output_dir: Path
    state_dir: Path

    @property
    def visited_path(self) -> Path:
        return self.state_dir / "visited_urls.json"

    @property
    def downloaded_path(self) -> Path:
        return self.state_dir / "downloaded_items.json"


def load_json_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def save_json_set(path: Path, values: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(values), ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.UNICODE).strip()
    return re.sub(r"[-\s]+", "-", cleaned)[:80] or "pattern"


def stable_item_folder(title: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{slugify(title)}-{digest}"


def normalize_image_url(base_url: str, img_url: str) -> str:
    return urljoin(base_url, img_url)


def is_supported_image(url: str) -> bool:
    low = url.lower()
    return any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"])


def generate_tags(payload: PatternData) -> list[str]:
    corpus = " ".join(
        [payload.title, payload.short_description, payload.pattern_info, " ".join(payload.details), " ".join(payload.season)]
    ).lower()

    vocab = [
        "dress", "shirt", "blouse", "trousers", "pants", "jeans", "skirt", "jacket", "coat", "vest",
        "hoodie", "sweater", "cardigan", "jumpsuit", "shorts", "t-shirt", "top", "suit", "outerwear",
        "casual", "formal", "business", "smart-casual", "sport", "minimalist", "classic", "romantic",
        "streetwear", "oversize", "slim-fit", "relaxed-fit", "tailored", "spring", "summer", "autumn",
        "winter", "all-season", "collar", "v-neck", "crew-neck", "lapel", "buttoned", "zipper", "pleats",
        "darts", "pockets", "ruffles", "belt", "lining", "long-sleeve", "short-sleeve", "sleeveless",
        "midi", "maxi", "mini", "womenswear", "menswear",
    ]

    found = [token for token in vocab if token in corpus]
    if payload.gender in {"womenswear", "menswear"}:
        found.append(payload.gender)
    return sorted(set(found))


async def discover_urls(site_url: str, llm: ChatOpenAI, browser: Browser, limit: int) -> list[str]:
    controller = Controller(output_model=ProductUrlBatch)
    task = (
        f"Open {site_url}. Find pattern/product pages for MEN and WOMEN clothing only. "
        "Do not include kids, accessories, tools, or education pages. "
        f"Return up to {limit} unique absolute URLs as JSON."
    )
    agent = Agent(task=task, llm=llm, controller=controller, browser=browser)
    history = await agent.run()
    raw = history.final_result()
    if not raw:
        return []
    batch = ProductUrlBatch.model_validate_json(raw)
    return [item.url for item in batch.items]


async def extract_pattern(url: str, llm: ChatOpenAI, browser: Browser) -> PatternData:
    controller = Controller(output_model=PatternData)
    task = (
        f"Open {url}. Extract product data from this page only. "
        "Return: title, gender (womenswear|menswear|unknown), short description, garment details, season, "
        "pattern info text, and image URLs of finished garment in multiple angles. "
        "Exclude downloadable pattern files like PDF/DXF and exclude unrelated images."
    )
    agent = Agent(task=task, llm=llm, controller=controller, browser=browser)
    history = await agent.run()
    raw = history.final_result()
    if not raw:
        return PatternData()
    return PatternData.model_validate_json(raw)


def download_images(image_urls: list[str], base_url: str, item_dir: Path, timeout: int = 30) -> list[str]:
    downloaded_files: list[str] = []
    for i, raw_url in enumerate(image_urls, start=1):
        url = normalize_image_url(base_url, raw_url)
        if not is_supported_image(url):
            continue
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
        except Exception:
            continue
        ext = Path(urlparse(url).path).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        filename = f"image_{i:02d}{ext}"
        path = item_dir / filename
        path.write_bytes(response.content)
        downloaded_files.append(filename)
    return downloaded_files


def is_adult_clothing(payload: PatternData) -> bool:
    text = " ".join([payload.title, payload.short_description, payload.pattern_info]).lower()
    banned = ["kid", "child", "children", "baby", "accessory", "bag", "hat", "toy"]
    if any(word in text for word in banned):
        return False
    return payload.gender in {"womenswear", "menswear"} or any(x in text for x in ["women", "men", "жен", "муж"])


async def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    state_dir = Path(args.state_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    paths = CrawlerPaths(output_dir=output_dir, state_dir=state_dir)
    visited_urls = load_json_set(paths.visited_path)
    downloaded_urls = load_json_set(paths.downloaded_path)

    stop_flag = StopFlag()
    signal.signal(signal.SIGINT, stop_flag.request_stop)
    signal.signal(signal.SIGTERM, stop_flag.request_stop)

    llm = ChatOpenAI(model=args.model, temperature=0)
    browser = Browser()

    processed = 0
    try:
        for site in SEED_SITES:
            if stop_flag.stop_requested:
                break

            candidate_urls = await discover_urls(site, llm=llm, browser=browser, limit=args.per_site_limit)
            for url in candidate_urls:
                if stop_flag.stop_requested:
                    break
                if url in visited_urls or url in downloaded_urls:
                    continue

                visited_urls.add(url)
                save_json_set(paths.visited_path, visited_urls)

                payload = await extract_pattern(url, llm=llm, browser=browser)
                if not payload.title or not is_adult_clothing(payload):
                    continue

                folder_name = stable_item_folder(payload.title, url)
                item_dir = output_dir / folder_name
                if item_dir.exists() and (item_dir / "item.json").exists():
                    downloaded_urls.add(url)
                    save_json_set(paths.downloaded_path, downloaded_urls)
                    continue

                item_dir.mkdir(parents=True, exist_ok=True)
                local_images = download_images(payload.image_urls, url, item_dir)

                item_json = {
                    "title": payload.title,
                    "source_url": url,
                    "domain": urlparse(url).netloc,
                    "gender": payload.gender,
                    "short_description": payload.short_description,
                    "details": payload.details,
                    "season": payload.season,
                    "pattern_info": payload.pattern_info,
                    "generated_tags": generate_tags(payload),
                    "images": local_images,
                }
                (item_dir / "item.json").write_text(json.dumps(item_json, ensure_ascii=False, indent=2), encoding="utf-8")

                downloaded_urls.add(url)
                save_json_set(paths.downloaded_path, downloaded_urls)
                processed += 1

                if args.max_items and processed >= args.max_items:
                    stop_flag.stop_requested = True
                    break
    finally:
        await browser.close()
        save_json_set(paths.visited_path, visited_urls)
        save_json_set(paths.downloaded_path, downloaded_urls)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl sewing pattern websites and save garment photos + metadata.")
    parser.add_argument("--output-dir", default="output", help="Directory where per-item folders will be created")
    parser.add_argument("--state-dir", default="state", help="Directory where resumable crawl state is stored")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model name")
    parser.add_argument("--per-site-limit", type=int, default=30, help="How many candidate product pages to collect per site")
    parser.add_argument("--max-items", type=int, default=0, help="Stop after N saved items (0 = no limit)")
    parser.add_argument("--headless", action="store_true", help="Compatibility flag (some browser-use versions ignore this)")
    return parser


if __name__ == "__main__":
    cli_args = build_parser().parse_args()
    asyncio.run(run(cli_args))
