"""Animation easing + per-element progress functions.

Every animated element has a `<element>_progress(frame) -> float` function
in this module that returns 0.0 (not started) → 1.0 (complete).

Tweak timings here to retune the animation without touching renderers.
"""

from __future__ import annotations

import math

from . import config

F = config.FRAMES


def ease(t: float) -> float:
    """Smooth in-out easing on [0, 1].

    Uses a cosine ease-in-out curve: slow start, fast middle, slow end.
    This makes motion feel organic rather than robotic.
    """
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def _ramp(frame: int, start: float, end: float) -> float:
    """Eased ramp from frame=start*F to frame=end*F.

    Returns 0.0 before the start frame, 1.0 after the end frame,
    and an eased interpolation in between.

    Parameters
    ----------
    frame : int
        Current frame number (0 … FRAMES-1).
    start : float
        Start point as a fraction of the total loop (0.0 … 1.0).
    end   : float
        End point as a fraction of the total loop (0.0 … 1.0).
    """
    if frame <= start * F:
        return 0.0
    if frame >= end * F:
        return 1.0
    return ease((frame - start * F) / ((end - start) * F))


# ── element progress functions ──────────────────────────────────────────


def constellation_progress(f: int) -> float:
    """Constellation network draw-in progress.

    The starfield behind the hero image fades in from frame 0.00 to 0.30
    (i.e. the first 30 % of the loop). Increase the end value to slow the
    draw-in; decrease it to make the stars appear faster.
    """
    return _ramp(f, 0.00, 0.30)


def code_alpha(f: int, slot: int) -> int:
    """Three code blocks fade in staggered.

    slot 0 : AGENTS_BLOCK   (top-left code snippet)
    slot 1 : GITHUB_BLOCK   (middle code snippet)
    slot 2 : TURNLOG_BLOCK  (bottom code snippet)

    Each block starts at a different point and fades in over 0.18 of the
    loop. Adjust `starts` to change the stagger spacing.
    """
    starts = [0.18, 0.30, 0.42]   # start fraction for each slot
    ramp = _ramp(f, starts[slot], starts[slot] + 0.18)
    return int(255 * ramp)


def hold_to_loop(f: int) -> float:
    """Constellation / icons dim slightly at end-of-loop for smooth wrap.

    At 90 % through the loop we begin dimming to 45 % brightness so the
    transition back to frame 0 is seamless. Adjust 0.90 to start the
    fade earlier or later; adjust 0.55 to change how dark it gets.
    """
    start = 0.90 * F
    if f < start:
        return 1.0
    return 1.0 - ease((f - start) / (F - start)) * 0.55


# ── workflow-flow pipeline animation ────────────────────────────────────
#
# 7 tokens in the flow line:  Issue → Code → Review → Merge
# Each token has two phases:
#   1. fade-in       — alpha 0 → 255
#   2. ignite-settle — colour cyan → ink  (a brief "the stage just lit up"
#                      highlight before it cools to body-text colour)

# Flow timing — first token ignites at frame 0 so the pipeline is the
# very first thing the viewer sees. Tokens are spread across most of
# the loop so each stage stays on screen long enough to read.
FLOW_TOKEN_COUNT = 7
FLOW_FIRST_START = 0.00  # first token starts at the beginning of the loop
FLOW_TOKEN_STRIDE = 0.095  # gap between consecutive token starts
FLOW_FADE_IN = 0.06  # fade-in duration per token
FLOW_SETTLE = 0.18  # cyan → ink settle duration per token


def flow_token_state(f: int, token_idx: int) -> tuple[int, float]:
    """Return ``(alpha, color_blend)`` for token ``token_idx`` at frame ``f``.

    * alpha          0..255  (0 = invisible, 255 = fully opaque)
    * color_blend    0.0 = full cyan (just ignited)
                     1.0 = full ink  (settled)

    The ignition timing is driven by FLOW_TOKEN_COUNT, FLOW_FIRST_START,
    FLOW_TOKEN_STRIDE, FLOW_FADE_IN and FLOW_SETTLE above.
    """
    t = f / F
    start = FLOW_FIRST_START + token_idx * FLOW_TOKEN_STRIDE

    fade_p = max(0.0, min(1.0, (t - start) / FLOW_FADE_IN))
    if fade_p == 0.0:
        return 0, 0.0
    alpha = int(255 * ease(fade_p))

    settle_p = max(0.0, min(1.0, (t - start - FLOW_FADE_IN) / FLOW_SETTLE))
    return alpha, ease(settle_p)


def flow_pulse_progress(f: int) -> float | None:
    """Position (0..1) of the travelling glow pulse, or None if not active.

    Fires once after all tokens have ignited, sweeping left → right.
    """
    pulse_start = (
        FLOW_FIRST_START + (FLOW_TOKEN_COUNT - 1) * FLOW_TOKEN_STRIDE + FLOW_FADE_IN
    )
    pulse_end = 1.0
    t = f / F
    if t < pulse_start or t > pulse_end:
        return None
    return ease((t - pulse_start) / (pulse_end - pulse_start))
