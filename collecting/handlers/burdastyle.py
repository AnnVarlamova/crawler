from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import LinkRecord, CollectedProduct, CollectedImage

logger = logging.getLogger("collecting")


class BurdaStyleCollectingHandler(CollectingHandler):
    site = "burdastyle"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect BurdaStyle product: %s", record.url)

        await page.wait_for_selector("h1.pattern-stats__title", timeout=15000)

        title = await self._text_or_none(page, "h1.pattern-stats__title")
        difficulty = await self._difficulty(page)
        similar_patterns = await self._similar_patterns(page)
        raw_sections = await self._tech_details(page)
        description = raw_sections.get("Описание")
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed BurdaStyle product title=%r difficulty=%r tags=%s images=%s url=%s",
            title,
            difficulty,
            len(similar_patterns),
            len(images),
            record.url,
        )

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=difficulty,
            similar_patterns=similar_patterns,
            description=description,
            images=images,
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
            },
        )

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        text = await loc.first.inner_text()
        text = self._clean_text(text)

        return text or None

    async def _difficulty(self, page: Page) -> int | None:
        """
        На Burda сложность выглядит примерно так:

        <div class="difficulty-rating ...">
          <ul class="clearfix">
            <li class="icon-difficulty active">1</li>
            <li class="icon-difficulty">2</li>
            ...
          </ul>
        </div>

        Берём количество active.
        """
        active = page.locator(".pattern-info__difficulty li.icon-difficulty.active")
        count = await active.count()

        if count > 0:
            return count

        fallback_active = page.locator(".difficulty-rating li.icon-difficulty.active")
        fallback_count = await fallback_active.count()

        if fallback_count > 0:
            return fallback_count

        return None

    async def _similar_patterns(self, page: Page) -> list[str]:
        selectors = [
            ".pattern-info__bottom .tag-list .swiper-slide",
            ".tag-list .swiper-slide",
            ".pattern-info__bottom .tag-list a",
            ".tag-list a",
        ]

        result: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                text = await loc.nth(i).inner_text()
                text = self._clean_text(text)

                if text:
                    result.append(text)

            if result:
                break

        return list(dict.fromkeys(result))

    async def _tech_details(self, page: Page) -> dict[str, str]:
        """
        Блоки вида:

        <ul class="tech-details">
          <li>
            <div class="tech-title">Описание</div>
            <div class="tech-description">
              <p>...</p>
            </div>
          </li>
        </ul>
        """
        result: dict[str, str] = {}

        items = page.locator("ul.tech-details > li")
        count = await items.count()

        for i in range(count):
            item = items.nth(i)

            title_loc = item.locator(".tech-title")
            desc_loc = item.locator(".tech-description")

            if await title_loc.count() == 0 or await desc_loc.count() == 0:
                continue

            title = self._clean_text(await title_loc.first.inner_text())
            desc = self._clean_text(await desc_loc.first.inner_text())

            if title and desc:
                result[title] = desc

        return result

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        На Burda картинки лежат внутри галереи:

        .pattern-gallery__images img[src]
        .pattern-gallery__thumbs img[src]
        .pattern-gallery img[src]

        Не берём все img со страницы, иначе попадут баннеры, логотипы и промо.
        """
        selectors = [
            ".pattern-gallery__images img[src]",
            ".pattern-gallery__thumbs img[src]",
            ".pattern-gallery img[src]",
        ]

        result: list[CollectedImage] = []
        seen: set[str] = set()

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt")

                if not src:
                    continue

                src = urljoin(page_url, src.strip())

                if not self._looks_like_real_image(src):
                    continue

                if src in seen:
                    continue

                seen.add(src)

                result.append(
                    CollectedImage(
                        url=src,
                        alt=self._clean_text(alt) if alt else None,
                        source=selector,
                    )
                )

        return result

    def _looks_like_real_image(self, url: str) -> bool:
        lower = url.lower()

        if not any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return False

        bad_parts = [
            "logo",
            "sprite",
            "icon",
            "placeholder",
            "avatar",
            "banner",
            "payment",
            "social",
            "loader",
        ]

        return not any(part in lower for part in bad_parts)

    def _clean_text(self, value: str | None) -> str:
        if not value:
            return ""

        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines).strip()