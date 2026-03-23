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