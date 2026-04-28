"""Reusable icon glyphs.

Two groups:

  PNG-embedded icons — load a real artwork once, recolour to any tint,
  paste into the banner at the requested size:
    * `paste_caduceus`     — Hermes's herald wand (Wikimedia line drawing)
    * `paste_github_mark`  — official Octicons GitHub mark

  Programmatic glyphs — drawn directly with PIL primitives, useful for
  small ambient decorations:
    * `draw_margin_icons`  — small editorial vignettes
    * `draw_github_mark`   — fallback silhouette (no PNG required)
    * `draw_caduceus`      — fallback line drawing

Adding new icons: drop a `paste_<name>` or `draw_<name>` function below
and import it where you need it. Each icon paints into an existing
Image / ImageDraw — no global state.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageOps

from . import config, typography


# ── PNG-embedded icons ──────────────────────────────────────────────────

_png_cache: dict[str, Image.Image] = {}


def _load_png(path) -> Image.Image:
    key = str(path)
    if key not in _png_cache:
        _png_cache[key] = Image.open(path).convert("RGBA")
    return _png_cache[key].copy()


def _recolour(src: Image.Image, color: tuple[int, int, int],
              alpha: int = 255) -> Image.Image:
    """Recolour a single-tone artwork to `color`.

    Picks the right "silhouette mask" for the source format:

    * **Alpha-shaped PNG** (e.g. Octicons Github mark — opaque shape on
      a transparent background): use the alpha channel directly.
    * **Line-art on white** (e.g. PSF caduceus — black ink on a white
      background): use inverted luminance so dark ink becomes opaque
      coloured pixels and the white background drops out.

    We detect the alpha-shaped case by checking whether the source
    actually has variable alpha. If it does, alpha is the silhouette;
    otherwise we fall back to luminance.
    """
    if src.mode == "RGBA":
        a_channel = src.split()[3]
        a_min, a_max = a_channel.getextrema()
        has_real_alpha = a_min < 250 and a_max > 5
    else:
        has_real_alpha = False

    if has_real_alpha:
        mask = a_channel
    else:
        # Line-art: dark pixels are the silhouette.
        grey = ImageOps.grayscale(src)
        mask = ImageOps.invert(grey)

    out = Image.new("RGBA", src.size, (*color, 0))
    fill = Image.new("RGBA", src.size, (*color, alpha))
    out.paste(fill, (0, 0), mask)
    return out


def paste_png(im: Image.Image, src_path, cx: int, cy: int,
              height: int, color: tuple[int, int, int],
              alpha: int = 255) -> None:
    """Paste a single-tone PNG at (cx, cy) scaled to `height`, recoloured."""
    if alpha <= 0:
        return
    src = _load_png(src_path)
    aspect = src.width / src.height
    target_h = height
    target_w = max(1, int(round(target_h * aspect)))
    src = src.resize((target_w, target_h), Image.LANCZOS)
    tinted = _recolour(src, color, alpha)
    im.paste(tinted, (cx - target_w // 2, cy - target_h // 2), tinted)


def paste_caduceus(im: Image.Image, cx: int, cy: int, height: int,
                   color: tuple[int, int, int] = config.HERMES_GOLD,
                   alpha: int = 255) -> None:
    """Hermes's herald wand — PNG-embedded line drawing."""
    paste_png(im, config.ASSETS / "source" / "caduceus.jpg",
              cx, cy, height, color, alpha)


def paste_github_mark(im: Image.Image, cx: int, cy: int, height: int,
                      color: tuple[int, int, int] = config.INK,
                      alpha: int = 255) -> None:
    """Official Octicons GitHub mark — PNG-embedded."""
    paste_png(im, config.ASSETS / "source" / "github-mark.png",
              cx, cy, height, color, alpha)


# ── programmatic fallbacks (kept for ambient decoration) ────────────────


# ── right-margin editorial vignettes ────────────────────────────────────

def draw_margin_icons(d: ImageDraw.ImageDraw, alpha: int) -> None:
    """Magnifying glass + doc + curly braces. Used as ambient decoration."""
    col = (*config.INK_SOFT, alpha)
    W = config.W

    # Magnifying glass
    cx, cy, r = W - 50, 40, 10
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=2)
    d.line((cx + 7, cy + 7, cx + 14, cy + 14), fill=col, width=2)

    # Curly braces
    bx, by = W - 48, 180
    d.text((bx, by), "{ }", font=typography.caption_sans(), fill=col)

    # Doc icon
    dx, dy = W - 56, 110
    d.rectangle((dx, dy, dx + 16, dy + 20), outline=col, width=2)
    d.line((dx + 4, dy + 6, dx + 12, dy + 6), fill=col, width=1)
    d.line((dx + 4, dy + 11, dx + 12, dy + 11), fill=col, width=1)
    d.line((dx + 4, dy + 16, dx + 9, dy + 16), fill=col, width=1)


