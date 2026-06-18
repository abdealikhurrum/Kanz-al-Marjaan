#!/usr/bin/env python3
"""Render the same Arabic/LD text runs with two font files and stack them
(OLD above NEW per run) into a single comparison image.

  python scripts/compare_versions.py --old /tmp/old.ttf --new /tmp/new.ttf \
      --out out/version_compare.png
"""
import argparse
import uharfbuzz as hb
import freetype
from PIL import Image, ImageDraw, ImageFont

GREY = (140, 140, 140)
INK = (20, 20, 20)
LBL = (170, 60, 60)


class Renderer:
    def __init__(self, path):
        data = open(path, "rb").read()
        self.hb = hb.Font(hb.Face(data))
        self.face = freetype.Face(path)
        self.upm = self.face.units_per_EM

    def draw(self, img, s, x_right, baseline, ppem, lang=None, color=INK):
        sc = ppem / self.upm
        self.face.set_pixel_sizes(0, ppem)
        buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
        if lang:
            buf.language = lang
        hb.shape(self.hb, buf)
        tot = sum(p.x_advance for p in buf.glyph_positions) * sc
        penx = x_right - tot
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            self.face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
            g = self.face.glyph; bm = g.bitmap
            if bm.width and bm.rows:
                ink = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
                img.paste(Image.new("RGB", ink.size, color),
                          (int(penx + pos.x_offset * sc + g.bitmap_left),
                           int(baseline - pos.y_offset * sc - g.bitmap_top)), ink)
            penx += pos.x_advance * sc
        return tot


# label, text, lang, ppem — runs chosen to exercise the changed glyphs
RUNS = [
    ("Bismillah", "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ", None, 86),
    ("Fatiha", "الْحَمْدُ لِلَّهِ رَبِّ الْعالَمِينَ", None, 86),
    ("seen / sheen teeth", "السِّين والشِّين تتكرّر", None, 80),
    ("kaf / gaf / lam", "الكَلِمات كُلّها جميلة", None, 80),
    ("waw / meem-jeem", "ومجموعة الحُروف المُتّصلة", None, 80),
    ("body text", "يولد جميع الناس أحرارًا متساوين في الكرامة والحقوق", None, 60),
    ("digits ٠-٩", "٠١٢٣٤٥٦٧٨٩", None, 90),
    ("Lisan al-Dawat", "چھے گھر ٹھيك ڈاڑھي", "gu", 84),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="/tmp/old.ttf")
    ap.add_argument("--new", default="/tmp/new.ttf")
    ap.add_argument("--out", default="out/version_compare.png")
    A = ap.parse_args()
    old = Renderer(A.old)
    new = Renderer(A.new)

    W = 1600
    R = W - 60
    pad_top = 70
    row_h = lambda ppem: int(ppem * 1.5)
    # precompute layout
    y = pad_top
    blocks = []
    for label, s, lang, ppem in RUNS:
        h = row_h(ppem)
        blocks.append((label, s, lang, ppem, y, h))
        y += 2 * h + 46          # OLD line + NEW line + gap
    H = y + 30

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        f_hdr = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
        f_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    except Exception:
        f_hdr = f_sm = ImageFont.load_default()
    d.text((60, 24), "Kanz al-Marjaan — outline cleanup:  OLD (top, grey)  vs  NEW (bottom, black)",
           fill=INK, font=f_hdr)

    for label, s, lang, ppem, y0, h in blocks:
        # left caption
        d.text((60, y0 + h - 14), label, fill=LBL, font=f_sm)
        # OLD on first baseline (grey), NEW on second (black)
        base_old = y0 + h - 18
        base_new = y0 + 2 * h - 12
        d.text((60, base_old - 6), "old", fill=GREY, font=f_sm)
        d.text((60, base_new - 6), "new", fill=(60, 120, 60), font=f_sm)
        old.draw(img, s, R, base_old, ppem, lang=lang, color=(120, 120, 120))
        new.draw(img, s, R, base_new, ppem, lang=lang, color=INK)
        d.line([(60, y0 + 2 * h + 16), (R, y0 + 2 * h + 16)], fill=(230, 230, 230))

    img.save(A.out)
    print("wrote", A.out, img.size)


if __name__ == "__main__":
    main()
