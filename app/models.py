from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class ListingLinks(BaseModel):
    listing_urls: list[str] = Field(default_factory=list)


class DiscoveryBatch(BaseModel):
    product_urls: list[str] = Field(default_factory=list)
    next_section_urls: list[str] = Field(default_factory=list)


class ProductImage(BaseModel):
    url: str
    alt: Optional[str] = None


class AgentProductCard(BaseModel):
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

    image_urls: list[str] = Field(default_factory=list)


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


@dataclass
class State:
    discovered_urls: set[str]
    processed_urls: set[str]
    saved_item_ids: set[str]
    downloaded_image_urls: set[str]
    in_progress_urls: set[str]
    reserved_item_ids: set[str]
    pending_section_urls: set[str]
    visited_section_urls: set[str]
    site_error_counts: dict[str, int] = field(default_factory=dict)