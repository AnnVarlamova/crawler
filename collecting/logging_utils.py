from __future__ import annotations

import logging
import sys

from collecting.config import DETAILED_LOG_FILE, GENERAL_LOG_FILE


def setup_logging() -> logging.Logger:
    DETAILED_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    GENERAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("collecting")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    general_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    detailed_file_handler = logging.FileHandler(
        DETAILED_LOG_FILE,
        encoding="utf-8",
    )
    detailed_file_handler.setLevel(logging.DEBUG)
    detailed_file_handler.setFormatter(detailed_formatter)

    general_file_handler = logging.FileHandler(
        GENERAL_LOG_FILE,
        encoding="utf-8",
    )
    general_file_handler.setLevel(logging.INFO)
    general_file_handler.setFormatter(general_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(general_formatter)

    logger.addHandler(detailed_file_handler)
    logger.addHandler(general_file_handler)
    logger.addHandler(console_handler)

    return logger