from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class MarfyCollectingHandler(CollectingHandler):
    site = "marfy"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Marfy product: %s", record.url)

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        title = await self._title(page)
        description = await self._description(page)
        details = await self._details(page)
        images = await self._images(page, record.url)

        collection = self._first_value(details, ["Collections", "Collection", "Collezione"])
        season = collection
        style = self._first_value(details, ["Style", "Stile"])

        logger.info(
            "Marfy details url=%s collection=%r season=%r style=%r details=%r",
            record.url,
            collection,
            season,
            style,
            details,
        )

        logger.debug(
            "Parsed Marfy product title=%r images=%s collection=%r season=%r style=%r url=%s",
            title,
            len(images),
            collection,
            season,
            style,
            record.url,
        )

        raw_sections: dict[str, str] = {}

        if description:
            raw_sections["Description"] = description

        for key, value in details.items():
            raw_sections[key] = value

        return CollectedProduct(
            url=record.url,
            site=record.site,
            category=record.category,
            source_page=record.source_page,
            title=title,
            difficulty=None,
            similar_patterns=[],
            description=description,
            collection=collection,
            season=season,
            style=style,
            images=images,
            review_images=[],
            raw_sections=raw_sections,
            raw={
                "html_title": await page.title(),
                "details": details,
                "reference": self._first_value(details, ["Reference", "Riferimento"]),
                "typology": self._first_value(details, ["Typology", "Tipologia"]),
                "size": self._first_value(details, ["Size", "Taglia"]),
            },
        )

    async def _title(self, page: Page) -> str | None:
        selectors = [
            ".product-information h1",
            ".product-info h1",
            "h1",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text:
                return text

        return None

    async def _description(self, page: Page) -> str | None:
        selectors = [
            "#description .product-description",
            "#description .rte-content",
            "#description",
            ".product-description .rte-content",
            ".product-description",
        ]

        candidates: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(min(count, 3)):
                text = await self._text_content_or_none_from_locator(loc.nth(i))

                if text and self._looks_like_description(text):
                    candidates.append(text)

            if candidates:
                break

        if candidates:
            return self._deduplicate_lines(candidates[0])

        meta_description = await self._meta_content(page, "meta[name='description']")
        if meta_description:
            return self._clean_text(meta_description)

        return None

    async def _details(self, page: Page) -> dict[str, str]:
        result: dict[str, str] = {}

        data_sheet_details = await self._details_from_data_sheet(page)
        if data_sheet_details:
            result.update(data_sheet_details)

        product_reference = await self._product_reference(page)
        if product_reference:
            result.setdefault("Reference", product_reference)

        product_condition = await self._product_condition(page)
        if product_condition:
            result.setdefault("Condition", product_condition)

        if not result:
            text_details = await self._details_from_text_blocks(page)
            result.update(text_details)

        json_details = await self._details_from_data_product(page)
        for key, value in json_details.items():
            result.setdefault(key, value)

        return result

    async def _details_from_data_sheet(self, page: Page) -> dict[str, str]:
        """
        ВАЖНО:
        Product Details может быть скрытой вкладкой.
        Поэтому читаем через text_content(), а не inner_text().
        """
        result: dict[str, str] = {}

        pairs = await page.evaluate(
            """
            () => {
                const out = [];
                const sheets = Array.from(document.querySelectorAll('dl.data-sheet'));

                for (const sheet of sheets) {
                    const children = Array.from(sheet.children);
                    let currentName = null;

                    for (const child of children) {
                        const text = (child.textContent || '').replace(/\\s+/g, ' ').trim();

                        if (!text) continue;

                        if (child.matches('dt.name, dt')) {
                            currentName = text;
                        } else if (child.matches('dd.value, dd') && currentName) {
                            out.push([currentName, text]);
                            currentName = null;
                        }
                    }
                }

                return out;
            }
            """
        )

        for item in pairs:
            if not isinstance(item, list) or len(item) != 2:
                continue

            key = self._clean_text(str(item[0]))
            value = self._clean_text(str(item[1]))

            if key and value:
                result[key] = value

        return result

    async def _product_reference(self, page: Page) -> str | None:
        selectors = [
            ".product-reference span",
            ".product-reference",
        ]

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            if count == 0:
                continue

            text = await self._text_content_or_none_from_locator(loc.first)
            if not text:
                continue

            text = text.replace("Reference", "").strip()
            if text:
                return text

        return None

    async def _product_condition(self, page: Page) -> str | None:
        selectors = [
            ".product-condition span",
            ".product-condition",
        ]

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            if count == 0:
                continue

            text = await self._text_content_or_none_from_locator(loc.first)
            if not text:
                continue

            text = text.replace("Condition", "").strip()
            if text:
                return text

        return None

    async def _details_from_text_blocks(self, page: Page) -> dict[str, str]:
        result: dict[str, str] = {}

        selectors = [
            "#product-detailstab",
            "#product-details",
            "#product-infos-tabs-content #product-detailstab",
            ".product-features",
            ".data-sheet",
        ]

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            if count == 0:
                continue

            text = await self._text_content_or_none_from_locator(loc.first)
            if not text:
                continue

            parsed = self._parse_details_text(text)
            if parsed:
                result.update(parsed)
                break

        return result

    async def _details_from_data_product(self, page: Page) -> dict[str, str]:
        result: dict[str, str] = {}

        loc = page.locator("[data-product]")
        count = await loc.count()

        if count == 0:
            return result

        raw = await loc.first.get_attribute("data-product")
        if not raw:
            return result

        try:
            data = json.loads(raw)
        except Exception:
            return result

        mapping = {
            "name": "Name",
            "reference": "Reference",
            "description_short": "Description short",
        }

        for json_key, out_key in mapping.items():
            value = data.get(json_key)
            if isinstance(value, str):
                cleaned = self._clean_htmlish_text(value)
                if cleaned:
                    result[out_key] = cleaned

        return result

    def _parse_details_text(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}

        if not text:
            return result

        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        known_keys = {
            "Collections",
            "Collection",
            "Size",
            "Typology",
            "Style",
            "Reference",
            "Condition",
            "Collezione",
            "Taglia",
            "Tipologia",
            "Stile",
            "Riferimento",
            "Condizione",
        }

        i = 0

        while i < len(lines):
            line = lines[i]

            if line in known_keys:
                values: list[str] = []
                i += 1

                while i < len(lines) and lines[i] not in known_keys:
                    values.append(lines[i])
                    i += 1

                value = "\n".join(values).strip()

                if value:
                    result[line] = value

                continue

            for key in known_keys:
                prefix = key + " "
                if line.startswith(prefix):
                    value = line[len(prefix):].strip()
                    if value:
                        result[key] = value
                    break

            i += 1

        return result

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        result: list[CollectedImage] = []
        seen: set[str] = set()

        attr_selectors = [
            (".product-images-large img[data-image-large-src]", "data-image-large-src"),
            (".product-images-thumbs img[data-image-large-src]", "data-image-large-src"),
            ("img[data-image-large-src]", "data-image-large-src"),
            (".product-images-large img[data-full-size-image-url]", "data-full-size-image-url"),
            ("img[data-full-size-image-url]", "data-full-size-image-url"),
        ]

        for selector, attr in attr_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)
                url_raw = await img.get_attribute(attr)
                alt = await img.get_attribute("alt")

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

        link_selectors = [
            ".product-images-large a[href]",
            ".images-container a[href]",
            ".product-cover a[href]",
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

        img_selectors = [
            ".product-images-large img[src]",
            ".product-images-thumbs img[src]",
            ".images-container img[src]",
            ".product-cover img[src]",
            "img.thumb[src]",
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

        source_selectors = [
            ".product-images-large source[srcset]",
            ".product-images-thumbs source[srcset]",
            ".images-container source[srcset]",
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

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        return await self._text_content_or_none_from_locator(loc.first)

    async def _text_content_or_none_from_locator(self, loc) -> str | None:
        try:
            text = await loc.text_content(timeout=5000)
        except Exception:
            return None

        text = self._clean_text(text)

        return text or None

    async def _meta_content(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        content = await loc.first.get_attribute("content")
        return content or None

    def _first_value(self, data: dict[str, str], keys: list[str]) -> str | None:
        for key in keys:
            value = data.get(key)
            if value:
                return value
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
            "flag",
            "language",
        ]

        return not any(part in lower for part in bad_parts)

    def _looks_like_description(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()

        bad_parts = [
            "product details",
            "order info",
            "add to cart",
            "how to choose your size",
        ]

        if any(part in lower for part in bad_parts) and len(text) < 250:
            return False

        return len(text) > 30

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

    def _clean_htmlish_text(self, value: str | None) -> str:
        if not value:
            return ""

        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"<[^>]+>", " ", value)

        return self._clean_text(value)

    def _clean_text(self, value: str | None) -> str:
        if not value:
            return ""

        value = value.replace("\xa0", " ")
        value = value.replace("&nbsp;", " ")

        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]

        return "\n".join(lines).strip()