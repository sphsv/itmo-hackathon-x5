from data.generate import BABY_FOOD, EXCLUDED, SAFE_MARKDOWN


def eligible_category(category: str) -> bool:
    return category not in EXCLUDED and category not in BABY_FOOD


def markdown_allowed(category: str) -> bool:
    return eligible_category(category) and category in SAFE_MARKDOWN
