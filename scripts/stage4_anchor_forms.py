"""Stage 4: add mark anchors to every Arabic base form that lacks one
(positional .tall/.short variants, ligatures, presentation forms), so marks
attach instead of piling at the glyph origin. Anchors from the ink profile +
the Stage-1 line model.
"""
import re, numpy as np, freetype
from fontTools.ttLib import TTFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
C_TOP, C_BOT, MIN = 600, -250, 80

fea = open(FEA).read()
have = set(re.findall(r"pos base (\S+)\s*<anchor", fea))

tt = TTFont(TTF); upm = tt["head"].unitsPerEm
order = tt.getGlyphOrder(); n2g = {n: i for i, n in enumerate(order)}
gdef = tt["GDEF"].table.GlyphClassDef.classDefs
marks = {g for g, c in gdef.items() if c == 3}
markclass_glyphs = set(re.findall(r"markClass (\S+) <anchor", fea))
# candidates: any Arabic inked form that isn't a mark and has no anchor yet
base_class = [g for g in order if g not in marks and g not in markclass_glyphs]

def is_arabic_form(n):
    return (re.match(r"uni0[67]", n) or re.match(r"uniF[BCDE]", n)
            or n.startswith("glyph")
            or re.search(r"\.(init|medi|fina|isol|liga|tall|short|alt)", n))

face = freetype.Face(TTF); PPEM = 1024; face.set_pixel_sizes(0, PPEM); sc = PPEM / upm

def anchors(gn):
    face.load_glyph(n2g[gn], freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
    if not (bm.width and bm.rows):
        return None
    a = np.frombuffer(bytes(bm.buffer), "uint8").reshape(bm.rows, bm.width) > 40
    xs = np.where(a.any(axis=0))[0]
    x0u = (g.bitmap_left + xs.min()) / sc; x1u = (g.bitmap_left + xs.max()) / sc
    # central 60% band for choosing where the mark sits
    cx = (x0u + x1u) / 2; half = (x1u - x0u) * 0.5
    bx0, bx1 = cx - half * 0.6, cx + half * 0.6
    c0 = max(0, int(round(bx0 * sc - g.bitmap_left)))
    c1 = min(bm.width, int(round(bx1 * sc - g.bitmap_left)))
    sub = a[:, c0:c1] if c1 > c0 else a
    rows = np.where(sub.any(axis=1))[0]
    top = (g.bitmap_top - rows.min()) / sc
    bot = (g.bitmap_top - rows.max()) / sc
    TX = round(cx); BX = round(cx)
    TY = max(round(0.30 * top + C_TOP), round(top + MIN))
    BY = min(round(0.30 * bot + C_BOT), round(bot - MIN))
    return TX, TY, BX, BY

rules = []
for gn in base_class:
    if gn in have or not is_arabic_form(gn) or gn not in n2g:
        continue
    a = anchors(gn)
    if a is None:
        continue
    TX, TY, BX, BY = a
    rules.append("  pos base %s\n      <anchor %d %d> mark @t.uni064B\n"
                 "      <anchor %d %d> mark @b.uni064D_1;" % (gn, TX, TY, BX, BY))

# insert before the mark lookup close
fea = fea.replace("} mark_arab_1;", "\n".join(rules) + "\n} mark_arab_1;", 1)

# refresh @BASES_mk to include the new bases (so narrowing context still works)
allbases = sorted(set(re.findall(r"pos base (\S+)\s*<anchor", fea)))
fea = re.sub(r"@BASES_mk = \[[^\]]*\];",
             "@BASES_mk = [" + " ".join(allbases) + "];", fea)

open(FEA, "w").write(fea)
print("added anchors to %d previously-anchorless forms; @BASES now %d" % (len(rules), len(allbases)))
