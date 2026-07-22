"""
Central configuration for the pipeline.
Keep every tunable knob here so later stages (TTS, video, upload) share one source of truth.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Stage 1 — News sources (RSS only, no paid API)
# ---------------------------------------------------------------------------
# Google News India RSS supports topic-scoped feeds. PIB has its own English/Hindi feeds.
RSS_FEEDS = {
    "google_news_india_top": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "google_news_india_nation": "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    "pib_india_all": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
}

# How many articles to pull through the whole daily pipeline (keeps token/quota use low)
MAX_ARTICLES_PER_DAY = 5

# Drop articles whose title matches these (ads, sponsored, duplicate-wire boilerplate)
TITLE_BLOCKLIST_SUBSTRINGS = ["advertisement", "sponsored"]

# ---------------------------------------------------------------------------
# Stage 2 — Hindi summarization (LLM)
# ---------------------------------------------------------------------------
# Free-tier model. Swap to a Groq model name if you prefer that provider —
# see summarize_hindi.py's call_llm() for the one function to edit.
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

SUMMARY_MIN_WORDS = 100
SUMMARY_MAX_WORDS = 150

# Kept short deliberately: fewer input tokens = more headroom on the free daily quota.
SUMMARY_SYSTEM_PROMPT = (
    "आप एक हिंदी समाचार स्क्रिप्ट राइटर हैं। दिए गए शीर्षक और संक्षिप्त विवरण के आधार पर, "
    f"{SUMMARY_MIN_WORDS}-{SUMMARY_MAX_WORDS} शब्दों में एक मौलिक, सरल हिंदी स्क्रिप्ट लिखें। "
    "मूल अंग्रेज़ी वाक्यों की नकल न करें — अपने शब्दों में बताएं। कोई अतिरिक्त टिप्पणी न जोड़ें, "
    "केवल स्क्रिप्ट लौटाएं।"
)

# Caps model output so it can't ramble past budget (saves output tokens too)
GEMINI_MAX_OUTPUT_TOKENS = 350
GEMINI_TEMPERATURE = 0.4

# ---------------------------------------------------------------------------
# Long-form vs short-form split
# ---------------------------------------------------------------------------
# The most cross-source-confirmed stories (already how select_top_articles in
# fetch_news.py ranks things) are the "big stories" — those get an extended
# script and a full standalone video; everything else stays a quick Short.
LONG_FORM_COUNT = 1  # bump to 2 if you want two long-form videos/day

LONG_FORM_MIN_WORDS = 400
LONG_FORM_MAX_WORDS = 600
LONG_FORM_SYSTEM_PROMPT = (
    "आप एक हिंदी समाचार स्क्रिप्ट राइटर हैं। दिए गए शीर्षक और विवरण के आधार पर, "
    f"{LONG_FORM_MIN_WORDS}-{LONG_FORM_MAX_WORDS} शब्दों में एक विस्तृत, मौलिक हिंदी स्क्रिप्ट लिखें। "
    "पृष्ठभूमि, मुख्य घटनाक्रम, और संभावित असर को शामिल करें। मूल अंग्रेज़ी वाक्यों की नकल न करें — "
    "अपने शब्दों में बताएं। कोई अतिरिक्त टिप्पणी न जोड़ें, केवल स्क्रिप्ट लौटाएं।"
)
GEMINI_MAX_OUTPUT_TOKENS_LONG = 900  # roomier cap for the extended script

# Per-format render settings. "short" values match the existing Shorts pipeline
# unchanged; "long" is native 16:9 — not a crop of the vertical assets, so
# headlines/subjects aren't cut off, and duration/aspect keep it out of
# YouTube's Shorts shelf entirely.
VIDEO_FORMATS = {
    "short": {
        "width": 1080,
        "height": 1920,
        "orientation": "portrait",
        "subtitle_font_size": 16,
        "subtitle_margin_v": 260,   # clears Shorts' like/comment UI at the bottom
    },
    "long": {
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",
        "subtitle_font_size": 30,
        "subtitle_margin_v": 60,    # no Shorts UI to avoid, just a normal caption margin
    },
}

# ---------------------------------------------------------------------------
# Stage 3 — Visuals (Pexels only — see README for why Pexels over Pixabay)
# ---------------------------------------------------------------------------
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"

# Target format: vertical, Shorts-native (short-form default; long-form uses VIDEO_FORMATS["long"])
VIDEO_MIN_WIDTH = 720          # minimum usable stock-video width to accept
VIDEO_MAX_DURATION_SECONDS = 20  # avoid clips so long we're paying download cost for unused footage
CARD_WIDTH, CARD_HEIGHT = VIDEO_FORMATS["short"]["width"], VIDEO_FORMATS["short"]["height"]

MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

# Font must support Devanagari. Download free from Google Fonts:
# https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari -> place at this path.
FONT_DIR = BASE_DIR / "assets" / "fonts"
FONT_BOLD_PATH = FONT_DIR / "NotoSansDevanagari-Bold.ttf"
FONT_REGULAR_PATH = FONT_DIR / "NotoSansDevanagari-Regular.ttf"

# Rule-based category classifier (keyword match on English title+description —
# no LLM call needed, keeps this stage free of token cost entirely).
# Each category gets a distinct accent color + Hindi tag, which also adds
# visual variety across a day's videos instead of every card looking the same.
CATEGORY_STYLES = {
    "politics":      {"tag": "राजनीति",        "gradient": ("#8E0E00", "#1F1C18"), "keywords": ["election", "parliament", "minister", "modi", "bjp", "congress", "party", "lok sabha", "rajya sabha", "cabinet"]},
    "sports":        {"tag": "खेल",            "gradient": ("#134E5E", "#71B280"), "keywords": ["cricket", "match", "tournament", "olympic", "ipl", "player", "medal", "world cup"]},
    "business":      {"tag": "व्यापार",         "gradient": ("#1A2980", "#26D0CE"), "keywords": ["market", "economy", "rupee", "sensex", "nifty", "gdp", "rbi", "stocks", "inflation", "budget"]},
    "entertainment": {"tag": "मनोरंजन",         "gradient": ("#8E2DE2", "#4A00E0"), "keywords": ["bollywood", "movie", "actor", "actress", "film", "box office", "trailer", "celebrity"]},
    "crime":         {"tag": "अपराध",           "gradient": ("#232526", "#414345"), "keywords": ["murder", "arrest", "crime", "police", "accident", "fire", "death", "attack"]},
    "world":         {"tag": "अंतरराष्ट्रीय",    "gradient": ("#005C97", "#363795"), "keywords": ["china", "pakistan", "us ", "america", "russia", "un ", "world", "global", "foreign"]},
    "technology":    {"tag": "तकनीक",           "gradient": ("#0F2027", "#2C5364"), "keywords": ["tech", "ai", "app", "smartphone", "isro", "satellite", "software", "startup"]},
    "national":      {"tag": "राष्ट्रीय",        "gradient": ("#F7971E", "#FFD200"), "keywords": []},  # default fallback
}
DEFAULT_CATEGORY = "national"

# Simple English stopword list for keyword extraction (titles arrive in English from RSS)
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are",
    "was", "were", "with", "as", "by", "from", "after", "over", "amid", "amidst",
    "his", "her", "its", "their", "says", "said", "will", "not", "into", "up", "out",
}

# ---------------------------------------------------------------------------
# Stage 4 — Text-to-speech (edge-tts: free, no API key, neural Hindi voices)
# ---------------------------------------------------------------------------
# hi-IN-MadhurNeural (male) or hi-IN-SwaraNeural (female) — both natural-sounding,
# news-appropriate. List all voices anytime with: `edge-tts --list-voices | grep hi-IN`
TTS_VOICE = "hi-IN-MadhurNeural"
TTS_RATE = "+0%"     # e.g. "+10%" to speak faster and tighten video length
TTS_VOLUME = "+0%"

# Small pause between requests — edge-tts is a free unofficial API, so we're
# polite about request pacing rather than firing 5 requests at once.
TTS_PAUSE_SECONDS = 1.0

# ---------------------------------------------------------------------------
# Stage 5 — Video assembly (ffmpeg)
# ---------------------------------------------------------------------------
# Background music: no music API is used here. Instead, curate a small folder
# of royalty-free tracks once (e.g. from the free YouTube Audio Library —
# no key, no rate limits, licensed for exactly this use) and drop the .mp3
# files in MUSIC_DIR. A track is picked at random per video.
MUSIC_DIR = BASE_DIR / "assets" / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_VOLUME = 0.12          # background music sits well under the voiceover
VOICEOVER_VOLUME = 1.0

FPS = 25
ZOOM_RATE_PER_FRAME = 0.0015   # Ken Burns speed for generated cards / stock photos
ZOOM_MAX = 1.2

# Subtitle burn-in styling (libass force_style). Alignment=2 is bottom-center.
# Font size and margin are per-format now (see VIDEO_FORMATS above) — short-form
# needs a bigger MarginV to clear Shorts' like/comment UI; long-form doesn't.
SUBTITLE_FONT_NAME = "Noto Sans Devanagari"

VIDEO_CRF = 20
VIDEO_PRESET = "veryfast"

# ---------------------------------------------------------------------------
# Stage 6 — YouTube upload (YouTube Data API v3, free quota: 10,000 units/day)
# ---------------------------------------------------------------------------
# OAuth, not the channel URL — see README for the one-time setup with
# youtube_auth_setup.py. client_secret.json comes from Google Cloud Console;
# token.json is generated once and reused (auto-refreshes) for unattended runs.
YOUTUBE_CLIENT_SECRETS_FILE = BASE_DIR / "client_secret.json"
YOUTUBE_TOKEN_FILE = BASE_DIR / "token.json"
YOUTUBE_UPLOAD_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# videos.insert costs ~1600 units regardless of file size. Budget conservatively
# so we never risk tripping the daily 10,000-unit free cap on other API calls too.
YOUTUBE_DAILY_QUOTA_LIMIT = 10000
YOUTUBE_UPLOAD_COST_UNITS = 1600

YOUTUBE_CATEGORY_ID = "25"  # News & Politics
YOUTUBE_DEFAULT_PRIVACY = "public"  # "private" or "unlisted" while testing
YOUTUBE_DEFAULT_LANGUAGE = "hi"

# Ledger of already-uploaded article IDs so re-running the script is safe
# (won't double-upload if it's re-run after a partial failure).
UPLOADED_LEDGER_FILE = DATA_DIR / "uploaded_ids.json"
