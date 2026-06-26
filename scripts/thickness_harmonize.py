#!/usr/bin/env python3
"""Phase 2: harmonize connection THICKNESS so every join has the same top-edge
height. Bottoms are already on the baseline (~0); thin connections (e.g. medial
heh at 155u) make their top edge sit low, reading as a baseline step at joins.

Per connection: keep the bottom, raise/lower the top on-curve point to
bottom+CANON, and shift its adjacent into-glyph handle by the same delta so the
edge stays smooth (no angle reshaping, no x change). Baseline untouched.

  python scripts/thickness_harmonize.py            # dry count
  python scripts/thickness_harmonize.py --apply
"""
import sys, os, argparse
from defcon import Font

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from join_conform import find_seam

SRC = "sources/KanzAlMarjaan-Regular.ufo"
CANON = 170      # target connection thickness (units)


def harmonize_side(contour, edge):
    seam = find_seam(contour, edge)
    if not seam:
        return False
    i_bot, i_top = seam
    n = len(contour)
    p_bot, p_top = contour[i_bot], contour[i_top]
    thick = p_top.y - p_bot.y
    if not (-60 <= p_bot.y <= 60 and 110 <= thick <= 230):
        return False
    delta = (p_bot.y + CANON) - p_top.y
    if abs(delta) < 1:
        return False
    nb_top = contour[(i_top + 1) % n] if (i_top + 1) % n != i_bot else contour[(i_top - 1) % n]
    p_top.y += delta
    if nb_top.segmentType is None:        # move handle with the on-curve point
        nb_top.y += delta
    return True


def harmonize_glyph(glyph):
    hit = False
    for c in glyph:
        if harmonize_side(c, 0):
            hit = True
        if harmonize_side(c, glyph.width):
            hit = True
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    font = Font(SRC)
    n = 0
    for g in font:
        if len(g) == 0:
            continue
        if harmonize_glyph(g):
            if args.apply:
                g.dirty = True
                for c in g:
                    c.dirty = True
            n += 1
    if args.apply:
        font.save(SRC)
        print(f"APPLIED: thickness harmonized to {CANON}u on {n} glyphs -> {SRC}")
    else:
        print(f"[dry] {n} glyphs would have connections harmonized to {CANON}u")


if __name__ == "__main__":
    main()
