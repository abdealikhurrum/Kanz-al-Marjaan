"""Annotation sheet for JOINED LETTERS: one representative per joining skeleton,
shown init / medi / fina (isol / - / fina for non-joiners), each with fatha
(top) + kasra (bottom).  Forms are elicited with a tatweel/kashida on the
joining side(s); marks are typed right after the letter so they attach to the
letter's positional glyph (whose pos base @t/@b anchors are the edit target).

Usage:  python3 scripts/joined_sheet.py [out/joined_sheet.png] [PPEM]
Env:    MARK_SHEET_TTF (default fonts/ttf/KanzAlMarjaan-Regular.ttf)
"""
import os, sys
import uharfbuzz as hb, freetype
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

TTF = os.environ.get("MARK_SHEET_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/joined_sheet.png"
PPEM = int(sys.argv[2]) if len(sys.argv) > 2 else 200
TOP, BOT, TAT = 0x064E, 0x0650, 0x0640

# (label, codepoint, joins_both_sides)
SHAPES = [
    ("tooth (beh)", 0x0628, True), ("bowl (hah)", 0x062D, True),
    ("seen", 0x0633, True), ("sad", 0x0635, True), ("tah", 0x0637, True),
    ("ain", 0x0639, True), ("feh", 0x0641, True), ("kaf", 0x0643, True),
    ("lam", 0x0644, True), ("meem", 0x0645, True), ("heh", 0x0647, True),
    ("noon", 0x0646, True),
    ("dal", 0x062F, False), ("reh", 0x0631, False),
    ("waw", 0x0648, False), ("alef", 0x0627, False),
]

def seqs(cp, joins):
    m = [TOP, BOT]
    if joins:
        return [("init", [cp] + m + [TAT]), ("medi", [TAT, cp] + m + [TAT]), ("fina", [TAT, cp] + m)]
    return [("isol", [cp] + m), ("—", None), ("fina", [TAT, cp] + m)]

data = open(TTF, "rb").read()
hbfont = hb.Font(hb.Face(data)); face = freetype.Face(TTF)
upm = face.units_per_EM; face.set_pixel_sizes(0, PPEM); sc = PPEM / upm
order = TTFont(TTF).getGlyphOrder()
try:
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
except Exception:
    small = lab = ImageFont.load_default()

CW, CH, HEADER = 300, 300, 56
COLS = 3
W = 150 + COLS * CW                 # left gutter for the skeleton label
H = HEADER + len(SHAPES) * CH
sheet = Image.new("RGB", (W, H), "white"); draw = ImageDraw.Draw(sheet)
draw.rectangle([0, 0, W, HEADER], fill=(245, 245, 250))
draw.text((16, 8), "Kanz al Marjaan — joined letters (init / medi / fina)", fill="black", font=lab)
draw.text((16, 32), "fatha (top) + kasra (bottom) per form.  grid=50px; 1px~%.1f units.  PPEM=%d"
          % (upm / PPEM, PPEM), fill=(90, 90, 90), font=small)
for j, h in enumerate(("init / isol", "medi", "fina")):
    draw.text((150 + j * CW + 8, 40), h, fill=(70, 70, 70), font=small)
GRID, GUIDE = (232, 232, 240), (150, 150, 220)

def shape_bitmaps(cps):
    buf = hb.Buffer(); buf.add_codepoints(cps); buf.guess_segment_properties(); hb.shape(hbfont, buf)
    gl = []; names = []; mnx = 1e9; mxx = -1e9; penx = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        names.append(order[info.codepoint])
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
        rx = (penx + pos.x_offset) * sc + g.bitmap_left; ry = -(pos.y_offset) * sc - g.bitmap_top
        if bm.width and bm.rows:
            gl.append((rx, ry, Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))))
            mnx = min(mnx, rx); mxx = max(mxx, rx + bm.width)
        penx += pos.x_advance
    return gl, (mnx, mxx), names

for i, (label, cp, joins) in enumerate(SHAPES):
    cy0 = HEADER + i * CH
    draw.text((10, cy0 + CH // 2 - 8), label, fill="black", font=small)
    for j, (form, cps) in enumerate(seqs(cp, joins)):
        cx0 = 150 + j * CW
        for gx in range(cx0, cx0 + CW, 50): draw.line([gx, cy0, gx, cy0 + CH], fill=GRID)
        for gy in range(cy0, cy0 + CH, 50): draw.line([cx0, gy, cx0 + CW, gy], fill=GRID)
        draw.rectangle([cx0, cy0, cx0 + CW - 1, cy0 + CH - 1], outline=(210, 210, 210))
        if cps is None:
            continue
        oy = cy0 + CH - 110
        draw.line([cx0, oy, cx0 + CW, oy], fill=GUIDE)
        gl, (mnx, mxx), names = shape_bitmaps(cps)
        ox = cx0 + CW / 2 - (mnx + mxx) / 2
        cell = sheet.crop((cx0, cy0, cx0 + CW, cy0 + CH))
        for rx, ry, ink in gl:
            cell.paste((20, 20, 20), (int(ox + rx) - cx0, int(oy + ry) - cy0), ink)
        sheet.paste(cell, (cx0, cy0))
        letterglyph = next((n for n in names if n not in ("uni064E", "uni0650", "uni0640")), "?")
        draw.text((cx0 + 6, cy0 + 4), "%s  %s" % (form, letterglyph), fill=(120, 120, 120), font=small)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
sheet.save(OUT)
print("wrote", OUT, "(%dx%d, %d shapes)" % (W, H, len(SHAPES)))
