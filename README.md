# YT Hindi News Shorts — Autopilot Pipeline

Fully automated Hindi-language India-news Shorts channel, built entirely on free tiers.

**On a phone with no computer?** Skip straight to [Scheduling → Option A](#scheduling-pick-one--both-are-free) —
the entire pipeline, including the one-time YouTube login, runs on GitHub's free cloud
runners. You never need to run Python locally; you just tap links and type codes in your
phone's browser.


## Pipeline stages (built incrementally)

| # | Stage | Script | Status |
|---|-------|--------|--------|
| 1 | Fetch news (RSS) | `fetch_news.py` | ✅ done |
| 2 | Hindi summarization (LLM) | `summarize_hindi.py` | ✅ done |
| 3 | Visuals (stock/graphic cards) | `fetch_visuals.py` | ✅ done |
| 4 | TTS (Hindi voiceover) | `tts_generate.py` | ✅ done |
| 5 | Video assembly (ffmpeg) | `build_video.py` | ✅ done |
| 6 | YouTube upload | `upload_youtube.py` | ✅ done |
| 7 | Orchestration + scheduler | `run_pipeline.py` + GitHub Actions | ✅ done |

## Design choices & why

- **News source**: Google News India RSS + PIB India RSS. No paid news API, no scraping
  full article bodies — only title + short RSS description, which is standard fair-use-safe
  metadata, not the article's copyrighted body text.
- **LLM for summarization**: Google Gemini API (`gemini-1.5-flash` or `gemini-2.0-flash`) —
  free tier is generous (15 RPM / 1M tokens per day range depending on model) and has an
  official Hindi-capable model. The wrapper in `summarize_hindi.py` is provider-agnostic —
  swap in Groq (free, fast Llama models) by editing one function if you prefer.
- **Token minimization**: prompt is a fixed ~40-word instruction; only title+description
  (never full article) go in as input; `max_output_tokens` capped so the model can't ramble
  past the 150-word Hindi target. One API call per article, no retries-by-default loop.
- **Copyright stance**: we never store or pass the source image, and we never ask the LLM to
  reproduce article text — only to paraphrase into a new Hindi script. Visuals in stage 3 will
  come from Pexels/Pixabay/Unsplash (all offer free API keys with commercial-use licenses) or
  generated text-card graphics, never from the news source itself.

- **Visuals (stage 3)**: **Pexels only**, not Pixabay — Pexels has one stable API covering
  both photos and vertical video, curated quality, and a solid free quota (200 req/hour,
  20k/month). For each article: try a short **vertical stock video** first (motion holds
  Shorts viewers far better than a static frame), fall back to a stock **photo**, and only
  if neither is found, generate a **"breaking news"-style headline card** — category-colored
  gradient, dark vignette for text contrast, pill-shaped tag, big auto-sized Hindi headline,
  and a small story-progress counter (`2/5`) as a "keep watching" cue. Category is detected
  with plain keyword matching (no LLM call), so this stage costs zero extra tokens.
- **Font**: card rendering needs a Devanagari-capable font. Download **Noto Sans Devanagari**
  (free, Google Fonts) and place `NotoSansDevanagari-Bold.ttf` / `-Regular.ttf` under
  `assets/fonts/` — see the path constants in `config.py`.

- **TTS (stage 4)**: **edge-tts** — free, no API key/quota at all, and its neural voices
  (`hi-IN-MadhurNeural` / `hi-IN-SwaraNeural`) sound far more natural than gTTS. It also
  streams word-boundary timing as it synthesizes, which we capture straight into a `.srt`
  subtitle file — free, accurate subtitle timestamps with no separate alignment step.
  `ffprobe` (bundled with ffmpeg, which stage 5 needs anyway) double-checks each clip's
  duration for the manifest.

- **Video assembly (stage 5)**: three separate ffmpeg passes (background → subtitles → audio
  mux) rather than one giant filter graph, so a failure is easy to isolate and re-run. Stock
  video backgrounds are looped/trimmed to the voiceover's exact duration; stock photos and
  generated cards get a Ken Burns zoom so nothing sits static on screen. Background music
  comes from a small locally curated folder (`assets/music/*.mp3` — grab a few free tracks
  from the YouTube Audio Library, no API needed) rather than another API dependency, mixed
  well under the voiceover with a fade-out at the end.
- **Long-form vs Shorts split**: `LONG_FORM_COUNT` (default 1) of the day's most
  cross-source-confirmed stories — the ones already ranked highest by
  `select_top_articles` — get `format: "long"`; everything else is `format: "short"`.
  This flag flows through every stage's JSON manifest and changes real behavior at each
  step, not just the final render:
  - stage 2: a longer, structured 400-600 word script instead of 100-150 words
  - stage 3: Pexels is queried for **landscape** stock instead of portrait
  - stage 3 fallback: the headline card is rendered **natively at 1920x1080** — its own
    layout pass, not a crop or stretch of the vertical card — so nothing gets cut off
  - stage 5: output is native 16:9 (1920x1080), which keeps YouTube from classifying it
    as a Short regardless of duration, with subtitle margins tuned for a normal video
    (no Shorts UI to dodge) instead of the Shorts-safe bottom margin
- **YouTube upload (stage 6)**: auth is OAuth2 tied to your Google account, **not the
  channel URL**. Set up once using the device authorization flow (`youtube_auth_setup.py`)
  — the same "open this URL and type this code" flow smart TVs use, so it needs no local
  server and works from a phone. Every later run is unattended. Quota-aware: `videos.insert`
  costs ~1600 units against the free 10,000/day cap, so the uploader computes how many
  videos fit and defers the rest to the next run rather than risking a failed request
  mid-batch. An `uploaded_ids` ledger makes re-runs idempotent — nothing gets uploaded
  twice. Short-form videos get a `#shorts` tag (YouTube's own recommended signal on top of
  the vertical/short duration itself); long-form videos deliberately don't, since stage 5
  already built them to not be classified as Shorts.

### One-time YouTube auth setup — entirely from a phone, no computer needed

1. https://console.cloud.google.com/ → create/select a project (works fine in a mobile
   browser)
