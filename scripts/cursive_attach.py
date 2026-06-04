"""Add cursive attachment (curs) to close vertical notches at letter joins.

For every glyph whose baseline-band ink reaches its left and/or right edge (a
connecting form), derive an exit anchor (left/next connection) and/or entry
anchor (right/previous connection) at the connecting stroke's height, then emit
a `curs` feature so HarfBuzz aligns exit[i] to entry[i+1].
"""
import re, numpy as np, freetype
from fontTools.ttLib import TTFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"

tt = TTFont(TTF); upm = tt["head"].unitsPerEm
order = tt.getGlyphOrder(); hmtx = tt["hmtx"]
marks = {g for g, c in tt["GDEF"].table.GlyphClassDef.classDefs.items() if c == 3}
n2g = {n: i for i, n in enumerate(order)}
face = freetype.Face(TTF); PPEM = 1024; face.set_pixel_sizes(0, PPEM); sc = PPEM / upm

EDGE = 30          # column window at each edge (font units)
BAND = (-120, 260) # baseline band where connections live (font units)
THRESH = 45        # ink must reach within this of the edge to count as connecting


def conn(gn):
    """Return (exit_anchor or None, entry_anchor or None) for a connecting glyph."""
    gid = n2g[gn]
    face.load_glyph(gid, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
    if not (bm.width and bm.rows):
        return None, None
    a = np.frombuffer(bytes(bm.buffer), "uint8").reshape(bm.rows, bm.width) > 40
    y0 = max(0, int(g.bitmap_top - BAND[1] * sc)); y1 = max(0, int(g.bitmap_top - BAND[0] * sc))
    adv = hmtx[gn][0]

    def col_y(px):  # vertical centre (font units) of ink in column px within band
        if px < 0 or px >= bm.width:
            return None
        rows = np.where(a[y0:y1, px])[0]
        if not len(rows):
            return None
        return (g.bitmap_top - (y0 + (rows.min() + rows.max()) / 2)) / sc

    # left edge (exit): is there ink within THRESH of x=0 at the baseline band?
    exit_a = entry_a = None
    leftpx = int(round((0 + EDGE) * sc - g.bitmap_left))
    # find leftmost band column with ink
    bandcols = np.where(a[y0:y1, :].any(axis=0))[0]
    if len(bandcols):
        lx = (g.bitmap_left + bandcols.min()) / sc
        rx = (g.bitmap_left + bandcols.max()) / sc
        if lx <= THRESH:           # connects on the left -> exit
            y = col_y(bandcols.min())
            if y is not None:
                exit_a = (round(lx), round(y))
        if rx >= adv - THRESH:     # connects on the right -> entry
            y = col_y(bandcols.max())
            if y is not None:
                entry_a = (round(rx), round(y))
    return exit_a, entry_a


rules = []
for gn in order:
    if gn in marks:
        continue
    exit_a, entry_a = conn(gn)
    if not exit_a and not entry_a:
        continue
    en = "<anchor %d %d>" % entry_a if entry_a else "<anchor NULL>"
    ex = "<anchor %d %d>" % exit_a if exit_a else "<anchor NULL>"
    rules.append("  pos cursive %s %s %s;" % (gn, en, ex))

block = ("\nfeature curs {\n  script arab;\n  lookupflag RightToLeft IgnoreMarks;\n"
         + "\n".join(rules) + "\n} curs;\n")
fea = open(FEA).read().rstrip() + "\n" + block
open(FEA, "w").write(fea)
print("added curs feature with %d connecting glyphs" % len(rules))
