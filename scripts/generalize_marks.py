"""Generalize a representative skeleton's tuned mark anchors to its nukta-siblings.

For each (sibling, form, side) it transfers the representative's anchor as a
constant gap beyond the glyph's ink extreme (yMax for top, yMin for bottom) and
re-centres x on the sibling ink — so dotted siblings push the mark out to clear
their nuktas.  --apply writes features.fea; default is a dry run.
"""
import os, re, sys
import numpy as np
import uharfbuzz as hb, freetype
from fontTools.ttLib import TTFont

TTF = os.environ.get("READ_MARKS_TTF", "/tmp/_kam_new.ttf")
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
APPLY = "--apply" in sys.argv
TAT = 0x0640
data = open(TTF, "rb").read(); hbf = hb.Font(hb.Face(data))
tt = TTFont(TTF); glyf = tt["glyf"]; order = tt.getGlyphOrder()
fea = open(FEA).read()
face = freetype.Face(TTF); PPEM_M = 256; face.set_pixel_sizes(0, PPEM_M); scm = PPEM_M / face.units_per_EM

def masscx(g):
    """ink mass-centroid x in font units (sits in the dense body, ignores thin tails)."""
    face.load_glyph(order.index(g), freetype.FT_LOAD_RENDER)
    bm = face.glyph.bitmap
    if not (bm.width and bm.rows): return None
    arr = np.frombuffer(bytes(bm.buffer), np.uint8).reshape(bm.rows, bm.width).astype(float)
    cols = arr.sum(axis=0)
    meanpx = (cols * np.arange(bm.width)).sum() / cols.sum()
    return (face.glyph.bitmap_left + meanpx) / scm

# rep base cp -> sibling base cps (same joining skeleton, differ by nuktas)
SIBS = {
    0x0628: [0x062A, 0x062B, 0x064A, 0x067E, 0x0679],   # beh -> teh theh yeh peh tteh
    0x062D: [0x062C, 0x062E, 0x0686],                   # hah -> jeem khah tcheh
    0x0639: [0x063A],                                   # ain -> ghain
    0x0641: [0x0642],                                   # feh -> qaf
    0x062F: [0x0630],                                   # dal -> thal
    0x0631: [0x0632],                                   # reh -> zain
}
# which (rep cp, form, side) were tuned -> generalize those
TUNED = [
    (0x0628,"medi","top"),(0x0628,"fina","top"),
    (0x062D,"fina","top"),
    (0x0639,"medi","top"),(0x0639,"fina","top"),
    (0x0641,"fina","top"),
    (0x062F,"isol","top"),(0x062F,"fina","top"),
    (0x0631,"isol","top"),(0x0631,"fina","top"),
]
JOIN = {"init":([],[TAT]),"medi":([TAT],[TAT]),"fina":([TAT],[]),"isol":([],[])}

def posglyph(cp, form):
    pre, suf = JOIN[form]
    buf = hb.Buffer(); buf.add_codepoints(pre+[cp]+suf); buf.guess_segment_properties(); hb.shape(hbf, buf)
    for info in buf.glyph_infos:
        n = order[info.codepoint]
        if n != "uni0640" and re.search(r"pos base %s\s*<anchor" % re.escape(n), fea):
            return n
    return None

def bounds(g):
    gl = glyf[g]
    if gl.numberOfContours == 0: return None
    return gl.xMin, gl.yMin, gl.xMax, gl.yMax

def anchors(g):
    m = re.search(r"pos base %s\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                  r"<anchor (-?\d+) (-?\d+)> mark \@b" % re.escape(g), fea)
    return tuple(map(int, m.groups()))

edits = {}
print(f"{'rep':9}->{'sibling':9} {'form':5} {'side':4} {'rep_anchor':14} {'new':14}")
for rep_cp, form, side in TUNED:
    rg = posglyph(rep_cp, form)
    if not rg: continue
    tx, ty, bx, by = anchors(rg)
    ra = (tx, ty) if side == "top" else (bx, by)
    rb = bounds(rg)
    rxmin, rymin, rxmax, rymax = rb
    rcx = masscx(rg)                       # mass-centroid x (visual center), not bbox center
    edits[f"{rg}:{side}"] = (round(rcx), ra[1])   # recenter the rep's own eraab x too (keep its tuned height)
    gap_y = ra[1] - (rymax if side == "top" else rymin)
    dx = ra[0] - rcx
    for scp in SIBS.get(rep_cp, []):
        sg = posglyph(scp, form)
        if not sg: continue
        sb = bounds(sg)
        if not sb: continue
        sxmin, symin, sxmax, symax = sb
        scx = masscx(sg)                   # mass-centroid x (visual center), not bbox center
        ny = round((symax if side == "top" else symin) + gap_y)
        nx = round(scx)            # eraab at the sibling's own visual center (mass-centroid x)
        cur = anchors(sg); cur_side = (cur[0], cur[1]) if side == "top" else (cur[2], cur[3])
        edits[f"{sg}:{side}"] = (nx, ny)
        print(f"{rg:9}->{sg:9} {form:5} {side:4} {str(ra):14} {str((nx,ny)):14}")

print(f"\n{len(edits)} sibling edits")
if APPLY:
    s = fea
    for k, (nx, ny) in edits.items():
        g, side = k.rsplit(":", 1)
        pat = re.compile(r"(pos base %s\s*<anchor )(-?\d+) (-?\d+)(> mark \@t\.uni064B\s*<anchor )(-?\d+) (-?\d+)(> mark \@b\.uni064D_1;)" % re.escape(g))
        m = pat.search(s)
        if not m: print("NO MATCH", g); continue
        if side == "top": rep = m.group(1)+f"{nx} {ny}"+m.group(4)+m.group(5)+" "+m.group(6)+m.group(7)
        else: rep = m.group(1)+m.group(2)+" "+m.group(3)+m.group(4)+f"{nx} {ny}"+m.group(7)
        s = s[:m.start()]+rep+s[m.end():]
    open(FEA, "w").write(s); print("APPLIED", len(edits))
