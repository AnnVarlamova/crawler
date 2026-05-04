from __future__ import annotations

import logging
import re
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
        difficulty = await self._difficulty(page)

        description = await self._description(page)
        images = await self._product_images(page, record.url)


        tags = await self._tags(page)

        logger.debug(
            "Parsed Grasser product title=%r difficulty=%r images=%s review_images=%s url=%s",
            title,
            difficulty,
            len(images),
            record.url,
        )

        raw_sections = {}
        if subtitle:
            raw_sections["Краткое описание"] = subtitle
        if description:
            raw_sections["Описание"] = description

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=difficulty,
            similar_patterns=[],
            description=description,
            images=images,
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
                "subtitle": subtitle,
                "tags": tags,
            },
        )

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        text = await loc.first.inner_text()
        text = self._clean_text(text)

        return text or None

    async def _tags(self, page: Page) -> list[str]:
        result: list[str] = []

        loc = page.locator(".product__info .tags .tag, .tags .tag")
        count = await loc.count()

        for i in range(count):
            text = self._clean_text(await loc.nth(i).inner_text())
            if text:
                result.append(text)

        return list(dict.fromkeys(result))

    async def _difficulty(self, page: Page) -> int | None:
        """
        На Grasser сложность лежит в тегах:

        <div class="tags">
          <div class="tag">Сложность: 3 из 5</div>
          ...
        </div>
        """
        tags = await self._tags(page)

        for tag in tags:
            match = re.search(r"сложность\s*:\s*(\d+)\s*из\s*(\d+)", tag, flags=re.IGNORECASE)
            if match:
                return int(match.group(1))

        text = self._clean_text(await page.locator("body").inner_text())
        match = re.search(r"сложность\s*:\s*(\d+)\s*из\s*(\d+)", text, flags=re.IGNORECASE)

        if match:
            return int(match.group(1))

        return None

    async def _description(self, page: Page) -> str | None:
        """
        Основное описание находится во вкладке:

        .tabs__content-block[data-content="description"]
        внутри:
          .product__description
          .product__collapsing
          .collapse-block
          .collapse-text

        Берём текст только из активной/описательной вкладки, чтобы не прихватить отзывы и вопросы.
        """
        selectors = [
            '.tabs__content-block[data-content="description"] .product__description',
            '.tabs__content-block[data-content="description"] .product__collapsing',
            '.tabs__content-block[data-content="description"]',
            ".product__description",
            ".product__collapsing",
        ]

        candidates: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(min(count, 3)):
                text = self._clean_text(await loc.nth(i).inner_text())

                if self._looks_like_description(text):
                    candidates.append(text)

            if candidates:
                break

        if not candidates:
            return None

        return self._deduplicate_description(candidates[0])

    async def _product_images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        На Grasser в большой галерее есть ссылки:

        <a data-fancybox="gallery" href="/upload/iblock/...jpg">
          ...
        </a>

        Лучше брать href, потому что там обычно оригинальная картинка.
        Потом fallback — img[src] в большой и мини-галерее.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        link_selectors = [
            '.product__slider-big a[data-fancybox="gallery"][href]',
            ".product__slider-big a[href]",
            ".product__left-gallery a[href]",
        ]

        for selector in link_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                href = await loc.nth(i).get_attribute("href")
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
                        alt=None,
                        source=selector,
                    )
                )

            if result:
                break

        img_selectors = [
            ".product__slider-big img[src]",
            ".product__slider-mini img[src]",
            ".product__left-gallery img[src]",
        ]

        for selector in img_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt")

                if not src:
                    src = await img.get_attribute("data-src")

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
            "preloader",
        ]

        return not any(part in lower for part in bad_parts)

    def _looks_like_description(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()

        bad_parts = [
            "отзывы",
            "вопросы",
            "чтобы оставить свой отзыв",
            "необходимо войти",
        ]

        if any(part in lower for part in bad_parts):
            return False

        return len(text) > 80

    def _deduplicate_description(self, text: str) -> str:
        """
        Иногда inner_text() может собрать одинаковые куски из раскрытых collapse-блоков.
        Убираем точные дубли строк.
        """
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        result: list[str] = []
        seen: set[str] = set()

        for line in lines:
            key = line.lower()
            if key in seen:
                continue

            seen.add(key)
            result.append(line)

        return "\n".join(result).strip()

    def _clean_text(self, value: str | None) -> str:
        if not value:
            return ""

        value = value.replace("\xa0", " ")

        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines).strip()