# ── GitHub mark ─────────────────────────────────────────────────────────

def draw_github_mark(d: ImageDraw.ImageDraw, cx: int, cy: int,
                     size: int, color: tuple[int, int, int],
                     alpha: int = 255) -> None:
    """Filled circular silhouette + ear nubs + tail-tick.

    Reads as "GitHub" because of the cat-face proportions, without
    reproducing the official Octocat. Renders crisp at sizes 12-32 px.
    """
    if alpha <= 0:
        return
    col = (*color, alpha)
    bg = (*config.PAPER, alpha)
    r = size // 2

    # main circle
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    # ear nubs
    nub = max(2, size // 6)
    d.ellipse((cx - r - 1, cy - r - 1, cx - r + nub + 1, cy - r + nub + 1),
              fill=col)
    d.ellipse((cx + r - nub - 1, cy - r - 1, cx + r + 1, cy - r + nub + 1),
              fill=col)
    # tail flick
    d.line((cx + r - nub, cy + r - nub,
            cx + r + nub - 1, cy + r + nub - 1),
           fill=col, width=max(2, size // 8))
    # negative-space "eyes" so it reads as a mark, not a blob
    eye_r = max(1, size // 10)
    d.ellipse((cx - 3 * eye_r, cy - eye_r,
               cx - eye_r, cy + eye_r), fill=bg)
    d.ellipse((cx + eye_r, cy - eye_r,
               cx + 3 * eye_r, cy + eye_r), fill=bg)


# ── Caduceus (Hermes's wand) ────────────────────────────────────────────

def draw_caduceus(d: ImageDraw.ImageDraw, cx: int, cy: int,
                  height: int, color: tuple[int, int, int],
                  alpha: int = 255) -> None:
    """Hermes's herald wand: vertical staff + two snakes + spread wings.

    Drawn in line-art style. Staff height = `height`. Wings span ~height
    horizontally. (cx, cy) is the visual centre.
    """
    if alpha <= 0:
        return
    col = (*color, alpha)
    half = height // 2
    top = cy - half
    bot = cy + half

    line_w = max(1, height // 28)

    # ── staff ────────────────────────────────────────────────────────────
    d.line((cx, top + 4, cx, bot), fill=col, width=line_w + 1)

    # finial orb at the tip
    orb_r = max(2, height // 22)
    d.ellipse((cx - orb_r, top - orb_r,
               cx + orb_r, top + orb_r), fill=col)

    # ── wings (two arcs spreading from below the orb) ───────────────────
    wing_y = top + max(3, height // 14)
    span = max(8, height // 2)
    # left wing — series of feather-curves
    for i in range(3):
        d.arc(
            (cx - span - i * 2, wing_y - 2 - i,
             cx - 2, wing_y + max(4, height // 14) + i * 2),
            start=180, end=350,
            fill=col, width=line_w,
        )
    # right wing — mirror
    for i in range(3):
        d.arc(
            (cx + 2, wing_y - 2 - i,
             cx + span + i * 2, wing_y + max(4, height // 14) + i * 2),
            start=190, end=360,
            fill=col, width=line_w,
        )

    # ── two snakes (sinusoidal coils crossing the staff) ────────────────
    snake_top = top + max(6, height // 8)
    snake_bot = bot - max(2, height // 16)
    n = 24
    amp = max(3, height // 10)
    cycles = 1.6
    for phase in (0.0, math.pi):
        pts = []
        for i in range(n + 1):
            t = i / n
            y = snake_top + (snake_bot - snake_top) * t
            x = cx + amp * math.sin(t * cycles * 2 * math.pi + phase)
            pts.append((x, y))
        d.line(pts, fill=col, width=line_w)
        # head — slightly larger dot at the top end of each snake
        head = pts[0]
        d.ellipse((head[0] - line_w - 1, head[1] - line_w - 1,
                   head[0] + line_w + 1, head[1] + line_w + 1),
                  fill=col)
