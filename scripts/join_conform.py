#!/usr/bin/env python3
"""Phase 2: conform cursive connections to a flat stub so joins are tangent-
continuous. At each connection the two on-curve seam points (vertical edge at
the cell boundary) get canonical heights (bottom=0, top=CANON), and the
into-glyph off-curve handle next to each is set to the same y -> the stroke
leaves the seam HORIZONTALLY. Any exit then meets any entry with no kink.

Default = pilot/dry-run: conform a few glyphs in memory and render abutted
before/after joins. --apply writes the source UFO (all joining outline glyphs).

  python scripts/join_conform.py                 # pilot render
  python scripts/join_conform.py --apply
"""
import sys, os, argparse
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curve_cleanup_run import _passthrough, _seg_path_points
# (geometric detection; no join_flags needed)

SRC = "sources/KanzAlMarjaan-Regular.ufo"
CANON = 171
STUB = 55       # length of the flat horizontal stub at the seam (font units)


def find_seam(contour, edge, xtol=10, ywin=(-40, 470)):
    """Return (i_bot, i_top) point indices of the vertical seam pair: two
    consecutive on-curve points at x≈edge spanning the connecting stroke."""
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


def conform_side(contour, edge, canon=CANON):
    """Flatten the connection at vertical line x=edge on this contour, if a
    valid baseline connection seam is present there. Returns True if applied."""
    seam = find_seam(contour, edge)
    if not seam:
        return False
    i_bot, i_top = seam
    # validity: a real connection sits on the baseline with ~canonical thickness
    if not (-45 <= contour[i_bot].y <= 45
            and 120 <= contour[i_top].y - contour[i_bot].y <= 230):
        return False
    n = len(contour)
    p_bot, p_top = contour[i_bot], contour[i_top]
    seam_x = p_bot.x
    dir = 1 if seam_x <= 1 else -1        # exit (x≈0): into-glyph +x; entry: -x
    # into-glyph neighbour = the one away from the seam partner
    nb_top = contour[(i_top + 1) % n] if (i_top + 1) % n != i_bot else contour[(i_top - 1) % n]
    nb_bot = contour[(i_bot + 1) % n] if (i_bot + 1) % n != i_top else contour[(i_bot - 1) % n]
    # PRESERVE the bottom (keeps the glyph on its baseline); harmonize the
    # thickness by moving only the TOP to bottom+canon.
    new_bot_y = p_bot.y
    new_top_y = p_bot.y + canon
    p_top.y = new_top_y
    # Flatten both edges to a horizontal stub at the seam. Off-curve handles get
    # pulled out horizontally by STUB; line on-curve neighbours just take the
    # seam y (so that straight segment becomes horizontal).
    def flatten(nb, y):
        nb.y = y
        if nb.segmentType is None:
            nb.x = seam_x + dir * STUB
    flatten(nb_top, new_top_y)
    flatten(nb_bot, new_bot_y)
    return True


def conform_glyph(glyph):
    """Detect & flatten connections geometrically: exit at x=0, entry at
    x=advance. No reliance on glyph naming."""
    done = []
    for c in glyph:
        if conform_side(c, 0):
            done.append("exit")
        if conform_side(c, glyph.width):
            done.append("entry")
    return done


# ---------- rendering helpers (abutted-join simulation) ----------
def flat_glyph(glyph):
    return [[ (p[0], p[1]) for p in _seg_path_points(_passthrough(c), 16)] for c in glyph
            if sum(1 for _ in c) >= 3]


def render_pair(font_before, font_after, name, path):
    """Abut two copies of `name` (exit-of-right meets entry-of-left) and draw
    before vs after, zoomed at the seam."""
    def abutted(font):
        g = font[name]; w = g.width
        polys = flat_glyph(g)
        # right copy at origin; left copy shifted so its entry (x=w) meets x=0
        out = []
        for poly in polys:
            out.append([(x, y) for x, y in poly])           # right copy
            out.append([(x - w, y) for x, y in poly])        # left copy
        return out, w

    pb, w = abutted(font_before)
    pa, _ = abutted(font_after)
    size = 520; H = 560
    allp = [p for poly in pb + pa for p in poly]
    xs = [p[0] for p in allp]; ys = [p[1] for p in allp]
    mnx, mny = min(xs), min(ys); rw = max(max(xs) - mnx, 1); rh = max(max(ys) - mny, 1)
    sc = (size - 60) / max(rw, rh)
    img = Image.new("RGB", (size, H * 2), "white"); d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except Exception:
        f = ImageFont.load_default()

    def draw(polys, oy, title, col):
        for poly in polys:
            d.line([(30 + (x - mnx) * sc, oy + H - 60 - (y - mny) * sc) for x, y in poly]
                   + [(30 + (poly[0][0] - mnx) * sc, oy + H - 60 - (poly[0][1] - mny) * sc)],
                   fill=col, width=2)
        # seam line at x=0
        sx = 30 + (0 - mnx) * sc
        d.line([(sx, oy + 20), (sx, oy + H - 40)], fill=(220, 180, 180), width=1)
        d.text((30, oy + 6), title, fill=(20, 20, 20), font=f)

    draw(pb, 0, f"BEFORE  {name}+{name}  (kink at seam)", (180, 40, 40))
    draw(pa, H, f"AFTER  flat-stub conform", (30, 120, 30))
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pilot", default="uniFEB4,uniFEE4,uniFBE9,uniFEE3,uni06A1.medi")
    ap.add_argument("--out", default="out/join")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not args.apply:
        before = Font(SRC)
        after = Font(SRC)
        for nm in args.pilot.split(","):
            if nm not in after:
                print("skip", nm); continue
            done = conform_glyph(after[nm])
            render_pair(before, after, nm, os.path.join(args.out, f"conform_{nm}.png"))
            print(f"{nm}: conformed {done} -> {args.out}/conform_{nm}.png")
        return

    font = Font(SRC)
    n_glyph = n_conn = 0
    for g in font:
        if len(g) == 0:
            continue
        done = conform_glyph(g)
        if done:
            g.dirty = True          # ensure defcon writes the mutated points
            for c in g:
                c.dirty = True
            n_glyph += 1; n_conn += len(done)
    font.save(SRC)
    print(f"APPLIED: conformed {n_conn} connections on {n_glyph} glyphs -> {SRC}")


if __name__ == "__main__":
    main()
