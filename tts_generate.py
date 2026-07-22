"""
Stage 4 — Convert each article's Hindi script into a voiceover.

Uses edge-tts: free, no API key, Microsoft neural voices with natural Hindi
pronunciation (much better than gTTS for this use case). As a side effect of
synthesis, edge-tts also emits word-boundary timing events, which we turn
into a .srt subtitle file — giving stage 5 accurate subtitle timestamps
without any separate (and costly) forced-alignment step.

Output per article: data/media/<id>/voiceover.mp3 + data/media/<id>/subtitles.srt
Manifest: data/audio_<date>.json
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

import edge_tts

from config import (
    DATA_DIR,
    MEDIA_DIR,
    TTS_VOICE,
    TTS_RATE,
    TTS_VOLUME,
    TTS_PAUSE_SECONDS,
)


async def _synthesize_with_subtitles(text: str, audio_path: Path, srt_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice=TTS_VOICE, rate=TTS_RATE, volume=TTS_VOLUME)
    submaker = edge_tts.SubMaker()

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(submaker.get_srt())


def _get_audio_duration_seconds(audio_path: Path) -> float:
    """Independent duration check via ffprobe (ffmpeg is required for stage 5 anyway)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return round(float(result.stdout.strip()), 2)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"[warn] could not read duration for {audio_path} (is ffmpeg/ffprobe installed?): {e}")
        return 0.0


def generate_voiceover(article: dict) -> dict:
    article_dir = MEDIA_DIR / article["id"]
    article_dir.mkdir(parents=True, exist_ok=True)

    audio_path = article_dir / "voiceover.mp3"
    srt_path = article_dir / "subtitles.srt"

    asyncio.run(_synthesize_with_subtitles(article["hindi_script"], audio_path, srt_path))
    duration = _get_audio_duration_seconds(audio_path)

    return {
        "audio_path": str(audio_path),
        "subtitle_path": str(srt_path),
        "duration_seconds": duration,
        "voice": TTS_VOICE,
    }


def _latest_visuals_file() -> Path:
    candidates = sorted(DATA_DIR.glob("visuals_*.json"))
    if not candidates:
        raise FileNotFoundError("No visuals_*.json found — run fetch_visuals.py first.")
    return candidates[-1]


def main():
    visuals_path = _latest_visuals_file()
    with open(visuals_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"[info] loaded {len(articles)} articles from {visuals_path}")

    results = []
    for i, article in enumerate(articles, 1):
        print(f"[info] synthesizing voiceover {i}/{len(articles)}: {article['title'][:60]}")
        try:
            audio_info = generate_voiceover(article)
            results.append({**article, **audio_info})
            print(f"       -> {audio_info['duration_seconds']}s audio")
        except Exception as e:
            print(f"[warn] TTS failed for '{article['title'][:50]}...': {e}")
        if i < len(articles):
            time.sleep(TTS_PAUSE_SECONDS)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"audio_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()
