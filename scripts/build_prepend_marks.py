"""Native 'prepended concatenation mark' spanning (Amiri-style), shape-and-bake.

Works for any gftools/UFO Arabic font: SHAPE the cluster head + (3N tatweels) +
tail with the font itself and BAKE the positioned glyphs as components, so the
kashida joins the heads exactly (contiguous). y-offsets are zeroed (flat
kashida). Tabular nesting digits uniXXXX.span (W = shaped span of 3 tatweels)
make the run length exact. The matching GSUB/GPOS is appended separately; this
script also PRINTS the W and per-sign left-head widths (LH) needed for it.

Usage:  python3 scripts/build_prepend_marks.py [UFO] [TTF]
        (defaults to the Kanz source/binary)
"""
import sys
import defcon
import uharfbuzz as hb
from defcon import Component
from fontTools.ttLib import TTFont

UFO = sys.argv[1] if len(sys.argv) > 1 else "sources/KanzAlMarjaan-Regular.ufo"
TTF = sys.argv[2] if len(sys.argv) > 2 else "fonts/ttf/KanzAlMarjaan-Regular.ttf"
TPD = 3
DIGIT_RAISE = 170
WAW_FINAL = "uniFEEE"
WAW_CLIP = "waw.notail"

tt = TTFont(TTF); GO = tt.getGlyphOrder()
hbf = hb.Font(hb.Face(open(TTF, "rb").read()))
f = defcon.Font(UFO)

def assemble(text):
    # shape to get the correctly-joined glyph SEQUENCE (GSUB), but lay out at
    # NOMINAL advances (ignore GPOS curs/kashida-justification, which can give
    # negative advances / y-shifts in some fonts). Flat, predictable kashida.
    b = hb.Buffer(); b.add_str(text); b.guess_segment_properties(); hb.shape(hbf, b)
    penx = 0; out = []
    for info in b.glyph_infos:
        name = GO[info.codepoint]
        out.append([name, penx, 0]); penx += f[name].width
    return out, penx

_, a3 = assemble("ـ" * 3); _, a6 = assemble("ـ" * 6)
W = round(a6 - a3)

# clip the waw tail (keep y >= -20) -> waw.notail
import pathops
sk = pathops.Path(); f[WAW_FINAL].draw(sk.getPen())
b = f[WAW_FINAL].bounds
rect = pathops.Path(); rp = rect.getPen()
rp.moveTo((b[0]-50, -20)); rp.lineTo((b[2]+50, -20)); rp.lineTo((b[2]+50, b[3]+50)); rp.lineTo((b[0]-50, b[3]+50)); rp.closePath()
res = pathops.op(sk, rect, pathops.PathOp.INTERSECTION)
if WAW_CLIP in f: del f[WAW_CLIP]
wg = f.newGlyph(WAW_CLIP); wg.width = f[WAW_FINAL].width; res.draw(wg.getPen())

# tabular nesting digit variants
for cp in range(0x0660, 0x066A):
    dn = "uni%04X" % cp; nn = dn + ".span"
    if nn in f: del f[nn]
    g = f.newGlyph(nn); g.width = W
    dx = round((W - f[dn].width) / 2.0)
    c = Component(); c.baseGlyph = dn; c.move((dx, DIGIT_RAISE)); g.appendComponent(c)

def build_sign(cp, gname, head_right_ch="", left_text="", swap=None):
    """head_right_ch: one or more letters shaped at the right (kashida runs left
    from them). left_text: letters that join on the left end. Junction (kashida
    right end) is placed at local x=0 via the rightmost tatweel, so heads of any
    length sit at x>=0 and the advance reserves exactly the right head."""
    swap = swap or {}
    def make(name, n, encode=None):
        text = head_right_ch + ("ـ" * (TPD * n)) + left_text
        placed, total = assemble(text)
        tats = [(x, gn) for gn, x, y in placed if gn.startswith("uni0640")]
        rx, rgn = max(tats, key=lambda t: t[0])      # rightmost tatweel
        R = rx + f[rgn].width                          # kashida right end
        dx = -R; adv = round(total - R)                # right head reserved on the right
        if name in f: del f[name]
        g = f.newGlyph(name); g.width = adv
        if encode is not None: g.unicodes = [encode]
        for gn, x, y in placed:
            c = Component(); c.baseGlyph = swap.get(gn, gn); c.move((round(x + dx), 0))
            g.appendComponent(c)
    for n in range(1, 5):
        make("%s.d%d" % (gname, n), n)
    make(gname, 1, encode=cp)

build_sign(0x0603, "uni0603", head_right_ch="ص")            # safha = saad
build_sign(0x0601, "uni0601", head_right_ch="س", left_text="نة")  # sanah = seen..noon-teh
build_sign(0x0602, "uni0602", left_text="و", swap={WAW_FINAL: WAW_CLIP})  # footnote = waw(clip) left
build_sign(0x0600, "uni0600", head_right_ch="ع")            # number sign = ain
build_sign(0x0604, "uni0604", head_right_ch="سم")           # samvat = seen+meem

f.save()

# left-head widths (overshoot past the kashida left end -W, from the .d1 forms)
def LH(gname):
    bb = f[gname + ".d1"].bounds
    return round(-W - bb[0]) if bb else 0
print("W=%d  LH_sanah=%d  LH_footnote=%d  LH_safha=%d"
      % (W, LH("uni0601"), LH("uni0602"), LH("uni0603")))
