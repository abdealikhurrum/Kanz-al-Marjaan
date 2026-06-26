"""Render a labeled annotation sheet of base letters with a top mark (fatha)
AND a bottom mark (kasra) attached simultaneously, so both @t and @b anchors
can be eyeballed and marked up.

Each glyph cluster is horizontally CENTERED in its cell and CLIPPED to the cell
box, so wide letters cannot bleed into a neighbour (which would make a red dot
ambiguous).  Cells carry a faint 50px grid so a drawn arrow maps to font units.

Usage:
  python3 scripts/mark_sheet.py [out/mark_sheet.png] [PPEM]
Env:
  MARK_SHEET_TTF    font to render (default fonts/ttf/KanzAlMarjaan-Regular.ttf)
  MARK_SHEET_BASES  comma hex base set (default = core 28 + extras)
"""
import os
import sys
import uharfbuzz as hb
import freetype
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

TTF = os.environ.get("MARK_SHEET_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/mark_sheet.png"
PPEM = int(sys.argv[2]) if len(sys.argv) > 2 else 200

TOP_MARK = 0x064E   # fatha
BOT_MARK = 0x0650   # kasra

DEFAULT_BASES = [
    0x0627, 0x0628, 0x062A, 0x062B, 0x062C, 0x062D, 0x062E, 0x062F,
    0x0630, 0x0631, 0x0632, 0x0633, 0x0634, 0x0635, 0x0636, 0x0637,
    0x0638, 0x0639, 0x063A, 0x0641, 0x0642, 0x0643, 0x0644, 0x0645,
    0x0646, 0x0647, 0x0648, 0x064A, 0x0629, 0x0621,
]
env = os.environ.get("MARK_SHEET_BASES")
BASES = [int(h, 16) for h in env.split(",")] if env else DEFAULT_BASES

with open(TTF, "rb") as fh:
    data = fh.read()
hbfont = hb.Font(hb.Face(data))
face = freetype.Face(TTF)
upm = face.units_per_EM
face.set_pixel_sizes(0, PPEM)
sc = PPEM / upm
units_per_px = upm / PPEM

tt = TTFont(TTF)
cmap = tt.getBestCmap()

def gname(cp):
    return cmap.get(cp, "?")

try:
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
except Exception:
    lab = small = ImageFont.load_default()

CW, CH = 360, 420
COLS = 6
rows = (len(BASES) + COLS - 1) // COLS
HEADER = 56
W = COLS * CW
H = HEADER + rows * CH

sheet = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(sheet)

draw.rectangle([0, 0, W, HEADER], fill=(245, 245, 250))
draw.text((16, 8), "Kanz al Marjaan — mark annotation sheet", fill="black", font=lab)
draw.text((16, 32),
          "fatha (top) + kasra (bottom) on each base.  glyph centered & clipped "
          "per cell.  grid = 50px;  1px ~ %.1f units (50px ~ %d units).  PPEM=%d"
          % (units_per_px, round(50 * units_per_px), PPEM),
          fill=(90, 90, 90), font=small)

GRID = (232, 232, 240)
GUIDE = (150, 150, 220)


def shape_bitmaps(base):
    """Return [(rel_x, rel_y, PIL_ink)] relative to pen origin (0,0), and ink bbox."""
    buf = hb.Buffer()
    buf.add_codepoints([base, TOP_MARK, BOT_MARK])
    buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    glyphs = []
    penx = 0
    minx = miny = 10**9
    maxx = maxy = -10**9
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        g = face.glyph
        bmp = g.bitmap
        rx = (penx + pos.x_offset) * sc + g.bitmap_left
        ry = -(pos.y_offset) * sc - g.bitmap_top
        if bmp.width and bmp.rows:
            ink = Image.frombytes("L", (bmp.width, bmp.rows), bytes(bmp.buffer))
            glyphs.append((rx, ry, ink))
            minx = min(minx, rx); maxx = max(maxx, rx + bmp.width)
            miny = min(miny, ry); maxy = max(maxy, ry + bmp.rows)
        penx += pos.x_advance
    return glyphs, (minx, miny, maxx, maxy)


for i, base in enumerate(BASES):
    r, c = divmod(i, COLS)
    cx0 = c * CW
    cy0 = HEADER + r * CH

    for gx in range(cx0, cx0 + CW, 50):
        draw.line([gx, cy0, gx, cy0 + CH], fill=GRID)
    for gy in range(cy0, cy0 + CH, 50):
        draw.line([cx0, gy, cx0 + CW, gy], fill=GRID)
    draw.rectangle([cx0, cy0, cx0 + CW - 1, cy0 + CH - 1], outline=(210, 210, 210))

    oy = cy0 + CH - 150                      # baseline (fixed)
    draw.line([cx0, oy, cx0 + CW, oy], fill=GUIDE)

    glyphs, (minx, miny, maxx, maxy) = shape_bitmaps(base)
    # center the ink cluster horizontally inside the cell
    cluster_cx = (minx + maxx) / 2 if maxx > minx else 0
    ox = cx0 + CW / 2 - cluster_cx

    cell_img = sheet.crop((cx0, cy0, cx0 + CW, cy0 + CH))   # clip target
    for rx, ry, ink in glyphs:
        px = int(ox + rx) - cx0
        py = int(oy + ry) - cy0
        cell_img.paste((20, 20, 20), (px, py), ink)
    sheet.paste(cell_img, (cx0, cy0))

    draw.text((cx0 + 8, cy0 + 6), "%s  U+%04X" % (gname(base), base),
              fill="black", font=small)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
sheet.save(OUT)
print("wrote", OUT, "(%dx%d, %d bases, font=%s)" % (W, H, len(BASES), TTF))