2. Enable **YouTube Data API v3** (APIs & Services → Library)
3. APIs & Services → Credentials → Create Credentials → OAuth client ID →
   **"TVs and Limited Input devices"** (not "Desktop app" — that type doesn't support the
   device flow this script uses)
4. Download the JSON — save its contents for the next step
5. OAuth consent screen → add your Google account as a **Test User**
6. Push this repo to GitHub (GitHub's mobile app, or github.com in a mobile browser using
   "Create new file" and typing a path with `/` in the filename to place files in folders,
   both work for this)
7. Repo → Settings → Secrets and variables → Actions → add secret
   `YOUTUBE_CLIENT_SECRET_JSON` = the file contents from step 4
8. Actions tab → **"YouTube Auth Setup (one-time, manual)"** → Run workflow. Open the
   run's log: it prints a URL and a short code. Open that URL on your phone, type the code,
   approve. The job then prints a `token.json` — copy that into a new secret named
   `YOUTUBE_TOKEN_JSON`
9. Done — the daily pipeline workflow reads that secret and uploads unattended from then on.

- **Orchestration + scheduler (stage 7)**: `run_pipeline.py` runs all six stages in order,
  treats a whole-stage exception as fatal (later stages depend on earlier stages' output
  files) while leaving each stage's own per-article error handling intact, and logs to both
  stdout and `data/logs/pipeline_<date>.log` so a failure is diagnosable after the fact from
  a scheduler's job history. `--skip-upload` builds videos without touching YouTube, for
  testing prompts/visuals/voice changes safely.

## Scheduling (pick one — both are free)

### Option A: GitHub Actions (works entirely from a phone, no local Python at all)

The workflow at `.github/workflows/daily-pipeline.yml` runs the whole pipeline daily on
GitHub's free runners (2,000 min/month free on private repos, unlimited on public repos —
a daily run here takes a few minutes) — everything (fetching, ffmpeg, uploading) happens in
GitHub's cloud, not on your device.

