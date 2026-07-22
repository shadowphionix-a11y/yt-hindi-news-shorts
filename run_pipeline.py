"""
Stage 7 — Orchestrate the full daily pipeline: fetch -> summarize -> visuals ->
TTS -> video -> upload, in one command, suitable for an unattended scheduler
(GitHub Actions or an Oracle Cloud Always Free VM cron job — see README).

Design for unattended runs:
- Each stage's own main() already handles per-article failures internally
  (skips a bad article, keeps going) — this orchestrator only needs to treat
  a whole-stage exception as fatal, since every later stage depends on the
  previous stage's output file existing.
- Logs to both stdout (captured by GitHub Actions / cron) and a per-day log
  file under data/logs/, so a failure is diagnosable after the fact.
- Non-zero exit code on fatal failure so the scheduler can flag/alert on it.
- --skip-upload lets you dry-run the content pipeline without touching
  YouTube (handy while testing prompts/visuals/voice).
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from config import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _setup_logging() -> logging.Logger:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"pipeline_{today}.log"

    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def _run_stage(logger: logging.Logger, name: str, main_fn):
    logger.info(f"===== starting stage: {name} =====")
    start = time.time()
    try:
        main_fn()
    except Exception:
        elapsed = time.time() - start
        logger.exception(f"===== FATAL: stage '{name}' failed after {elapsed:.1f}s — stopping pipeline =====")
        raise
    elapsed = time.time() - start
    logger.info(f"===== finished stage: {name} ({elapsed:.1f}s) =====")


def main():
    parser = argparse.ArgumentParser(description="Run the full daily Hindi news video pipeline.")
    parser.add_argument("--skip-upload", action="store_true", help="Build videos but don't upload to YouTube.")
    args = parser.parse_args()

    logger = _setup_logging()
    pipeline_start = time.time()

    # Imported here (not at module top) so a missing dependency for one stage
    # (e.g. edge-tts not installed yet) doesn't block --help or early stages.
    import fetch_news
    import summarize_hindi
    import fetch_visuals
    import tts_generate
    import build_video

    stages = [
        ("fetch_news", fetch_news.main),
        ("summarize_hindi", summarize_hindi.main),
        ("fetch_visuals", fetch_visuals.main),
        ("tts_generate", tts_generate.main),
        ("build_video", build_video.main),
    ]

    if not args.skip_upload:
        import upload_youtube
        stages.append(("upload_youtube", upload_youtube.main))
    else:
        logger.info("--skip-upload set: pipeline will build videos but not upload them")

    try:
        for name, fn in stages:
            _run_stage(logger, name, fn)
    except Exception:
        logger.error("Pipeline aborted due to a fatal stage failure. See traceback above.")
        sys.exit(1)

    total_elapsed = time.time() - pipeline_start
    logger.info(f"===== pipeline complete in {total_elapsed:.1f}s =====")


if __name__ == "__main__":
    main()
