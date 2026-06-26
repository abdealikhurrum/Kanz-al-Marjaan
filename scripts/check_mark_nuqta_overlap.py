"""Collision check: for every ligature with mark-to-ligature anchors, place a
fatha at each top anchor and a kasra at each bottom anchor and test pixel
overlap with the glyph ink (rasm + nuqta).  An eraab must not collide with /
come between the rasm and its nuqta, so any overlap is a flag.

Usage: python3 scripts/check_mark_nuqta_overlap.py   (reports overlapping ligatures)
"""
import os, re
import numpy as np, freetype
from fontTools.ttLib import TTFont

TTF = os.environ.get("CHECK_TTF", "/tmp/_kam_roll.ttf")
TOL = 3   # px of overlap tolerated (anti-alias edges)
tt = TTFont(TTF); order = tt.getGlyphOrder(); cmap = tt.getBestCmap()
face = freetype.Face(TTF); P = 200; face.set_pixel_sizes(0, P); sc = P / face.units_per_EM
FATHA, KASRA = order.index(cmap[0x064E]), order.index(cmap[0x0650])
MDX = 239   # markClass x-anchor for both fatha(@t) and kasra(@b)
fea = open("sources/KanzAlMarjaan-Regular.ufo/features.fea").read()

ligs = {}
for m in re.finditer(r"pos ligature (\S+)\s*(.*?);", fea, re.S):
    a = re.findall(r"<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*<anchor (-?\d+) (-?\d+)> mark \@b", m.group(2))
    if a: ligs[m.group(1)] = [tuple(map(int, t)) for t in a]

def pix(gid, ox, oy):
    face.load_glyph(gid, freetype.FT_LOAD_RENDER); bm = face.glyph.bitmap; g = face.glyph
    if not (bm.width and bm.rows): return set()
    arr = np.frombuffer(bytes(bm.buffer), np.uint8).reshape(bm.rows, bm.width)
    ys, xs = np.where(arr > 60)
    return set(zip((ox + g.bitmap_left + xs).astype(int), (oy - g.bitmap_top + ys).astype(int)))

top_bad, bot_bad = [], []
for g, anchs in ligs.items():
    base = pix(order.index(g), 400, 400)
    if not base: continue
    for tx, ty, bx, by in anchs:
        if len(base & pix(FATHA, 400 + (tx - MDX) * sc, 400 - ty * sc)) > TOL: top_bad.append(g); break
    for tx, ty, bx, by in anchs:
        if len(base & pix(KASRA, 400 + (bx - MDX) * sc, 400 - by * sc)) > TOL: bot_bad.append(g); break

print("ligatures checked:", len(ligs))
print("top-mark (fatha) overlaps:", len(top_bad), top_bad[:8])
print("bottom-mark (kasra) overlaps:", len(bot_bad), bot_bad[:8])
