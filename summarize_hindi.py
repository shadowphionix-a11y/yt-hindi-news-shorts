"""
Stage 2 — Summarize each fetched article into a 100-150 word Hindi script.

Token-minimization choices:
- One short, fixed system prompt (defined once in config.py, not resent as
  free-form text per call beyond what's needed).
- Only title + RSS description go in as input — never full article text.
- max_output_tokens capped so the model can't overrun the word budget.
- One LLM call per article, no automatic retry loop (a failed article is
  logged and skipped, not re-tried, to avoid silently burning quota).

Provider: Google Gemini free tier by default. To switch to Groq (also free),
only call_llm() needs to change — everything else in this file is provider-agnostic.
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from config import (
    DATA_DIR,
    GEMINI_MODEL,
    GEMINI_API_KEY,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MAX_OUTPUT_TOKENS_LONG,
    GEMINI_TEMPERATURE,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_MIN_WORDS,
    SUMMARY_MAX_WORDS,
    LONG_FORM_SYSTEM_PROMPT,
    LONG_FORM_MIN_WORDS,
    LONG_FORM_MAX_WORDS,
)


def call_llm(title: str, description: str, system_prompt: str, max_output_tokens: int) -> str:
    """
    Single LLM call. Swap this function's internals to use a different
    free-tier provider (e.g. Groq) without touching the rest of the pipeline.
    """
    import google.generativeai as genai

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — copy .env.example to .env and fill it in.")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_prompt,
    )

    # Deliberately terse user turn — the system prompt already carries the instructions.
    user_prompt = f"शीर्षक: {title}\nविवरण: {description}"

    response = model.generate_content(
        user_prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_output_tokens,
            temperature=GEMINI_TEMPERATURE,
        ),
    )
    return (response.text or "").strip()


def _word_count(text: str) -> int:
    return len(text.split())


def summarize_article(article: dict) -> dict | None:
    is_long = article.get("format") == "long"
    system_prompt = LONG_FORM_SYSTEM_PROMPT if is_long else SUMMARY_SYSTEM_PROMPT
    max_tokens = GEMINI_MAX_OUTPUT_TOKENS_LONG if is_long else GEMINI_MAX_OUTPUT_TOKENS
    min_words = LONG_FORM_MIN_WORDS if is_long else SUMMARY_MIN_WORDS
    max_words = LONG_FORM_MAX_WORDS if is_long else SUMMARY_MAX_WORDS

    try:
        script = call_llm(article["title"], article["description"], system_prompt, max_tokens)
    except Exception as e:
        print(f"[warn] LLM call failed for '{article['title'][:50]}...': {e}")
        return None

    wc = _word_count(script)
    if wc == 0:
        print(f"[warn] empty script for '{article['title'][:50]}...' — skipping")
        return None

    # Soft warning only — trimming/re-prompting would cost extra tokens, so we accept
    # minor overshoot rather than looping.
    if not (min_words - 20 <= wc <= max_words + 30):
        print(f"[warn] script word count {wc} outside target band for '{article['title'][:50]}...'")

    return {
        **article,
        "hindi_script": script,
        "word_count": wc,
    }


def summarize_batch(articles: list[dict], pause_seconds: float = 1.0) -> list[dict]:
    """Sequential, with a small pause between calls to stay well under free-tier RPM limits."""
    results = []
    for i, article in enumerate(articles, 1):
        print(f"[info] summarizing {i}/{len(articles)}: {article['title'][:60]}")
        summarized = summarize_article(article)
        if summarized:
            results.append(summarized)
        if i < len(articles):
            time.sleep(pause_seconds)
    return results


def _latest_raw_news_file() -> Path:
    candidates = sorted(DATA_DIR.glob("raw_news_*.json"))
    if not candidates:
        raise FileNotFoundError("No raw_news_*.json found — run fetch_news.py first.")
    return candidates[-1]


def main():
    raw_path = _latest_raw_news_file()
    with open(raw_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"[info] loaded {len(articles)} articles from {raw_path}")
    summarized = summarize_batch(articles)
    print(f"[info] successfully summarized {len(summarized)}/{len(articles)} articles")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"scripts_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summarized, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