1. Push this project to a GitHub repo (see step 6 above for mobile-friendly ways to do this).
2. Commit `assets/fonts/*.ttf` and `assets/music/*.mp3` — the runner starts from a clean
   checkout each time, so these curated assets need to be in the repo (secrets and
   generated `data/` stay out via `.gitignore`).
3. Repo → Settings → Secrets and variables → Actions → add:
   - `GEMINI_API_KEY`
   - `PEXELS_API_KEY`
   - `YOUTUBE_TOKEN_JSON` — from the one-time auth setup above
4. That's it — it runs daily at the cron time in the workflow file (edit the `cron:` line
   to change when). You can also trigger it manually from the Actions tab, from your phone.

### Option B: Oracle Cloud Always Free VM (needs a computer for initial setup)

This option needs an SSH session at least once to provision the VM — less phone-friendly
than Option A, included here for completeness / if you later want more control.

An Always Free Ampere/micro VM doesn't reset between runs, so `client_secret.json` and
`token.json` can just live on disk normally — no secrets-injection step needed.

1. Provision an Always Free VM, SSH in, install Python 3.11+ and ffmpeg
   (`sudo apt-get install -y python3 python3-pip ffmpeg`).
2. Clone the repo, `pip install -r requirements.txt`, add `assets/fonts/`, `assets/music/`,
   `client_secret.json`, and run `python youtube_auth_setup.py` once (needs a browser —
   either use SSH port forwarding for the OAuth redirect, or run this one step locally and
   just copy the resulting `token.json` onto the VM).
3. Add `GEMINI_API_KEY` / `PEXELS_API_KEY` to a `.env` file on the VM (already supported —
   see `.env.example`).
4. `crontab -e` and add:
   ```
   0 3 * * * cd /path/to/yt-hindi-news-shorts && /path/to/venv/bin/python run_pipeline.py >> data/logs/cron.log 2>&1
   ```

## Setup

```bash
cd yt-hindi-news-shorts
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your free Gemini API key
```

## Run stage 1 + 2 today

```bash
python fetch_news.py            # -> data/raw_news_YYYY-MM-DD.json
python summarize_hindi.py       # -> data/scripts_YYYY-MM-DD.json
python fetch_visuals.py         # -> data/visuals_YYYY-MM-DD.json + data/media/<id>/...
python tts_generate.py          # -> data/audio_YYYY-MM-DD.json + voiceover.mp3/subtitles.srt per article
python build_video.py           # -> data/videos_YYYY-MM-DD.json + final.mp4 per article
python upload_youtube.py        # -> data/uploaded_YYYY-MM-DD.json (uploads to your channel)
```

Or run everything in one shot (what the scheduler calls):
```bash
python run_pipeline.py              # full daily run
python run_pipeline.py --skip-upload  # dry run — build videos, skip YouTube
```

## Folder layout

```
yt-hindi-news-shorts/
├── config.py              # central knobs: feeds, model name, categories, Pexels/font settings
├── fetch_news.py          # stage 1
├── summarize_hindi.py     # stage 2
├── categorize.py          # keyword-based category classifier + search-term extraction (stage 3 helper)
├── card_generator.py      # Pillow headline-card renderer (stage 3 fallback visual)
├── fetch_visuals.py       # stage 3
├── tts_generate.py        # stage 4
├── build_video.py         # stage 5
├── youtube_auth_setup.py  # stage 6 — run once, locally
├── upload_youtube.py      # stage 6
├── run_pipeline.py        # stage 7 — orchestrates all stages
├── .github/workflows/daily-pipeline.yml  # stage 7 — GitHub Actions scheduler
├── .gitignore
├── requirements.txt
├── .env.example
├── client_secret.json     # from Google Cloud Console — you provide this (gitignore it!)
├── token.json             # generated by youtube_auth_setup.py (gitignore it!)
├── assets/fonts/          # place NotoSansDevanagari-Bold.ttf / -Regular.ttf here
├── assets/music/          # place a few royalty-free .mp3 tracks here (YouTube Audio Library)
├── data/                  # gitignored in practice; JSON + media artifacts land here
└── README.md
```
