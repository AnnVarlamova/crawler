from __future__ import annotations

from collecting.handlers.base import CollectingHandler
from collecting.handlers.burdastyle import BurdaStyleCollectingHandler
from collecting.handlers.grasser import GrasserCollectingHandler
from collecting.handlers.helpersew import HelpersewCollectingHandler
from collecting.handlers.marfy import MarfyCollectingHandler


HANDLERS: dict[str, type[CollectingHandler]] = {
    "burdastyle": BurdaStyleCollectingHandler,
    "grasser": GrasserCollectingHandler,
    "helpersew": HelpersewCollectingHandler,
    "marfy": MarfyCollectingHandler,

    # Потом добавим:
    # "vikisews": VikisewsCollectingHandler,
    # "shkatulka": ShkatulkaCollectingHandler,
    # "simplicity": SimplicityCollectingHandler,
    # "etsy": EtsyCollectingHandler,
}