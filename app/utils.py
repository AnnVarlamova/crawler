from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import SITE_URLS


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


def read_json_string_list(path: Path, key: str = "urls") -> list[str]:
    if not path.exists():
        return []

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        values = obj.get(key, [])
        if isinstance(values, list):
            return [x for x in values if isinstance(x, str) and x]
    except Exception:
        return []

    return []


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


def get_site_host(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def get_structured_output(result):
    if hasattr(result, "output") and result.output is not None:
        return result.output
    if hasattr(result, "structured_output") and result.structured_output is not None:
        return result.structured_output
    if hasattr(result, "final_result") and result.final_result is not None:
        return result.final_result
    return None


def is_allowed_product_url(url: str) -> bool:
    host = get_site_host(url)
    allowed_hosts = {
        "simplicity.com",
        "vikisews.com",
        "burdastyle.ru",
        "helpersew.com",
        "grasser.ru",
        "shkatulka-sew.ru",
        "marfy.it",
        "blog.pattern-vault.com",
        "pattern-vault.com",
    }
    return any(host == d or host.endswith("." + d) for d in allowed_hosts)


def is_allowed_section_url(url: str) -> bool:
    if not is_allowed_product_url(url):
        return False

    parsed = urlparse(url)
    host = get_site_host(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if "pattern-vault.com" in host:
        return False

    banned_substrings = [
        "/account", "/login", "/register", "/checkout", "/cart", "/wishlist",
        "/blog", "/article", "/news", "/journal", "/help", "/support",
        "/contacts", "/contact", "/about", "/privacy", "/policy", "/terms",
        "/delivery", "/shipping", "/returns", "/faq",
        "/search", "/lookbook", "/magazine",
    ]
    if any(part in path for part in banned_substrings):
        return False

    banned_suffixes = [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".zip"]
    if any(path.endswith(suffix) for suffix in banned_suffixes):
        return False

    useful_path_tokens = [
        "catalog", "category", "shop", "store", "patterns", "pattern",
        "women", "woman", "men", "man",
        "dress", "dresses", "skirt", "skirts", "blouse", "blouses",
        "shirt", "shirts", "top", "tops", "jacket", "jackets",
        "coat", "coats", "trousers", "pants", "jeans", "shorts",
        "vest", "sweater", "cardigan", "jumpsuit",
        "odezhda", "platya", "yubki", "bryuki", "bluzki",
        "page",
    ]
    if path in {"", "/"}:
        return True

    if any(token in path for token in useful_path_tokens):
        return True

    if any(k.lower() in {"page", "p", "paged"} for k in query):
        return True

    return False