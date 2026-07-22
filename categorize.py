"""
Rule-based helpers shared by stage 3: category classification (for card color/tag)
and keyword extraction (for Pexels search terms). Deliberately zero-LLM-cost —
plain string matching only.
"""

import re

from config import CATEGORY_STYLES, DEFAULT_CATEGORY, STOPWORDS


def classify_category(title: str, description: str) -> str:
    """Return a CATEGORY_STYLES key based on keyword hits in title+description."""
    text = f"{title} {description}".lower()

    best_category = DEFAULT_CATEGORY
    best_hits = 0
    for category, style in CATEGORY_STYLES.items():
        if category == DEFAULT_CATEGORY:
            continue
        hits = sum(1 for kw in style["keywords"] if kw in text)
        if hits > best_hits:
            best_hits = hits
            best_category = category

    return best_category


def extract_search_keywords(title: str, max_keywords: int = 4) -> str:
    """
    Turn an English headline into a short Pexels search query.
    Keeps capitalized/longer words (proper nouns, substantive terms), drops stopwords.
    """
    words = re.findall(r"[A-Za-z]+", title)
    candidates = [w for w in words if w.lower() not in STOPWORDS and len(w) > 2]

    # Prefer longer words first (tend to be more specific/searchable), then original order
    candidates_sorted = sorted(candidates, key=len, reverse=True)[:max_keywords]

    # Preserve original headline order among the picked words for a more natural query
    ordered = [w for w in candidates if w in candidates_sorted]
    return " ".join(ordered[:max_keywords]) if ordered else title
