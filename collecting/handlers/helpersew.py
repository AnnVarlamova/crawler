from __future__ import annotations

import logging
import re
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
        difficulty_text = await self._difficulty_text(page)
        difficulty = self._difficulty_to_number(difficulty_text)
        description = await self._description(page)
        images = await self._images(page, record.url)

        logger.debug(
            "Parsed Helpersew product title=%r difficulty=%r difficulty_text=%r images=%s url=%s",
            title,
            difficulty,
            difficulty_text,
            len(images),
            record.url,
        )

        raw_sections = {}

        if description:
            raw_sections["Описание"] = description

        if difficulty_text:
            raw_sections["Сложность"] = difficulty_text

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
                "difficulty_text": difficulty_text,
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

        if any(part in lower_text for part in bad_text_parts):
            return True

        return False

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

    async def _difficulty_text(self, page: Page) -> str | None:
        selectors = [
            ".cat-detail-difficult",
            ".cat-detail__difficult",
            "[class*='difficult']",
        ]

        for selector in selectors:
            text = await self._text_or_none(page, selector)
            if text and "слож" in text.lower():
                return self._normalize_difficulty_text(text)

        body_text = self._clean_text(await page.locator("body").inner_text())
        match = re.search(
            r"уровень\s+сложности\s*:\s*([А-Яа-яA-Za-z0-9\s\-]+)",
            body_text,
            flags=re.IGNORECASE,
        )

        if match:
            return self._normalize_difficulty_text(match.group(0))

        return None

    def _difficulty_to_number(self, difficulty_text: str | None) -> int | None:
        """
        У Helpersew сложность текстовая:
        - простой / низкий / легкий -> 1
        - средний -> 3
        - сложный / высокий -> 5

        В metadata сохраняем число для общего поля difficulty,
        а исходный текст кладём в raw["difficulty_text"].
        """
        if not difficulty_text:
            return None

        lower = difficulty_text.lower()

        if any(word in lower for word in ["простой", "низкий", "лёгкий", "легкий", "начальный"]):
            return 1

        if "сред" in lower:
            return 3

        if any(word in lower for word in ["слож", "высок"]):
            return 5

        return None

    def _normalize_difficulty_text(self, text: str) -> str:
        text = self._clean_text(text)
        text = text.replace("Уровень сложности :", "Уровень сложности:")
        text = text.replace("Уровень сложности:", "Уровень сложности: ")
        text = re.sub(r"\s+", " ", text).strip()
        text = text.replace(":  ", ": ")
        return text

    async def _description(self, page: Page) -> str | None:
        """
        По DOM описание находится здесь:

        .cat-detail-t-cont
          .cat-detail-t-cont-wrap
            .cat-detail-t-cont-item.active

        Там текст может быть прямо текстовыми нодами + <br>.
        inner_text() должен собрать его нормально.
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
                text = self._clean_text(await loc.nth(i).inner_text())

                if self._looks_like_description(text):
                    candidates.append(text)

            if candidates:
                break

        if not candidates:
            return None

        return self._deduplicate_description(candidates[0])

    async def _images(self, page: Page, page_url: str) -> list[CollectedImage]:
        """
        Helpersew хранит фото в блоке:

        .cat-detail__pics
          picture.cat-detail__pic.loaded
          picture.cat-detail__pic.check.loaded

        Внутри могут быть img[src] и source[srcset].
        Берём только изображения из карточки, чтобы не прихватить логотипы.
        """
        result: list[CollectedImage] = []
        seen: set[str] = set()

        img_selectors = [
            ".cat-detail__pics picture.cat-detail__pic img[src]",
            ".cat-detail__pics .cat-detail__pic img[src]",
            ".cat-detail__pics img[src]",
            ".cat-detail__l-wrap img[src]",
            ".cat-detail img[src]",
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
            ".cat-detail__pics picture.cat-detail__pic source[srcset]",
            ".cat-detail__pics source[srcset]",
            ".cat-detail source[srcset]",
        ]

        for selector in source_selectors:
            loc = page.locator(selector)
            count = await loc.count()

            for i in range(count):
                srcset = await loc.nth(i).get_attribute("srcset")
                url = self._best_from_srcset(srcset)

                if not url:
                    continue

                url = urljoin(page_url, url.strip())

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

        text = await loc.first.inner_text()
        text = self._clean_text(text)

        return text or None

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