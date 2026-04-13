from __future__ import annotations


def make_discovery_prompt(page_url: str, product_limit: int, section_limit: int) -> str:
    return f"""
Open this exact page inside the allowed domain: {page_url}

Your goal:
Inspect listing/category/search pages and return:
1) product_urls: direct URLs of individual sewing pattern product pages
2) next_section_urls: pagination/listing/category URLs worth visiting later

CRITICAL RULES:
- DO NOT open product pages.
- DO NOT click product cards for inspection.
- DO NOT analyze product details.
- DO NOT download images.
- DO NOT visit help/blog/account/cart/checkout pages.
- DO NOT leave the current section of the site.
- DO NOT spend multiple steps trying to repair a broken or timed-out page.
- If the page fails to load properly, do not keep retrying reload/buttons repeatedly.
- You may only:
  - inspect the current page
  - scroll if needed
  - open pagination/listing/category pages inside the same section if needed to discover links
- Prefer collecting product URLs directly from visible product cards, anchors, and repeated catalog elements.
- If the current page already shows repeated product cards/items, extract their direct links into product_urls immediately.
- Do NOT treat obvious product card links as next_section_urls.

CONTENT RULES:
- Focus only on WOMEN'S and MEN'S clothing sewing patterns.
- Exclude:
  - children / kids / baby / teen
  - accessories
  - bags, hats, scarves, belts, gloves, socks
  - toys, dolls, pets
  - home decor, quilts, crafts
  - blog/editorial/help/account/cart/checkout/login pages
- Prefer concrete product pages for garments.
- next_section_urls must contain only pagination/listing/category/search-result pages relevant to the same section.

OUTPUT RULES:
- Return up to {product_limit} unique absolute URLs in product_urls.
- Return up to {section_limit} unique absolute URLs in next_section_urls.
- Do not include duplicates.
- Do not place the same URL in both lists.
- product_urls must contain only product pages.
- next_section_urls must contain only section/listing/category/pagination pages.

Output only the structured result.
""".strip()


def make_discovery_via_parent_prompt(
    parent_url: str,
    target_url: str,
    product_limit: int,
    section_limit: int,
) -> str:
    return f"""
Open this exact parent page inside the allowed domain: {parent_url}

There is a known target section URL:
{target_url}

Your goal:
Reach the exact known target section URL FROM the parent page by using the site's own navigation.
After reaching that exact target section, inspect it and return:
1) product_urls: direct URLs of individual sewing pattern product pages
2) next_section_urls: pagination/listing/category URLs worth visiting later

CRITICAL RULES:
- Use the parent page only to reach the exact known target URL.
- If a visible link points exactly to the target URL, click that exact link.
- Do NOT substitute a different subcategory just because it looks relevant.
- If you cannot reach the exact target URL from the parent page, return an empty result instead of drifting into another section.
- Do NOT open product pages.
- Do NOT click product cards for inspection.
- Do NOT analyze product details.
- Do NOT download images.
- Stay within the same relevant catalog flow.
- Do NOT spend multiple steps trying to repair a broken page with repeated reloads.
- If the exact target section is reached and visible, extract product URLs directly from visible product cards.
- Do NOT treat obvious product card links as next_section_urls.

CONTENT RULES:
- Focus only on WOMEN'S and MEN'S clothing sewing patterns.
- Exclude:
  - children / kids / baby / teen
  - accessories
  - bags, hats, scarves, belts, gloves, socks
  - toys, dolls, pets
  - home decor, quilts, crafts
  - blog/editorial/help/account/cart/checkout/login pages

OUTPUT RULES:
- Return up to {product_limit} unique absolute URLs in product_urls.
- Return up to {section_limit} unique absolute URLs in next_section_urls.
- Do not include duplicates.
- Do not place the same URL in both lists.
- product_urls must contain only product pages.
- next_section_urls must contain only section/listing/category/pagination pages.
- Do not include the target URL itself in next_section_urls.

Output only the structured result.
""".strip()