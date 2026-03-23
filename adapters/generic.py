from .base import BaseAdapter


class GenericAdapter(BaseAdapter):
    name = "generic"

    def match(self, domain: str) -> bool:
        return True