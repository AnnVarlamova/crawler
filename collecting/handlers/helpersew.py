from __future__ import annotations

import logging
from urllib.parse import urljoin

from playwright.async_api import Page

from collecting.handlers.base import CollectingHandler
from collecting.models import CollectedImage, CollectedProduct, LinkRecord

logger = logging.getLogger("collecting")


class HelpersewCollectingHandler(CollectingHandler):
    site = "helpersew"

    async def collect(self, page: Page, record: LinkRecord) -> CollectedProduct:
        logger.debug("Collect Helpersew product: %s", record.url)

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        current_url = page.url
        body_text = await self._safe_body_text(page)

        if self._looks_like_not_product_page(current_url, body_text):
            raise RuntimeError(
                f"Helpersew page does not look like product page: "
                f"current_url={current_url!r}, title={await page.title()!r}"
            )

        title = await self._title(page)
        description = await self._description(page)
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Helpersew product title=%r images=%s url=%s",
            title,
            len(images),
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

    async def _safe_body_text(self, page: Page) -> str:
        try:
            return self._clean_text(await page.locator("body").inner_text(timeout=5000))
        except Exception:
            return ""

    def _looks_like_not_product_page(self, current_url: str, body_text: str) -> bool:
        lower_url = current_url.lower()
        lower_text = body_text.lower()

        bad_url_parts = [
            "/404",
            "not-found",
        ]

        if any(part in lower_url for part in bad_url_parts):
            return True

        bad_text_parts = [
            "страница не найдена",
            "товар не найден",
            "ничего не найдено",
            "access denied",
            "доступ запрещен",
        ]

        return any(part in lower_text for part in bad_text_parts)

    async def _title(self, page: Page) -> str | None:
        selectors = [
            "h1.page-title.visible",
            ".cat-detail-title[itemprop='name']",
            ".cat-detail-title",
            "h1",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text:
                return text

        return None

    async def _description(self, page: Page) -> str | None:
        """
        По DOM описание находится здесь:

        .cat-detail-t-cont
          .cat-detail-t-cont-wrap
            .cat-detail-t-cont-item.active

        Там текст может быть прямо текстовыми нодами + <br>.
        """
        selectors = [
            ".cat-detail-t-cont-item.active",
            ".cat-detail-t-cont-wrap .cat-detail-t-cont-item",
            ".cat-detail-t-cont",
            ".cat-detail-tabscont",
        ]

        candidates: list[str] = []

        for selector in selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(min(count, 3)):
                try:
                    text = self._clean_text(await loc.nth(i).inner_text(timeout=5000))
                except Exception:
                    continue

                if self._looks_like_description(text):
                    candidates.append(text)

            if candidates:
                break

        if not candidates:
            return None

        return self._deduplicate_description(candidates[0])

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Helpersew: один <picture class="cat-detail__pic" counter="..."> = одна фотография.

        Внутри picture может быть несколько source/img для разных размеров и форматов.
        Поэтому НЕ обходим отдельно все source и все img как независимые картинки.
        Иначе получаются дубли одной фотографии в разных размерах.

        Берём ровно один лучший URL из каждого picture.
        """
        result: list[CollectedImage] = []
        seen_urls: set[str] = set()
        seen_counters: set[str] = set()

        gallery_root = page.locator(".cat-detail__l-wrap .cat-detail__pics")
        if await gallery_root.count() == 0:
            gallery_root = page.locator(".cat-detail__pics")

        if await gallery_root.count() == 0:
            logger.warning("Helpersew gallery root not found url=%s", page_url)
            return result

        root = gallery_root.first

        pictures = root.locator("picture.cat-detail__pic")
        picture_count = await pictures.count()

        for i in range(picture_count):
            picture = pictures.nth(i)
            counter = await picture.get_attribute("counter")

            if counter and counter in seen_counters:
                continue

            candidates: list[str] = []

            # 1. img-атрибуты
            imgs = picture.locator("img")
            img_count = await imgs.count()

            alt: str | None = None

            for j in range(img_count):
                img = imgs.nth(j)

                if alt is None:
                    alt = await img.get_attribute("alt")

                for attr in ["data-original", "data-src", "data-lazy", "src"]:
                    value = await img.get_attribute(attr)
                    if value:
                        candidates.append(value)

            # 2. source/srcset внутри этого же picture
            sources = picture.locator("source[srcset]")
            source_count = await sources.count()

            for j in range(source_count):
                srcset = await sources.nth(j).get_attribute("srcset")
                candidates.extend(self._extract_srcset_urls(srcset))

            best = self._pick_best_candidate(candidates, page_url)

            if not best:
                continue

            if best in seen_urls:
                continue

            seen_urls.add(best)
            if counter:
                seen_counters.add(counter)

            result.append(
                CollectedImage(
                    url=best,
                    alt=self._clean_text(alt) if alt else None,
                    source=f".cat-detail__pics picture.cat-detail__pic[counter={counter}]",
                )
            )

        return result

    def _extract_srcset_urls(self, srcset: str | None) -> list[str]:
        if not srcset:
            return []

        urls: list[str] = []

        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue

            # srcset формат: "url 1x" или "url 800w"
            url = part.split()[0].strip()
            if url:
                urls.append(url)

        return urls

    def _pick_best_candidate(self, candidates: list[str], page_url: str) -> str | None:
        normalized: list[str] = []

        for candidate in candidates:
            url = urljoin(page_url, candidate.strip())

            if not self._looks_like_product_image(url):
                continue

            if url not in normalized:
                normalized.append(url)

        if not normalized:
            return None

        def score(url: str) -> tuple[int, int]:
            lower = url.lower()

            s = 0

            # Оригинал обычно лучше resize_cache.
            if "/upload/iblock/" in lower:
                s += 1000

            # resize_cache тоже ок, но это уже производная версия.
            if "/upload/resize_cache/" in lower:
                s += 500

            # Избегаем слишком маленьких превью.
            bad_size_parts = [
                "/50_",
                "/80_",
                "/100_",
                "/120_",
                "/150_",
                "/200_",
                "/250_",
            ]
            if any(part in lower for part in bad_size_parts):
                s -= 300

            # Пытаемся угадать большие размеры из URL.
            # Например resize_cache/.../900_1200_...
            import re

            numbers = [int(x) for x in re.findall(r"(?<!\d)(\d{2,4})(?!\d)", lower)]
            size_bonus = max(numbers) if numbers else 0

            return s, size_bonus

        return max(normalized, key=score)

    def _looks_like_product_image(self, url: str) -> bool:
        lower = url.lower()

        # Убираем webp как альтернативный формат, чтобы не плодить дубли.
        if ".webp" in lower:
            return False

        if not any(ext in lower for ext in [".jpg", ".jpeg", ".png"]):
            return False

        good_parts = [
            "/upload/iblock/",
            "/upload/resize_cache/",
            "/upload/",
        ]

        if not any(part in lower for part in good_parts):
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
            "star",
            "rating",
            "favicon",
        ]

        return not any(part in lower for part in bad_parts)

    async def _text_or_none(self, page: Page, selector: str) -> str | None:
        loc = page.locator(selector)

        if await loc.count() == 0:
            return None

        try:
            text = await loc.first.inner_text(timeout=5000)
        except Exception:
            return None

        text = self._clean_text(text)

        return text or None

    def _looks_like_product_image(self, url: str) -> bool:
        lower = url.lower()

        if not any(ext in lower for ext in [".jpg", ".jpeg", ".png"]):
            return False

        # Специально не разрешаем webp, потому что они у тебя сейчас лишние.
        if ".webp" in lower:
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
            "star",
            "rating",
        ]

        return not any(part in lower for part in bad_parts)

    def _looks_like_description(self, text: str) -> bool:
        if not text:
            return False

        lower = text.lower()

        bad_parts = [
            "таблица размеров",
            "как снять мерки",
            "подобрать",
            "выбрать вручную",
            "после оплаты",
            "скачать пример инструкции",
            "отзывы",
        ]

        if any(part in lower for part in bad_parts) and len(text) < 300:
            return False

        return len(text) > 80

    def _deduplicate_description(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        result: list[str] = []
        seen: set[str] = set()

        for line in lines:
            normalized = line.lower()
            if normalized in seen:
                continue

            seen.add(normalized)
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