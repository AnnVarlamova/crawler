from __future__ import annotations

from collecting.handlers.base import CollectingHandler
from collecting.handlers.burdastyle import BurdaStyleCollectingHandler
from collecting.handlers.grasser import GrasserCollectingHandler
from collecting.handlers.helpersew import HelpersewCollectingHandler


HANDLERS: dict[str, type[CollectingHandler]] = {
    "burdastyle": BurdaStyleCollectingHandler,
    "grasser": GrasserCollectingHandler,
    "helpersew": HelpersewCollectingHandler,

    # Потом добавим:
    # "vikisews": VikisewsCollectingHandler,
    # "shkatulka": ShkatulkaCollectingHandler,
    # "simplicity": SimplicityCollectingHandler,
    # "marfy": MarfyCollectingHandler,
    # "etsy": EtsyCollectingHandler,
    # "helpersew": HelpersewCollectingHandler,
}