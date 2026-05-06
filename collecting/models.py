from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkRecord:
    url: str
    site: str
    category: str


@dataclass
class CollectedImage:
    url: str
    local_path: str | None = None
    source: str | None = None


@dataclass
class CollectedProduct:
    url: str
    site: str
    category: str

    title: str | None = None
    similar_patterns: list[str] = field(default_factory=list)
    description: str | None = None

    collection: str | None = None
    season: str | None = None
    style: str | None = None

    images: list[CollectedImage] = field(default_factory=list)