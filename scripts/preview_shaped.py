"""Render shaped base+mark combinations using HarfBuzz positions + freetype,
so mark attachment can be eyeballed.  Args: comma-separated 'BASEHEX:MARKHEX' pairs.
"""
import sys
import uharfbuzz as hb
import freetype
from PIL import Image, ImageDraw, ImageFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
PAIRS = [tuple(int(h, 16) for h in p.split(":")) for p in sys.argv[1].split(",")]
OUT = sys.argv[2] if len(sys.argv) > 2 else "out/shaped.png"

with open(TTF, "rb") as fh:
    data = fh.read()
hbfont = hb.Font(hb.Face(data))
face = freetype.Face(TTF)
upm = face.units_per_EM
PPEM = 200
face.set_pixel_sizes(0, PPEM)
sc = PPEM / upm

CW, CH = 460, 470
cols = len(PAIRS)
sheet = Image.new("RGB", (cols * CW, CH), "white")
draw = ImageDraw.Draw(sheet)
try:
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
except Exception:
    lab = ImageFont.load_default()

for col, (base, mark) in enumerate(PAIRS):
    buf = hb.Buffer()
    buf.add_codepoints([base, mark])
    buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    cx0 = col * CW
    oy = CH - 170
    ox = cx0 + 300            # pen start (RTL: start right)
    draw.line([cx0, oy, cx0 + CW, oy], fill=(150, 150, 220))   # baseline
    penx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        g = face.glyph
        bmp = g.bitmap
        gx = int(ox + (penx + pos.x_offset) * sc + g.bitmap_left)
        gy = int(oy - (pos.y_offset) * sc - g.bitmap_top)
        if bmp.width and bmp.rows:
            ink = Image.frombytes("L", (bmp.width, bmp.rows), bytes(bmp.buffer))
            sheet.paste((20, 20, 20), (gx, gy), ink)
        penx += pos.x_advance
    draw.text((cx0 + 16, 14), "U+%04X + U+%04X" % (base, mark), fill="black", font=lab)

sheet.save(OUT)
print("wrote", OUT)
