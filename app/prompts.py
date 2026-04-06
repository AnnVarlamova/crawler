from __future__ import annotations

import json

from app.config import BASE_TAGS
from app.models import ProductCard


def make_discovery_prompt(start_url: str, limit: int) -> str:
    return f"""
Open this site: {start_url}

Your goal:
Find individual product pages for adult sewing/clothing patterns.

Important constraints:
- Work ONLY inside the allowed domain.
- Return ONLY concrete product/item pages, not category pages.
- Focus on WOMEN'S and MEN'S clothing.
- Exclude:
  - children / kids / baby / teen
  - accessories
  - bags, hats, scarves, belts, gloves, socks
  - toys, dolls, pets
  - home decor, quilts, crafts
  - articles/blog/editorial pages unless they clearly correspond to one concrete garment pattern page
- Prefer pages with finished garment photos and product/pattern description.
- Return up to {limit} unique absolute URLs.

Output only the structured result.
""".strip()


def make_product_prompt(product_url: str) -> str:
    return f"""
Open this exact product page: {product_url}

Extract structured information for this item.

Rules:
- This should be an adult clothing item or clothing pattern page.
- Exclude children items and accessories.
- product_url must be exactly "{product_url}".
- source_site should be the site key inferred from the domain.
- Collect URLs of finished garment photos from different angles if available.
- Prefer photos of the garment, not technical drawings only.
- Put useful readable page text into raw_text.
- Leave unknown fields empty rather than inventing data.

Output only the structured result.
""".strip()


def make_tags_prompt(card: ProductCard) -> str:
    payload = json.dumps(card.model_dump(mode="json"), ensure_ascii=False, indent=2)
    vocab = ", ".join(BASE_TAGS)
    return f"""
Generate tags for this clothing item.

Allowed tag vocabulary:
{vocab}

Input item:
{payload}

Rules:
- Return 5 to 20 tags.
- lowercase
- hyphen-separated
- no duplicates
- prioritize garment type, fit, details, gender, season, style
- use vocabulary above whenever possible
- if a necessary tag is not in vocabulary, you may add a short normalized tag

Output only the structured result.
""".strip()