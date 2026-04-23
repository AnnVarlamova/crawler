from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from discovery.browser_sites.common import (
    new_page,
    safe_close_context,
    safe_goto,
    save_dataset_links,
    wait_ms,
)
from discovery.config import build_etsy_search_url

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")

ETSY_CARD_SELECTORS = [
    ".js-merch-stash-check-listing",
    "[data-listing-card-v2]",
    "a[data-listing-link][href*='/listing/']",
]

ETSY_LINK_SELECTOR = "a[data-listing-link][href*='/listing/']"

BAD_TITLE_PATTERNS = [
    r"\bpdf\b",
    r"\bdigital\b",
    r"\bdownload\b",
    r"\bprintable\b",
    r"\binstant download\b",
    r"\bcrochet\b",
    r"\bknit\b",
    r"\bknitting\b",
    r"\bdoll\b",
    r"\bbaby\b",
    r"\bkids?\b",
    r"\bchild(?:ren)?\b",
    r"\btoddler\b",
    r"\bbundle\b",
    r"\blot\b",
    r"\bmagazine\b",
    r"\bbook\b",
    r"\bposter\b",
    r"\bwall art\b",
    r"\bclipart\b",
    r"\bsvg\b",
    r"\bpng\b",
    r"\bjpeg\b",
    r"\bjpg\b",
    r"\bmachine embroidery\b",
    r"\bembroidery design\b",
    r"\bquilt\b",
    r"\bquilting\b",
    r"\bcross stitch\b",
    r"\bapplique\b",
    r"\bpatch\b",
    r"\bhat\b",
    r"\bbag\b",
    r"\bpurse\b",
    r"\bwallet\b",
    r"\bscarf\b",
    r"\bsocks?\b",
    r"\bgloves?\b",
    r"\bshoes?\b",
    r"\btoy\b",
    r"\bpet\b",
    r"\bdog\b",
    r"\bcat\b",
    r"\bamerican girl\b",
    r"\b18 inch doll\b",
]

GOOD_CORE_PATTERNS = [
    r"\bvogue\b",
]

GOOD_SEWING_PATTERNS = [
    r"\bpattern\b",
    r"\bsewing\b",
    r"выкройк",
]

GARMENT_HINT_PATTERNS = [
    r"\bdress\b",
    r"\btop\b",
    r"\bblouse\b",
    r"\bshirt\b",
    r"\bskirt\b",
    r"\bpants?\b",
    r"\btrousers?\b",
    r"\bshorts?\b",
    r"\bjacket\b",
    r"\bvest\b",
    r"\bwaistcoat\b",
    r"\bjumpsuit\b",
    r"\bcoat\b",
    r"\bouterwear\b",
    r"\bhoodie\b",
    r"\bsweater\b",
    r"\bcardigan\b",
    r"\bblazer\b",
    r"\bbolero\b",
    r"\bculottes?\b",
    r"\bromper\b",
    r"плать",
    r"блуз",
    r"рубаш",
    r"юбк",
    r"брюк",
    r"шорт",
    r"жакет",
    r"жилет",
    r"пальт",
    r"комбинез",
]

BAD_URL_PATTERNS = [
    r"/market/",
    r"/shop/",
    r"/search\?",
]


def normalize_etsy_listing_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _title_is_good(title: str) -> bool:
    title_l = _normalize_text(title)

    if not title_l:
        return False

    if not _matches_any(title_l, GOOD_CORE_PATTERNS):
        return False

    if not _matches_any(title_l, GOOD_SEWING_PATTERNS):
        return False

    if _matches_any(title_l, BAD_TITLE_PATTERNS):
        return False

    if not _matches_any(title_l, GARMENT_HINT_PATTERNS):
        return False

    return True


def _href_is_good(href: str) -> bool:
    if not isinstance(href, str):
        return False
    if "/listing/" not in href:
        return False
    href_l = href.lower()
    if any(re.search(pattern, href_l) for pattern in BAD_URL_PATTERNS):
        return False
    return True


