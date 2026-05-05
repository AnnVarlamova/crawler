from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class GrasserCollectingHandler(CollectingHandler):
    site = "grasser"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Grasser product: %s", record.url)

        await page.wait_for_selector(".product__info h1, h1", timeout=15000)

        title = await self._text_or_none(page, ".product__info h1")
        if not title:
            title = await self._text_or_none(page, "h1")

        subtitle = await self._text_or_none(page, ".product__info-subtitle")
        description = subtitle

        images = await self._product_images(page, record.url)
        tags = await self._tags(page)

        logger.debug(
            "Parsed Grasser product title=%r images=%s subtitle=%r url=%s",
            title,
            len(images),
            subtitle,
            record.url,
        )

        raw_sections: dict[str, str] = {}

        if subtitle:
            raw_sections["Краткое описание"] = subtitle
            raw_sections["Описание"] = subtitle

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            title=title,
            similar_patterns=[],
            description=description,
            collection=None,
            season=None,
            style=None,
            images=images,
        )

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        try:
            text = await loc.first.text_content(timeout=5000)
        except Exception:
            return None

        text = self._clean_text(text)
        return text or None

    async def _tags(self, page: Page) -> list[str]:
        result: list[str] = []

        loc = page.locator(".product__info .tags .tag, .tags .tag")
        count = await loc.count()

        for i in range(count):
            try:
                text = await loc.nth(i).text_content(timeout=5000)
            except Exception:
                continue

            text = self._clean_text(text)
            if text:
                result.append(text)

        return list(dict.fromkeys(result))

    async def _product_images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Берём только большие фотографии Grasser.

        Основной источник:
          .product__slider-big a[data-fancybox="gallery"][href]

        Не берём:
          .product__slider-mini img[src]

        Потому что вертикальная галерея даёт маленькие превью.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        gallery_root = page.locator(".product__left-gallery")
        if await gallery_root.count() == 0:
            gallery_root = page.locator(".product__left")

        if await gallery_root.count() == 0:
            gallery_root = page.locator(".product")

        if await gallery_root.count() == 0:
            logger.warning("Grasser gallery root not found url=%s", page_url)
            return result

        root = gallery_root.first

        # 1. Лучший вариант — большие картинки из href.
        link_selectors = [
            '.product__slider-big a[data-fancybox="gallery"][href]',
            ".product__slider-big a[href]",
        ]

        for selector in link_selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                link = loc.nth(i)

                href = await link.get_attribute("href")
                if not href:
                    continue

                url = urljoin(page_url, href.strip())

                if not self._looks_like_real_image(url):
                    continue

                if url in seen:
                    continue

                seen.add(url)

                result.append(
                    CollectedImage(
                        url=url,
                        source=f".product__left-gallery {selector}",
                    )
                )

            if result:
                break

        # 2. Fallback: если href не нашли, берём src больших img, но не мини-слайдер.
        if not result:
            img_selectors = [
                ".product__slider-big img[src]",
                ".product__slider-big img[data-src]",
                ".product__slider-big img[data-lazy]",
            ]

            for selector in img_selectors:
                loc = root.locator(selector)
                count = await loc.count()

                for i in range(count):
                    img = loc.nth(i)

                    src = await self._best_image_attr(img)
                    if not src:
                        continue

                    alt = await img.get_attribute("alt")
                    url = urljoin(page_url, src.strip())

                    if not self._looks_like_real_image(url):
                        continue

                    if url in seen:
                        continue

                    seen.add(url)

                    result.append(
                        CollectedImage(
                            url=url,
                            source=f".product__left-gallery {selector}",
                        )
                    )

        return result

    async def _best_image_attr(self, img) -> str | None:
        attrs = [
            "data-src",
            "data-lazy",
            "data-original",
            "data-img",
            "src",
        ]

        for attr in attrs:
            value = await img.get_attribute(attr)
            if value:
                return value

        srcset = await img.get_attribute("srcset")
        if srcset:
            return self._best_from_srcset(srcset)

        return None

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
            "preloader",
            "play",
            "video",
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