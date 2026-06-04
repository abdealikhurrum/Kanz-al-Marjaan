"""Replace the GF_Latin_Kernel glyphs in the UFO with Source Sans 3 (OFL)
outlines, scaled so cap-height matches this font (1025).  Arabic is untouched.
"""
import defcon
from fontTools.ttLib import TTFont
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.qu2cuPen import Qu2CuPen

UFO = "sources/KanzAlMarjaan-Regular.ufo"
SRC = "/tmp/srcsans/SourceSans3-Regular.ttf"

def is_arabic(cp):
    return (0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F
            or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF)

src = TTFont(SRC)
src_cap = 656.0
S = 1025.0 / src_cap                  # 1.5617
src_cmap = src.getBestCmap()
src_gs = src.getGlyphSet()
src_hmtx = src["hmtx"]

ufo = defcon.Font(UFO)
# unicode -> ufo glyph name
uni2name = {}
for g in ufo:
    for u in g.unicodes:
        uni2name[u] = g.name

# Every non-Arabic codepoint currently mapped (>= 0x20) gets its outline taken
# from Source Sans, so no Arial-derived Latin/punctuation/symbol ink remains.
TARGETS = sorted(cp for cp in uni2name if cp >= 0x20 and not is_arabic(cp))

done, missing_src, missing_tgt = 0, [], []
for cp in TARGETS:
    sname = src_cmap.get(cp)
    if not sname:
        missing_src.append(cp); continue
    tname = uni2name.get(cp)
    if not tname:
        missing_tgt.append(cp); continue
    # record Source Sans outline with components decomposed
    drp = DecomposingRecordingPen(src_gs)
    src_gs[sname].draw(drp)
    g = ufo[tname]
    g.clearContours(); g.clearComponents()
    # scale, and convert Source Sans quadratic curves to cubic (UFO convention)
    tpen = TransformPen(g.getPen(), (S, 0, 0, S, 0, 0))
    drp.replay(Qu2CuPen(tpen, max_err=0.6, all_cubic=True))
    g.width = round(src_hmtx[sname][0] * S)
    g.unicode = cp
    done += 1

ufo.save()
print("replaced %d Kernel glyphs (scale %.4f)" % (done, S))
if missing_src:
    print("  not in Source Sans:", [hex(c) for c in missing_src])
if missing_tgt:
    print("  not in target UFO:", [hex(c) for c in missing_tgt])