async def _dismiss_cookie_if_present(page: Page) -> None:
    candidates = [
        "Accept",
        "I agree",
        "I Agree",
        "Allow all",
        "Accept all",
        "Got it",
        "OK",
        "Принять",
        "Согласен",
    ]

    for text in candidates:
        try:
            locator = page.get_by_role("button", name=text)
            if await locator.count():
                await locator.first.click(timeout=2000)
                await wait_ms(page, 1200)
                logger.info("[etsy] cookie dismissed via button=%s", text)
                return
        except Exception:
            continue


async def _is_challenge_page(page: Page) -> bool:
    try:
        content = (await page.content()).lower()
    except Exception:
        content = ""

    url = page.url.lower()

    signals = [
        "captcha",
        "verify you are human",
        "are you a robot",
        "security check",
        "puzzle",
        "/checkpoint",
        "/captcha",
        "robot",
    ]

    if any(s in content for s in signals):
        return True
    if any(s in url for s in ["/checkpoint", "/captcha"]):
        return True

    return False


async def _wait_until_listing_or_manual_pass(page: Page) -> None:
    for _ in range(90):
        if await _is_challenge_page(page):
            logger.warning("[etsy] challenge detected, waiting for manual solve...")
            await wait_ms(page, 2000)
            continue

        for selector in ETSY_CARD_SELECTORS:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    logger.info("[etsy] listing detected via selector=%s count=%s", selector, count)
                    return
            except Exception:
                continue

        await wait_ms(page, 1000)

    logger.warning("[etsy] listing not detected after waiting")


async def _get_page_links(page: Page) -> list[str]:
    loc = page.locator(ETSY_LINK_SELECTOR)
    count = await loc.count()

    result: list[str] = []
    seen = set()

    for i in range(count):
        a = loc.nth(i)

        try:
            href = await a.get_attribute("href")
        except Exception:
            href = None

        if not href or not _href_is_good(href):
            continue

        title = ""
        try:
            title = await a.get_attribute("aria-label") or ""
        except Exception:
            title = ""

        if not title:
            try:
                title = await a.inner_text()
            except Exception:
                title = ""

        if not _title_is_good(title):
            logger.debug("[etsy] skip by title=%s", title)
            continue

        clean = normalize_etsy_listing_url(href)
        if clean in seen:
            continue

        seen.add(clean)
        result.append(clean)

    return result


async def run(browser: Browser, spec: dict) -> list[str]:
    context, page = await new_page(browser, height=1400)

    try:
        site = spec["site"]
        category = spec["category"]
        query = spec["query"]
        page_from = spec.get("page_from", 1)
        page_to = spec.get("page_to", 1)

        runlog.info("START etsy %s", category)

        all_links: list[str] = []
        seen = set()
        stagnant_rounds = 0

        for page_num in range(page_from, page_to + 1):
            page_url = build_etsy_search_url(query, page_num)
            logger.info("[etsy] open page=%s url=%s", page_num, page_url)

            await safe_goto(
                page,
                page_url,
                primary_wait_until="domcontentloaded",
                fallback_wait_until="commit",
            )
            await wait_ms(page, 1500)
            await _dismiss_cookie_if_present(page)
            await wait_ms(page, 1000)

            logger.info(
                "[etsy] debug cards=%s links=%s url=%s",
                await page.locator(".js-merch-stash-check-listing").count(),
                await page.locator(ETSY_LINK_SELECTOR).count(),
                page.url,
            )

            await _wait_until_listing_or_manual_pass(page)

            links = await _get_page_links(page)

            fresh_links: list[str] = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    all_links.append(link)
                    fresh_links.append(link)

            if fresh_links:
                save_dataset_links(
                    site=site,
                    category=category,
                    source_page=page_url,
                    links=fresh_links,
                )

            logger.info(
                "[etsy] page=%s found=%s fresh=%s total=%s",
                page_num,
                len(links),
                len(fresh_links),
                len(all_links),
            )

            if not fresh_links:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 4:
                logger.info("[etsy] stop by stagnant pages at page=%s", page_num)
                break

        runlog.info("DONE etsy %s total=%s", category, len(all_links))
        return all_links

    finally:
        await safe_close_context(context)