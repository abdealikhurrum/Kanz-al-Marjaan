"""Render a contact sheet of selected glyphs from the built TTF, with the
em-box, baseline and advance-width drawn so over-sizing / overhang is visible.
"""
import sys
import freetype
from PIL import Image, ImageDraw, ImageFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
OUT = sys.argv[2] if len(sys.argv) > 2 else "out/preview.png"
NAMES = sys.argv[1].split(",")

face = freetype.Face(TTF)
upm = face.units_per_EM
PPEM = 240                      # pixels per em -> common scale for every glyph
scale = PPEM / upm
face.set_pixel_sizes(0, PPEM)

# cell geometry (pixels)
CW, CH = 470, 520
PAD = 22
baseline_y = CH - 180           # where y=0 sits inside the cell
origin_x = 130                  # where pen x=0 sits inside the cell
cols = 3
rows = (len(NAMES) + cols - 1) // cols
sheet = Image.new("RGB", (cols * CW, rows * CH), "white")
draw = ImageDraw.Draw(sheet)
try:
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
except Exception:
    lab = small = ImageFont.load_default()

asc_px = face.ascender * scale
desc_px = face.descender * scale

for i, name in enumerate(NAMES):
    cx = (i % cols) * CW
    cy = (i // cols) * CH
    ox, oy = cx + origin_x, cy + baseline_y

    gid = face.get_name_index(name.encode())
    if gid == 0:
        draw.text((cx + PAD, cy + PAD), name + "  (missing)", fill="red", font=lab)
        continue
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    g = face.glyph
    adv_px = g.advance.x / 64.0

    # reference guides: em-box (0..upm), baseline, ascender/descender, advance
    draw.rectangle([ox, oy - PPEM, ox + PPEM, oy], outline=(210, 210, 210))      # em square
    draw.line([cx, oy, cx + CW, oy], fill=(150, 150, 220))                       # baseline
    draw.line([ox, oy - asc_px, ox + CW - origin_x, oy - asc_px], fill=(230, 200, 200))  # ascender
    draw.line([ox, oy - desc_px, ox + CW - origin_x, oy - desc_px], fill=(230, 200, 200))# descender
    draw.line([ox + adv_px, oy - PPEM - 40, ox + adv_px, oy + 60], fill=(120, 200, 120)) # advance

    bmp = g.bitmap
    if bmp.width and bmp.rows:
        # glyph bitmap, drawn relative to pen origin
        img = Image.frombytes("L", (bmp.width, bmp.rows), bytes(bmp.buffer))
        img = Image.eval(img, lambda v: 255 - v)            # ink = dark
        gx = int(ox + g.bitmap_left)
        gy = int(oy - g.bitmap_top)
        # paste with the grey ink as a mask
        ink = Image.frombytes("L", (bmp.width, bmp.rows), bytes(bmp.buffer))
        sheet.paste((20, 20, 20), (gx, gy), ink)

    overflow = ""
    if g.bitmap_top * 1 > asc_px + 4:
        overflow += " ↑above-asc"
    if (g.bitmap_left + bmp.width) > adv_px * 1.4:
        overflow += " →overhang"
    draw.text((cx + PAD, cy + 8), name, fill="black", font=lab)
    draw.text((cx + PAD, cy + 30), f"adv={int(adv_px)}px{overflow}",
              fill=(120, 120, 120), font=small)

sheet.save(OUT)
print("wrote", OUT, sheet.size)
