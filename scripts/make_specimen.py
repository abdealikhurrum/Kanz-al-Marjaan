"""Generate specimen / Google Fonts article images for an Arabic font.

Uses HarfBuzz (uharfbuzz) + FreeType so Arabic shapes and joins correctly
(DrawBot's default text path does not shape complex scripts reliably).

Outputs into documentation/:
  image1.png          GF article hero (2048x1024) — big Arabic display
  image2.png          GF article (2048x1024)      — Arabic text specimen
  specimen.png        full specimen (title, Fatiha, body, LD letters)
  specimen-features.png  fixes & Lisan al-Dawat feature showcase

Usage:
  python3 scripts/make_specimen.py [--font fonts/ttf/KanzAlMarjaan-Regular.ttf]
"""
import argparse
import uharfbuzz as hb
import freetype
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("--font", default="fonts/ttf/KanzAlMarjaan-Regular.ttf")
ap.add_argument("--outdir", default="documentation")
A = ap.parse_args()

DATA = open(A.font, "rb").read()
HB = hb.Font(hb.Face(DATA))
FACE = freetype.Face(A.font)
UPM = FACE.units_per_EM
INK = (20, 20, 20)
GREY = (150, 150, 150)


def text(img, s, x_right, baseline, ppem, lang=None, color=INK):
    """Draw RTL string right-aligned at x_right on the given baseline. Returns width(px)."""
    sc = ppem / UPM
    FACE.set_pixel_sizes(0, ppem)
    buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
    if lang:
        buf.language = lang
    hb.shape(HB, buf)
    tot = sum(p.x_advance for p in buf.glyph_positions) * sc
    penx = x_right - tot
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        FACE.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        g = FACE.glyph; bm = g.bitmap
        if bm.width and bm.rows:
            ink = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
            img.paste(Image.new("RGB", ink.size, color),
                      (int(penx + pos.x_offset * sc + g.bitmap_left),
                       int(baseline - pos.y_offset * sc - g.bitmap_top)), ink)
        penx += pos.x_advance * sc
    return tot


def save(img, name):
    path = "%s/%s" % (A.outdir, name)
    img.save(path); print("wrote", path, img.size)


# ---- image1.png : Arabic hero (2048x1024) -----------------------------------
def image1():
    W, H = 2048, 1024
    img = Image.new("RGB", (W, H), "white")
    R = W - 150
    text(img, "كَنْز المَرْجان", R, 480, 330)                       # display title
    text(img, "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ", R, 720, 150)   # vocalized line
    d = ImageDraw.Draw(img)
    d.text((150, H - 70), "Kanz al Marjaan  ·  Naskh Arabic  ·  OFL", fill=GREY)
    save(img, "image1.png")


# ---- image2.png : Arabic text specimen (2048x1024) --------------------------
def image2():
    W, H = 2048, 1024
    img = Image.new("RGB", (W, H), "white")
    R = W - 150
    text(img, "الْحَمْدُ لِلَّهِ رَبِّ الْعالَمِينَ", R, 230, 132)
    body = ["يولد جميع الناس أحرارًا متساوين في الكرامة والحقوق،",
            "وقد وهبوا عقلًا وضميرًا وعليهم أن يعامل بعضهم بعضًا",
            "بروح الإخاء. واللغة العربية من أكثر اللغات انتشارًا."]
    y = 430
    for ln in body:
        text(img, ln, R, y, 74); y += 132
    d = ImageDraw.Draw(img)
    d.line([(150, 860), (R, 860)], fill=(225, 225, 225))
    d.text((150, 885), "Lisan al-Dawat (Gujarati)", fill=GREY)
    text(img, "چھے گھر ٹھيك ڈاڑھي", R, 1000, 78, lang="gu")
    save(img, "image2.png")


# ---- specimen.png : full specimen --------------------------------------------
def specimen():
    W = 1400; img = Image.new("RGB", (W, 1180), "white"); d = ImageDraw.Draw(img); R = W - 90
    d.text((90, 40), "Kanz al Marjaan — Regular", fill=GREY)
    text(img, "كَنْز المَرْجان", R, 210, 150)
    text(img, "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ", R, 360, 108)
    text(img, "الْحَمْدُ لِلَّهِ رَبِّ الْعالَمِينَ ﴿الفاتحة﴾", R, 500, 84)
    d.line([(90, 560), (R, 560)], fill=(225, 225, 225))
    for i, ln in enumerate([
            "يولد جميع الناس أحرارًا متساوين في الكرامة والحقوق، وقد وهبوا",
            "عقلًا وضميرًا وعليهم أن يعامل بعضهم بعضًا بروح الإخاء.",
            "اللغة العربية من أكثر اللغات انتشارًا، ويتحدث بها مئات الملايين."]):
        text(img, ln, R, 660 + i * 92, 60)
    d.line([(90, 952), (R, 952)], fill=(225, 225, 225))
    d.text((90, 972), "Lisan al-Dawat letters (Gujarati)", fill=GREY)
    text(img, "چھے گھر ٹھيك ڈاڑھي", R, 1100, 84, lang="gu")
    save(img, "specimen.png")


# ---- specimen-features.png : fixes & LD feature showcase ---------------------
def features():
    W = 1400
    rows = [
        ("Allah ligature: no doubled diacritics", "بِسْمِ اللَّهِ", None),
        ("Non-joining spacing kerns", "الَّذِينَ   أَكْبَر", None),
        ("Spanning sign over number (safha, sanah)", "؃٢٣   ؁١٤٤٢", None),
        ("Honorific signs (U+0610, U+0613)", "محمدؐ   عليؓ", None),
        ("LD double-press input, Gujarati only", "سس  حح  ضض  كك", "gu"),
    ]
    Hh = 140; img = Image.new("RGB", (W, Hh * len(rows) + 60), "white"); d = ImageDraw.Draw(img); R = W - 70
    d.text((40, 22), "What changed: fixes and Lisan al-Dawat features", fill=(90, 90, 90))
    for i, (lbl, s, lang) in enumerate(rows):
        y = 70 + i * Hh
        d.text((40, y + 10), lbl, fill=GREY)
        text(img, s, R, y + 95, 76, lang=lang)
        d.line([(40, y + Hh - 12), (R, y + Hh - 12)], fill=(235, 235, 235))
    save(img, "specimen-features.png")


# ---- preview.png : black & white preview (both polarities) ------------------
def preview():
    W, H = 2048, 1024
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, H // 2, W, H], fill=INK)                    # bottom half black
    R = W - 150
    WHITE = (255, 255, 255)
    text(img, "كَنْز المَرْجان", R, 360, 280, color=INK)        # black on white (top)
    text(img, "كَنْز المَرْجان", R, 880, 280, color=WHITE)      # white on black (bottom)
    text(img, "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ", R, 470, 80, color=INK)
    text(img, "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ", R, 990, 80, color=WHITE)
    save(img, "preview.png")


if __name__ == "__main__":
    image1(); image2(); specimen(); features(); preview()
