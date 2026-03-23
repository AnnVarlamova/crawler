import re
from .base import BaseAdapter
from utils import text_norm


class VikisewsAdapter(BaseAdapter):
    name = "vikisews"

    def match(self, domain: str) -> bool:
        return domain == "vikisews.com"

    def extract_custom_fields(self, soup, base_url):
        text = self.extract_text(soup)
        price = ""
        node = soup.select_one(".price, [data-price], .product-price")
        if node:
            price = text_norm(node.get_text(" ", strip=True))

        size_info = []
        for el in soup.select(".size-guide, .sizes, .product-sizes, [class*='size']"):
            t = text_norm(el.get_text(" ", strip=True))
            if t and len(t) < 400:
                size_info.append(t)

        fabric = []
        for heading in soup.select("h2, h3, h4"):
            h = text_norm(heading.get_text(" ", strip=True)).lower()
            if "fabric" in h or "материал" in h or "ткан" in h:
                nxt = heading.find_next(["p", "div", "ul"])
                if nxt:
                    fabric.append(text_norm(nxt.get_text(" ", strip=True)))

        notes = []
        for term in ["bust darts", "princess seams", "bias", "lining", "waist darts", "center seam"]:
            if term in text.lower():
                notes.append(term)

        return {
            "designer": "",
            "collection": "",
            "season": "",
            "year": "",
            "difficulty": "",
            "product_code": "",
            "price_text": price,
            "pattern_format": ["pdf"],
            "size_info": size_info[:10],
            "fabric_recommendations": fabric[:10],
            "construction_notes": notes,
        }


class GrasserAdapter(BaseAdapter):
    name = "grasser"

    def match(self, domain: str) -> bool:
        return domain == "grasser.ru"

    def extract_custom_fields(self, soup, base_url):
        text = self.extract_text(soup)
        product_code = ""
        m = re.search(r"(?:арт\.?|article)\s*[:#]?\s*([A-Za-zА-Яа-я0-9\-]+)", text, re.I)
        if m:
            product_code = m.group(1)

        price = ""
        node = soup.select_one(".price, .product-price")
        if node:
            price = text_norm(node.get_text(" ", strip=True))

        return {
            "designer": "",
            "collection": "",
            "season": "",
            "year": "",
            "difficulty": "",
            "product_code": product_code,
            "price_text": price,
            "pattern_format": ["pdf"] if "pdf" in text.lower() else [],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": [],
        }


class SimpleProductAdapter(BaseAdapter):
    def __init__(self, domain_name: str, adapter_name: str):
        self.domain_name = domain_name
        self.name = adapter_name

    def match(self, domain: str) -> bool:
        return domain == self.domain_name