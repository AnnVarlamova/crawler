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
        similar_patterns = await self._similar_patterns(page)
        raw_sections = await self._tech_details(page)
        description = raw_sections.get("Описание")
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed BurdaStyle product title=%r tags=%s images=%s url=%s",
            title,
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
            difficulty=None,
            similar_patterns=similar_patterns,
            description=description,
            images=images,
            review_images=[],
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
                "tags": similar_patterns,
            },
        )

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        text = await loc.first.text_content(timeout=5000)
        text = self._clean_text(text)

        return text or None

    async def _similar_patterns(self, page: Page) -> list[str]:
        selectors = [
            ".pattern-info__bottom .tag-list .swiper-slide",
            ".pattern-info__bottom .tag-list a",
            ".tag-list .swiper-slide",
            ".tag-list a",
        ]

        result: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                text = await loc.nth(i).text_content(timeout=5000)
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

            title = self._clean_text(await title_loc.first.text_content(timeout=5000))
            desc = self._clean_text(await desc_loc.first.text_content(timeout=5000))

            if title and desc:
                result[title] = desc

        return result

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Берём только большие изображения из основной галереи Burda.

        Не берём:
          .pattern-gallery__thumbs img[src]

        Потому что вертикальные thumbnails дублируют большие картинки.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        gallery_root = page.locator(".pattern-gallery__images")

        if await gallery_root.count() == 0:
            gallery_root = page.locator(".pattern-gallery")

        if await gallery_root.count() == 0:
            logger.warning("BurdaStyle gallery root not found url=%s", page_url)
            return result

        root = gallery_root.first

        selectors = [
            "img[src]",
            "img[data-src]",
            "source[srcset]",
        ]

        for selector in selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                el = loc.nth(i)

                src = await el.get_attribute("src")
                if not src:
                    src = await el.get_attribute("data-src")

                if not src:
                    srcset = await el.get_attribute("srcset")
                    src = self._best_from_srcset(srcset)

                alt = await el.get_attribute("alt")

                if not src:
                    continue

                url = urljoin(page_url, src.strip())

                if not self._looks_like_real_image(url):
                    continue

                if url in seen:
                    continue

                seen.add(url)

                result.append(
                    CollectedImage(
                        url=url,
                        alt=self._clean_text(alt) if alt else None,
                        source=f".pattern-gallery__images {selector}",
                    )
                )

        return result

    def _best_from_srcset(self, srcset: str | None) -> str | None:
        if not srcset:
            return None

        parts = [part.strip() for part in srcset.split(",") if part.strip()]
        if not parts:
            return None

        return parts[-1].split()[0]

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

        value = value.replace("\xa0", " ")
        value = value.replace("&nbsp;", " ")

        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines).strip()