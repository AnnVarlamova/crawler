import asyncio
import itertools
import random
from collections import defaultdict
from dataclasses import asdict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from config import (
    ALLOWED_DOMAINS,
    SEED_URLS,
    MAX_CONCURRENCY,
    MAX_PAGES_PER_SITE,
    MAX_DEPTH,
    NAV_TIMEOUT_MS,
    WAIT_AFTER_LOAD_MS,
    HEADLESS,
    RESPECT_DELAY_SEC,
    RESPECT_JITTER_MIN,
    RESPECT_JITTER_MAX,
    ITEMS_JSONL,
    CANDIDATES_JSONL,
    DATA_DIR,
    SITES_DIR,
    RAW_HTML_DIR,
    TEXT_DIR,
    IMAGES_DIR,
    FILES_DIR,
    JSONL_DIR,
    STATE_DIR,
    BLOCK_BROWSER_IMAGES,
    BLOCK_BROWSER_FONTS,
    BLOCK_BROWSER_MEDIA,
    BLOCK_BROWSER_STYLESHEETS,
    USE_ROBOTS_TXT,
)
from extractor import parse_page
from storage import append_jsonl, ensure_dirs
from utils import normalize_url, domain_of


def should_abort_resource(resource_type: str) -> bool:
    if resource_type == "image" and BLOCK_BROWSER_IMAGES:
        return True
    if resource_type == "font" and BLOCK_BROWSER_FONTS:
        return True
    if resource_type == "media" and BLOCK_BROWSER_MEDIA:
        return True
    if resource_type == "stylesheet" and BLOCK_BROWSER_STYLESHEETS:
        return True
    return False


class RobotsCache:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.cache: dict[str, RobotFileParser] = {}
        self.http = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 garment research crawler"},
            timeout=20,
            follow_redirects=True,
        )

    async def close(self):
        await self.http.aclose()

    async def allowed(self, url: str, user_agent: str = "*") -> bool:
        if not self.enabled:
            return True

        domain = domain_of(url)
        parser = self.cache.get(domain)
        if parser is None:
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            parser = RobotFileParser()
            try:
                resp = await self.http.get(robots_url)
                if resp.status_code == 200 and resp.text:
                    parser.parse(resp.text.splitlines())
                else:
                    # if robots.txt unavailable, do not block crawl
                    parser = RobotFileParser()
                    parser.parse([])
            except Exception:
                parser = RobotFileParser()
                parser.parse([])
            self.cache[domain] = parser

        try:
            return parser.can_fetch(user_agent, url)
        except Exception:
            return True


class CrawlState:
    def __init__(self):
        self.visited = set()
        self.enqueued = set()
        self.site_counts: dict[str, int] = {}
        self.queue: asyncio.PriorityQueue[tuple[int, int, int, str]] = asyncio.PriorityQueue()
        self._counter = itertools.count()

        # One in-flight page per domain
        self.domain_locks: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(1))

    async def enqueue(self, url: str, depth: int = 0, seed_priority: int = 0):
        url = normalize_url(url)
        if depth > MAX_DEPTH:
            return
        if not url.startswith("http"):
            return
        if domain_of(url) not in ALLOWED_DOMAINS:
            return
        if url in self.visited or url in self.enqueued:
            return
        if self.site_counts.get(domain_of(url), 0) >= MAX_PAGES_PER_SITE:
            return
        self.enqueued.add(url)
        order = next(self._counter)
        await self.queue.put((seed_priority, depth, order, url))


async def polite_sleep():
    await asyncio.sleep(
        RESPECT_DELAY_SEC + random.uniform(RESPECT_JITTER_MIN, RESPECT_JITTER_MAX)
    )


async def gentle_scroll(page):
    for _ in range(4):
        await page.mouse.wheel(0, 1500)
        await page.wait_for_timeout(350)


async def fetch_rendered_html(page, url: str):
    await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
    await gentle_scroll(page)
    for attempt in range(3):
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        await page.wait_for_timeout(500 + attempt * 300)
        try:
            return await page.content(), page.url
        except Exception as e:
            if "page is navigating" not in str(e).lower() or attempt == 2:
                raise
    return await page.content(), page.url


