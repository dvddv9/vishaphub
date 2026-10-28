# -*- coding: utf-8 -*-
"""Generate the Tauri icon set for Vishap (Block 38).

``cargo tauri init`` normally drops a set of generic Tauri icons under
``src-tauri/icons/``. This project ships its own mark instead: a dark rounded
tile with a teal hexagonal badge and a white "V" glyph, so the installed
``.exe`` does not carry the default Tauri logo.

Windows needs a multi-resolution ``.ico`` (16/24/32/48/64/128/256). The PNGs are
used by the tray/favicon paths and by the non-Windows bundles.

Usage:
    python scripts/make_tauri_icons.py [--out DIR]

Deterministic: no randomness, no network. Overwrites the files it generates.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

# Colours picked to match ui-next/src/app/globals.css (dark surface + teal).
BG_TOP = (12, 18, 32)
BG_BOTTOM = (23, 35, 58)
TEAL = (45, 212, 191)
WHITE = (240, 248, 255)

# Sizes Windows/macOS/Linux bundles ask for.
PNG_SIZES = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.png": 512,
}
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _rounded_gradient(size: int) -> Image.Image:
    """Dark vertical gradient inside a squircle."""
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        grad.putpixel(
            (0, y),
            tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)),
        )
    base = grad.resize((size, size)).convert("RGBA")

    mask = Image.new("L", (size, size), 0)
    radius = round(size * 0.22)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    base.putalpha(mask)
    return base


def _hexagon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, width: int) -> None:
    points = [
        (
            cx + r * math.cos(math.radians(60 * i - 30)),
            cy + r * math.sin(math.radians(60 * i - 30)),
        )
        for i in range(6)
    ]
    draw.line(points + [points[0]], fill=TEAL, width=width, joint="curve")


def _v_glyph(draw: ImageDraw.ImageDraw, size: int) -> None:
    """A heavy "V" — Vishap's initial — with squared-off terminals."""
    w = size * 0.24  # half-width of the glyph bounding box
    top = size * 0.36
    bottom = size * 0.68
    stroke = max(2, round(size * 0.082))
    cx = size / 2
    # One polyline, so the joint at the apex is filled instead of notched.
    draw.line(
        [(cx - w, top), (cx, bottom), (cx + w, top)],
        fill=WHITE,
        width=stroke,
        joint="curve",
    )


def render(size: int) -> Image.Image:
    """Render the Vishap mark at an arbitrary size."""
    # Draw at 4x and downsample so the strokes and the hexagon stay clean at 16px.
    ss = 4
    big = size * ss
    img = _rounded_gradient(big)
    draw = ImageDraw.Draw(img)

    _hexagon(draw, big / 2, big / 2, big * 0.375, max(2, round(big * 0.018)))
    _v_glyph(draw, big)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Vishap Tauri icons")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "src-tauri" / "icons"),
        help="output directory (default: src-tauri/icons)",
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for name, size in PNG_SIZES.items():
        path = out / name
        render(size).save(path, format="PNG", optimize=True)
        print(f"{path.name}: {size}x{size} ({path.stat().st_size} bytes)")

    # One render per size, then let Pillow pack them into a single .ico.
    frames = [render(s) for s in ICO_SIZES]
    ico = out / "icon.ico"
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"{ico.name}: {ico.stat().st_size} bytes ({len(ICO_SIZES)} sizes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
