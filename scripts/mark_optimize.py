"""Measure optimal Arabic mark (above/below) anchor heights per base from the
base's actual ink profile in the band under the mark.

For each base: render it, find the highest ink within the fatha footprint band
(for the top mark) and the lowest ink within the kasra footprint band (bottom
mark), then report current anchor clearance vs an ink-hugging target.
"""
import re, sys
import freetype
from fontTools.ttLib import TTFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
GAP = 110  # desired clearance between base ink and mark, font units

# fatha (top) footprint relative to its anchor, and kasra (bottom) footprint.
# markClass anchors: fatha (114,0) ink x[0,537]; kasra (114,0) ink x[0,537].
TOP_BAND = (-114, 423)      # x offset range around TX covered by fatha ink
BOT_BAND = (-114, 423)      # x offset range around BX covered by kasra ink

REPS = {
    "clear-top shosha":        ["uni0628", "uni0633", "uni067E", "uniFECC", "uniFEB4", "uniFE92"],
    "high ascender":           ["uni0627", "uniFE8E", "uni0644", "uniFEDE", "uni06AF", "uni0643", "uniFEDB"],
    "low descender":           ["uni0648", "uni0631", "uni064A", "uni0632", "uni0646", "uni0642"],
    "ascender + low section":  ["uni0637", "uni0638"],
}

fea = open(FEA).read()
rx = re.compile(r"pos base (\S+)\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                r"<anchor (-?\d+) (-?\d+)> mark \@b\.uni064D_1;", re.S)
ANC = {m.group(1): tuple(map(int, m.group(2, 3, 4, 5))) for m in rx.finditer(fea)}

tt = TTFont(TTF)
upm = tt["head"].unitsPerEm
order = tt.getGlyphOrder()
name2gid = {n: i for i, n in enumerate(order)}
face = freetype.Face(TTF)
PPEM = 1024
face.set_pixel_sizes(0, PPEM)
sc = PPEM / upm


def ink_extent_in_band(gname, x0u, x1u, want_top):
    """Return highest (want_top) or lowest ink y in font units within x band."""
    gid = name2gid[gname]
    face.load_glyph(gid, freetype.FT_LOAD_RENDER)
    g = face.glyph
    bm = g.bitmap
    if not (bm.width and bm.rows):
        return None
    import numpy as np
    arr = np.frombuffer(bytes(bm.buffer), dtype="uint8").reshape(bm.rows, bm.width) > 40
    # column c -> font x = (g.bitmap_left + c)/sc ; row r -> font y = (g.bitmap_top - r)/sc
    c0 = max(0, int(round(x0u * sc - g.bitmap_left)))
    c1 = min(bm.width, int(round(x1u * sc - g.bitmap_left)))
    if c1 <= c0:
        return None
    sub = arr[:, c0:c1]
    rows = np.where(sub.any(axis=1))[0]
    if len(rows) == 0:
        return None
    r = rows.min() if want_top else rows.max()
    return (g.bitmap_top - r) / sc


print(f"GAP target = {GAP}u.  Clearance = current anchor - base ink (top) / base ink - anchor (bottom).")
print(f"{'glyph':10} {'TY':>6}{'topInk':>8}{'clrT':>7}{'->TY*':>7}   {'BY':>7}{'botInk':>8}{'clrB':>7}{'->BY*':>7}")
for cls, glyphs in REPS.items():
    print(f"\n== {cls} ==")
    for gn in glyphs:
        if gn not in ANC:
            print(f"  {gn:10} (no anchor rule)"); continue
        TX, TY, BX, BY = ANC[gn]
        top = ink_extent_in_band(gn, TX + TOP_BAND[0], TX + TOP_BAND[1], True)
        bot = ink_extent_in_band(gn, BX + BOT_BAND[0], BX + BOT_BAND[1], False)
        tline = f"{TY:6}"
        if top is not None:
            clrT = TY - top
            optTY = round(top + GAP)
            tline += f"{round(top):8}{round(clrT):7}{optTY:7}"
        else:
            tline += f"{'-':>8}{'-':>7}{'-':>7}"
        bline = f"{BY:7}"
        if bot is not None:
            clrB = bot - BY
            optBY = round(bot - GAP)
            bline += f"{round(bot):8}{round(clrB):7}{optBY:7}"
        else:
            bline += f"{'-':>8}{'-':>7}{'-':>7}"
        print(f"  {gn:10} {tline}   {bline}")
