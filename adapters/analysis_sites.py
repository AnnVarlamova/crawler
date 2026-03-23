import re
from .base import BaseAdapter


class CuttingClassAdapter(BaseAdapter):
    name = "thecuttingclass"

    def match(self, domain: str) -> bool:
        return domain in {"thecuttingclass.com", "www.thecuttingclass.com"}

    def extract_custom_fields(self, soup, base_url):
        text = self.extract_text(soup)
        title, _ = self.extract_title_meta(soup)

        designer = ""
        m = re.search(r"\b(Balenciaga|Dior|Schiaparelli|Chanel|YSL|Saint Laurent|Margiela|Yohji Yamamoto)\b", title + " " + text, re.I)
        if m:
            designer = m.group(1)

        season = ""
        year = ""
        m = re.search(r"\b(Spring|Fall|Autumn|Summer|Resort|Pre[- ]?Fall|AW|SS)\b.*?\b(19\d{2}|20\d{2})\b", title + " " + text, re.I)
        if m:
            season = m.group(1)
            year = m.group(2)

        construction_terms = []
        for term in [
            "seam", "panel", "drape", "grainline", "bias cut", "armhole",
            "princess seam", "shoulder slope", "collar", "dart", "hip", "waist"
        ]:
            if term in text.lower():
                construction_terms.append(term)

        return {
            "designer": designer,
            "collection": title,
            "season": season,
            "year": year,
            "difficulty": "advanced",
            "product_code": "",
            "price_text": "",
            "pattern_format": ["analysis"],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": construction_terms,
        }


class PatternVaultAdapter(BaseAdapter):
    name = "patternvault"

    def match(self, domain: str) -> bool:
        return domain == "blog.pattern-vault.com"

    def extract_custom_fields(self, soup, base_url):
        title, _ = self.extract_title_meta(soup)
        text = self.extract_text(soup)

        designer = ""
        season = ""
        year = ""

        m = re.search(r"\b(Balenciaga|Dior|Schiaparelli|Chanel|McQueen|Givenchy|Mugler|Valentino|Rahul Mishra|Yohji Yamamoto)\b", title, re.I)
        if m:
            designer = m.group(1)

        m = re.search(r"\b(Spring|Fall|Autumn|Summer|Resort|Pre[- ]?Fall|AW|SS)\b.*?\b(19\d{2}|20\d{2})\b", title, re.I)
        if m:
            season = m.group(1)
            year = m.group(2)

        return {
            "designer": designer,
            "collection": title,
            "season": season,
            "year": year,
            "difficulty": "",
            "product_code": "",
            "price_text": "",
            "pattern_format": ["article", "collection", "reference"],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": [],
        }