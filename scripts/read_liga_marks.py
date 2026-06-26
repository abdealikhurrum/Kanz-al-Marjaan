"""Read yellow target ovals on liga_sheet.png and propose anchor edits.

Same empirical calibration as read_marks.py, but: (1) liga_sheet geometry
(CW380/CH440/COLS4, baseline = cy0+CH-160), (2) each cell shapes a codepoint
SEQUENCE, (3) the mark attaches to the ligature glyph in the run, whose pos
base @t/@b anchor is the edit target.  Yellow (not red) = target.
"""
import os, re, sys
import numpy as np
import uharfbuzz as hb, freetype
from PIL import Image
from fontTools.ttLib import TTFont

TTF = os.environ.get("READ_MARKS_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
SHEET = sys.argv[1] if len(sys.argv) > 1 else "out/liga_sheet.png"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
CW, CH, COLS, HEADER, PPEM = 380, 440, 4, 56, 200
TOP_MARK, BOT_MARK = 0x064E, 0x0650

# must match liga_sheet.py SAMPLE order
SAMPLE = [
    ("lam-alef",[0x0644,0x0627]),("Allah",[0x0627,0x0644,0x0644,0x0647]),
    ("Muhammad",[0x0645,0x062D,0x0645,0x062F]),("beh-meem",[0x0628,0x0645]),
    ("beh-hah",[0x0628,0x062D]),("feh-hah",[0x0641,0x062D]),
    ("gaf-lam-alef",[0x06AF,0x0644,0x0627]),("LD yeh-jeem-meem",[0x0626,0x062C,0x0645,0x062C]),
    ("LD yeh-hah-meem",[0x0626,0x062D,0x0645,0x062C]),("LD beh-jeem-meem",[0x0628,0x062C,0x0645,0x062C]),
    ("LD theh-jeem-meem",[0x062B,0x062C,0x0645,0x062C]),("LD yeh-yehbarree",[0x0626,0x06D2]),
    ("LD yeh-noon-ybar",[0x0626,0x0646,0x06D2]),("LD yeh-heh-jeem",[0x0626,0x0647,0x062C,0x062C]),
]

data = open(TTF, "rb").read()
hbf = hb.Font(hb.Face(data)); face = freetype.Face(TTF)
UPM = face.units_per_EM; face.set_pixel_sizes(0, PPEM); sc = PPEM / UPM
order = TTFont(TTF).getGlyphOrder(); fea = open(FEA).read()

def has_posbase(g):
    return re.search(r"pos base %s\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                     r"<anchor (-?\d+) (-?\d+)> mark \@b" % re.escape(g), fea)

def anchors(g):
    return tuple(map(int, has_posbase(g).groups()))

def shaped(cps):
    buf = hb.Buffer(); buf.add_codepoints(cps); buf.guess_segment_properties(); hb.shape(hbf, buf)
    gl = []; names = []; mnx = 1e9; mxx = -1e9; penx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        names.append(order[info.codepoint])
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
        rx = (penx + pos.x_offset) * sc + g.bitmap_left; ry = -(pos.y_offset) * sc - g.bitmap_top
        ink = None
        if bm.width and bm.rows:
            ink = np.frombuffer(bytes(bm.buffer), np.uint8).reshape(bm.rows, bm.width)
            gl.append((rx, ry, ink)); mnx = min(mnx, rx); mxx = max(mxx, rx + bm.width)
        penx += pos.x_advance
    return gl, (mnx, mxx), names

def cell_mask(cps, ox, oy):
    img = np.zeros((CH, CW), np.uint8)
    for rx, ry, ink in shaped(cps)[0]:
        px = int(ox + rx); py = int(oy + ry); h, w = ink.shape
        for yy in range(h):
            Y = py + yy
            if 0 <= Y < CH:
                row = ink[yy]
                for xx in range(w):
                    X = px + xx
                    if 0 <= X < CW and row[xx] > 40: img[Y, X] = 255
    return img

def markbearing(cps):
    """ligature glyph in the run that carries a pos base anchor (skip marks)."""
    _, _, names = shaped(cps)
    cand = [n for n in names if has_posbase(n)]
    # prefer an explicit ligature glyph; else the last base in logical order
    for n in names:
        if n in cand and ("liga" in n or n.startswith("uniFD") or n.startswith("uniFE") or n == "MHMD.liga"):
            return n
    return cand[-1] if cand else None

a = np.asarray(Image.open(SHEET).convert("RGB")).astype(int)
R, G, B = a[:,:,0], a[:,:,1], a[:,:,2]
yellow = (R > 180) & (G > 160) & (B < 120)
from collections import defaultdict
cells = defaultdict(list)
ys, xs = np.where(yellow)
for x, y in zip(xs, ys):
    if y < HEADER: continue
    cells[((y - HEADER) // CH, x // CW)].append((x, y))

print(f"{'glyph':30} side cur_anchor       new_anchor       delta(px)")
edits = {}
for (r, c) in sorted(cells):
    i = r * COLS + c
    if i >= len(SAMPLE): continue
    label, cps = SAMPLE[i]
    g = markbearing(cps)
    if not g:
        print(f"{label}: no mark-bearing glyph"); continue
    cx0, cy0 = c * CW, HEADER + r * CH
    oy = cy0 + CH - 160
    _, (mnx, mxx), _ = shaped(cps + [TOP_MARK, BOT_MARK])
    ox = cx0 + CW/2 - (mnx + mxx)/2
    pts = np.array(cells[(r, c)])
    tx, ty, bx, by = anchors(g)
    for side in ("top", "bot"):
        sel = pts[pts[:,1] < oy] if side == "top" else pts[pts[:,1] >= oy]
        if len(sel) < 8: continue
        rx, ry = sel[:,0].mean(), sel[:,1].mean()
        mark = TOP_MARK if side == "top" else BOT_MARK
        diff = (cell_mask(cps + [mark], ox - cx0, oy - cy0) > 0) & (cell_mask(cps, ox - cx0, oy - cy0) == 0)
        dys, dxs = np.where(diff)
        if len(dxs) == 0:
            print(f"{g} {side}: no mark ink"); continue
        mlx, mly = dxs.mean() + cx0, dys.mean() + cy0
        cur = (tx, ty) if side == "top" else (bx, by)
        new = (round(cur[0] + (rx - mlx)/sc), round(cur[1] - (ry - mly)/sc))
        edits[f"{g}:{side}"] = new
        print(f"{g:30} {side} {str(cur):16} {str(new):16} ({round(rx-mlx)},{round(ry-mly)})  [{label}]")

print("\nEDITS =", edits)
