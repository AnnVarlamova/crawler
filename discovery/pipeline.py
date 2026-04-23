from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections import defaultdict

from discovery import runtime
from discovery.browser_sites.runner import run_browser_spec
from discovery.config import (
    DISCOVERED_FILE,
    ERRORS_FILE,
    SITE_ERROR_LIMIT,
    SITE_SPECS,
    SPEC_GROUPS,
    VPN_SITES,
)
from discovery.logging_setup import configure_logging
from discovery.net import detect_country_code, is_ru_country
from discovery.state import load_state
from discovery.utils import append_jsonl, append_jsonl_unique, get_site_host

logger = logging.getLogger(__name__)
runlog = logging.getLogger("discovery.run")


def _handle_stop(signum, frame):
    runtime.STOP_REQUESTED = True
    logger.warning("Stop requested. Waiting for current task to finish safely...")


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


def is_site_blocked(state, site_host: str) -> bool:
    return state.site_error_counts.get(site_host, 0) >= SITE_ERROR_LIMIT


def record_site_success(state, site_host: str) -> None:
    if state.site_error_counts.get(site_host, 0):
        state.site_error_counts[site_host] = 0


def record_site_error(state, site_host: str) -> int:
    current = state.site_error_counts.get(site_host, 0) + 1
    state.site_error_counts[site_host] = current
    return current


def should_skip_by_country(site_name: str, is_ru: bool) -> bool:
    is_vpn_site = site_name in VPN_SITES
    if is_ru:
        return is_vpn_site
    return not is_vpn_site


def parse_args() -> tuple[set[str], bool]:
    requested_specs: set[str] = set()
    requested_groups: set[str] = set()
    verbose = False

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--spec" and i + 1 < len(argv):
            requested_specs.add(argv[i + 1])
            i += 2
        elif argv[i] == "--group" and i + 1 < len(argv):
            requested_groups.add(argv[i + 1])
            i += 2
        elif argv[i] == "--verbose":
            verbose = True
            i += 1
        else:
            i += 1

    expanded_specs = set(requested_specs)
    for group_name in requested_groups:
        group_specs = SPEC_GROUPS.get(group_name)
        if group_specs:
            expanded_specs.update(group_specs)
        else:
            print(f"[WARN] unknown group: {group_name}")

    return expanded_specs, verbose


async def run_pagination_stub(spec_name: str, spec: dict) -> list[str]:
    runlog.info("SKIP  pagination-stub %s", spec_name)
    logger.info("[pagination-stub] skip spec=%s url=%s", spec_name, spec["start_url"])
    return []


