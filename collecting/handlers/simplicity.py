from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class SimplicityCollectingHandler(CollectingHandler):
    site = "simplicity"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Simplicity product: %s", record.url)

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        await self._close_cookie_banner(page)

        title = await self._title(page)
        description = await self._description(page)
        difficulty_text = await self._difficulty_text(page)
        difficulty = self._difficulty_to_number(difficulty_text)
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Simplicity product title=%r difficulty=%r difficulty_text=%r images=%s url=%s",
            title,
            difficulty,
            difficulty_text,
            len(images),
            record.url,
        )

        raw_sections: dict[str, str] = {}

        if description:
            raw_sections["Description"] = description

        if difficulty_text:
            raw_sections["Sewing Rating"] = difficulty_text

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=difficulty,
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
                "difficulty_text": difficulty_text,
            },
        )

    async def _close_cookie_banner(self, page: Page) -> None:
        """
        На Simplicity снизу может висеть cookie banner.
        Он не критичен для DOM, но иногда мешает кликам/скроллу.
        """
        candidates = [
            "button:has-text('Accept')",
            "button:has-text('I Agree')",
            "button:has-text('Got it')",
            "button:has-text('OK')",
        ]

        for selector in candidates:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0:
                    await loc.first.click(timeout=1000)
                    await page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    async def _title(self, page: Page) -> str | None:
        selectors = [
            "h1.productView-title",
            ".productView-title",
            "h1",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text:
                return text

        return None

    async def _description(self, page: Page) -> str | None:
        """
        На странице Simplicity описание может быть просто <p> в правом блоке товара,
        не всегда с удобным классом. Поэтому сначала берём наиболее точные блоки,
        потом fallback через JS: ищем длинный абзац внутри productView.
        """
        selectors = [
            ".productView-description",
            ".productView-info .productView-info-value",
            '[data-content-region="product_below_price"]',
            ".productView-details",
            ".productView",
        ]

        candidates: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(min(count, 3)):
                text = await self._text_content_from_locator(loc.nth(i))
                if text and self._looks_like_description(text):
                    candidates.append(text)

            if candidates:
                break

        if candidates:
            return self._deduplicate_lines(candidates[0])

        description = await page.evaluate(
            """
            () => {
                const clean = (text) => (text || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim();

                const root =
                    document.querySelector('.productView') ||
                    document.querySelector('main') ||
                    document.body;

                if (!root) return null;

                const badParts = [
                    'Choose Format',
                    'Choose Size',
                    'Add to Bag',
                    'Add to Wish List',
                    'Product Format',
                    'Size Charts',
                    'A0 Print Size',
                    'PDF orders now automatically include',
                    'We use cookies'
                ];

                const paragraphs = Array.from(root.querySelectorAll('p'));

                for (const p of paragraphs) {
                    const text = clean(p.textContent);

                    if (text.length < 80) continue;

                    const isBad = badParts.some(part => text.includes(part));
                    if (isBad) continue;

                    return text;
                }

                return null;
            }
            """
        )

        if description:
            return self._deduplicate_lines(self._clean_text(description))

        return None

    async def _difficulty_text(self, page: Page) -> str | None:
        """
        На Simplicity сложность выглядит как:
          SEWING RATING : Easy

        В DOM рядом есть:
          .sewing-rating
          #about_sewing_ratings
        """
        selectors = [
            ".sewing-rating",
            "[class*='sewing-rating']",
            "dt:has(.sewing-rating)",
            ".productView",
            "main",
        ]

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(min(count, 3)):
                text = await self._text_content_from_locator(loc.nth(i))
                if not text:
                    continue

                parsed = self._extract_difficulty_text(text)
                if parsed:
                    return parsed

        body_text = await self._text_content_from_locator(page.locator("body"))
        return self._extract_difficulty_text(body_text or "")

    def _extract_difficulty_text(self, text: str) -> str | None:
        text = self._clean_text(text)

        if not text:
            return None

        patterns = [
            r"SEWING\s+RATING\s*:?\s*([A-Za-zА-Яа-яЁё0-9\s\-]+)",
            r"Sewing\s+Rating\s*:?\s*([A-Za-zА-Яа-яЁё0-9\s\-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)

            if not match:
                continue

            value = match.group(1).strip()

            if not value:
                continue

            lines = [line.strip() for line in value.splitlines() if line.strip()]

            if not lines:
                continue

            value = lines[0]

            value = re.split(
                r"\s{2,}|Line Art|Product|Choose|Size|Add|Front|Back|Fabric|Description",
                value,
                maxsplit=1,
            )[0].strip()

            if value:
                return value

        # fallback для случаев, когда текст лежит рядом как отдельный dd:
        # Sewing Rating
        # Easy
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for index, line in enumerate(lines):
            if re.search(r"sewing\s+rating", line, flags=re.IGNORECASE):
                for next_line in lines[index + 1: index + 4]:
                    cleaned = next_line.strip(" :\t")

                    if not cleaned:
                        continue

                    if cleaned.lower() in {"easy", "average", "medium", "intermediate", "advanced", "difficult",
                                           "hard"}:
                        return cleaned

        return None

    def _difficulty_to_number(self, difficulty_text: str | None) -> int | None:
        """
        Общая шкала difficulty у нас числовая.
        Для Simplicity маппим текст:

        Easy -> 1
        Average / Medium -> 3
        Advanced / Difficult -> 5
        """
        if not difficulty_text:
            return None

        lower = difficulty_text.lower()

        if any(word in lower for word in ["easy", "beginner", "прост"]):
            return 1

        if any(word in lower for word in ["average", "medium", "intermediate", "сред"]):
            return 3

        if any(word in lower for word in ["advanced", "difficult", "hard", "слож"]):
            return 5

        return None

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Берём фото из галереи товара.

        Важно: не берём изображения, где alt/title содержит:
          Front of Envelope
          Back of Envelope

        Потому что это обложки/оборот упаковки, а тебе нужны фото/изображения изделия.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        attr_selectors = [
            (".productView-images img[data-image-gallery-new-image-url]", "data-image-gallery-new-image-url"),
            (".productView-images img[data-image-gallery-zoom-image-url]", "data-image-gallery-zoom-image-url"),
            (".slider-product-main img[data-image-gallery-new-image-url]", "data-image-gallery-new-image-url"),
            (".slider-product-main img[data-image-gallery-zoom-image-url]", "data-image-gallery-zoom-image-url"),
            ("img[data-image-gallery-new-image-url]", "data-image-gallery-new-image-url"),
            ("img[data-image-gallery-zoom-image-url]", "data-image-gallery-zoom-image-url"),
        ]

        for selector, attr in attr_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                url_raw = await img.get_attribute(attr)
                alt = await img.get_attribute("alt")
                title = await img.get_attribute("title")

                if self._is_envelope_image(alt, title, url_raw):
                    continue

                if not url_raw:
                    continue

                url = urljoin(page_url, url_raw.strip())

                if not self._looks_like_real_image(url):
                    continue

                if url in seen:
                    continue

                seen.add(url)

                result.append(
                    CollectedImage(
                        url=url,
                        alt=self._clean_text(alt) if alt else None,
                        source=f"{selector}@{attr}",
                    )
                )

        img_selectors = [
            ".slider-product-main img[src]",
            ".slider-product-nav img[src]",
            ".productView-images img[src]",
            ".productView-image img[src]",
            ".productView img[src]",
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
                title = await img.get_attribute("title")

                if self._is_envelope_image(alt, title, src):
                    continue

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

        source_selectors = [
            ".productView-images source[srcset]",
            ".slider-product-main source[srcset]",
            ".slider-product-nav source[srcset]",
        ]

        for selector in source_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                srcset = await loc.nth(i).get_attribute("srcset")
                url_raw = self._best_from_srcset(srcset)

                if self._is_envelope_image(None, None, url_raw):
                    continue

                if not url_raw:
                    continue

                url = urljoin(page_url, url_raw.strip())

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

        return result

    def _is_envelope_image(
        self,
        alt: str | None,
        title: str | None,
        url: str | None,
    ) -> bool:
        """
        Фильтр по просьбе:
        избегаем Front of Envelope и Back of Envelope.
        """
        joined = " ".join(
            part for part in [alt, title, url] if part
        ).lower()

        bad_phrases = [
            "front of envelope",
            "back of envelope",
            "front envelope",
            "back envelope",
            "envelope front",
            "envelope back",
        ]

        return any(phrase in joined for phrase in bad_phrases)

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

    def _looks_like_description(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()

        bad_parts = [
            "choose format",
            "choose size",
            "add to bag",
            "add to wish list",
            "product format",
            "size charts",
            "a0 print size",
            "pdf orders now automatically include",
            "we use cookies",
        ]

        if any(part in lower for part in bad_parts) and len(text) < 400:
            return False

        return len(text) > 80

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
            "flag",
            "rating",
            "star",
            "write-review",
            "heart",
        ]

        return not any(part in lower for part in bad_parts)

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