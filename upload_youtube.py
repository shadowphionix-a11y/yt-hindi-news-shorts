"""
Stage 6 — Upload each finished video to YouTube.

- Auth: loads the token saved once by youtube_auth_setup.py, auto-refreshes it.
  No browser interaction needed here, so this runs fine unattended.
- Quota: videos.insert costs ~1600 units regardless of file size; the free
  daily cap is 10,000. We compute how many uploads fit and stop before going
  over rather than letting a request fail expensively partway through.
- Idempotent: an uploaded_ids ledger means re-running after a partial failure
  won't re-upload videos that already succeeded.
- Metadata differs by format: short-form gets a #Shorts hashtag (the signal
  YouTube's own docs recommend, on top of the vertical-short-duration format
  itself) and a punchy title; long-form gets a fuller description and no
  Shorts hashtag, since we deliberately built it to NOT be classified as one.
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from config import (
    DATA_DIR,
    YOUTUBE_TOKEN_FILE,
    YOUTUBE_UPLOAD_SCOPES,
    YOUTUBE_DAILY_QUOTA_LIMIT,
    YOUTUBE_UPLOAD_COST_UNITS,
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_DEFAULT_PRIVACY,
    YOUTUBE_DEFAULT_LANGUAGE,
    UPLOADED_LEDGER_FILE,
    CATEGORY_STYLES,
)


def _get_authenticated_service():
    if not YOUTUBE_TOKEN_FILE.exists():
        raise RuntimeError(
            f"No token at {YOUTUBE_TOKEN_FILE} — run youtube_auth_setup.py once, locally, first."
        )

    creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), YOUTUBE_UPLOAD_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        YOUTUBE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")  # persist the refreshed token

    return build("youtube", "v3", credentials=creds)


def _load_ledger() -> set:
    if UPLOADED_LEDGER_FILE.exists():
        return set(json.loads(UPLOADED_LEDGER_FILE.read_text(encoding="utf-8")))
    return set()


def _save_ledger(ledger: set) -> None:
    UPLOADED_LEDGER_FILE.write_text(json.dumps(sorted(ledger), ensure_ascii=False, indent=2), encoding="utf-8")


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def build_metadata(article: dict) -> dict:
    is_long = article.get("format") == "long"
    category_tag = CATEGORY_STYLES.get(article.get("category", "national"), CATEGORY_STYLES["national"])["tag"]

    # Title from the headline itself, not the full script — YouTube titles cap at 100 chars.
    headline = article["title"]
    if is_long:
        title = _truncate(f"{headline} | पूरी खबर", 100)
    else:
        title = _truncate(f"{headline} #shorts", 100)

    description_lines = [
        article["hindi_script"],
        "",
        f"श्रेणी: {category_tag}",
        "",
        "स्रोत: सार्वजनिक समाचार RSS फीड (Google News India, PIB) — यह वीडियो मूल रिपोर्टों "
        "का स्वतंत्र, संक्षिप्त सारांश है।",
    ]
    if not is_long:
        description_lines += ["", "#shorts #hindinews #india"]
    else:
        description_lines += ["", "#hindinews #india #news"]

    return {
        "snippet": {
            "title": title,
            "description": "\n".join(description_lines),
            "tags": ["hindi news", "india news", category_tag, "shorts" if not is_long else "news bulletin"],
            "categoryId": YOUTUBE_CATEGORY_ID,
            "defaultLanguage": YOUTUBE_DEFAULT_LANGUAGE,
            "defaultAudioLanguage": YOUTUBE_DEFAULT_LANGUAGE,
        },
        "status": {
            "privacyStatus": YOUTUBE_DEFAULT_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }


def upload_video(youtube, article: dict) -> str:
    body = build_metadata(article)
    media = MediaFileUpload(article["final_video_path"], chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"       upload progress: {int(status.progress() * 100)}%")

    return response["id"]


def main():
    videos_candidates = sorted(DATA_DIR.glob("videos_*.json"))
    if not videos_candidates:
        raise FileNotFoundError("No videos_*.json found — run build_video.py first.")
    videos_path = videos_candidates[-1]

    with open(videos_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    ledger = _load_ledger()
    pending = [a for a in articles if a["id"] not in ledger]
    print(f"[info] {len(pending)}/{len(articles)} videos pending upload ({len(ledger)} already uploaded previously)")

    max_uploads_by_quota = YOUTUBE_DAILY_QUOTA_LIMIT // YOUTUBE_UPLOAD_COST_UNITS
    if len(pending) > max_uploads_by_quota:
        print(
            f"[warn] {len(pending)} pending videos would exceed the free daily quota "
            f"(~{max_uploads_by_quota} uploads/day at {YOUTUBE_UPLOAD_COST_UNITS} units each). "
            f"Uploading only the first {max_uploads_by_quota} today; the rest stay off the "
            "ledger and will upload on the next run."
        )
        pending = pending[:max_uploads_by_quota]

    youtube = _get_authenticated_service()

    results = []
    for i, article in enumerate(pending, 1):
        print(f"[info] uploading {i}/{len(pending)} ({article.get('format', 'short')}): {article['title'][:60]}")
        try:
            video_id = upload_video(youtube, article)
            url = f"https://youtube.com/watch?v={video_id}"
            print(f"       -> {url}")
            ledger.add(article["id"])
            results.append({"id": article["id"], "title": article["title"], "format": article.get("format"), "youtube_url": url})
        except HttpError as e:
            print(f"[warn] upload failed for '{article['title'][:50]}...': {e}")
            if "quotaExceeded" in str(e):
                print("[warn] quota exceeded — stopping remaining uploads for today")
                break
        finally:
            _save_ledger(ledger)  # persist progress after every attempt, not just at the end
        time.sleep(1.0)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"uploaded_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path} ({len(results)} uploaded this run)")
    return out_path


if __name__ == "__main__":
    main()
