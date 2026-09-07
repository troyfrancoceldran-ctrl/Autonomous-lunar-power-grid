"""
@file    tests/palette_check.py
@brief   Measure the figure palettes instead of asserting they are fine.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
visualization.py used to call its palette "validated". Nothing validated it.
When it was finally measured, two colours sat below the WCAG contrast floor
and two pairs were closer under simulated colour blindness than the just-
noticeable threshold for categorical data. That is defect D-02, recorded in
visualization.py.

This module is the fix for the process, not just the palette: it makes the
claim FALSIFIABLE. test_visualization.py runs it, so a future edit that picks
a prettier colour breaks the suite instead of quietly breaking the figure.

Two questions, both answerable in arithmetic:

1. Can every mark be SEEN against its own background?
    WCAG 2.2 SC 1.4.11 asks >= 3.0:1 for a graphical object that carries
    meaning. A 2 pt chart line is exactly that.

2. Can every mark be TOLD APART from every other mark on the same axis,
    including by a viewer with colour vision deficiency?
    Simulate protanopia, deuteranopia and tritanopia, then measure CIEDE2000
    between all pairs that share an axis, under normal vision and each
    deficiency. The worst of those four is the pair's real separation.

Deliberately pure stdlib — no numpy, no matplotlib for the maths — so the
measurement carries no dependency of its own and can be run anywhere.

@note WHICH PAIRS. Not all pairs: the ones that actually share an axis in
    some figure, read off visualization.py. With three categorical slots that
    is every series pair plus the reserved status colour against each of
    them. An earlier version of this check constrained CRITICAL against only
    the two slots it meets in figure_two_signals, and a palette search
    promptly returned a CRITICAL identical to slot 2 — technically satisfying
    every constraint it had been given. Constraints omitted are constraints
    an optimiser will exploit.

@see Machado, G., Oliveira, M. & Fernandes, L. (2009), "A Physiologically-
    based Model for Simulation of Color Vision Deficiency", IEEE TVCG 15(6).
    The matrices below are that model at severity 1.0.
@see Okabe, M. & Ito, K. (2008), "Color Universal Design". Its hues were the
    starting point; its published lightnesses assume large fills on white,
    so they are re-tuned per surface here.


================================================================================
API
================================================================================

contrast_ratio(a, b) -> float
    WCAG relative-luminance contrast ratio between two hex colours.

ciede2000(lab1, lab2) -> float
    Perceptual distance in CIELAB. ~1.0 is a just-noticeable difference;
    categorical data wants considerably more.

simulate(hex, deficiency) -> (L, a, b)
    The colour as seen under 'normal', 'protanopia', 'deuteranopia' or
    'tritanopia', returned in CIELAB.

check_theme(theme) -> list[str]
    Every floor violation in a visualization.Theme, as readable strings.
    Empty list means the theme passes.

report(theme) -> bool
    Print the full measurement table; True if the theme passes.
"""

import math
from itertools import combinations

CONTRAST_FLOOR = 3.0      # WCAG 2.2 SC 1.4.11, non-text contrast
DELTA_FLOOR = 18.0        # CIEDE2000 between marks sharing an axis

VISIONS = ("normal", "protanopia", "deuteranopia", "tritanopia")

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied to LINEAR RGB.
CVD = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}

# sRGB primaries under D65.
_M = ((0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041))
_WHITE = (0.95047, 1.00000, 1.08883)


