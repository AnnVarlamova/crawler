import json
from bs4 import BeautifulSoup


def extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    out = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                out.extend([x for x in obj if isinstance(x, dict)])
            elif isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def flatten_jsonld_nodes(nodes: list[dict]) -> list[dict]:
    out = []
    for node in nodes:
        if "@graph" in node and isinstance(node["@graph"], list):
            out.extend([x for x in node["@graph"] if isinstance(x, dict)])
        else:
            out.append(node)
    return out


def find_product_schema(nodes: list[dict]) -> dict | None:
    flat = flatten_jsonld_nodes(nodes)
    for node in flat:
        t = node.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return node
    return None


def extract_images_from_product_schema(product: dict | None) -> list[str]:
    if not product:
        return []
    imgs = product.get("image", [])
    if isinstance(imgs, str):
        return [imgs]
    if isinstance(imgs, list):
        return [x for x in imgs if isinstance(x, str)]
    return []


def extract_price_from_product_schema(product: dict | None) -> str:
    if not product:
        return ""
    offers = product.get("offers")
    if isinstance(offers, dict):
        return str(offers.get("price", "")).strip()
    if isinstance(offers, list) and offers:
        return str(offers[0].get("price", "")).strip()
    return ""