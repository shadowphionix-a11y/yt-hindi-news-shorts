"""
Generates a "breaking news"-style headline card when no suitable stock
video/photo is found. Designed to hold attention past the first few seconds:
- diagonal gradient background (color varies by category — visual variety
  across a day's videos instead of every slide looking identical)
- dark vignette so text stays readable regardless of gradient brightness
- pill-shaped category tag (like a news-channel "lower third")
- large, auto-sized bold Hindi headline, word-wrapped
- thin accent bar + story counter ("1/5") — a small progress cue that gives
  viewers a reason to keep watching to the end
"""

from PIL import Image, ImageDraw, ImageFont

from config import (
    CARD_WIDTH,
    CARD_HEIGHT,
    CATEGORY_STYLES,
    FONT_BOLD_PATH,
    FONT_REGULAR_PATH,
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _diagonal_gradient(size: tuple[int, int], color_a: str, color_b: str) -> Image.Image:
    w, h = size
    rgb_a = _hex_to_rgb(color_a)
    rgb_b = _hex_to_rgb(color_b)

    base = Image.new("RGB", (w, h), rgb_a)
    top = Image.new("RGB", (w, h), rgb_b)
    mask = Image.new("L", (w, h))
    diag_len = w + h
    mask_data = [int(255 * ((x + y) / diag_len)) for y in range(h) for x in range(w)]
    mask.putdata(mask_data)

    base.paste(top, (0, 0), mask)
    return base


def _load_font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Missing font at {path}. Download Noto Sans Devanagari (free, Google Fonts) "
            "and place Bold/Regular .ttf files there — see config.py comment."
        )
    return ImageFont.truetype(str(path), size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_headline_font(draw, text: str, max_width: int, max_height: int, start_size: int = 96, min_size: int = 48):
    """Shrink font size until the wrapped headline fits within max_height."""
    size = start_size
    while size >= min_size:
        font = _load_font(bold=True, size=size)
        lines = _wrap_text(draw, text, font, max_width)
        line_height = int(size * 1.35)
        total_height = line_height * len(lines)
        if total_height <= max_height:
            return font, lines, line_height
        size -= 4
    font = _load_font(bold=True, size=min_size)
    lines = _wrap_text(draw, text, font, max_width)
    return font, lines, int(min_size * 1.35)


def generate_headline_card(
    hindi_headline: str,
    category: str,
    story_index: int,
    story_total: int,
    out_path,
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
) -> str:
    """Render and save a headline card at the given size (defaults to short-form 1080x1920).
    Pass width/height explicitly for long-form (1920x1080) so the layout is native to that
    aspect ratio rather than a crop of the vertical version — that's what avoids cutting
    off headline text/subjects when a story is long-form."""
    style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["national"])
    color_a, color_b = style["gradient"]

    img = _diagonal_gradient((width, height), color_a, color_b)

    # Vignette: darken top/bottom bands so overlaid text/tag stay legible on any gradient
    vignette = Image.new("L", (width, height), 0)
    vgrad = ImageDraw.Draw(vignette)
    for y in range(height):
        dist_from_edge = min(y, height - y)
        alpha = max(0, 140 - int(dist_from_edge * 0.35))
        vgrad.line([(0, y), (width, y)], fill=alpha)
    dark_overlay = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.composite(dark_overlay, img, vignette)

    draw = ImageDraw.Draw(img)
    margin = 80

    # --- Category tag (pill) ---
    tag_font = _load_font(bold=True, size=44)
    tag_text = style["tag"]
    tag_w = draw.textlength(tag_text, font=tag_font) + 60
    tag_h = 90
    tag_y = 90 if height <= 1080 else 130  # tighter top margin on the shorter 16:9 frame
    draw.rounded_rectangle(
        [(margin, tag_y), (margin + tag_w, tag_y + tag_h)],
        radius=tag_h // 2,
        fill=_hex_to_rgb(color_b),
    )
    draw.text((margin + 30, tag_y + 18), tag_text, font=tag_font, fill="white")

    # --- Headline (auto-sized, wrapped, vertically centered in the middle band) ---
    max_text_width = width - 2 * margin
    headline_zone_top = tag_y + tag_h + 60
    bottom_reserve = 130 if height <= 1080 else 300  # less reserved space on the shorter frame
    headline_zone_height = height - headline_zone_top - bottom_reserve

    font, lines, line_height = _fit_headline_font(
        draw, hindi_headline, max_text_width, headline_zone_height
    )
    total_text_height = line_height * len(lines)
    start_y = headline_zone_top + (headline_zone_height - total_text_height) // 2

    y = start_y
    for line in lines:
        draw.text((margin, y), line, font=font, fill="white")
        y += line_height

    # --- Bottom accent bar + story progress counter (a small "keep watching" cue) ---
    bar_y = height - (100 if height <= 1080 else 160)
    draw.rectangle([(margin, bar_y), (margin + 140, bar_y + 8)], fill=_hex_to_rgb(color_b))

    counter_font = _load_font(bold=False, size=38)
    counter_text = f"{story_index}/{story_total}"
    draw.text((margin, bar_y + 30), counter_text, font=counter_font, fill=(220, 220, 220))

    img.save(out_path, quality=92)
    return str(out_path)
