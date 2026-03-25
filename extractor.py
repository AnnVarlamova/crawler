import time
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import asdict

import httpx
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT_SEC, RAW_HTML_DIR, TEXT_DIR, SITES_DIR
from filters import classify_page
from jsonld import extract_json_ld, find_product_schema, extract_images_from_product_schema, extract_price_from_product_schema
from models import ParsedPage
from site_registry import get_adapter
from storage import save_text, save_json
from utils import (
    unique_keep_order,
    url_hash,
    safe_slug,
    path_parts,
    canonical_pattern_signature,
    domain_key,
)


async def download_binary(url: str, dest: Path, client: httpx.AsyncClient) -> str | None:
    try:
        if dest.exists() and dest.stat().st_size > 0:
            return str(dest)
        r = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT_SEC)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return str(dest)
    except Exception:
        return None


def categories_from_all(url: str, breadcrumbs: list[str], tags: list[str]) -> list[str]:
    return unique_keep_order(breadcrumbs + tags + path_parts(url))


async def parse_page(
    original_url: str,
    final_url: str,
    html: str,
    download_images=True,
    download_files=True,
):
    domain = urlparse(final_url).netloc.lower()
    adapter = get_adapter(domain)
    soup = BeautifulSoup(html, "lxml")

    title, meta_description = adapter.extract_title_meta(soup)
    h1 = adapter.extract_h1(soup)
    breadcrumbs = adapter.extract_breadcrumbs(soup)
    tags = adapter.extract_tags(soup)
    text = adapter.extract_text(soup)

    json_ld_nodes = extract_json_ld(soup)
    product_schema = find_product_schema(json_ld_nodes)

    custom = adapter.extract_custom_fields(soup, final_url)

    image_urls = adapter.extract_images(soup, final_url)
    image_urls += extract_images_from_product_schema(product_schema)

    tech_drawing_urls = adapter.extract_tech_drawings(soup, final_url)
    file_urls = adapter.extract_file_links(soup, final_url)
    discovered_links = adapter.extract_links(soup, final_url, domain)

    price_text = custom.get("price_text") or extract_price_from_product_schema(product_schema)
    has_price = bool(price_text)
    has_product_schema = product_schema is not None

    categories = categories_from_all(final_url, breadcrumbs, tags)

    cls = classify_page(
        title=title,
        text=text,
        tags=tags,
        breadcrumbs=breadcrumbs,
        url=final_url,
        has_price=has_price,
        has_product_schema=has_product_schema,
        adapter_name=adapter.name,
        image_count=len(image_urls),
        file_count=len(file_urls),
    )

    uid = url_hash(final_url)
    slug = safe_slug(title or (h1[0] if h1 else uid))

    html_path = RAW_HTML_DIR / f"{domain_key(domain)}__{slug}__{uid}.html"
    text_path = TEXT_DIR / f"{domain_key(domain)}__{slug}__{uid}.txt"
    await save_text(html_path, html)
    await save_text(text_path, text)

    signature = canonical_pattern_signature(
        domain=domain,
        final_url=final_url,
        title=title,
        product_code=custom.get("product_code", ""),
        h1=h1,
    )
    pattern_dir = SITES_DIR / domain_key(domain) / signature
    pattern_html_path = pattern_dir / "source.html"
    pattern_text_path = pattern_dir / "description.txt"
    await save_text(pattern_html_path, html)
    await save_text(pattern_text_path, text)

    page = ParsedPage(
        url=original_url,
        final_url=final_url,
        domain=domain,
        title=title,
        meta_description=meta_description,
        h1=h1,
        breadcrumbs=breadcrumbs,
        tags=tags,
        categories=categories,
        text=text,
        page_type=cls["page_type"],
        entity_type=cls["entity_type"],
        source_adapter=adapter.name,
        garment_type=cls["garment_type"],
        gender=cls["gender"],
        style_keywords=cls["style_keywords"],
        is_child_related=cls["is_child_related"],
        is_accessory_related=cls["is_accessory_related"],
        relevant=cls["relevant"],
        download=cls["download"],
        designer=custom["designer"],
        collection=custom["collection"],
        season=custom["season"],
        year=custom["year"],
        difficulty=custom["difficulty"],
        product_code=custom["product_code"],
        price_text=price_text,
        pattern_format=custom["pattern_format"],
        size_info=custom["size_info"],
        fabric_recommendations=custom["fabric_recommendations"],
        construction_notes=custom["construction_notes"] + [f"signature:{signature}"],
        json_ld_raw=json_ld_nodes,
        html_path=str(pattern_html_path),
        text_path=str(pattern_text_path),
        discovered_links=discovered_links,
        timestamp_utc=time.time(),
    )

    page.assets.image_urls = unique_keep_order(image_urls)
    page.assets.tech_drawing_urls = unique_keep_order(tech_drawing_urls)
    page.assets.file_urls = unique_keep_order(file_urls)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 garment research crawler"},
        timeout=REQUEST_TIMEOUT_SEC,
        follow_redirects=True,
    ) as client:
        if page.download and download_images:
            for idx, img_url in enumerate(page.assets.image_urls[:40]):
                ext = Path(urlparse(img_url).path).suffix.lower() or ".jpg"
                dest = pattern_dir / "images" / f"{idx:03d}{ext}"
                saved = await download_binary(img_url, dest, client)
                if saved:
                    page.assets.downloaded_images.append(saved)

        if page.download and download_files:
            for idx, file_url in enumerate(page.assets.file_urls[:20]):
                ext = Path(urlparse(file_url).path).suffix.lower() or ".bin"
                dest = pattern_dir / "files" / f"{idx:03d}{ext}"
                saved = await download_binary(file_url, dest, client)
                if saved:
                    page.assets.downloaded_files.append(saved)

    await save_json(pattern_dir / "meta.json", asdict(page))

    return page
