from __future__ import annotations

from collecting.handlers.base import CollectingHandler
from collecting.handlers.burdastyle import BurdaStyleCollectingHandler


HANDLERS: dict[str, type[CollectingHandler]] = {
    "burdastyle": BurdaStyleCollectingHandler,
}