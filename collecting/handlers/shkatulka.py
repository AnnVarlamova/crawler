from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class ShkatulkaCollectingHandler(CollectingHandler):
    site = "shkatulka"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Shkatulka product: %s", record.url)

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        title = await self._title(page)
        description = await self._description(page)
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Shkatulka product title=%r images=%s description_len=%s url=%s",
            title,
            len(images),
            len(description or ""),
            record.url,
        )

        raw_sections: dict[str, str] = {}
        if description:
            raw_sections["Описание"] = description

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=None,
            similar_patterns=[],
            description=description,
            collection=None,
            season=None,
            style=None,
            images=images,
            review_images=[],
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
            },
        )

    async def _title(self, page: Page) -> str | None:
        selectors = [
            "h1.page-title",
            ".product-details__title",
            ".product-details h1",
            "h1",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text:
                return text

        return None

    async def _description(self, page: Page) -> str | None:
        description = await page.evaluate(
            """
            () => {
                const root =
                    document.querySelector('#productDescription') ||
                    document.querySelector('.product-details__product-description') ||
                    document.querySelector('.product-details-module__content');

                if (!root) return null;

                const clean = (text) => {
                    return (text || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim();
                };

                const badTextParts = [
                    'Для ознакомления доступны',
                    'После оформления заказа',
                    'Параметры модели',
                    'Таблица размеров',
                    'Что вы получите после оплаты'
                ];

                const paragraphs = Array.from(root.querySelectorAll('p'));

                // Основной вариант: абзац, где перед описанием стоит картинка-вешалка.
                for (const p of paragraphs) {
                    const hasImage = !!p.querySelector('img');
                    const text = clean(p.textContent);

                    if (!hasImage) continue;
                    if (text.length < 80) continue;

                    const isBad = badTextParts.some(part => text.includes(part));
                    if (isBad) continue;

                    return text;
                }

                // Fallback: первый длинный нормальный абзац.
                for (const p of paragraphs) {
                    const text = clean(p.textContent);

                    if (text.length < 80) continue;

                    const isBad = badTextParts.some(part => text.includes(part));
                    if (isBad) continue;

                    return text;
                }

                return null;
            }
            """
        )

        if not description:
            return None

        return self._clean_text(description) or None

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Строго только товарная галерея Шкатулки:

        <div class="product-details__gallery details-gallery">
          <div class="details-gallery__wrap">
            <div class="details-gallery__wrap-inner">
              <div class="slider slider-for ...">
                <a class="main_modal_gallery ..." href="/data/uploads/pattern/...jpg">
              ...
              <div class="slider slider-nav ...">
                ...
              </div>
            </div>
          </div>
        </div>

        НЕ используем:
          .product-details img
          main img
          #productDescription img
        потому что они тянут вешалку, описания, отзывы, иконки и мусор.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        gallery_root = page.locator(".product-details__gallery.details-gallery")
        if await gallery_root.count() == 0:
            gallery_root = page.locator(".details-gallery")

        if await gallery_root.count() == 0:
            logger.warning("Shkatulka gallery root not found url=%s", page_url)
            return result

        root = gallery_root.first

        # 1. Лучший источник — href у main_modal_gallery.
        link_selectors = [
            ".slider-for a.main_modal_gallery[href]",
            "a.main_modal_gallery[href]",
            ".slider-for a[href]",
        ]

        for selector in link_selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                href = await loc.nth(i).get_attribute("href")
                if not href:
                    continue

                url = urljoin(page_url, href.strip())

                if not self._looks_like_product_image(url):
                    continue

                if url in seen:
                    continue

                seen.add(url)
                result.append(
                    CollectedImage(
                        url=url,
                        alt=None,
                        source=f".product-details__gallery {selector}",
                    )
                )

            if result:
                break

        # 2. Только если href не нашли — img внутри этой же галереи.
        if not result:
            img_selectors = [
                ".slider-for img[src]",
                ".slider-nav img[src]",
                "img[src]",
            ]

            for selector in img_selectors:
                loc = root.locator(selector)
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
                            source=f".product-details__gallery {selector}",
                        )
                    )

        return result

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

    def _looks_like_product_image(self, url: str) -> bool:
        lower = url.lower()

        if not any(ext in lower for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return False

        # Для Шкатулки товарные картинки обычно лежат здесь.
        if "/data/uploads/pattern/" not in lower:
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
            "rating",
            "star",
            "review",
            "otzyv",
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