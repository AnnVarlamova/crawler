import hashlib
import re
from pathlib import Path
from urllib.parse import urldefrag, urlparse


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
FILE_EXTS = {".pdf", ".zip", ".rar", ".7z", ".svg"}


def normalize_url(url: str) -> str:
    return urldefrag(url)[0].rstrip("/").strip()


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()

def domain_key(domain: str) -> str:
    domain = domain.lower().strip()
    return domain[4:] if domain.startswith("www.") else domain


def text_norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def text_low(s: str) -> str:
    return text_norm(s).lower()


def unique_keep_order(items):
    out = []
    seen = set()
    for x in items:
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def safe_slug(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w\- ]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text[:max_len] or "untitled"


def path_parts(url: str) -> list[str]:
    return [p for p in urlparse(url).path.split("/") if p]

def canonical_pattern_signature(
    domain: str,
    final_url: str,
    title: str = "",
    product_code: str = "",
    h1: list[str] | None = None,
) -> str:
    h1 = h1 or []
    core_title = text_low(title or (h1[0] if h1 else ""))
    core_domain = domain_key(domain)
    core_url = normalize_url(final_url)

    if product_code:
        base = f"{core_domain}|code|{text_low(product_code)}"
    elif core_title:
        base = f"{core_domain}|title|{core_title}"
    else:
        base = f"{core_domain}|url|{core_url}"

    return hashlib.sha1(base.encode("utf-8")).hexdigest()