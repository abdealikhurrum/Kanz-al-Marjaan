"""Spot-check sheet for mark-to-ligature: render each sampled ligature glyph
directly and place a fatha (top) + kasra (bottom) at every component anchor
parsed from the pos ligature rules in features.fea.  No shaping needed, so it
works for every ligature regardless of context-form triggering.

Usage: python3 scripts/spotcheck_ligatures.py [out.png] [stride]
"""
import os, re, sys
import freetype
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

TTF = os.environ.get("SPOT_TTF", "/tmp/_kam_roll.ttf")
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/spotcheck.png"
STRIDE = int(sys.argv[2]) if len(sys.argv) > 2 else 28   # sample every Nth ligature
PPEM = 150
FATHA, KASRA = 0x064E, 0x0650
MARK_T_DX, MARK_B_DX = 239, 239   # markClass x-anchor for @t / @b

face = freetype.Face(TTF); face.set_pixel_sizes(0, PPEM); sc = PPEM / face.units_per_EM
tt = TTFont(TTF); order = tt.getGlyphOrder(); cmap = tt.getBestCmap()
fatha_gid, kasra_gid = order.index(cmap[FATHA]), order.index(cmap[KASRA])
fea = open("sources/KanzAlMarjaan-Regular.ufo/features.fea").read()

# parse pos ligature blocks -> {glyph: [(t_x,t_y,b_x,b_y) per component]}
ligs = {}
for m in re.finditer(r"pos ligature (\S+)\s*(.*?);", fea, re.S):
    g = m.group(1); body = m.group(2)
    anc = re.findall(r"<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*<anchor (-?\d+) (-?\d+)> mark \@b", body)
    if anc: ligs[g] = [tuple(map(int, a)) for a in anc]
names = sorted(ligs)
sample = names[::STRIDE]
print("total ligatures parsed:", len(names), "| sampling", len(sample))

def glyph_img(gid):
    face.load_glyph(gid, freetype.FT_LOAD_RENDER); bm = face.glyph.bitmap
    g = face.glyph
    if not (bm.width and bm.rows): return None, 0, 0
    return Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer)), g.bitmap_left, g.bitmap_top

CW, CH, COLS = 320, 320, 6
rows = (len(sample) + COLS - 1) // COLS
W, H = COLS * CW, rows * CH
sheet = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(sheet)
try: fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
except Exception: fnt = ImageFont.load_default()

def place(cell, gid, ox, oy, fontx, fonty):
    img, bl, bt = glyph_img(gid)
    if img is None: return
    px = int(ox + fontx * sc + bl); py = int(oy - fonty * sc - bt)
    cell.paste((20, 20, 20), (px, py), img)

for i, g in enumerate(sample):
    r, c = divmod(i, COLS); cx0, cy0 = c * CW, r * CH
    d.rectangle([cx0, cy0, cx0 + CW - 1, cy0 + CH - 1], outline=(220, 220, 220))
    oy = cy0 + CH - 120; baseline_y = oy
    d.line([cx0, baseline_y, cx0 + CW, baseline_y], fill=(150, 150, 220))
    gid = order.index(g)
    bg, bl, bt = glyph_img(gid)
    if bg is None: continue
    # centre glyph in cell
    gw = bg.width; gx0 = cx0 + (CW - gw) // 2 - bl
    ox = gx0
    cell = sheet.crop((cx0, cy0, cx0 + CW, cy0 + CH))
    lx = gx0 - cx0
    cell.paste((20, 20, 20), (lx + bl, int((oy - bt)) - cy0), bg)
    # marks at each component anchor
    for (tx, ty, bx, by) in ligs[g]:
        for gid_m, ax, ay, dx in ((fatha_gid, tx, ty, MARK_T_DX), (kasra_gid, bx, by, MARK_B_DX)):
            mi, mbl, mbt = glyph_img(gid_m)
            if mi is None: continue
            px = int((ox - cx0) + (ax - dx) * sc + mbl); py = int((oy - cy0) - ay * sc - mbt)
            cell.paste((200, 30, 30), (px, py), mi)
    sheet.paste(cell, (cx0, cy0))
    d.text((cx0 + 4, cy0 + 3), "%s  (%dc)" % (g[:34], len(ligs[g])), fill="black", font=fnt)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
sheet.save(OUT)
print("wrote", OUT, "(%dx%d)" % (W, H))
