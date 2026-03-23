from .base import BaseAdapter


class SewistAdapter(BaseAdapter):
    name = "sewist"

    def match(self, domain: str) -> bool:
        return domain in {"sewist.com", "www.sewist.com"}

    def extract_custom_fields(self, soup, base_url):
        text = self.extract_text(soup).lower()
        notes = []
        if "3d" in text:
            notes.append("3d-preview")
        if "generator" in text:
            notes.append("generator")
        return {
            "designer": "",
            "collection": "",
            "season": "",
            "year": "",
            "difficulty": "",
            "product_code": "",
            "price_text": "",
            "pattern_format": ["generator", "pdf"] if "pdf" in text else ["generator"],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": notes,
        }


class BootstrapFashionAdapter(BaseAdapter):
    name = "bootstrapfashion"

    def match(self, domain: str) -> bool:
        return domain == "bootstrapfashion.com"

    def extract_custom_fields(self, soup, base_url):
        text = self.extract_text(soup).lower()
        notes = []
        if "made-to-measure" in text:
            notes.append("made-to-measure")
        if "designer" in text:
            notes.append("designer-source")
        return {
            "designer": "",
            "collection": "",
            "season": "",
            "year": "",
            "difficulty": "",
            "product_code": "",
            "price_text": "",
            "pattern_format": ["generator", "custom"],
            "size_info": [],
            "fabric_recommendations": [],
            "construction_notes": notes,
        }