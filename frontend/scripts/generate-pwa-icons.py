"""Generate the Hexagare PWA icon set into ``frontend/public/``.

Run from ``frontend/``::

    python scripts/generate-pwa-icons.py

Produces a dark rounded-square mark with a scan-line / barcode motif that
matches the app shell's near-black primary colour. Committed so the icons
are reproducible rather than opaque binaries.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).resolve().parent.parent / "public"

# hsl(222.2 47.4% 11.2%) -> the app's --primary, plus a light foreground.
BG = (15, 23, 42, 255)
FG = (241, 245, 249, 255)
ACCENT = (56, 189, 248, 255)

# Barcode bar layout as fractions of the glyph width: (x, width, is_accent).
BARS = [
    (0.00, 0.10, False),
    (0.14, 0.06, False),
    (0.24, 0.12, True),
    (0.40, 0.06, False),
    (0.50, 0.10, False),
    (0.64, 0.06, False),
    (0.74, 0.14, True),
    (0.92, 0.08, False),
]


def _rounded(size: int, radius_frac: float, fill) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=fill)
    return img


def _draw_glyph(img: Image.Image, inset_frac: float) -> None:
    """Draw the scan frame + barcode bars centred in ``img``."""
    size = img.size[0]
    d = ImageDraw.Draw(img)
    inset = int(size * inset_frac)
    box = (inset, inset, size - inset, size - inset)
    gw = box[2] - box[0]
    gh = box[3] - box[1]

    # Corner brackets (viewfinder).
    arm = int(gw * 0.24)
    stroke = max(2, int(size * 0.035))
    for cx, cy, dx, dy in (
        (box[0], box[1], 1, 1),
        (box[2], box[1], -1, 1),
        (box[0], box[3], 1, -1),
        (box[2], box[3], -1, -1),
    ):
        d.line([(cx, cy), (cx + dx * arm, cy)], fill=FG, width=stroke)
        d.line([(cx, cy), (cx, cy + dy * arm)], fill=FG, width=stroke)

    # Barcode bars inside the frame.
    bar_pad = int(gh * 0.26)
    bar_top = box[1] + bar_pad
    bar_bot = box[3] - bar_pad
    span_x0 = box[0] + int(gw * 0.16)
    span_w = int(gw * 0.68)
    for x_frac, w_frac, is_accent in BARS:
        x0 = span_x0 + int(span_w * x_frac)
        x1 = x0 + max(2, int(span_w * w_frac * 0.7))
        d.rectangle([x0, bar_top, x1, bar_bot], fill=ACCENT if is_accent else FG)

    # Scan line across the middle.
    mid = (bar_top + bar_bot) // 2
    d.line([(span_x0, mid), (span_x0 + span_w, mid)], fill=ACCENT, width=stroke)


def make_icon(size: int, *, maskable: bool = False) -> Image.Image:
    # Maskable icons need the glyph inside the safe zone (~80%); standard
    # icons can use a tighter rounded square.
    radius_frac = 0.5 if maskable else 0.22
    img = _rounded(size, radius_frac, BG)
    _draw_glyph(img, inset_frac=0.30 if maskable else 0.22)
    return img


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    make_icon(192).save(PUBLIC / "pwa-192x192.png")
    make_icon(512).save(PUBLIC / "pwa-512x512.png")
    make_icon(512, maskable=True).save(PUBLIC / "pwa-maskable-512x512.png")
    make_icon(180).save(PUBLIC / "apple-touch-icon.png")

    favicon = make_icon(64)
    favicon.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"wrote icons to {PUBLIC}")


if __name__ == "__main__":
    main()
