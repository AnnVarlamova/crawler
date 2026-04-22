from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)


async def detect_country_code() -> str | None:
    urls = [
        "https://ipapi.co/json/",
        "https://ipinfo.io/json",
    ]

    for url in urls:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    data = await resp.json()

            country = (
                data.get("country")
                or data.get("country_code")
                or data.get("countryCode")
            )

            if country:
                code = str(country).upper()
                logger.info("[geo] detected country=%s via %s", code, url)
                return code

        except Exception as e:
            logger.warning("[geo] failed via %s: %s", url, e)

    logger.warning("[geo] failed to detect country")
    return None


def is_ru_country(country_code: str | None) -> bool:
    # safer: если страну не удалось определить, считаем RU
    return country_code is None or str(country_code).upper() == "RU"