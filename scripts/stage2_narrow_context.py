"""Stage 2 (contextual narrowing) + Stage 3 (shadda-cluster vowel on the line).

- creates .narrow variants of the above/below marks + shadda combos
- registers their markClass entries (same anchors)
- adds a calt feature: narrow a mark when an adjacent letter is also marked
- lowers the above shadda-combo anchors so the vowel aligns to the mark line
"""
import re
import defcon
from defcon import Component
from fontTools.misc.transform import Transform
from defcon.pens.transformPointPen import TransformPointPen

UFO = "sources/KanzAlMarjaan-Regular.ufo"
FEA = UFO + "/features.fea"
SX, SY = 0.65, 0.88          # narrow scale (around the markClass anchor)

ABOVE = ["uni064E", "uni064F", "uni064B", "uni064C", "uni0651", "uni0652",
         "uni0653", "uni0654", "uni0670",
         "uni0651064E", "uni0651064F", "uni0651064B", "uni0651064C"]
BELOW = ["uni0650", "uni064D", "uni0651064D", "uni06510650"]
# shadda combos whose vowel should drop toward the line (above-stacked)
SHADDA_ABOVE = {"uni0651064E": 300, "uni0651064F": 470,
                "uni0651064B": 440, "uni0651064C": 310}  # anchor Y raise => combo drops

fea = open(FEA).read()

# current markClass anchors: glyph -> (x, y, class)
mc = {}
for m in re.finditer(r"markClass (\S+) <anchor (-?\d+) (-?\d+)> @(\S+);", fea):
    mc[m.group(1)] = (int(m.group(2)), int(m.group(3)), m.group(4))

f = defcon.Font(UFO)

def make_narrow(name):
    ax, ay, cls = mc[name]
    nn = name + ".narrow"
    if nn in f:
        del f[nn]
    g = f.newGlyph(nn); g.width = f[name].width
    t = Transform().translate(ax, ay).scale(SX, SY).translate(-ax, -ay)
    f[name].drawPoints(TransformPointPen(g.getPointPen(), t))
    return nn, ax, ay, cls

# effective anchor Y per mark (shadda-above combos lowered for Stage 3)
def eff_y(nm, ay):
    return ay + SHADDA_ABOVE.get(nm, 0)

new_markclass = []
for nm in ABOVE + BELOW:
    if nm not in mc:
        print("WARN no markClass for", nm); continue
    nn, ax, ay, cls = make_narrow(nm)
    new_markclass.append("  markClass %s <anchor %d %d> @%s;" % (nn, ax, eff_y(nm, ay), cls))

f.save()
print("created %d narrow variants" % len(new_markclass))

# ---- Stage 3: lower the existing above-shadda-combo markClass anchors ----
for combo, dy in SHADDA_ABOVE.items():
    ax, ay, cls = mc[combo]
    old = "markClass %s <anchor %d %d> @%s;" % (combo, ax, ay, cls)
    new = "markClass %s <anchor %d %d> @%s;" % (combo, ax, ay + dy, cls)
    assert old in fea, "could not find %s" % old
    fea = fea.replace(old, new)

# ---- insert narrow markClass lines just before the first pos base rule ----
fea = fea.replace("  pos base uni0621",
                  "\n".join(new_markclass) + "\n  pos base uni0621", 1)

# ---- @BASES from the 229 pos base rules; @ASC/@DESC by ink height ----
bases = sorted(set(re.findall(r"pos base (\S+)\s*<anchor", fea)))
import numpy as np, freetype
from fontTools.ttLib import TTFont
tt = TTFont("fonts/ttf/KanzAlMarjaan-Regular.ttf"); upm = tt["head"].unitsPerEm
n2g = {n: i for i, n in enumerate(tt.getGlyphOrder())}
face = freetype.Face("fonts/ttf/KanzAlMarjaan-Regular.ttf"); face.set_pixel_sizes(0, 512); sc = 512 / upm
def ytop_bot(gn):
    if gn not in n2g: return None
    face.load_glyph(n2g[gn], freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
    if not (bm.width and bm.rows): return (0, 0)
    a = np.frombuffer(bytes(bm.buffer), "uint8").reshape(bm.rows, bm.width) > 40
    rows = np.where(a.any(axis=1))[0]
    return ((g.bitmap_top - rows.min()) / sc, (g.bitmap_top - rows.max()) / sc)
ASC = [b for b in bases if (ytop_bot(b) or (0, 0))[0] > 1100]
DESC = [b for b in bases if (ytop_bot(b) or (0, 0))[1] < -350]

def cls_list(names): return "[" + " ".join(names) + "]"
AM = list(ABOVE); AMn = [n + ".narrow" for n in ABOVE]
BM = list(BELOW); BMn = [n + ".narrow" for n in BELOW]

block = f"""
# ---- Stage 2: contextual mark narrowing ----
@BASES_mk = {cls_list(bases)};
@ASC_mk  = {cls_list(ASC)};
@DESC_mk = {cls_list(DESC)};
@AM_mk  = {cls_list(AM)};
@AMn_mk = {cls_list(AMn)};
@AMany_mk = [@AM_mk @AMn_mk];
@BM_mk  = {cls_list(BM)};
@BMn_mk = {cls_list(BMn)};
@BMany_mk = [@BM_mk @BMn_mk];
lookup narrowAbove {{ sub @AM_mk by @AMn_mk; }} narrowAbove;
lookup narrowBelow {{ sub @BM_mk by @BMn_mk; }} narrowBelow;
feature calt {{
  script arab;
  # above mark next to another above mark (either side) -> narrow both
  sub @AMany_mk' lookup narrowAbove @BASES_mk @AMany_mk;
  sub @AMany_mk @BASES_mk @AMany_mk' lookup narrowAbove;
  # above mark next to a tall ascender -> narrow
  sub @AMany_mk' lookup narrowAbove @ASC_mk;
  sub @ASC_mk @AMany_mk' lookup narrowAbove;
  # below mark next to another below mark or a deep descender
  sub @BMany_mk' lookup narrowBelow @BASES_mk @BMany_mk;
  sub @BMany_mk @BASES_mk @BMany_mk' lookup narrowBelow;
  sub @BMany_mk' lookup narrowBelow @DESC_mk;
  sub @DESC_mk @BMany_mk' lookup narrowBelow;
}} calt;
"""
fea = fea.rstrip() + "\n" + block
print("ASC:", len(ASC), "DESC:", len(DESC))

open(FEA, "w").write(fea)
print("wrote features.fea: +%d bases, calt narrowing, shadda anchors lowered" % len(bases))
