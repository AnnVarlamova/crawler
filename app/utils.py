from __future__ import annotations

import json
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


def read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, data: dict | list) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


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
    candidates = []

    if hasattr(result, "output"):
        candidates.append(getattr(result, "output"))

    if hasattr(result, "structured_output"):
        candidates.append(getattr(result, "structured_output"))

    if hasattr(result, "final_result"):
        candidates.append(getattr(result, "final_result"))

    for candidate in candidates:
        if candidate is None:
            continue

        if callable(candidate):
            try:
                candidate = candidate()
            except TypeError:
                continue
            except Exception:
                continue

        if candidate is None:
            continue

        if hasattr(candidate, "product_urls") and hasattr(candidate, "next_section_urls"):
            return candidate

        if isinstance(candidate, dict):
            return candidate

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


def is_not_forbidden_section_url(url: str) -> bool:
    if not is_allowed_product_url(url):
        return False

    parsed = urlparse(url)
    host = get_site_host(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    query_map = parse_qs(parsed.query)

    full = f"{host}{path}"
    if query:
        full = f"{full}?{query}"

    banned_substrings = [
        "/account",
        "/login",
        "/register",
        "/checkout",
        "/cart",
        "/wishlist",
        "/profile",
        "/auth",
        "/password",
        "/compare",
        "/blog",
        "/article",
        "/articles",
        "/news",
        "/journal",
        "/help",
        "/support",
        "/contacts",
        "/contact",
        "/about",
        "/privacy",
        "/policy",
        "/terms",
        "/delivery",
        "/shipping",
        "/returns",
        "/faq",
        "/lookbook",
        "/magazine",
        "/search",
        "/filter/apply",
    ]

    banned_suffixes = [
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".gif",
        ".svg",
        ".zip",
        ".rar",
        ".7z",
    ]

    banned_tokens = [
        "kids",
        "kid",
        "child",
        "children",
        "baby",
        "babies",
        "teen",
        "teens",
        "junior",
        "newborn",
        "toddler",
        "deti",
        "detyam",
        "detsk",
        "detskaya",
        "detskie",
        "detskij",
        "detskii",
        "dlya-detey",
        "dlya-detej",
        "dlya-detei",
        "dlya-malchikov",
        "dlya-devochek",
        "malchik",
        "malchiki",
        "devoch",
        "devochki",
        "podrost",
        "malyshi",
        "accessory",
        "accessories",
        "aksessuar",
        "aksessuary",
        "аксессуар",
        "bag",
        "bags",
        "sumk",
        "sumka",
        "sumki",
        "backpack",
        "backpacks",
        "ryukzak",
        "рюкзак",
        "hat",
        "hats",
        "cap",
        "caps",
        "shapka",
        "shapki",
        "shlyapa",
        "shlyapy",
        "scarf",
        "scarves",
        "shawl",
        "shawls",
        "sharf",
        "sharfy",
        "palantin",
        "belt",
        "belts",
        "remen",
        "remni",
        "glove",
        "gloves",
        "mittens",
        "perchat",
        "varezh",
        "sock",
        "socks",
        "nosk",
        "noski",
        "kolgot",
        "kolgoto",
        "tights",
        "stocking",
        "stockings",
        "tie",
        "ties",
        "galstuk",
        "wallet",
        "кошелек",
        "koshelek",
        "toy",
        "toys",
        "doll",
        "dolls",
        "pet",
        "pets",
        "home",
        "decor",
        "quilt",
        "quilts",
        "craft",
        "crafts",
        "podushk",
        "odeyal",
        "pled",
    ]

    banned_query_pairs = {
        ("sort", "price"),
        ("order", "desc"),
    }

    if any(part in path for part in banned_substrings):
        return False

    if any(path.endswith(suffix) for suffix in banned_suffixes):
        return False

    if any(token in full for token in banned_tokens):
        return False

    for key, values in query_map.items():
        key_l = key.lower()
        for value in values:
            if (key_l, value.lower()) in banned_query_pairs:
                return False

    return True


def is_allowed_section_url(url: str) -> bool:
    return is_not_forbidden_section_url(url)