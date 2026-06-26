"""Roll out per-component mark-to-ligature to all in-scope multi-component
ligatures.

In-scope = mark-bearing glyphs (have a pos base @t/@b) that are formed by a GSUB
ligature substitution of >=2 inputs, excluding the Allah special case.
For each, place per-component anchors: equal x-spacing (RTL) + per-component
natural height (clear each component's local ink + gap).  Rewrites the
mark_lig_arab lookup body and sets GDEF ligature class via openTypeCategories.

Allah (uni064406440647.isol) is preserved as a hand-tuned special case.
MHMD.liga comp3 keeps the user's manual raise.

Usage: python3 scripts/rollout_mark_to_ligature.py [--apply]   (default: report)
"""
import os, re, sys
import numpy as np, freetype
from fontTools.ttLib import TTFont

TTF = os.environ.get("ROLLOUT_TTF", "/tmp/_kam_lig.ttf")
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
LIB = "sources/KanzAlMarjaan-Regular.ufo/lib.plist"
APPLY = "--apply" in sys.argv
TOPGAP, BOTGAP = 180, 120
ALLAH_TARGET = "uni064406440647.isol"

face = freetype.Face(TTF); P = 256; face.set_pixel_sizes(0, P); scm = P / face.units_per_EM
tt = TTFont(TTF); order = tt.getGlyphOrder()
fea = open(FEA).read()

# --- enumerate in-scope ---
markbearing = set(re.findall(r"pos base (\S+)\s*<anchor -?\d+ -?\d+> mark \@t\.uni064B", fea))
ligcount = {}
for m in re.finditer(r"^\s*sub ((?:\S+ )+?)by (\S+);", fea, re.M):
    inp = m.group(1).split(); g = m.group(2)
    if len(inp) >= 2 and not any("'" in t for t in inp):
        ligcount[g] = max(ligcount.get(g, 0), len(inp))
EXCLUDE = {ALLAH_TARGET, "uniFDF2"}
inscope = {g: ligcount[g] for g in markbearing if g in ligcount and ligcount[g] >= 2 and g not in EXCLUDE}

def raster(g):
    face.load_glyph(order.index(g), freetype.FT_LOAD_RENDER); bm = face.glyph.bitmap
    if not (bm.width and bm.rows): return None
    arr = np.frombuffer(bytes(bm.buffer), np.uint8).reshape(bm.rows, bm.width)
    ys, xs = np.where(arr > 40)
    fx = (face.glyph.bitmap_left + xs) / scm
    fy = (face.glyph.bitmap_top - ys) / scm
    return fx, fy

TOPCOMPRESS = 0.35   # top marks: keep this fraction of natural height variation (pull up toward highest)
BOTCOMPRESS = 0.50   # bottom marks: own compression, pull DOWN toward deepest so a kasra never
                     # sits between the rasm and its lower nuqta (eraab stays below the nuqta)

def anchors(g, N):
    r = raster(g)
    if r is None: return None
    fx, fy = r; xmin, xmax = fx.min(), fx.max(); w = xmax - xmin
    bands = []
    for k in range(1, N + 1):
        cx = xmax - (k - 0.5) / N * w; half = w / (2 * N)
        m = (fx >= cx - half) & (fx < cx + half)
        if m.sum() < 5: m = (fx >= cx - w / N) & (fx < cx + w / N)
        if m.sum() < 1: top, bot = fy.max(), fy.min()
        else: top, bot = fy[m].max(), fy[m].min()
        bands.append((cx, top, bot))
    gtop = max(b[1] for b in bands)         # highest component top
    gbot = min(b[2] for b in bands)         # deepest component bottom
    rows = []
    for cx, top, bot in bands:
        cy_top = round(gtop - (gtop - top) * TOPCOMPRESS + TOPGAP)   # above each comp's top ink (incl upper nuqta)
        cy_bot = round(gbot + (bot - gbot) * BOTCOMPRESS - BOTGAP)   # below each comp's bottom ink (incl lower nuqta)
        rows.append((round(cx), cy_top, cy_bot))
    return rows

def block(g, rows):
    out = [f"  pos ligature {g}"]
    for i, (x, ty, by) in enumerate(rows):
        lead = "" if i == 0 else "    ligComponent\n"
        out.append(f"{lead}      <anchor {x} {ty}> mark @t.uni064B\n      <anchor {x} {by}> mark @b.uni064D_1")
    return "\n".join(out) + ";"

# preserve the existing Allah pos ligature block verbatim
mall = re.search(r"(  pos ligature %s.*?;)" % re.escape(ALLAH_TARGET), fea, re.S)
allah_block = mall.group(1)

blocks = [allah_block]; gen = 0; skipped = []
for g in sorted(inscope):
    rows = anchors(g, inscope[g])
    if rows is None: skipped.append(g); continue
    if g == "MHMD.liga" and len(rows) >= 3: rows[2] = (rows[2][0], 1480, rows[2][2])  # shadda+fatha sits highest
    blocks.append(block(g, rows)); gen += 1

new_lookup = "lookup mark_lig_arab {\n" + "\n\n".join(blocks) + "\n} mark_lig_arab;"
print("in-scope %d | generated %d | skipped(no ink) %d" % (len(inscope), gen, len(skipped)))
if skipped: print("  skipped:", skipped[:10])

if APPLY:
    new_fea = re.sub(r"lookup mark_lig_arab \{.*?\} mark_lig_arab;", lambda _: new_lookup, fea, flags=re.S)
    open(FEA, "w").write(new_fea)
    import plistlib
    d = plistlib.load(open(LIB, "rb")); cats = d["public.openTypeCategories"]
    for g in list(inscope) + [ALLAH_TARGET]: cats[g] = "ligature"
    plistlib.dump(d, open(LIB, "wb"))
    print("APPLIED: %d ligature blocks, %d glyphs classed ligature" % (gen + 1, sum(v == "ligature" for v in cats.values())))
