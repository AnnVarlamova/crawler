from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class DiscoveryBatch(BaseModel):
    product_urls: list[str] = Field(default_factory=list)
    next_section_urls: list[str] = Field(default_factory=list)


class SectionTask(BaseModel):
    url: str
    parent_url: Optional[str] = None


@dataclass
class State:
    discovered_urls: set[str]
    pending_sections: dict[str, Optional[str]]
    visited_section_urls: set[str]
    section_attempts: dict[str, int] = field(default_factory=dict)
    site_error_counts: dict[str, int] = field(default_factory=dict)