def should_follow(link: str) -> bool:
    low = link.lower()

    deny = [
        "/cart", "/checkout", "/login", "/account", "/wishlist",
        "privacy", "policy", "terms", "refund", "contact", "faq",
        "/forum", "/community", "/feed", "/wp-json",
        "/search", "?s=", "add-to-cart", "customer-service",
    ]
    if any(x in low for x in deny):
        return False

    allow_hints = [
        "dress", "skirt", "coat", "jacket", "shirt", "pants", "trousers",
        "pattern", "product", "shop", "collection", "collections",
        "vikroj", "vykroj", "vikroyki", "vykrojki", "catalog", "category",
        "blog", "tag", "couture", "analysis", "free-sewing-patterns",
        "sewing-pattern", "pdf", "marfy", "stylearc", "tessuti",
    ]
    return any(x in low for x in allow_hints)


async def install_safe_routing(context):
    async def _route(route):
        if should_abort_resource(route.request.resource_type):
            await route.abort()
        else:
            await route.continue_()

    await context.route("**/*", _route)


async def worker(state: CrawlState, context, robots: RobotsCache, worker_id: int):
    try:
        page = await context.new_page()
    except Exception as e:
        print(f"[worker-init-error] worker={worker_id} error={e}", flush=True)
        return

    while True:
        try:
            seed_priority, depth, _, url = await state.queue.get()
            try:
                d = domain_of(url)
                if depth > MAX_DEPTH:
                    continue
                if state.site_counts.get(d, 0) >= MAX_PAGES_PER_SITE:
                    continue
                if not await robots.allowed(url):
                    print(f"[robots-skip] {url}", flush=True)
                    continue

                lock = state.domain_locks[d]

                async with lock:
                    state.visited.add(url)
                    state.site_counts[d] = state.site_counts.get(d, 0) + 1

                    await polite_sleep()

                    try:
                        html, final_url = await fetch_rendered_html(page, url)
                    except PlaywrightTimeout:
                        print(f"[timeout] {url}", flush=True)
                        continue
                    except Exception as e:
                        print(f"[nav-error] {url} -> {e}", flush=True)
                        continue

                    item = await parse_page(url, final_url, html)
                    await append_jsonl(ITEMS_JSONL, asdict(item))

                    high_value = (
                        item.download and
                        len(item.assets.image_urls) > 0 and
                        (
                            len(item.assets.file_urls) > 0
                            or len(item.assets.tech_drawing_urls) > 0
                            or item.source_adapter in {"thecuttingclass", "patternvault"}
                        )
                    )
                    if high_value:
                        await append_jsonl(CANDIDATES_JSONL, asdict(item))

                    if item.relevant:
                        for link in item.discovered_links:
                            if should_follow(link):
                                await state.enqueue(link, depth + 1, seed_priority=seed_priority)

                    print(
                        f"[ok] worker={worker_id} domain={d} depth={depth} "
                        f"adapter={item.source_adapter} page_type={item.page_type} "
                        f"relevant={item.relevant} download={item.download} url={item.final_url}"
                        ,
                        flush=True,
                    )

            finally:
                state.queue.task_done()

        except asyncio.CancelledError:
            break

    await page.close()


async def main():
    ensure_dirs([DATA_DIR, SITES_DIR, RAW_HTML_DIR, TEXT_DIR, IMAGES_DIR, FILES_DIR, JSONL_DIR, STATE_DIR])

    state = CrawlState()
    for idx, url in enumerate(SEED_URLS):
        await state.enqueue(url, 0, seed_priority=idx)
    print(
        f"[start] seeds={len(SEED_URLS)} enqueued={state.queue.qsize()} "
        f"workers={MAX_CONCURRENCY} max_depth={MAX_DEPTH}",
        flush=True,
    )

    robots = RobotsCache(enabled=USE_ROBOTS_TXT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            accept_downloads=True,
            locale="ru-RU",
            viewport={"width": 1440, "height": 2200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        await install_safe_routing(context)

        workers = [asyncio.create_task(worker(state, context, robots, i)) for i in range(MAX_CONCURRENCY)]

        join_task = asyncio.create_task(state.queue.join())
        done, _ = await asyncio.wait([join_task, *workers], return_when=asyncio.FIRST_COMPLETED)

        # Queue drained normally.
        if join_task in done:
            pass
        else:
            # At least one worker terminated unexpectedly while queue still has work.
            for w in workers:
                if w.done() and not w.cancelled():
                    exc = w.exception()
                    if exc:
                        print(f"[worker-crash] {exc}", flush=True)
            if not join_task.done():
                join_task.cancel()
            raise RuntimeError("Workers terminated before crawl queue was fully processed")

        for w in workers:
            w.cancel()

        await context.close()
        await browser.close()
        await robots.close()


if __name__ == "__main__":
    asyncio.run(main())
