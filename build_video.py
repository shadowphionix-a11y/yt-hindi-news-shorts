"""
Stage 5 — Assemble the final video for each article:
  background (stock video looped/trimmed, OR stock photo/generated card with
  a Ken Burns zoom) + burned-in Hindi subtitles + voiceover mixed with
  low-volume background music.

Three ffmpeg passes, kept separate on purpose (easier to debug/re-run a
single failed step than one giant filter graph):
  1. _prepare_background  -> silent video, exact duration, 1080x1920
  2. _burn_subtitles       -> same video with captions burned in
  3. _mux_audio            -> mux captioned video with voiceover + bg music

Output: data/media/<id>/final.mp4 ; manifest: data/videos_<date>.json
"""

import json
import random
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from config import (
    DATA_DIR,
    MEDIA_DIR,
    MUSIC_DIR,
    MUSIC_VOLUME,
    VOICEOVER_VOLUME,
    FPS,
    ZOOM_RATE_PER_FRAME,
    ZOOM_MAX,
    FONT_DIR,
    SUBTITLE_FONT_NAME,
    VIDEO_CRF,
    VIDEO_PRESET,
    VIDEO_FORMATS,
)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr[-2000:]}")


def _escape_for_filter(path: Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filtergraph argument."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def _prepare_background(article: dict, duration: float, out_path: Path) -> None:
    """Produce a silent, exactly-duration background clip sized natively for this
    article's format (short = 1080x1920, long = 1920x1080 — never a crop of the other)."""
    fmt = VIDEO_FORMATS[article.get("format", "short")]
    width, height = fmt["width"], fmt["height"]

    if article["visual_type"] == "stock_video":
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", article["path"],
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                   f"crop={width}:{height},format=yuv420p",
            "-t", str(duration),
            "-an", "-r", str(FPS),
            str(out_path),
        ]
    else:
        # stock_photo or generated_card: static image + Ken Burns zoom
        total_frames = max(int(duration * FPS), FPS)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", article["path"],
            "-vf", (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"zoompan=z='min(zoom+{ZOOM_RATE_PER_FRAME},{ZOOM_MAX})':"
                f"d={total_frames}:s={width}x{height}:fps={FPS},format=yuv420p"
            ),
            "-t", str(duration),
            "-r", str(FPS),
            str(out_path),
        ]
    _run(cmd)


def _burn_subtitles(background_path: Path, subtitle_path: Path, out_path: Path, fmt: dict) -> None:
    srt_escaped = _escape_for_filter(subtitle_path)
    fontsdir_escaped = _escape_for_filter(FONT_DIR)
    style = (
        f"FontName={SUBTITLE_FONT_NAME},FontSize={fmt['subtitle_font_size']},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,"
        f"Outline=2,Shadow=0,Alignment=2,MarginV={fmt['subtitle_margin_v']}"
    )
    vf = f"subtitles='{srt_escaped}':fontsdir='{fontsdir_escaped}':force_style='{style}'"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(background_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-an",
        str(out_path),
    ]
    _run(cmd)


def _pick_music_track() -> Path | None:
    tracks = list(MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        return None
    return random.choice(tracks)


def _mux_audio(captioned_path: Path, voiceover_path: Path, duration: float, out_path: Path) -> None:
    music_path = _pick_music_track()

    if music_path:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(captioned_path),
            "-stream_loop", "-1", "-i", str(music_path),
            "-i", str(voiceover_path),
            "-filter_complex",
            (
                f"[1:a]volume={MUSIC_VOLUME},atrim=0:{duration},asetpts=PTS-STARTPTS,"
                f"afade=t=out:st={max(duration - 1, 0)}:d=1[bg];"
                f"[2:a]volume={VOICEOVER_VOLUME}[vo];"
                "[bg][vo]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            ),
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(out_path),
        ]
    else:
        print("[warn] no background music found in assets/music/ — voiceover only")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(captioned_path),
            "-i", str(voiceover_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(out_path),
        ]
    _run(cmd)


def build_video(article: dict) -> str:
    article_dir = MEDIA_DIR / article["id"]
    article_dir.mkdir(parents=True, exist_ok=True)

    duration = article["duration_seconds"]
    if not duration or duration <= 0:
        raise ValueError(f"Article {article['id']} has no valid duration_seconds — check stage 4 output.")

    background_path = article_dir / "background_prepared.mp4"
    captioned_path = article_dir / "captioned.mp4"
    final_path = article_dir / "final.mp4"

    _prepare_background(article, duration, background_path)
    _burn_subtitles(background_path, Path(article["subtitle_path"]), captioned_path, VIDEO_FORMATS[article.get("format", "short")])
    _mux_audio(captioned_path, Path(article["audio_path"]), duration, final_path)

    # Clean up intermediates — keep only what's needed for stage 6 upload / debugging
    background_path.unlink(missing_ok=True)
    captioned_path.unlink(missing_ok=True)

    return str(final_path)


def _latest_audio_file() -> Path:
    candidates = sorted(DATA_DIR.glob("audio_*.json"))
    if not candidates:
        raise FileNotFoundError("No audio_*.json found — run tts_generate.py first.")
    return candidates[-1]


def main():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH — install it before running this stage.")

    audio_path = _latest_audio_file()
    with open(audio_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"[info] loaded {len(articles)} articles from {audio_path}")

    results = []
    for i, article in enumerate(articles, 1):
        print(f"[info] building video {i}/{len(articles)}: {article['title'][:60]}")
        try:
            final_path = build_video(article)
            results.append({**article, "final_video_path": final_path})
            print(f"       -> {final_path}")
        except Exception as e:
            print(f"[warn] video build failed for '{article['title'][:50]}...': {e}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DATA_DIR / f"videos_{today}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote {out_path} ({len(results)}/{len(articles)} videos built)")
    return out_path


if __name__ == "__main__":
    main()