def _to_linear(c):
    """Undo the sRGB transfer function."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(value):
    """'#2a78d6' -> linear-light RGB."""
    v = value.lstrip("#")
    return tuple(_to_linear(int(v[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def contrast_ratio(a, b):
    """WCAG contrast ratio between two hex colours."""
    def lum(x):
        r, g, bl = linear_rgb(x)
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def lin_to_lab(lin):
    """Linear RGB -> CIELAB under D65."""
    xyz = [sum(_M[i][j] * lin[j] for j in range(3)) for i in range(3)]
    f = []
    for i in range(3):
        t = xyz[i] / _WHITE[i]
        f.append(t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116)
    return (116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2]))


def simulate(value, deficiency):
    """Hex colour as seen under a colour vision deficiency, in CIELAB."""
    lin = linear_rgb(value)
    if deficiency != "normal":
        m = CVD[deficiency]
        lin = tuple(max(0.0, min(1.0, sum(m[i][j] * lin[j] for j in range(3))))
                    for i in range(3))
    return lin_to_lab(lin)


def ciede2000(lab1, lab2):
    """Perceptual distance between two CIELAB colours."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7))) if Cbar > 0 else 0.5
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)

    Lbar, Cbarp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbarp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbarp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbarp = (h1p + h2p + 360) / 2
    else:
        hbarp = (h1p + h2p - 360) / 2

    T = (1 - 0.17 * math.cos(math.radians(hbarp - 30))
         + 0.24 * math.cos(math.radians(2 * hbarp))
         + 0.32 * math.cos(math.radians(3 * hbarp + 6))
         - 0.20 * math.cos(math.radians(4 * hbarp - 63)))
    dtheta = 30 * math.exp(-(((hbarp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbarp ** 7 / (Cbarp ** 7 + 25 ** 7)) if Cbarp > 0 else 0.0
    Sl = 1 + (0.015 * (Lbar - 50) ** 2) / math.sqrt(20 + (Lbar - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc

    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def separation(a, b):
    """Worst CIEDE2000 between two colours over all four vision types."""
    return min(ciede2000(simulate(a, v), simulate(b, v)) for v in VISIONS)


def _marks(theme):
    """Every colour that must be visible against the surface, labelled."""
    marks = [(f"series[{i}]", c) for i, c in enumerate(theme.series)]
    marks.append(("critical", theme.critical))
    marks.append(("bar", theme.bar))
    return marks


def _shared_axis_pairs(theme):
    """Pairs that appear together on one axis in some figure."""
    named = [(f"series[{i}]", c) for i, c in enumerate(theme.series)]
    pairs = list(combinations(named, 2))
    pairs += [(("critical", theme.critical), s) for s in named]
    return pairs


def check_theme(theme):
    """Every floor violation in a theme, as readable strings."""
    problems = []
    for label, colour in _marks(theme):
        ratio = contrast_ratio(colour, theme.surface)
        if ratio < CONTRAST_FLOOR:
            problems.append(
                f"{theme.name}: {label} {colour} contrast {ratio:.2f}:1 "
                f"against surface {theme.surface} (floor {CONTRAST_FLOOR})")
    for (la, ca), (lb, cb) in _shared_axis_pairs(theme):
        d = separation(ca, cb)
        if d < DELTA_FLOOR:
            worst = min(VISIONS,
                        key=lambda v: ciede2000(simulate(ca, v), simulate(cb, v)))
            problems.append(
                f"{theme.name}: {la} {ca} vs {lb} {cb} CIEDE2000 {d:.1f} "
                f"under {worst} (floor {DELTA_FLOOR})")
    return problems


def report(theme):
    """Print the full measurement table; True if the theme passes."""
    print(f"\n{'=' * 74}\n{theme.name.upper()}   surface {theme.surface}\n{'=' * 74}")
    print(f"\ncontrast against surface   (floor {CONTRAST_FLOOR}:1)")
    for label, colour in _marks(theme):
        r = contrast_ratio(colour, theme.surface)
        print(f"  {'ok ' if r >= CONTRAST_FLOOR else 'LOW'}  "
            f"{label:<12} {colour}   {r:5.2f}:1")
    print(f"\nCIEDE2000 between marks sharing an axis, worst of 4 vision types"
        f"   (floor {DELTA_FLOOR})")
    for (la, ca), (lb, cb) in _shared_axis_pairs(theme):
        d = separation(ca, cb)
        worst = min(VISIONS,
                    key=lambda v: ciede2000(simulate(ca, v), simulate(cb, v)))
        print(f"  {'ok ' if d >= DELTA_FLOOR else 'LOW'}  "
            f"{la:<12} vs {lb:<12} {d:6.1f}  ({worst})")
    problems = check_theme(theme)
    print(f"\n  {theme.name}: {'PASS' if not problems else str(len(problems)) + ' VIOLATION(S)'}")
    for p in problems:
        print(f"    - {p}")
    return not problems


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from visualization import LIGHT, DARK

    ok = all([report(LIGHT), report(DARK)])
    print(f"\n{'all themes pass' if ok else 'FAILURES ABOVE'}")
    raise SystemExit(0 if ok else 1)
