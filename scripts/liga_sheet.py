"""Annotation sheet for JOINED LETTERS & LIGATURES (core + LD calligraphic).

Each cell shapes a codepoint SEQUENCE (which fires the ligature) plus fatha
(top) + kasra (bottom), centered & clipped per cell, on a 50px grid.  The
ligature glyph carries the same @t.uni064B / @b.uni064D_1 pos-base anchors as
ordinary bases, so the read_marks calibration applies unchanged.

Usage:  python3 scripts/liga_sheet.py [out/liga_sheet.png] [PPEM]
Env:    MARK_SHEET_TTF (default fonts/ttf/KanzAlMarjaan-Regular.ttf)
"""
import os, sys
import uharfbuzz as hb, freetype
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

TTF = os.environ.get("MARK_SHEET_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/liga_sheet.png"
PPEM = int(sys.argv[2]) if len(sys.argv) > 2 else 200
TOP_MARK, BOT_MARK = 0x064E, 0x0650

# (label, [codepoints])  — trailing connector letters fire the LD .init.medi forms
SAMPLE = [
    ("lam-alef",        [0x0644, 0x0627]),
    ("Allah",           [0x0627, 0x0644, 0x0644, 0x0647]),
    ("Muhammad",        [0x0645, 0x062D, 0x0645, 0x062F]),
    ("beh-meem",        [0x0628, 0x0645]),
    ("beh-hah",         [0x0628, 0x062D]),
    ("feh-hah",         [0x0641, 0x062D]),
    ("gaf-lam-alef",    [0x06AF, 0x0644, 0x0627]),
    ("LD yeh-jeem-meem",[0x0626, 0x062C, 0x0645, 0x062C]),
    ("LD yeh-hah-meem", [0x0626, 0x062D, 0x0645, 0x062C]),
    ("LD beh-jeem-meem",[0x0628, 0x062C, 0x0645, 0x062C]),
    ("LD theh-jeem-meem",[0x062B, 0x062C, 0x0645, 0x062C]),
    ("LD yeh-yehbarree",[0x0626, 0x06D2]),
    ("LD yeh-noon-ybar",[0x0626, 0x0646, 0x06D2]),
    ("LD yeh-heh-jeem", [0x0626, 0x0647, 0x062C, 0x062C]),
]

data = open(TTF, "rb").read()
hbfont = hb.Font(hb.Face(data)); face = freetype.Face(TTF)
upm = face.units_per_EM; face.set_pixel_sizes(0, PPEM); sc = PPEM / upm
order = TTFont(TTF).getGlyphOrder()
try:
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
except Exception:
    small = lab = ImageFont.load_default()

CW, CH, COLS, HEADER = 380, 440, 4, 56
rows = (len(SAMPLE) + COLS - 1) // COLS
W, H = COLS * CW, HEADER + rows * CH
sheet = Image.new("RGB", (W, H), "white"); draw = ImageDraw.Draw(sheet)
draw.rectangle([0, 0, W, HEADER], fill=(245, 245, 250))
draw.text((16, 8), "Kanz al Marjaan — joined letters & ligatures", fill="black", font=lab)
draw.text((16, 32), "fatha (top) + kasra (bottom) on each ligature.  grid = 50px; "
          "1px ~ %.1f units.  PPEM=%d" % (upm / PPEM, PPEM), fill=(90, 90, 90), font=small)
GRID, GUIDE = (232, 232, 240), (150, 150, 220)

def shape_bitmaps(cps):
    buf = hb.Buffer(); buf.add_codepoints(cps); buf.guess_segment_properties(); hb.shape(hbfont, buf)
    gl = []; names = []; minx = miny = 1e9; maxx = maxy = -1e9; penx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        names.append(order[info.codepoint])
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
        rx = (penx + pos.x_offset) * sc + g.bitmap_left
        ry = -(pos.y_offset) * sc - g.bitmap_top
        if bm.width and bm.rows:
            ink = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
            gl.append((rx, ry, ink))
            minx = min(minx, rx); maxx = max(maxx, rx + bm.width)
        penx += pos.x_advance
    return gl, (minx, maxx), names

for i, (label, cps) in enumerate(SAMPLE):
    r, c = divmod(i, COLS)
    cx0, cy0 = c * CW, HEADER + r * CH
    for gx in range(cx0, cx0 + CW, 50): draw.line([gx, cy0, gx, cy0 + CH], fill=GRID)
    for gy in range(cy0, cy0 + CH, 50): draw.line([cx0, gy, cx0 + CW, gy], fill=GRID)
    draw.rectangle([cx0, cy0, cx0 + CW - 1, cy0 + CH - 1], outline=(210, 210, 210))
    oy = cy0 + CH - 160
    draw.line([cx0, oy, cx0 + CW, oy], fill=GUIDE)
    gl, (mnx, mxx), names = shape_bitmaps(cps + [TOP_MARK, BOT_MARK])
    ox = cx0 + CW / 2 - (mnx + mxx) / 2
    cell = sheet.crop((cx0, cy0, cx0 + CW, cy0 + CH))
    for rx, ry, ink in gl:
        cell.paste((20, 20, 20), (int(ox + rx) - cx0, int(oy + ry) - cy0), ink)
    sheet.paste(cell, (cx0, cy0))
    glyphs = "+".join(n for n in names if n not in ("uni064E", "uni0650"))
    draw.text((cx0 + 8, cy0 + 6), label, fill="black", font=small)
    draw.text((cx0 + 8, cy0 + 24), glyphs[:46], fill=(120, 120, 120), font=small)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
sheet.save(OUT)
print("wrote", OUT, "(%dx%d, %d cells)" % (W, H, len(SAMPLE)))
