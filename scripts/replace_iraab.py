"""Replace Kanz's auto-traced iraab with Fatemi Maqala's clean diacritics
(sukun -> head-of-khah jazm). Same UPM + letter size, so 1:1; reposition to
Kanz's mark convention (attachment edge at y=0, centred on its anchor) and
recompute markClass anchors + regenerate .narrow variants.
"""
import re
import defcon
from defcon import Component
from fontTools.ttLib import TTFont
from fontTools.misc.transform import Transform
from defcon.pens.transformPointPen import TransformPointPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.transformPen import TransformPen

UFO = "sources/KanzAlMarjaan-Regular.ufo"
FEA = UFO + "/features.fea"
FAT = "/Users/abdealikhurrum/fatemimaqala-pub/fonts/FatemiMaqala-Regular.ttf"
SX, SY = 0.65, 0.88

# Kanz mark (by glyph name) <- Fatemi source codepoint; sukun uses head-of-khah
ABOVE = {"uni064E": 0x064E, "uni064F": 0x064F, "uni0651": 0x0651,
         "uni0652": 0x06E1, "uni064B": 0x064B, "uni064C": 0x064C,
         "uni0653": 0x0653, "uni0670": 0x0670}
BELOW = {"uni0650": 0x0650, "uni064D": 0x064D}

fat = TTFont(FAT); fcm = fat.getBestCmap(); fgs = fat.getGlyphSet()
f = defcon.Font(UFO)

def fatemi_contours(cp, target_glyph):
    """Draw Fatemi glyph cp into a temp, return its defcon glyph (cubic)."""
    drp = DecomposingRecordingPen(fgs)
    fgs[fcm[cp]].draw(drp)
    tmp = f.newGlyph("__tmp__")
    drp.replay(Qu2CuPen(tmp.getPen(), max_err=1.0, all_cubic=True))
    return tmp

new_anchor = {}   # glyphname -> (ax, ay) recomputed
def place(name, cp, above):
    tmp = fatemi_contours(cp, name)
    b = tmp.bounds  # xMin,yMin,xMax,yMax
    # shift so attachment edge at y=0 (above: bottom->0; below: top->0)
    dy = -b[1] if above else -b[3]
    cx = round((b[0] + b[2]) / 2)
    g = f[name]
    g.clearContours(); g.clearComponents()
    tmp.draw(TransformPen(g.getPen(), (1, 0, 0, 1, 0, dy)))
    del f["__tmp__"]
    g.width = 0
    new_anchor[name] = (cx, 0)
    # narrow variant
    nn = name + ".narrow"
    if nn in f:
        del f[nn]
    ng = f.newGlyph(nn); ng.width = 0
    t = Transform().translate(cx, 0).scale(SX, SY).translate(-cx, 0)
    g.drawPoints(TransformPointPen(ng.getPointPen(), t))
    new_anchor[nn] = (cx, 0)

for nm, cp in ABOVE.items():
    place(nm, cp, True)
for nm, cp in BELOW.items():
    place(nm, cp, False)

f.save()
print("replaced %d marks (+ narrows) from Fatemi" % (len(ABOVE) + len(BELOW)))

# rewrite markClass anchors for the replaced marks + their narrows
fea = open(FEA).read()
n = 0
for nm, (ax, ay) in new_anchor.items():
    pat = re.compile(r"(markClass %s <anchor )-?\d+ -?\d+(> @)" % re.escape(nm))
    fea, k = pat.subn(r"\g<1>%d %d\g<2>" % (ax, ay), fea)
    n += k
open(FEA, "w").write(fea)
print("updated %d markClass anchors" % n)
