"""Read an annotated mark_sheet.png and propose anchor edits.

Detects red target dots, maps each to the glyph in its cell (replicating the
centered/clipped geometry of mark_sheet.py), and converts the dot to a new
@t/@b anchor via EMPIRICAL calibration: render base-only vs base+mark, diff to
isolate the mark ink, and shift the anchor by (dot - mark_ink)/scale.  This is
immune to RTL / side-bearing skew in any forward model.

Usage:  python3 scripts/read_marks.py [annotated.png]   (prints an edit table)
Env:    READ_MARKS_TTF (default fonts/ttf/KanzAlMarjaan-Regular.ttf)
"""
import os, re, sys
import numpy as np
import uharfbuzz as hb, freetype
from PIL import Image

TTF = os.environ.get("READ_MARKS_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
SHEET = sys.argv[1] if len(sys.argv) > 1 else "out/mark_sheet.png"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"

CW, CH, HEADER, COLS = 360, 420, 56, 6
PPEM = 200
TOP_MARK, BOT_MARK = 0x064E, 0x0650
BASES = [0x0627,0x0628,0x062A,0x062B,0x062C,0x062D,0x062E,0x062F,0x0630,0x0631,
0x0632,0x0633,0x0634,0x0635,0x0636,0x0637,0x0638,0x0639,0x063A,0x0641,
0x0642,0x0643,0x0644,0x0645,0x0646,0x0647,0x0648,0x064A,0x0629,0x0621]

data = open(TTF, "rb").read()
hbf = hb.Font(hb.Face(data)); face = freetype.Face(TTF)
UPM = face.units_per_EM; face.set_pixel_sizes(0, PPEM); sc = PPEM / UPM
fea = open(FEA).read()

def anchors(g):
    m = re.search(r"pos base %s\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                  r"<anchor (-?\d+) (-?\d+)> mark \@b" % g, fea)
    return tuple(map(int, m.groups()))

def shaped(cps):
    """Return list of (rx, ry, ink_arr) relative to pen origin, + cluster bbox."""
    buf = hb.Buffer(); buf.add_codepoints(cps); buf.guess_segment_properties(); hb.shape(hbf, buf)
    gl = []; minx = miny = 1e9; maxx = maxy = -1e9; penx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
        rx = (penx + pos.x_offset) * sc + g.bitmap_left
        ry = -(pos.y_offset) * sc - g.bitmap_top
        if bm.width and bm.rows:
            ink = np.frombuffer(bytes(bm.buffer), np.uint8).reshape(bm.rows, bm.width)
            gl.append((rx, ry, ink))
            minx = min(minx, rx); maxx = max(maxx, rx + bm.width)
            miny = min(miny, ry); maxy = max(maxy, ry + bm.rows)
        penx += pos.x_advance
    return gl, (minx, miny, maxx, maxy)

def cell_mask(cps, ox, oy):
    """Rasterize cps into a CWxCH cell mask using fixed pen origin (ox,oy)."""
    img = np.zeros((CH, CW), np.uint8)
    gl, _ = shaped(cps)
    for rx, ry, ink in gl:
        px = int(ox + rx); py = int(oy + ry)
        h, w = ink.shape
        for yy in range(h):
            Y = py + yy
            if 0 <= Y < CH:
                for xx in range(w):
                    X = px + xx
                    if 0 <= X < CW and ink[yy, xx] > 40:
                        img[Y, X] = 255
    return img

# --- detect red dots ---
a = np.asarray(Image.open(SHEET).convert("RGB")).astype(int)
red = (a[:,:,0] > 150) & (a[:,:,1] < 110) & (a[:,:,2] < 110)
ys, xs = np.where(red)
from collections import defaultdict
cells = defaultdict(list)
for x, y in zip(xs, ys):
    if y < HEADER: continue
    cells[((y - HEADER) // CH, x // CW)].append((x, y))

print(f"{'glyph':9} side  cur_anchor       new_anchor       delta(px)")
edits = {}
for (r, c) in sorted(cells):
    i = r * COLS + c
    if i >= len(BASES): continue
    cp = BASES[i]; g = "uni%04X" % cp
    cx0, cy0 = c * CW, HEADER + r * CH
    oy = cy0 + CH - 150
    # replicate generator centering (full base+both-marks cluster)
    _, (mnx, _, mxx, _) = shaped([cp, TOP_MARK, BOT_MARK])
    ox = cx0 + CW/2 - (mnx + mxx)/2
    pts = np.array(cells[(r, c)])
    tx, ty, bx, by = anchors(g)
    # a cell may carry a top dot AND a bottom dot — split by baseline, treat each
    for side in ("top", "bot"):
        sel = pts[pts[:,1] < oy] if side == "top" else pts[pts[:,1] >= oy]
        if len(sel) < 8: continue                  # ignore stray specks
        rx, ry = sel[:,0].mean(), sel[:,1].mean()
        mark = TOP_MARK if side == "top" else BOT_MARK
        base_m = cell_mask([cp], ox - cx0, oy - cy0)
        both_m = cell_mask([cp, mark], ox - cx0, oy - cy0)
        diff = (both_m > 0) & (base_m == 0)
        dys, dxs = np.where(diff)
        if len(dxs) == 0:
            print(g, side, "NO MARK INK"); continue
        mlx, mly = dxs.mean() + cx0, dys.mean() + cy0
        dax = (rx - mlx) / sc
        day = -(ry - mly) / sc
        cur = (tx, ty) if side == "top" else (bx, by)
        new = (round(cur[0] + dax), round(cur[1] + day))
        edits[(g, side)] = (cur, new)
        print(f"{g:9} {side}  {str(cur):16} {str(new):16} ({round(rx-mlx)},{round(ry-mly)})")

# emit a python dict for the apply step
print("\nEDITS =", {f"{g}:{s}": v[1] for (g, s), v in edits.items()})
