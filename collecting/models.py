from __future__ import annotations

from dataclasses import dataclass, field


IMAGE_PHOTO = "photo"
IMAGE_MANNEQUIN = "mannequin"
IMAGE_TECHNICAL = "technical"


@dataclass(frozen=True)
class LinkRecord:
    url: str
    site: str
    category: str
    source_page: str | None = None


@dataclass
class CollectedImage:
    url: str
    alt: str | None = None
    local_path: str | None = None
    source: str | None = None
    image_type: str | None = None


@dataclass
class CollectedProduct:
    url: str
    site: str
    category: str
    source_page: str | None = None

    title: str | None = None
    description: str | None = None

    similar_patterns: list[str] = field(default_factory=list)

    collection: str | None = None
    season: str | None = None
    style: str | None = None

    # Это кандидаты на скачивание.
    # В metadata.json они больше не попадут.
    images: list[CollectedImage] = field(default_factory=list)
    review_images: list[CollectedImage] = field(default_factory=list)