"""Compare KanzAlMarjaan Latin glyphs against reference fonts at matched
cap-height, side by side, to identify the source typeface.
"""
import freetype
from PIL import Image, ImageDraw, ImageFont

FONTS = [
    ("KanzAlMarjaan", "fonts/ttf/KanzAlMarjaan-Regular.ttf"),
    ("Arial",         "/System/Library/Fonts/Supplemental/Arial.ttf"),
    ("Helvetica",     "/System/Library/Fonts/Helvetica.ttc"),
]
GLYPHS = "agReQtS1"
TARGET_CAP = 150          # px; every font scaled so cap-height == this

faces = []
for name, path in FONTS:
    f = freetype.Face(path)
    # measure cap height from 'H' in font units
    f.load_char("H", freetype.FT_LOAD_NO_SCALE)
    caph = f.glyph.outline.get_bbox().yMax or f.units_per_EM
    faces.append((name, f, caph))

cell = 200
sheet = Image.new("RGB", (cell * len(GLYPHS), cell * len(FONTS) + 40), "white")
draw = ImageDraw.Draw(sheet)
try:
    lab = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
except Exception:
    lab = ImageFont.load_default()

for row, (name, face, caph) in enumerate(faces):
    ppem = int(TARGET_CAP * (face.units_per_EM / caph))
    face.set_pixel_sizes(0, ppem)
    sc = ppem / face.units_per_EM
    draw.text((8, 40 + row * cell + 6), name, fill="black", font=lab)
    for col, ch in enumerate(GLYPHS):
        gid = face.get_char_index(ord(ch))
        if gid == 0:
            continue
        face.load_glyph(gid, freetype.FT_LOAD_RENDER)
        g = face.glyph
        bmp = g.bitmap
        baseline = 40 + row * cell + 175
        ox = col * cell + 60
        if bmp.width and bmp.rows:
            ink = Image.frombytes("L", (bmp.width, bmp.rows), bytes(bmp.buffer))
            sheet.paste((20, 20, 20),
                        (int(ox + g.bitmap_left), int(baseline - g.bitmap_top)), ink)
        if row == 0:
            draw.text((ox, 8), ch, fill=(120, 120, 120), font=lab)

sheet.save("out/8_latin_compare.png")
print("wrote out/8_latin_compare.png")
