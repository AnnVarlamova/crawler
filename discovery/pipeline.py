from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections import defaultdict

from discovery import runtime
from discovery.browser_sites.runner import run_browser_spec
from discovery.config import DISCOVERED_FILE, ERRORS_FILE, SITE_ERROR_LIMIT, SITE_SPECS
from discovery.logging_setup import configure_logging
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


def parse_args() -> tuple[set[str], bool, str]:
    requested_specs: set[str] = set()
    verbose = False
    net_mode = "ru"

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--spec" and i + 1 < len(argv):
            requested_specs.add(argv[i + 1])
            i += 2
        elif argv[i] == "--verbose":
            verbose = True
            i += 1
        elif argv[i] == "--net" and i + 1 < len(argv):
            net_mode = argv[i + 1].strip().lower()
            if net_mode not in {"ru", "en"}:
                raise ValueError(f"Unsupported --net value: {net_mode}. Use ru or en.")
            i += 2
        else:
            i += 1

    return requested_specs, verbose, net_mode


async def run_pagination_stub(spec_name: str, spec: dict) -> list[str]:
    runlog.info("SKIP  pagination-stub %s", spec_name)
    logger.info("[pagination-stub] skip spec=%s url=%s", spec_name, spec["start_url"])
    return []


async def async_main() -> int:
    requested_specs, verbose, net_mode = parse_args()
    configure_logging(verbose=verbose)

    state = load_state()

    failures: list[dict] = []
    site_failures: dict[str, list[str]] = defaultdict(list)

    runlog.info(
        "START discovery requested=%s net=%s",
        ",".join(sorted(requested_specs)) if requested_specs else "all",
        net_mode,
    )
    logger.info("Starting discovery pipeline")
    logger.info("Specs to run: %s", ", ".join(requested_specs) if requested_specs else "all")
    logger.info("Network mode: %s", net_mode)

    total_specs = 0
    success_specs = 0

    for spec_name, spec in SITE_SPECS.items():
        if runtime.STOP_REQUESTED:
            break

        if requested_specs and spec_name not in requested_specs:
            continue

        total_specs += 1

        site_host = get_site_host(spec["start_url"])
        if is_site_blocked(state, site_host):
            msg = f"blocked site={site_host} spec={spec_name}"
            logger.warning("[SKIP] %s", msg)
            runlog.info("SKIP  %s %s blocked", spec["site"], spec_name)
            failures.append(
                {
                    "spec_name": spec_name,
                    "site": spec["site"],
                    "reason": "blocked",
                }
            )
            site_failures[spec["site"]].append(spec_name)
            continue

        logger.info(
            "[RUN] spec=%s type=%s url=%s net=%s",
            spec_name,
            spec["type"],
            spec["start_url"],
            net_mode,
        )
        runlog.info("RUN   %s %s net=%s", spec["site"], spec_name, net_mode)

        try:
            if spec["type"] == "browser":
                links = await run_browser_spec(spec_name, spec, net_mode=net_mode)
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
                        "site": spec["site"],
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
            runlog.info(
                "OK    %s %s collected=%s new_unique=%s",
                spec["site"],
                spec_name,
                len(links),
                new_unique,
            )
            record_site_success(state, site_host)

        except Exception as e:
            count = record_site_error(state, site_host)

            append_jsonl(
                ERRORS_FILE,
                {
                    "phase": "pipeline",
                    "spec_name": spec_name,
                    "site": spec["site"],
                    "page_url": spec["start_url"],
                    "error": str(e),
                    "net_mode": net_mode,
                },
            )

            logger.exception("[FAIL] spec=%s", spec_name)
            runlog.info("FAIL  %s %s error=%s", spec["site"], spec_name, str(e))

            failures.append(
                {
                    "spec_name": spec_name,
                    "site": spec["site"],
                    "reason": str(e),
                }
            )
            site_failures[spec["site"]].append(spec_name)

            if count >= SITE_ERROR_LIMIT:
                logger.warning("[BLOCK] site=%s errors=%s", site_host, count)

            continue

    logger.info("[DONE] discovery finished")
    runlog.info("DONE  discovery success_specs=%s total_specs=%s failures=%s", success_specs, total_specs, len(failures))

    if failures:
        logger.warning("Failed specs summary:")
        for item in failures:
            logger.warning(
                "  site=%s spec=%s reason=%s",
                item["site"],
                item["spec_name"],
                item["reason"],
            )

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