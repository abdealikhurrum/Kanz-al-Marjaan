"""Design + preview a sterling (pound) glyph as explicit contours, then
optionally write it into the UFO.  Preview is drawn straight from the same
coordinates, so no font build is needed to iterate.

  python3 scripts/sterling_design.py preview   -> writes out/sterling_preview.png
  python3 scripts/sterling_design.py write      -> writes the glyph into the UFO
"""
import sys
from PIL import Image, ImageDraw

# Pound sign, drawn for UPM 2048, cap-height ~1025, baseline y=0.
# Built from filled rectangles (foot, stem, crossbar) plus a curved hook band
# at the top.  All contours wound the same way so they union under nonzero fill.
T = 150  # stroke weight

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

# hook band: stem rises, curves up-left to a peak, opens to the upper right
HOOK = [
    (210, 560), (210, 820),                     # outer left, rising
    (250, 960), (370, 1035), (520, 1010),       # over the top
    (610, 945),                                  # outer right tip
    (560, 850),                                  # inner right tip
    (470, 905), (380, 880), (330, 800),          # back under the arc
    (350, 560),                                  # inner left, down to stem
]

CONTOURS = [
    rect(40, 0, 705, 165),       # foot / base bar
    rect(210, 120, 350, 640),    # stem
    rect(150, 470, 560, 600),    # crossbar
    HOOK,
]
WIDTH = 760

def preview():
    upm = 2048
    sc = 0.22
    W, H = int(900), int(2400 * sc)
    img = Image.new("RGB", (W, 560), "white")
    d = ImageDraw.Draw(img)
    base = 470            # baseline y in px
    ox = 120
    # guides
    d.line([0, base, W, base], fill=(150, 150, 220))                 # baseline
    d.line([ox, base - 1025 * sc, W, base - 1025 * sc], fill=(230, 200, 200))  # cap height
    d.line([ox + WIDTH * sc, 40, ox + WIDTH * sc, 520], fill=(120, 200, 120))  # advance
    for c in CONTOURS:
        pts = [(ox + x * sc, base - y * sc) for (x, y) in c]
        d.polygon(pts, fill=(20, 20, 20))
    img.save("out/sterling_preview.png")
    print("wrote out/sterling_preview.png")

def write():
    import defcon
    f = defcon.Font("sources/KanzAlMarjaan-Regular.ufo")
    if "sterling" in f:
        del f["sterling"]
    g = f.newGlyph("sterling")
    g.unicode = 0x00A3
    g.width = WIDTH
    pen = g.getPen()
    for c in CONTOURS:
        pen.moveTo(c[0])
        for p in c[1:]:
            pen.lineTo(p)
        pen.closePath()
    f.save()
    print("wrote sterling into UFO")

(preview if sys.argv[1:] == ["preview"] else write)()
