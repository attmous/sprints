#!/usr/bin/env python3
"""Generate the editorial-style animated banner GIF for the README.

Composition (left → right):

    DAEDALUS                                        [marble bust]
    ──────                                          (eyes covered by
    Agents that fly.                                 a painted cyan
    Workflows that don't melt.                       brushstroke)
    Hot-reload · leases · stalls · shadow → active
                                          [labyrinth network]
                                          [floating code overlays]

Animations (~5 s loop):

    0.0–1.5 s   constellation/labyrinth network draws in
    0.7–2.5 s   three code snippets fade in, staggered
    2.0–2.8 s   brushstroke paints across the bust's eyes
    2.8–3.4 s   gold underline draws in beneath the title
    3.4–4.5 s   hold
    4.5–5.0 s   constellation fades back to ghost-trace, loop

Re-run with::

    /usr/bin/python3 scripts/build_banner_gif.py

Writes assets/daedalus-banner.gif.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "assets" / "daedalus-banner.gif"
BUST_SRC = ROOT / "assets" / "source" / "plato-bust.jpg"
FONT_DISPLAY = ROOT / "assets" / "fonts" / "PlayfairDisplay.ttf"
FONT_DISPLAY_ITALIC = ROOT / "assets" / "fonts" / "PlayfairDisplay-Italic.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Editorial 3:1 banner.
W, H = 1200, 400

# Palette — parchment + brand cyan + muted earth tones.
PAPER = (232, 226, 213)        # cream parchment
PAPER_SHADOW = (210, 202, 186)
INK = (28, 32, 36)              # near-black for body text
INK_SOFT = (76, 84, 92)
CYAN = (16, 130, 142)           # darker, painterly version of #22D3EE
CYAN_BRIGHT = (34, 180, 195)
GOLD = (180, 148, 78)           # editorial accent under subtitle
NETWORK_COLORS = [
    (110, 70, 60),    # burgundy
    (170, 130, 70),   # ochre
    (60, 110, 110),   # teal-grey
    (120, 130, 90),   # olive
    (90, 80, 110),    # ink-purple
    (160, 100, 80),   # terracotta
]

FRAMES = 50
DURATION_MS = 80  # 12.5 fps — easier on palette + filesize

random.seed(7)  # deterministic constellation


# ──────────────────────────── helpers ─────────────────────────────────────

def ease(t: float) -> float:
    """Smooth in-out easing on [0, 1]."""
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def font(path, size: int) -> ImageFont.ImageFont:
    p = str(path)
    if Path(p).exists():
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_TITLE = font(FONT_DISPLAY, 100)
F_SUB = font(FONT_DISPLAY, 38)
F_SUB_IT = font(FONT_DISPLAY_ITALIC, 38)
F_TAG = font(FONT_SANS, 15)
F_CAPTION = font(FONT_SANS, 13)
F_CODE = font(FONT_MONO, 14)
F_CODE_SMALL = font(FONT_MONO, 12)


# ──────────────────────────── parchment ───────────────────────────────────

def make_parchment(w: int, h: int) -> Image.Image:
    """Cream paper background with subtle warm vignette + grain."""
    base = Image.new("RGB", (w, h), PAPER)
    px = base.load()
    rng = random.Random(11)
    # soft warm vignette darker at edges
    cx, cy = w / 2, h / 2
    maxd = math.hypot(cx, cy)
    for y in range(h):
        for x in range(0, w, 2):  # every other pixel — fast, looks fine
            d = math.hypot(x - cx, y - cy) / maxd
            warm = int(8 * d)
            r = max(0, PAPER[0] - warm - rng.randint(0, 5))
            g = max(0, PAPER[1] - warm - rng.randint(0, 5))
            b = max(0, PAPER[2] - warm - rng.randint(0, 6))
            px[x, y] = (r, g, b)
            if x + 1 < w:
                px[x + 1, y] = (r, g, b)
    # add a few faint smudges
    smudge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(smudge)
    for _ in range(40):
        cx2 = rng.randint(0, w)
        cy2 = rng.randint(0, h)
        r2 = rng.randint(40, 140)
        a = rng.randint(4, 12)
        sd.ellipse((cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2),
                   fill=(110, 90, 60, a))
    smudge = smudge.filter(ImageFilter.GaussianBlur(radius=18))
    base.paste(smudge, (0, 0), smudge)
    return base


# ──────────────────────────── bust ────────────────────────────────────────

def prepare_bust() -> Image.Image:
    """Load the bust, desaturate slightly, key out the museum backdrop.

    The Wikimedia photo has a saturated blue-grey backdrop. We chroma-key
    against the background colour sampled from the corners and apply a
    soft alpha ramp so edges don't look cut out.
    """
    src = Image.open(BUST_SRC).convert("RGBA")
    w0, h0 = src.size
    src = src.crop((int(w0 * 0.05), int(h0 * 0.02),
                    int(w0 * 0.95), int(h0 * 0.78)))
    target_h = 380
    ratio = target_h / src.height
    src = src.resize((int(src.width * ratio), target_h), Image.LANCZOS)

    # Sample background colour from a 4-corner neighbourhood.
    px = src.load()
    samples = []
    for sx, sy in [(5, 5), (src.width - 6, 5),
                   (5, src.height - 6), (src.width - 6, src.height - 6)]:
        r, g, b, _ = px[sx, sy]
        samples.append((r, g, b))
    bg_r = sum(s[0] for s in samples) // len(samples)
    bg_g = sum(s[1] for s in samples) // len(samples)
    bg_b = sum(s[2] for s in samples) // len(samples)

    # Distance threshold: pixels within `near` of bg → fully transparent;
    # within `far` → linearly faded; beyond → fully opaque.
    near, far = 55, 95

    for y in range(src.height):
        for x in range(src.width):
            r, g, b, _ = px[x, y]
            d = math.sqrt(
                (r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2
            )
            if d <= near:
                a = 0
            elif d >= far:
                a = 255
            else:
                a = int((d - near) / (far - near) * 255)
            # warm/lift the marble a touch so it harmonises with parchment
            r2 = min(255, int(r * 1.02 + 4))
            g2 = min(255, int(g * 1.01 + 2))
            b2 = min(255, int(b * 0.97))
            px[x, y] = (r2, g2, b2, a)

    # Slight desaturation to pull the marble toward parchment-grey.
    rgb = src.convert("RGB")
    grey = ImageOps.grayscale(rgb).convert("RGB")
    blended = Image.blend(rgb, grey, 0.30)
    blended.putalpha(src.split()[3])

    # Soften the alpha mask edge so we don't see a hard chroma-key line.
    alpha = blended.split()[3].filter(ImageFilter.GaussianBlur(radius=1.2))
    blended.putalpha(alpha)
    return blended


# ──────────────────────────── constellation ───────────────────────────────

def build_constellation(seed_origin: tuple[int, int]) -> tuple[list, list]:
    """Generate scattered nodes + edges around the bust area.

    Returns (nodes, edges) where nodes is list of (x, y, radius, color)
    and edges is list of (i, j) index pairs.
    """
    rng = random.Random(3)
    cx, cy = seed_origin
    nodes = []
    # cluster near origin, with a few outliers drifting toward margins
    for _ in range(34):
        angle = rng.uniform(0, 2 * math.pi)
        # distance distribution — most close, some far
        dist = rng.choice([
            rng.uniform(40, 130),
            rng.uniform(140, 240),
            rng.uniform(260, 380),
        ])
        x = int(cx + math.cos(angle) * dist)
        y = int(cy + math.sin(angle) * dist * 0.7)  # vertically squashed
        r = rng.choice([3, 4, 5, 6, 8])
        c = rng.choice(NETWORK_COLORS)
        nodes.append((x, y, r, c))
    # build edges: connect each node to 1–3 nearest others
    edges = set()
    for i, (x1, y1, _, _) in enumerate(nodes):
        dists = sorted(
            [(j, math.hypot(x2 - x1, y2 - y1))
             for j, (x2, y2, _, _) in enumerate(nodes) if j != i],
            key=lambda p: p[1],
        )
        for j, _ in dists[: rng.randint(1, 3)]:
            a, b = sorted((i, j))
            edges.add((a, b))
    return nodes, sorted(edges)


# ──────────────────────────── code overlays ───────────────────────────────

# Top block — multi-agent config. Each line shows a distinct role +
# model + runtime so the reader sees this isn't one model, it's a team.
CODE_AGENTS_TOP = [
    [("agents:", CYAN)],
    [("  coder    ", INK), ("→ ", INK_SOFT),
     ("claude", CYAN_BRIGHT), ("/", INK_SOFT), ("sonnet-4.5", INK)],
    [("  reviewer ", INK), ("→ ", INK_SOFT),
     ("codex", CYAN_BRIGHT), ("/", INK_SOFT), ("gpt-5", INK)],
    [("  merger   ", INK), ("→ ", INK_SOFT),
     ("claude", CYAN_BRIGHT), ("/", INK_SOFT), ("haiku", INK)],
]

# Middle block — a GitHub-native lane state. Repo + issue number in the
# code overlay are the strongest "this works on real GitHub" signal.
CODE_GITHUB_MID = [
    [('{', INK), ('"repo"', CYAN), (': ', INK),
     ('"attmous/daedalus"', INK), (',', INK)],
    [(' "issue"', CYAN), (': ', INK), ('#42', CYAN_BRIGHT), (',', INK),
     ('  "label"', CYAN), (': ', INK), ('"active-lane"', INK), (',', INK)],
    [(' "state"', CYAN), (': ', INK),
     ('"awaiting_review"', CYAN_BRIGHT), ('}', INK)],
]

# Bottom block — turn log showing the agents collaborating in sequence.
# This is the most evocative of "multiple agents working an issue."
CODE_TURNLOG_BOT = [
    [("[coder]    ", CYAN), ("claude/sonnet  ", INK),
     ("✓ wrote 3 files", INK_SOFT)],
    [("[reviewer] ", CYAN), ("codex/gpt-5    ", INK),
     ("⚠ 2 nits, 1 fix", INK_SOFT)],
    [("[coder]    ", CYAN), ("claude/sonnet  ", INK),
     ("✓ pushed fixes", INK_SOFT)],
    [("[reviewer] ", CYAN), ("codex/gpt-5    ", INK),
     ("✓ approved →  merge", INK_SOFT)],
]


def draw_code_block(d: ImageDraw.ImageDraw, lines: list, x: int, y: int,
                    font: ImageFont.ImageFont, alpha: int) -> None:
    """Draw a list-of-tokens style code block at (x, y), respecting alpha."""
    line_h = font.size + 4
    if isinstance(lines[0], list):
        for i, line in enumerate(lines):
            tx = x
            for tok, color in line:
                d.text((tx, y + i * line_h), tok, font=font,
                       fill=(*color, alpha))
                bbox = font.getbbox(tok)
                tx += bbox[2] - bbox[0]
    else:
        tx = x
        for tok, color in lines:
            d.text((tx, y), tok, font=font, fill=(*color, alpha))
            bbox = font.getbbox(tok)
            tx += bbox[2] - bbox[0]


# ──────────────────────────── margin icons ───────────────────────────────

def draw_margin_icons(d: ImageDraw.ImageDraw, alpha: int) -> None:
    """Tiny line-drawn vignettes in the right margin — like the reference."""
    col = (*INK_SOFT, alpha)

    # Magnifying glass — top-right
    cx, cy, r = W - 50, 40, 10
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=2)
    d.line((cx + 7, cy + 7, cx + 14, cy + 14), fill=col, width=2)

    # Curly braces — middle-right
    bx, by = W - 48, 180
    d.text((bx, by), "{ }", font=F_TAG, fill=col)

    # Doc icon
    dx, dy = W - 56, 110
    d.rectangle((dx, dy, dx + 16, dy + 20), outline=col, width=2)
    d.line((dx + 4, dy + 6, dx + 12, dy + 6), fill=col, width=1)
    d.line((dx + 4, dy + 11, dx + 12, dy + 11), fill=col, width=1)
    d.line((dx + 4, dy + 16, dx + 9, dy + 16), fill=col, width=1)

    # GitHub-mark glyph — circle silhouette with a stylised cat-tail tick.
    # Conveys "GitHub" without infringing the official Octocat by being a
    # generic round shoulder + ear silhouette. Filled cyan-soft to read as
    # a mark, not an outlined icon like the others above.
    gx, gy, gr = W - 50, 252, 13
    d.ellipse((gx - gr, gy - gr, gx + gr, gy + gr), fill=col)
    # ear nubs
    d.ellipse((gx - gr - 1, gy - gr - 2, gx - gr + 6, gy - gr + 5), fill=col)
    d.ellipse((gx + gr - 5, gy - gr - 2, gx + gr + 1, gy - gr + 5), fill=col)
    # tail flick
    d.line((gx + gr - 3, gy + gr - 3, gx + gr + 4, gy + gr + 4),
           fill=col, width=2)
    # negative-space "eyes" (paper colour) so it reads as a face/mark
    paper_alpha = (*PAPER, alpha)
    d.ellipse((gx - 5, gy - 3, gx - 1, gy + 1), fill=paper_alpha)
    d.ellipse((gx + 1, gy - 3, gx + 5, gy + 1), fill=paper_alpha)
    # tiny "GH" label below the mark
    d.text((gx - 11, gy + gr + 4), "GitHub",
           font=F_CAPTION, fill=col)


# ──────────────────────────── brushstroke ─────────────────────────────────

def draw_brushstroke(im: Image.Image, x1: int, y1: int, x2: int, y2: int,
                     progress: float) -> None:
    """Paint a hand-painted-looking horizontal stroke from x1..x1+(x2-x1)*progress."""
    if progress <= 0:
        return
    rng = random.Random(99)
    end_x = int(x1 + (x2 - x1) * progress)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Multiple overlapping passes with jitter — simulates a thick brush
    height = abs(y2 - y1)
    cy = (y1 + y2) // 2
    for pass_i in range(7):
        y_jit = rng.randint(-3, 3)
        thick = height + rng.randint(-4, 4)
        a = rng.randint(180, 230)
        col = (CYAN[0] + rng.randint(-10, 10),
               CYAN[1] + rng.randint(-15, 15),
               CYAN[2] + rng.randint(-10, 10),
               a)
        ld.line(
            [(x1 - 4, cy + y_jit), (end_x, cy + y_jit)],
            fill=col, width=thick,
        )
    # Add irregular "bristle" tail at the leading edge
    if progress < 1.0:
        for _ in range(40):
            tx = end_x + rng.randint(-12, 6)
            ty = cy + rng.randint(-height // 2, height // 2)
            r = rng.randint(1, 3)
            ld.ellipse((tx - r, ty - r, tx + r, ty + r),
                       fill=(*CYAN, rng.randint(80, 200)))
    # Slight blur for the "wet paint" look
    layer = layer.filter(ImageFilter.GaussianBlur(radius=0.8))
    im.paste(layer, (0, 0), layer)


# ──────────────────────────── timeline ────────────────────────────────────

def constellation_progress(f: int) -> float:
    return ease(f / (FRAMES * 0.30))


def code_alpha(f: int, slot: int) -> int:
    """slot: 0,1,2 — staggered fade-in."""
    starts = [FRAMES * 0.18, FRAMES * 0.30, FRAMES * 0.42]
    span = FRAMES * 0.18
    p = ease((f - starts[slot]) / span)
    p = max(0.0, min(1.0, p))
    return int(255 * p)


def brush_progress(f: int) -> float:
    start = FRAMES * 0.45
    end = FRAMES * 0.62
    return ease((f - start) / (end - start)) if f >= start else 0.0


def underline_progress(f: int) -> float:
    start = FRAMES * 0.62
    end = FRAMES * 0.74
    return ease((f - start) / (end - start)) if f >= start else 0.0


def hold_to_loop(f: int) -> float:
    """Constellation/code dimming at end of loop for smooth wrap."""
    start = FRAMES * 0.90
    if f < start:
        return 1.0
    return 1.0 - ease((f - start) / (FRAMES - start)) * 0.55


# ──────────────────────────── pre-bake ────────────────────────────────────

print("baking parchment …")
PARCHMENT = make_parchment(W, H)
print("preparing bust …")
BUST = prepare_bust()
BUST_X = W - BUST.width - 30
BUST_Y = H - BUST.height + 10  # let bottom touch banner edge

# Bust eye-line: empirically ~28% from top of cropped bust.
BUST_EYE_Y = BUST_Y + int(BUST.height * 0.28)
BUST_EYE_X1 = BUST_X + int(BUST.width * 0.20)
BUST_EYE_X2 = BUST_X + int(BUST.width * 0.78)

# Constellation seed near the bust head's upper-right.
NODES, EDGES = build_constellation((BUST_X + BUST.width - 60, BUST_Y + 110))

# Title baseline
TITLE_X = 56
TITLE_Y = 70


# ──────────────────────────── frame renderer ──────────────────────────────

def render_frame(f: int) -> Image.Image:
    im = PARCHMENT.copy()
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    cp = constellation_progress(f) * hold_to_loop(f)

    # Constellation: edges first (back), then nodes
    n_visible_edges = int(len(EDGES) * cp)
    for i, (a, b) in enumerate(EDGES[:n_visible_edges]):
        x1, y1, _, _ = NODES[a]
        x2, y2, _, _ = NODES[b]
        # color is a blend toward the b-node color
        col = NODES[b][3]
        alpha = int(95 * hold_to_loop(f))
        d.line([(x1, y1), (x2, y2)], fill=(*col, alpha), width=1)
    n_visible_nodes = int(len(NODES) * cp)
    for x, y, r, c in NODES[:n_visible_nodes]:
        a = int(255 * hold_to_loop(f))
        # halo
        d.ellipse((x - r - 2, y - r - 2, x + r + 2, y + r + 2),
                  fill=(*c, max(0, a // 4)))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(*c, a))

    # Composite overlay onto parchment so bust can sit on top
    im.paste(overlay, (0, 0), overlay)

    # Bust on the right
    im.paste(BUST, (BUST_X, BUST_Y), BUST)

    # Brushstroke across the eyes — ON TOP of the bust
    bp = brush_progress(f)
    if bp > 0:
        draw_brushstroke(im, BUST_EYE_X1, BUST_EYE_Y - 22,
                         BUST_EYE_X2, BUST_EYE_Y + 22, bp)

    # Code overlays — drawn on a fresh RGBA layer so alpha works
    code_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(code_layer)
    a0, a1, a2 = code_alpha(f, 0), code_alpha(f, 1), code_alpha(f, 2)
    if a0 > 0:
        draw_code_block(cd, CODE_AGENTS_TOP,
                        BUST_X - 290, 30, F_CODE, a0)
    if a1 > 0:
        draw_code_block(cd, CODE_GITHUB_MID,
                        BUST_X - 320, 145, F_CODE_SMALL, a1)
    if a2 > 0:
        draw_code_block(cd, CODE_TURNLOG_BOT,
                        BUST_X - 280, 230, F_CODE_SMALL, a2)
    im.paste(code_layer, (0, 0), code_layer)

    # ─── Title block (left) — drawn last so it sits on top of everything ──
    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)

    # DAEDALUS — display serif, black ink
    td.text((TITLE_X, TITLE_Y), "Daedalus", font=F_TITLE, fill=(*INK, 255))

    # Gold underline accent — animated draw-in
    up = underline_progress(f)
    if up > 0:
        ux2 = TITLE_X + int(140 * up)
        td.line((TITLE_X, TITLE_Y + 130, ux2, TITLE_Y + 130),
                fill=(*GOLD, 255), width=3)

    # Subtitle — two lines, second in cyan
    td.text((TITLE_X, TITLE_Y + 145), "Agents that fly.",
            font=F_SUB, fill=(*INK, 255))
    td.text((TITLE_X, TITLE_Y + 185), "Workflows that don't melt.",
            font=F_SUB, fill=(*CYAN, 255))

    # Caption — workflow stages (the high-level value, not implementation)
    td.text((TITLE_X, TITLE_Y + 240),
            "Issue   →   Code   →   Review   →   Merge",
            font=F_TAG, fill=(*INK, 255))
    # GitHub-native beat — one short italic line under the workflow flow
    td.text((TITLE_X, TITLE_Y + 264),
            "Out of the box on GitHub.",
            font=font(FONT_DISPLAY_ITALIC, 17), fill=(*INK_SOFT, 255))

    im.paste(text_layer, (0, 0), text_layer)

    # Margin icons (fade in alongside the constellation, faintly)
    icon_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    icon_draw = ImageDraw.Draw(icon_layer)
    icon_alpha = int(180 * cp)
    if icon_alpha > 0:
        draw_margin_icons(icon_draw, icon_alpha)
        im.paste(icon_layer, (0, 0), icon_layer)

    return im


# ──────────────────────────── entry ───────────────────────────────────────

def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"rendering {FRAMES} frames @ {W}x{H} …")
    frames = []
    for i in range(FRAMES):
        frames.append(render_frame(i))
        if i % 10 == 0:
            print(f"  frame {i}/{FRAMES}")
    print("quantizing …")
    # Quantize all frames against the FIRST frame's palette so subsequent
    # frames reuse the same indices — that lets the GIF encoder's
    # interframe optimisation actually help. Using per-frame ADAPTIVE
    # palettes prevents that and bloats the file.
    base_palette = frames[0].convert(
        "P", palette=Image.Palette.ADAPTIVE,
        colors=48, dither=Image.Dither.NONE,
    )
    quantized = [base_palette]
    for f in frames[1:]:
        quantized.append(f.quantize(palette=base_palette, dither=Image.Dither.NONE))
    print("encoding GIF …")
    quantized[0].save(
        OUT_PATH,
        save_all=True,
        append_images=quantized[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
        disposal=1,  # leave previous frame intact → encoder can skip
                     # unchanged pixels in subsequent frames.
    )
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"wrote {OUT_PATH} ({size_kb:.1f} KiB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
