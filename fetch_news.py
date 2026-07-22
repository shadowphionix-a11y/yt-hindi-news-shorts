"""
Stage 1 — Fetch trending India news from free RSS feeds.

- No paid news API.
- Only title + RSS-provided short description are kept (never the full article body,
  never the source image) — this is the copyright-safe boundary for stage 2 onward.
- Output: data/raw_news_<date>.json
"""

import json
import re
import hashlib
from datetime import datetime, timezone

import feedparser

from config import RSS_FEEDS, MAX_ARTICLES_PER_DAY, TITLE_BLOCKLIST_SUBSTRINGS, DATA_DIR, LONG_FORM_COUNT


def _clean_html(raw: str) -> str:
    """Strip HTML tags/entities that Google News often embeds in the description."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _article_id(title: str, link: str) -> str:
    """Stable dedupe key so re-runs don't reprocess the same story."""
    return hashlib.sha256(f"{title}|{link}".encode("utf-8")).hexdigest()[:16]


def _is_blocked(title: str) -> bool:
    lowered = title.lower()
    return any(bad in lowered for bad in TITLE_BLOCKLIST_SUBSTRINGS)


def fetch_all_feeds() -> list[dict]:
    """Pull every configured feed, normalize entries, dedupe by (title, link)."""
    seen_ids = set()
    articles = []

    for source_name, url in RSS_FEEDS.items():
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            print(f"[warn] could not parse feed '{source_name}': {parsed.bozo_exception}")
            continue

        for entry in parsed.entries:
            title = _clean_html(entry.get("title", "")).strip()
            if not title or _is_blocked(title):
                continue

            link = entry.get("link", "")
            description = _clean_html(entry.get("summary", entry.get("description", "")))

            article_id = _article_id(title, link)
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)

            published = entry.get("published", "") or entry.get("updated", "")

            articles.append(
                {
                    "id": article_id,
                    "source": source_name,
                    "title": title,
                    "description": description,
                    "link": link,
                    "published": published,
                }
            )

    return articles


def select_top_articles(articles: list[dict], limit: int) -> list[dict]:
    """
    Simple trending heuristic for a free pipeline: prefer articles that appear
    across more than one feed (cross-source confirmation), then fall back to
    feed order (RSS feeds are already roughly reverse-chronological/ranked).
    """
    title_counts: dict[str, int] = {}
    for a in articles:
        key = a["title"].lower()[:60]  # loose bucket to catch near-duplicate titles
        title_counts[key] = title_counts.get(key, 0) + 1

    def score(a: dict) -> int:
        return title_counts.get(a["title"].lower()[:60], 1)

    ranked = sorted(articles, key=score, reverse=True)

    # de-dupe near-identical titles across sources, keep first occurrence
    picked = []
    used_keys = set()
    for a in ranked:
        key = a["title"].lower()[:60]
        if key in used_keys:
            continue
        used_keys.add(key)
        picked.append(a)
        if len(picked) >= limit:
            break

    return picked


def assign_formats(articles: list[dict], long_form_count: int) -> list[dict]:
    """
    articles is already ranked (most cross-source-confirmed first) by
    select_top_articles. The first `long_form_count` — the day's biggest,
    most-confirmed stories — get an extended standalone video; the rest stay
    quick Shorts.
    """
    for i, article in enumerate(articles):
        article["format"] = "long" if i < long_form_count else "short"
    return articles


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_articles = fetch_all_feeds()
    print(f"[info] fetched {len(all_articles)} raw entries across {len(RSS_FEEDS)} feeds")

    top_articles = select_top_articles(all_articles, MAX_ARTICLES_PER_DAY)
    top_articles = assign_formats(top_articles, LONG_FORM_COUNT)
    long_count = sum(1 for a in top_articles if a["format"] == "long")
    print(f"[info] selected top {len(top_articles)} articles ({long_count} long-form, {len(top_articles) - long_count} short-form)")

    out_path = DATA_DIR / f"raw_news_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(top_articles, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