async def async_main() -> int:
    requested_specs, verbose = parse_args()
    configure_logging(verbose=verbose)

    state = load_state()

    failures: list[dict] = []
    site_failures: dict[str, list[str]] = defaultdict(list)

    country_code = await detect_country_code()
    is_ru = is_ru_country(country_code)

    runlog.info(
        "START discovery requested=%s country=%s ru=%s",
        ",".join(sorted(requested_specs)) if requested_specs else "all",
        country_code or "unknown",
        is_ru,
    )
    logger.info("Starting discovery pipeline")
    logger.info("Specs to run: %s", ", ".join(sorted(requested_specs)) if requested_specs else "all")
    logger.info("Detected country: %s", country_code or "unknown")
    logger.info("RU mode: %s", is_ru)
    logger.info("VPN sites: %s", ", ".join(sorted(VPN_SITES)) if VPN_SITES else "-")

    total_specs = 0
    success_specs = 0
    skipped_specs = 0

    for spec_name, spec in SITE_SPECS.items():
        if runtime.STOP_REQUESTED:
            break

        if requested_specs and spec_name not in requested_specs:
            continue

        total_specs += 1

        site_name = spec["site"]
        site_host = get_site_host(spec["start_url"])

        logger.info(
            "[CHECK] spec=%s site=%s country=%s is_ru=%s vpn_site=%s",
            spec_name,
            site_name,
            country_code or "unknown",
            is_ru,
            site_name in VPN_SITES,
        )

        if should_skip_by_country(site_name, is_ru):
            logger.info(
                "[SKIP] spec=%s site=%s skipped_by_country country=%s is_ru=%s vpn_site=%s",
                spec_name,
                site_name,
                country_code or "unknown",
                is_ru,
                site_name in VPN_SITES,
            )
            runlog.info(
                "SKIP  %s %s country=%s is_ru=%s vpn_site=%s",
                site_name,
                spec_name,
                country_code or "unknown",
                is_ru,
                site_name in VPN_SITES,
            )
            skipped_specs += 1
            continue

        if is_site_blocked(state, site_host):
            msg = f"blocked site={site_host} spec={spec_name}"
            logger.warning("[SKIP] %s", msg)
            runlog.info("SKIP  %s %s blocked", site_name, spec_name)
            failures.append({"spec_name": spec_name, "site": site_name, "reason": "blocked"})
            site_failures[site_name].append(spec_name)
            continue

        logger.info(
            "[RUN] spec=%s type=%s url=%s country=%s",
            spec_name,
            spec["type"],
            spec["start_url"],
            country_code or "unknown",
        )
        runlog.info("RUN   %s %s country=%s", site_name, spec_name, country_code or "unknown")

        try:
            if spec["type"] == "browser":
                links = await run_browser_spec(spec_name, spec)
            elif spec["type"] == "pagination":
                links = await run_pagination_stub(spec_name, spec)
            else:
                raise RuntimeError(f"unknown spec type: {spec['type']}")

            new_unique = 0
            for link in links:
                added = append_jsonl_unique(
                    DISCOVERED_FILE,
                    {
                        "url": link,
                        "site": site_name,
                        "source_page": spec["start_url"],
                        "category": spec["category"],
                        "spec_name": spec_name,
                    },
                    key="url",
                    existing_keys=state.discovered_urls,
                )
                if added:
                    new_unique += 1

            success_specs += 1
            logger.info(
                "[DONE] spec=%s collected=%s new_unique=%s total_unique=%s",
                spec_name,
                len(links),
                new_unique,
                len(state.discovered_urls),
            )
            runlog.info("OK    %s %s collected=%s new_unique=%s", site_name, spec_name, len(links), new_unique)
            record_site_success(state, site_host)

        except Exception as e:
            count = record_site_error(state, site_host)

            append_jsonl(
                ERRORS_FILE,
                {
                    "phase": "pipeline",
                    "spec_name": spec_name,
                    "site": site_name,
                    "page_url": spec["start_url"],
                    "error": str(e),
                    "country_code": country_code,
                    "is_ru": is_ru,
                    "vpn_site": site_name in VPN_SITES,
                },
            )

            logger.exception("[FAIL] spec=%s", spec_name)
            runlog.info("FAIL  %s %s error=%s", site_name, spec_name, str(e))

            failures.append({"spec_name": spec_name, "site": site_name, "reason": str(e)})
            site_failures[site_name].append(spec_name)

            if count >= SITE_ERROR_LIMIT:
                logger.warning("[BLOCK] site=%s errors=%s", site_host, count)

            continue

    logger.info("[DONE] discovery finished")
    runlog.info(
        "DONE  discovery success_specs=%s total_specs=%s skipped_specs=%s failures=%s",
        success_specs,
        total_specs,
        skipped_specs,
        len(failures),
    )

    if failures:
        logger.warning("Failed specs summary:")
        for item in failures:
            logger.warning("  site=%s spec=%s reason=%s", item["site"], item["spec_name"], item["reason"])

        runlog.info("SUMMARY failed_sites=%s", ",".join(sorted(site_failures.keys())))
        for site, specs in sorted(site_failures.items()):
            runlog.info("SUMMARY %s failed_specs=%s", site, ",".join(sorted(specs)))
        return 1

    runlog.info("SUMMARY all_ok")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()