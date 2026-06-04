"""Rebuild the shadda+vowel combos as composites of the new clean shadda + vowel.
Above combos: vowel on the standalone line, shadda tucked just below it.
Below combos (shadda+kasra/kasratan): shadda on top, vowel just below it (compact).
"""
import re
import defcon
from defcon import Component

UFO = "sources/KanzAlMarjaan-Regular.ufo"
FEA = UFO + "/features.fea"
SX, SY = 0.65, 0.88

f = defcon.Font(UFO)

def cx_of(name):
    b = f[name].bounds
    return (b[0] + b[2]) / 2, b[1], b[3]   # center_x, yMin, yMax

# above combos: vowel anchored on the line (bottom 0), shadda just below
ABOVE = {"uni0651064E": "uni064E", "uni0651064F": "uni064F",
         "uni0651064B": "uni064B", "uni0651064C": "uni064C"}
# below combos: shadda on top (bottom 0), kasra/kasratan tucked just below
BELOW = {"uni06510650": "uni0650", "uni0651064D": "uni064D"}

scx, symin, symax = cx_of("uni0651")
sh_h = symax - symin
GAP = 25
new_anchor = {}

def build_above(combo, vowel):
    vcx, vymin, vymax = cx_of(vowel)
    g = f[combo]; g.clearContours(); g.clearComponents()
    g.width = 0
    # vowel at its own position (bottom already at 0)
    g.appendComponent(_c(vowel, 0, 0))
    # shadda centred under the vowel, its top just below the vowel bottom (0)
    dy = -(symax + GAP)          # shadda top -> -GAP
    g.appendComponent(_c("uni0651", round(vcx - scx), round(dy)))
    new_anchor[combo] = (round(vcx), 0)

def build_below(combo, vowel):
    vcx, vymin, vymax = cx_of(vowel)
    g = f[combo]; g.clearContours(); g.clearComponents()
    g.width = 0
    # shadda on top at its own position (bottom 0)
    g.appendComponent(_c("uni0651", 0, 0))
    # vowel tucked just below the shadda (vowel top -> just under shadda bottom 0)
    dy = -GAP - vymax
    g.appendComponent(_c(vowel, round(scx - vcx), round(dy)))
    new_anchor[combo] = (round(scx), 0)

def _c(base, dx, dy):
    c = Component(); c.baseGlyph = base; c.move((dx, dy)); return c

for combo, v in ABOVE.items():
    build_above(combo, v)
for combo, v in BELOW.items():
    build_below(combo, v)

# regenerate narrow variants of the combos (scale around their anchor)
from fontTools.misc.transform import Transform
from defcon.pens.transformPointPen import TransformPointPen
for combo in list(ABOVE) + list(BELOW):
    ax, ay = new_anchor[combo]
    nn = combo + ".narrow"
    if nn in f:
        del f[nn]
    ng = f.newGlyph(nn); ng.width = 0
    t = Transform().translate(ax, ay).scale(SX, SY).translate(-ax, -ay)
    f[combo].drawPoints(TransformPointPen(ng.getPointPen(), t))
    new_anchor[nn] = (ax, ay)

f.save()
print("rebuilt %d shadda combos (+narrows)" % (len(ABOVE) + len(BELOW)))

# update markClass anchors
fea = open(FEA).read(); n = 0
for nm, (ax, ay) in new_anchor.items():
    pat = re.compile(r"(markClass %s <anchor )-?\d+ -?\d+(> @)" % re.escape(nm))
    fea, k = pat.subn(r"\g<1>%d %d\g<2>" % (ax, ay), fea); n += k
open(FEA, "w").write(fea)
print("updated %d combo markClass anchors" % n)
