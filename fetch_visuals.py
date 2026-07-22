"""
Stage 3 — Get a visual for each summarized article.

Priority order (best retention first):
  1. Pexels vertical stock VIDEO matching the headline's keywords — motion
     backgrounds hold Shorts viewers far better than static images.
  2. Pexels vertical stock PHOTO, if no suitable video exists.
  3. Generated "breaking news" headline card (card_generator.py) — used only
     when Pexels has nothing usable, so every video still gets a visual.

Only Pexels is used (see README for why, vs. Pixabay) to keep this stage to a
single, reliable API surface. Never touches the original news source's image.
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

from config import (
    DATA_DIR,
    MEDIA_DIR,
    PEXELS_API_KEY,
    PEXELS_VIDEO_SEARCH_URL,
    PEXELS_PHOTO_SEARCH_URL,
    VIDEO_MIN_WIDTH,
    VIDEO_MAX_DURATION_SECONDS,
    VIDEO_FORMATS,
)
from categorize import classify_category, extract_search_keywords
from card_generator import generate_headline_card

HEADERS = {"Authorization": PEXELS_API_KEY}


def _search_pexels_video(query: str, orientation: str) -> dict | None:
    params = {"query": query, "orientation": orientation, "size": "medium", "per_page": 5}
    resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    videos = resp.json().get("videos", [])

    for video in videos:
        if video.get("duration", 0) > VIDEO_MAX_DURATION_SECONDS:
            continue
        # pick the best file matching the requested orientation that meets our minimum width
        candidates = []
        for f in video.get("video_files", []):
            w, h = f.get("width"), f.get("height")
            if not w or not h or w < VIDEO_MIN_WIDTH:
                continue
            is_portrait = h > w
            if (orientation == "portrait") == is_portrait:
                candidates.append(f)
        if candidates:
            best = sorted(candidates, key=lambda f: f["width"])[0]  # smallest that still qualifies -> faster download
            return {"url": best["link"], "pexels_id": video["id"]}
    return None


def _search_pexels_photo(query: str, orientation: str) -> dict | None:
    params = {"query": query, "orientation": orientation, "size": "medium", "per_page": 5}
    resp = requests.get(PEXELS_PHOTO_SEARCH_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    if photos:
        photo = photos[0]
        src_key = "portrait" if orientation == "portrait" else "landscape"
        return {"url": photo["src"][src_key], "pexels_id": photo["id"]}
    return None


def _download(url: str, out_path: Path) -> str:
    resp = requests.get(url, timeout=30, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return str(out_path)


def get_visual_for_article(article: dict, story_index: int, story_total: int) -> dict:
    """Returns {"visual_type", "path", "category"} — tries video, then photo, then generated card."""
    query = extract_search_keywords(article["title"])
    category = classify_category(article["title"], article.get("description", ""))
    fmt = VIDEO_FORMATS[article.get("format", "short")]
    orientation = fmt["orientation"]
    article_dir = MEDIA_DIR / article["id"]
    article_dir.mkdir(parents=True, exist_ok=True)

    if PEXELS_API_KEY:
        try:
            video = _search_pexels_video(query, orientation)
            if video:
                out_path = article_dir / "background.mp4"
                _download(video["url"], out_path)
                return {"visual_type": "stock_video", "path": str(out_path), "category": category, "query": query}
        except Exception as e:
            print(f"[warn] Pexels video search/download failed for '{query}': {e}")

        try:
            photo = _search_pexels_photo(query, orientation)
            if photo:
                out_path = article_dir / "background.jpg"
                _download(photo["url"], out_path)
                return {"visual_type": "stock_photo", "path": str(out_path), "category": category, "query": query}
        except Exception as e:
            print(f"[warn] Pexels photo search/download failed for '{query}': {e}")
    else:
        print("[warn] PEXELS_API_KEY not set — skipping stock search, generating card instead")

    # Fallback: generated headline card, sized natively for this article's format
    # (not a crop of the other orientation's card — that's what would cut off text)
    out_path = article_dir / "card.jpg"
    generate_headline_card(
        hindi_headline=article["hindi_script"].split(".")[0][:80] or article["title"],
        category=category,
        story_index=story_index,
        story_total=story_total,
        out_path=out_path,
        width=fmt["width"],
        height=fmt["height"],
    )
    return {"visual_type": "generated_card", "path": str(out_path), "category": category, "query": query}


def _latest_scripts_file() -> Path:
    candidates = sorted(DATA_DIR.glob("scripts_*.json"))
    if not candidates:
        raise FileNotFoundError("No scripts_*.json found — run summarize_hindi.py first.")
    return candidates[-1]


def main():
    scripts_path = _latest_scripts_file()
    with open(scripts_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"[info] loaded {len(articles)} scripted articles from {scripts_path}")

    results = []
    total = len(articles)
    for i, article in enumerate(articles, 1):
        print(f"[info] fetching visual {i}/{total}: {article['title'][:60]}")
        visual = get_visual_for_article(article, story_index=i, story_total=total)
        results.append({**article, **visual})
        time.sleep(0.5)  # polite pacing, well under Pexels' 200/hr limit for a 5-article run

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"visuals_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
