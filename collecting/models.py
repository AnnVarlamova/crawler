from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass
class CollectedProduct:
    url: str
    site: str
    category: str
    source_page: str | None = None

    title: str | None = None
    difficulty: int | None = None
    similar_patterns: list[str] = field(default_factory=list)
    description: str | None = None

    images: list[CollectedImage] = field(default_factory=list)

    raw_sections: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)