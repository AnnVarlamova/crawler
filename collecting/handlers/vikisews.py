from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class VikisewsCollectingHandler(CollectingHandler):
    site = "vikisews"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Vikisews product: %s", record.url)

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        title = await self._title(page)
        description = await self._description(page)
        tags = await self._tags(page)
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Vikisews product title=%r images=%s tags=%s description_len=%s url=%s",
            title,
            len(images),
            len(tags),
            len(description or ""),
            record.url,
        )

        raw_sections: dict[str, str] = {}

        if description:
            raw_sections["Описание"] = description

        if tags:
            raw_sections["Теги"] = "\n".join(tags)

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=None,
            similar_patterns=tags,
            description=description,
            collection=None,
            season=None,
            style=None,
            images=images,
            review_images=[],
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
                "tags": tags,
            },
        )

    async def _title(self, page: Page) -> str | None:
        selectors = [
            "h1.product-main-header",
            ".product-main-header",
            "h1",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text:
                return text

        return None

    async def _description(self, page: Page) -> str | None:
        """
        На Vikisews основной текст описания лежит в блоке:

          #patternSubInfo

        Внутри несколько <p>. Первый большой абзац — описание модели.
        Далее могут идти модель, время пошива, образ модели,
        а потом секции типа "РЕКОМЕНДУЕМЫЕ МАТЕРИАЛЫ".

        Берём всё полезное до первой большой секции рекомендаций.
        """
        description = await page.evaluate(
            """
            () => {
                const root =
                    document.querySelector('#patternSubInfo') ||
                    document.querySelector('.main-content') ||
                    document.querySelector('main');

                if (!root) return null;

                const clean = (text) => {
                    return (text || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim();
                };

                const stopHeaders = [
                    'РЕКОМЕНДУЕМЫЕ МАТЕРИАЛЫ',
                    'РАСХОД',
                    'ОБОРУДОВАНИЕ',
                    'ПРИБАВКИ',
                    'ПРИМЕР ИНСТРУКЦИИ',
                    'КАК ВЫБРАТЬ РАЗМЕР',
                    'СОСТАВ ЗАКАЗА',
                    'ВАШ РОСТ',
                    'ВАШ РАЗМЕР'
                ];

                const result = [];
                const children = Array.from(root.children);

                for (const child of children) {
                    const text = clean(child.textContent);

                    if (!text) continue;

                    const upper = text.toUpperCase();

                    if (stopHeaders.some(header => upper.startsWith(header))) {
                        break;
                    }

                    if (text.length < 20) continue;

                    result.push(text);
                }

                if (result.length > 0) {
                    return result.join('\\n\\n');
                }

                const paragraphs = Array.from(root.querySelectorAll('p'));

                for (const p of paragraphs) {
                    const text = clean(p.textContent);

                    if (text.length > 80) {
                        return text;
                    }
                }

                return null;
            }
            """
        )

        if not description:
            return None

        description = self._deduplicate_lines(self._clean_text(description))

        return description or None

    async def _tags(self, page: Page) -> list[str]:
        selectors = [
            ".tags a.link-decoration",
            ".tags a",
            "div.tags li a",
            "div.tags a",
        ]

        result: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                text = await self._text_content_from_locator(loc.nth(i))
                if text:
                    result.append(text)

            if result:
                break

        return list(dict.fromkeys(result))

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        На Vikisews картинки видны в вертикальном preview-слайдере:

          .swiper-preview-vertical img.preview.img-fluid
          .main-slider img
          img.preview.img-fluid.img-resize.intrinsic-item

        В src обычно уже лежит нормальная CDN-ссылка:
          https://storage.yandexcloud.net/vikisews-public-media/...
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        img_selectors = [
            ".main-slider img[src]",
            ".swiper-preview-vertical img[src]",
            "img.preview.img-fluid[src]",
            "img.img-resize[src]",
            "main img[src]",
        ]

        for selector in img_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                src = await img.get_attribute("src")
                if not src:
                    src = await img.get_attribute("data-src")
                if not src:
                    src = await img.get_attribute("data-lazy")

                alt = await img.get_attribute("alt")

                if not src:
                    continue

                url = urljoin(page_url, src.strip())

                if not self._looks_like_product_image(url):
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

        source_selectors = [
            ".main-slider source[srcset]",
            ".swiper-preview-vertical source[srcset]",
            "main source[srcset]",
        ]

        for selector in source_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                srcset = await loc.nth(i).get_attribute("srcset")
                url_raw = self._best_from_srcset(srcset)

                if not url_raw:
                    continue

                url = urljoin(page_url, url_raw.strip())

                if not self._looks_like_product_image(url):
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

        return result

    def _looks_like_product_image(self, url: str) -> bool:
        lower = url.lower()

        if not any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return False

        good_parts = [
            "vikisews-public-media",
            "/media/cache/",
            "/upload/",
            "/storage/",
            "/media/",
        ]

        # Если это CDN Vikisews — почти наверняка нужная картинка.
        if any(part in lower for part in good_parts):
            return not self._is_bad_image_url(lower)

        return not self._is_bad_image_url(lower)

    def _is_bad_image_url(self, lower_url: str) -> bool:
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
            "rating",
            "star",
            "flag",
            "language",
        ]

        return any(part in lower_url for part in bad_parts)

    def _best_from_srcset(self, srcset: str | None) -> str | None:
        if not srcset:
            return None

        parts = [part.strip() for part in srcset.split(",") if part.strip()]
        if not parts:
            return None

        return parts[-1].split()[0]

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        return await self._text_content_from_locator(loc.first)

    async def _text_content_from_locator(self, loc) -> str | None:
        try:
            text = await loc.text_content(timeout=5000)
        except Exception:
            return None

        text = self._clean_text(text)

        return text or None

    def _deduplicate_lines(self, text: str) -> str:
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
        value = value.replace("&nbsp;", " ")

        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines).strip()