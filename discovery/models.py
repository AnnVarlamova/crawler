from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class State:
    discovered_urls: set[str]
    site_error_counts: dict[str, int] = field(default_factory=dict)