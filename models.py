from dataclasses import dataclass, field


@dataclass
class PageAssets:
    image_urls: list[str] = field(default_factory=list)
    tech_drawing_urls: list[str] = field(default_factory=list)
    file_urls: list[str] = field(default_factory=list)
    downloaded_images: list[str] = field(default_factory=list)
    downloaded_files: list[str] = field(default_factory=list)


@dataclass
class ParsedPage:
    url: str
    final_url: str
    domain: str

    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)

    breadcrumbs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    text: str = ""
    page_type: str = ""          # product/category/article/collection/generator
    entity_type: str = ""        # garment/pattern/analysis/collection_entry
    source_adapter: str = "generic"

    garment_type: list[str] = field(default_factory=list)
    gender: list[str] = field(default_factory=list)
    style_keywords: list[str] = field(default_factory=list)

    is_child_related: bool = False
    is_accessory_related: bool = False
    keep: bool = False

    designer: str = ""
    collection: str = ""
    season: str = ""
    year: str = ""
    difficulty: str = ""
    product_code: str = ""
    price_text: str = ""
    pattern_format: list[str] = field(default_factory=list)
    size_info: list[str] = field(default_factory=list)
    fabric_recommendations: list[str] = field(default_factory=list)
    construction_notes: list[str] = field(default_factory=list)

    json_ld_raw: list[dict] = field(default_factory=list)

    html_path: str = ""
    text_path: str = ""

    assets: PageAssets = field(default_factory=PageAssets)
    discovered_links: list[str] = field(default_factory=list)

    timestamp_utc: float = 0.0