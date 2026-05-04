from __future__ import annotations

from abc import ABC, abstractmethod

from playwright.async_api import Page

from collecting.models import LinkRecord, CollectedProduct


class CollectingHandler(ABC):
    site: str

    @abstractmethod
    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        raise NotImplementedError