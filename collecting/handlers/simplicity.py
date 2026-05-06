from __future__ import annotations

import logging
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
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Simplicity product title=%r images=%s description_len=%s url=%s",
            title,
            len(images),
            len(description or ""),
            record.url,
        )

        raw_sections: dict[str, str] = {}

        if description:
            raw_sections["Description"] = description

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

    async def _close_cookie_banner(self, page: Page) -> None:
        candidates = [
            "button:has-text('Accept All Cookies')",
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
        Simplicity: описание — это обычный текстовый <p> под блоками выбора формата/размера.

        По скрину DOM:
          <div id="view" class="productView">
            ...
            <p>
              Very loose-fit shirt sewing patterns ...
            </p>
            <ul>Fabric Suggestions...</ul>
            <dl>Sewing Rating...</dl>
          </div>

        Берём именно первый длинный нормальный <p> внутри .productView,
        не всю .productView целиком.
        """
        description = await page.evaluate(
            """
            () => {
                const clean = (text) => (text || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim();

                const root =
                    document.querySelector('#view.productView') ||
                    document.querySelector('.productView') ||
                    document.querySelector('main');

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
                    'We use cookies',
                    'Sewing Rating',
                    'Fabric Suggestions'
                ];

                const paragraphs = Array.from(root.querySelectorAll('p'));

                for (const p of paragraphs) {
                    const text = clean(p.textContent);

                    if (text.length < 60) continue;

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

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Simplicity:
        1. Берём только большие фото из основной галереи товара.
        2. Отдельно берём line art из #tab-lineart и кладём в общий images.
        3. Не берём миниатюры навигации как отдельные дубли.
        4. Не берём Front/Back of Envelope.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        await self._collect_product_gallery_images(page, page_url, result, seen)
        await self._collect_line_art_images(page, page_url, result, seen)

        return result

    async def _collect_product_gallery_images(
        self,
        page: Page,
        page_url: str,
        result: list[CollectedImage],
        seen: set[str],
    ) -> None:
        gallery_root = page.locator(".section-product-nav")

        if await gallery_root.count() == 0:
            gallery_root = page.locator(".productView")

        if await gallery_root.count() == 0:
            logger.warning("Simplicity product gallery root not found url=%s", page_url)
            return

        root = gallery_root.first

        """
        По BigCommerce/Simplicity часто нужные большие картинки лежат:
          .slider__slide img[data-image-gallery-new-image-url]
          .slider__slide img[data-image-gallery-zoom-image-url]
          .slider__slide[data-image-gallery-new-image-url]
        """
        attr_selectors = [
            (".slider__slide img[data-image-gallery-new-image-url]", "data-image-gallery-new-image-url"),
            (".slider__slide img[data-image-gallery-zoom-image-url]", "data-image-gallery-zoom-image-url"),
            ("img[data-image-gallery-new-image-url]", "data-image-gallery-new-image-url"),
            ("img[data-image-gallery-zoom-image-url]", "data-image-gallery-zoom-image-url"),
        ]

        for selector, attr in attr_selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                url_raw = await img.get_attribute(attr)
                alt = await img.get_attribute("alt")
                title = await img.get_attribute("title")

                self._add_image(
                    result=result,
                    seen=seen,
                    page_url=page_url,
                    url_raw=url_raw,
                    alt=alt,
                    title=title,
                    source=f".section-product-nav {selector}@{attr}",
                    allow_line_art=False,
                )

        data_slide_selectors = [
            ".slider__slide[data-image-gallery-new-image-url]",
            ".slider__slide[data-image-gallery-zoom-image-url]",
        ]

        for selector in data_slide_selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                slide = loc.nth(i)

                url_raw = await slide.get_attribute("data-image-gallery-new-image-url")
                if not url_raw:
                    url_raw = await slide.get_attribute("data-image-gallery-zoom-image-url")

                img = slide.locator("img").first
                alt = None
                title = None

                if await img.count() > 0:
                    alt = await img.get_attribute("alt")
                    title = await img.get_attribute("title")

                self._add_image(
                    result=result,
                    seen=seen,
                    page_url=page_url,
                    url_raw=url_raw,
                    alt=alt,
                    title=title,
                    source=f".section-product-nav {selector}",
                    allow_line_art=False,
                )

        # Fallback: только img внутри основной галереи. Миниатюрный nav сам по себе не обходим.
        if not result:
            img_selectors = [
                ".slider__slide img[src]",
                ".productView-image img[src]",
            ]

            for selector in img_selectors:
                loc = root.locator(selector)
                count = await loc.count()

                for i in range(count):
                    img = loc.nth(i)

                    src = await img.get_attribute("data-src")
                    if not src:
                        src = await img.get_attribute("data-lazy")
                    if not src:
                        src = await img.get_attribute("src")

                    alt = await img.get_attribute("alt")
                    title = await img.get_attribute("title")

                    self._add_image(
                        result=result,
                        seen=seen,
                        page_url=page_url,
                        url_raw=src,
                        alt=alt,
                        title=title,
                        source=f".section-product-nav {selector}",
                        allow_line_art=False,
                    )

    async def _collect_line_art_images(
        self,
        page: Page,
        page_url: str,
        result: list[CollectedImage],
        seen: set[str],
    ) -> None:
        """
        Чертёж на Simplicity лежит отдельно в:
          #tab-lineart
            img.lineArtImage
        Его сохраняем в общий images, потому что он ценен.
        """
        line_art_root = page.locator("#tab-lineart")

        if await line_art_root.count() == 0:
            return

        root = line_art_root.first

        selectors = [
            "img.lineArtImage[src]",
            "img[src]",
        ]

        for selector in selectors:
            loc = root.locator(selector)
            count = await loc.count()

            for i in range(count):
                img = loc.nth(i)

                src = await img.get_attribute("data-src")
                if not src:
                    src = await img.get_attribute("data-lazy")
                if not src:
                    src = await img.get_attribute("src")

                alt = await img.get_attribute("alt")
                title = await img.get_attribute("title")

                self._add_image(
                    result=result,
                    seen=seen,
                    page_url=page_url,
                    url_raw=src,
                    alt=alt,
                    title=title,
                    source=f"#tab-lineart {selector}",
                    allow_line_art=True,
                )

            if count > 0:
                break

    def _add_image(
        self,
        *,
        result: list[CollectedImage],
        seen: set[str],
        page_url: str,
        url_raw: str | None,
        alt: str | None,
        title: str | None,
        source: str,
        allow_line_art: bool,
    ) -> None:
        if not url_raw:
            return

        if self._is_envelope_image(alt, title, url_raw):
            return

        if not allow_line_art and self._is_line_art_image(alt, title, url_raw):
            return

        url = urljoin(page_url, url_raw.strip())

        if not self._looks_like_real_image(url):
            return

        if url in seen:
            return

        seen.add(url)

        result.append(
            CollectedImage(
                url=url,
                source=source,
            )
        )

    def _is_envelope_image(
        self,
        alt: str | None,
        title: str | None,
        url: str | None,
    ) -> bool:
        joined = " ".join(part for part in [alt, title, url] if part).lower()

        bad_phrases = [
            "front of envelope",
            "back of envelope",
            "front envelope",
            "back envelope",
            "envelope front",
            "envelope back",
        ]

        return any(phrase in joined for phrase in bad_phrases)

    def _is_line_art_image(
        self,
        alt: str | None,
        title: str | None,
        url: str | None,
    ) -> bool:
        joined = " ".join(part for part in [alt, title, url] if part).lower()

        return "lineart" in joined or "line art" in joined

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