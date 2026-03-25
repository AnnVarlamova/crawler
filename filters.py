from utils import text_low


GARMENT_KEYWORDS = {
    "dress": ["dress", "gown", "платье", "сарафан"],
    "skirt": ["skirt", "юбка"],
    "pants": ["pants", "trousers", "jeans", "брюки", "джинсы"],
    "shorts": ["shorts", "шорты"],
    "jacket": ["jacket", "blazer", "жакет", "пиджак"],
    "coat": ["coat", "пальто"],
    "shirt": ["shirt", "рубашка"],
    "blouse": ["blouse", "блузка"],
    "top": ["top", "топ", "camisole"],
    "corset": ["corset", "корсет", "bustier", "бюстье"],
    "vest": ["vest", "waistcoat", "жилет"],
    "jumpsuit": ["jumpsuit", "romper", "комбинезон"],
    "trench": ["trench", "тренч"],
    "hoodie": ["hoodie", "sweatshirt", "худи", "свитшот"],
    "sweater": ["sweater", "jumper", "pull", "свитер", "джемпер"],
    "cardigan": ["cardigan", "кардиган"],
    "bodysuit": ["bodysuit", "боди"],
    "cape": ["cape", "накидка"],
    "suit": ["suit", "костюм"],
}

STYLE_KEYWORDS = {
    "draped": ["draped", "drape", "драпиров"],
    "oversized": ["oversized", "оверсайз"],
    "tailored": ["tailored", "tailoring", "костюмн", "притал"],
    "asymmetric": ["asymmetric", "asymmetrical", "асимметр"],
    "pleated": ["pleated", "pleat", "плиссе", "складк"],
    "corsetry": ["corset", "corsetry", "корсет"],
    "structured": ["structured", "structure", "структур"],
    "voluminous": ["volume", "voluminous", "объем", "объём"],
    "fitted": ["fitted", "fit-and-flare", "прилегающ"],
    "minimal": ["minimal", "minimalist", "минимал"],
    "runway": ["runway", "catwalk", "подиум"],
    "vintage": ["vintage", "винтаж"],
    "couture": ["couture", "haute couture"],
}

POSITIVE_GENDER = {
    "women": [
        "women", "woman", "womens", "womenswear", "female",
        "ladies", "for her", "жен", "женский", "для женщин"
    ],
    "men": [
        "men", "mens", "menswear", "male",
        "for him", "муж", "мужской", "для мужчин"
    ],
}

CHILD_TERMS = {
    "kids", "kid", "child", "children", "baby", "toddler",
    "girls", "boys", "дет", "детск", "ребен", "ребён", "малыш"
}

ACCESSORY_TERMS = {
    "accessory", "accessories", "bag", "bags", "hat", "scarf",
    "gloves", "sock", "socks", "shoes", "shoe", "boots",
    "jewelry", "necklace", "earrings", "ring", "brooch", "bracelet",
    "сумк", "шляп", "шапк", "шарф", "перчат", "обув",
    "украшен", "аксессуар", "брошь", "браслет", "серьги", "кольцо"
}

SAFE_IN_GARMENT_CONTEXT = {
    "belt", "belted", "waist belt", "ремень"
}

PATTERN_HINTS = {
    "pattern", "pdf", "download", "print", "template", "pattern pieces",
    "sewing pattern", "digital pattern", "paper pattern", "size chart",
    "выкройк", "лекал", "скачать", "распечат", "pdf-выкройка", "размерная сетка"
}

PRODUCT_URL_HINTS = {
    "/product/", "/products/", "/shop/", "/vikrojki/", "/vykrojki/",
    "/dress", "/skirt", "/pants", "/coat", "/jacket", "/pattern"
}

CATEGORY_URL_HINTS = {
    "/category/", "/collections/", "/catalog", "/shop", "/vykrojki", "/vikroyki"
}

ARTICLE_URL_HINTS = {
    "/blog/", "/tag/", "/archives/", "/article/", "/post/", "/page/"
}

GENERATOR_HINTS = {"generator", "custom pattern", "made-to-measure", "3d preview"}
PATTERN_BLOB_HINTS = {
    "выкройка", "выкройки", "готовая выкройка", "лекало", "лекала",
    "sewing pattern", "pattern pdf", "digital pattern", "download pattern",
}


def find_labels(blob: str, mapping: dict[str, list[str]]) -> list[str]:
    blob = text_low(blob)
    out = []
    for label, variants in mapping.items():
        if any(v in blob for v in variants):
            out.append(label)
    return out


def has_any(blob: str, terms: set[str]) -> bool:
    blob = text_low(blob)
    return any(t in blob for t in terms)


def detect_page_type(url: str, blob: str, has_price: bool, has_product_schema: bool) -> str:
    ul = url.lower()
    bl = text_low(blob)

    if has_product_schema or has_price or any(x in ul for x in PRODUCT_URL_HINTS):
        return "product"
    if any(x in bl for x in PATTERN_BLOB_HINTS) and any(k in bl for k in GARMENT_KEYWORDS):
        return "product"
    if "/20" in ul and "korfiati.ru" in ul and "vykroj" in ul:
        return "product"
    if any(x in ul for x in ARTICLE_URL_HINTS):
        return "article"
    if any(x in bl for x in GENERATOR_HINTS) or "sewist.com" in ul or "bootstrapfashion.com" in ul:
        return "generator"
    if any(x in ul for x in CATEGORY_URL_HINTS):
        return "category"
    return "unknown"


def classify_page(
    title: str,
    text: str,
    tags: list[str],
    breadcrumbs: list[str],
    url: str,
    has_price: bool,
    has_product_schema: bool,
    adapter_name: str,
    image_count: int,
    file_count: int,
):
    blob = " ".join([title, text, " ".join(tags), " ".join(breadcrumbs), url])

    garment_type = find_labels(blob, GARMENT_KEYWORDS)
    gender = find_labels(blob, POSITIVE_GENDER)
    style_keywords = find_labels(blob, STYLE_KEYWORDS)

    is_child = has_any(blob, CHILD_TERMS)

    accessory_hit = has_any(blob, ACCESSORY_TERMS)
    garment_hit = bool(garment_type)
    safe_accessory_context = any(x in text_low(blob) for x in SAFE_IN_GARMENT_CONTEXT)
    is_accessory = accessory_hit and not garment_hit and not safe_accessory_context

    page_type = detect_page_type(url, blob, has_price, has_product_schema)

    if adapter_name in {"patternvault", "thecuttingclass"}:
        keep = not is_child and not is_accessory
        entity_type = "analysis" if adapter_name == "thecuttingclass" else "collection_entry"
    elif page_type == "generator":
        keep = garment_hit and not is_child and not is_accessory
        entity_type = "pattern"
    elif page_type == "product":
        keep = (garment_hit or has_any(blob, PATTERN_HINTS)) and not is_child and not is_accessory and image_count > 0
        entity_type = "pattern"
    elif page_type == "category":
        keep = garment_hit and not is_child and not is_accessory and image_count > 0
        entity_type = "garment"
    else:
        keep = garment_hit and not is_child and not is_accessory and (image_count > 0 or file_count > 0)
        entity_type = "garment"

    return {
        "garment_type": garment_type,
        "gender": gender,
        "style_keywords": style_keywords,
        "is_child_related": is_child,
        "is_accessory_related": is_accessory,
        "keep": keep,
        "page_type": page_type,
        "entity_type": entity_type,
    }
