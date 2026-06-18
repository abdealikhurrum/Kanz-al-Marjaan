#!/usr/bin/env python3
"""Phase 2 (overlap approach): add a small left overlap to every EXIT connection
so it overlaps the following glyph's entry, eliminating hairline seam gaps.

Letterform-preserving: it only extends the two exit-seam on-curve points (the
vertical connecting edge at x=0) leftwards by OVERLAP units. No angle/height
reshaping. Heights/baselines are left exactly as designed.

  python scripts/exit_overlap.py             # pilot render (ببببب)
  python scripts/exit_overlap.py --apply
"""
import sys, os, argparse
import numpy as np
from defcon import Font

SRC = "sources/KanzAlMarjaan-Regular.ufo"
OVERLAP = 20      # units the exit connection extends past the cell edge


def find_seam(contour, edge, xtol=10, ywin=(-40, 470)):
    """Vertical connection seam at x≈edge: the two consecutive on-curve points
    spanning the connecting stroke. Returns (i_bot, i_top) or None."""
    n = len(contour)
    best = None
    for i in range(n):
        a, b = contour[i], contour[(i + 1) % n]
        if (a.segmentType and b.segmentType
                and abs(a.x - edge) <= xtol and abs(b.x - edge) <= xtol
                and ywin[0] <= a.y <= ywin[1] and ywin[0] <= b.y <= ywin[1]):
            i_bot, i_top = (i, (i + 1) % n) if a.y < b.y else ((i + 1) % n, i)
            key = min(a.y, b.y)
            if best is None or key < best[0]:
                best = (key, i_bot, i_top)
    return (best[1], best[2]) if best else None


def overlap_exit(contour):
    """Extend the exit (x≈0) connection leftwards by OVERLAP. Returns True if a
    valid baseline exit connection was found and extended."""
    seam = find_seam(contour, 0)
    if not seam:
        return False
    i_bot, i_top = seam
    p_bot, p_top = contour[i_bot], contour[i_top]
    if not (-60 <= p_bot.y <= 60 and 110 <= p_top.y - p_bot.y <= 230):
        return False
    p_bot.x -= OVERLAP
    p_top.x -= OVERLAP
    return True


def conform_glyph(glyph):
    hit = False
    for c in glyph:
        if overlap_exit(c):
            hit = True
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out", default="out/join")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not args.apply:
        # pilot: conform in memory, render ببببب via an abutted simulation is
        # not enough (needs the build), so just report which glyphs change.
        font = Font(SRC)
        n = sum(1 for g in font if len(g) and conform_glyph(g))
        print(f"[dry] {n} glyphs would get an exit overlap of {OVERLAP}u")
        print("run with --apply, then rebuild and render to inspect")
        return

    font = Font(SRC)
    n = 0
    for g in font:
        if len(g) == 0:
            continue
        if conform_glyph(g):
            g.dirty = True
            for c in g:
                c.dirty = True
            n += 1
    font.save(SRC)
    print(f"APPLIED: exit overlap ({OVERLAP}u) on {n} glyphs -> {SRC}")


if __name__ == "__main__":
    main()
