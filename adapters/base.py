from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path

from utils import text_norm, unique_keep_order
from filters import PATTERN_HINTS


class BaseAdapter:
    name = "generic"

    def match(self, domain: str) -> bool:
        return False

    def extract_title_meta(self, soup: BeautifulSoup) -> tuple[str, str]:
        title = text_norm(soup.title.get_text(" ", strip=True)) if soup.title else ""
        meta = ""
        tag = soup.select_one('meta[name="description"]')
        if tag and tag.get("content"):
            meta = text_norm(tag["content"])
        return title, meta

    def extract_h1(self, soup: BeautifulSoup) -> list[str]:
        return unique_keep_order(
            text_norm(x.get_text(" ", strip=True))
            for x in soup.select("h1")
        )

    def extract_breadcrumbs(self, soup: BeautifulSoup) -> list[str]:
        selectors = [
            '[aria-label="breadcrumb"] a',
            '.breadcrumb a',
            '.breadcrumbs a',
            '.woocommerce-breadcrumb a',
            'nav.breadcrumb a',
            'ol.breadcrumb li',
        ]
        out = []
        for sel in selectors:
            for el in soup.select(sel):
                t = text_norm(el.get_text(" ", strip=True))
                if t:
                    out.append(t)
        return unique_keep_order(out)

    def extract_tags(self, soup: BeautifulSoup) -> list[str]:
        out = []
        meta_kw = soup.select_one('meta[name="keywords"]')
        if meta_kw and meta_kw.get("content"):
            out.extend([text_norm(x) for x in meta_kw["content"].split(",") if text_norm(x)])

        selectors = [
            '.tags a', '.tag a', '.product-tags a', '.posted_in a',
            '.entry-meta a[rel="tag"]', '.cat-links a', '.product_meta a',
            '.filters a', '.collection-tags a'
        ]
        for sel in selectors:
            for el in soup.select(sel):
                t = text_norm(el.get_text(" ", strip=True))
                if t:
                    out.append(t)
        return unique_keep_order(out)

    def extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
            tag.decompose()

        blocks = []
        for node in soup.select("main, article, .product, .entry-content, .post-content, .content, .product__description, .rte"):
            txt = text_norm(node.get_text("\n", strip=True))
            if len(txt) > 120:
                blocks.append(txt)

        if not blocks and soup.body:
            body = text_norm(soup.body.get_text("\n", strip=True))
            if body:
                blocks.append(body)

        return "\n\n".join(unique_keep_order(blocks))

    def extract_images(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        out = []
        for img in soup.select("img"):
            for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
                val = img.get(attr)
                if val:
                    out.append(urljoin(base_url, val))
            srcset = img.get("srcset")
            if srcset:
                parts = [x.strip().split(" ")[0] for x in srcset.split(",")]
                out.extend(urljoin(base_url, p) for p in parts if p)

        for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
            if meta.get("content"):
                out.append(urljoin(base_url, meta["content"]))

        return unique_keep_order(out)

    def extract_file_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        out = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            full = urljoin(base_url, href)
            low = full.lower()
            text = text_norm(a.get_text(" ", strip=True)).lower()
            ext = Path(urlparse(full).path).suffix.lower()

            if ext in {".pdf", ".zip", ".rar", ".7z", ".svg"}:
                out.append(full)
                continue

            if any(h in low or h in text for h in PATTERN_HINTS):
                out.append(full)
        return unique_keep_order(out)

    def extract_tech_drawings(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        out = []
        for img in soup.select("img"):
            alt = text_norm(img.get("alt", "")).lower()
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            if any(k in alt for k in ["technical", "tech drawing", "line drawing", "технический", "схема", "техрисунок"]):
                out.append(urljoin(base_url, src))
        return unique_keep_order(out)

    def extract_custom_fields(self, soup: BeautifulSoup, base_url: str) -> dict:
        return {
            "designer": "",
            "collection": "",
            "season": "",
            "year": "",
            "difficulty": "",
            "product_code": "",
            "price_text": "",
            "pattern_format": [],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": [],
        }

    def extract_links(self, soup: BeautifulSoup, base_url: str, domain: str) -> list[str]:
        out = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            full = urljoin(base_url, href).split("#")[0].rstrip("/")
            if full.startswith("http") and urlparse(full).netloc.lower() == domain:
                out.append(full)
        return unique_keep_order(out)