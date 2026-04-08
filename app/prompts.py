from __future__ import annotations

import json

from app.config import BASE_TAGS
from app.models import ProductCard


def make_discovery_prompt(page_url: str, product_limit: int, section_limit: int) -> str:
    return f"""
Open this exact page inside the allowed domain: {page_url}

Your goal:
Inspect the CURRENT page and return:
1) obvious product/item URLs for adult clothing sewing patterns
2) promising next section/listing/pagination URLs to continue discovery later

Important constraints:
- Work ONLY inside the same allowed domain.
- Prefer inferring product links from repeated product cards on the current page.
- Do NOT open every candidate product page just to verify it.
- If the current page is a category/listing/search page and several cards clearly represent valid garment patterns,
  collect those product URLs directly into product_urls.
- Add next_section_urls only for promising listing/category/pagination pages that are worth visiting later.
- Focus on WOMEN'S and MEN'S clothing.
- Exclude:
  - children / kids / baby / teen
  - accessories
  - bags, hats, scarves, belts, gloves, socks
  - toys, dolls, pets
  - home decor, quilts, crafts
  - articles/blog/editorial/help pages
  - account/cart/login/checkout/wishlist/search-policy pages
- Prefer pages with finished garment photos and product/pattern descriptions.
- Return up to {product_limit} unique absolute URLs in product_urls.
- Return up to {section_limit} unique absolute URLs in next_section_urls.
- Do not include duplicates across the two lists.
- product_urls must contain only concrete product pages.
- next_section_urls must contain only collection/listing/category/pagination pages.

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