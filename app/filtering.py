from __future__ import annotations

from app.models import ProductCard


def is_valid_product(card: ProductCard) -> bool:
    if card.is_accessory or card.is_child_item:
        return False

    text = " ".join([
        card.title or "",
        card.category or "",
        card.subcategory or "",
        card.short_description or "",
        card.pattern_info or "",
        card.raw_text or "",
    ]).lower()

    banned = [
        "kids", "child", "children", "baby", "teen",
        "аксессуар", "accessory", "bag", "hat", "cap", "scarf",
        "glove", "sock", "toy", "doll", "pet",
        "сумк", "шапк", "шарф", "перчат",
    ]
    if any(x in text for x in banned):
        return False

    positive = [
        "dress", "blouse", "shirt", "top", "skirt",
        "trousers", "pants", "jeans", "shorts",
        "jacket", "blazer", "coat", "vest", "hoodie",
        "sweater", "cardigan", "jumpsuit", "bodysuit",
        "плать", "блуз", "рубаш", "топ", "юбк",
        "брюк", "брюки", "джинс", "шорт", "жакет",
        "пиджак", "пальто", "жилет", "худи", "свитер",
        "кардиган", "комбинез",
    ]
    if not any(x in text for x in positive):
        return False

    if not card.images:
        return False

    return True