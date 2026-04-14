from __future__ import annotations

import logging

from discovery.config import DETAILED_LOG_DIR, GENERAL_LOG_DIR
from discovery.utils import ensure_dir


class IncludeLoggerPrefixFilter(logging.Filter):
    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self.prefix)


def configure_logging(verbose: bool = False) -> None:
    ensure_dir(DETAILED_LOG_DIR)
    ensure_dir(GENERAL_LOG_DIR)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    detailed_file = DETAILED_LOG_DIR / "discovery_detailed.log"
    concise_file = GENERAL_LOG_DIR / "discovery.log"

    detailed_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    concise_fmt = logging.Formatter(
        "%(asctime)s | %(message)s"
    )
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s"
    )

    fh_detailed = logging.FileHandler(detailed_file, encoding="utf-8")
    fh_detailed.setLevel(logging.DEBUG)
    fh_detailed.setFormatter(detailed_fmt)

    fh_concise = logging.FileHandler(concise_file, encoding="utf-8")
    fh_concise.setLevel(logging.INFO)
    fh_concise.setFormatter(concise_fmt)
    fh_concise.addFilter(IncludeLoggerPrefixFilter("discovery.run"))

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh.setFormatter(console_fmt)
    sh.addFilter(IncludeLoggerPrefixFilter("discovery"))

    root.addHandler(fh_detailed)
    root.addHandler(fh_concise)
    root.addHandler(sh)

    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)