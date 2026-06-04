"""One-off: minimise Latin cmap + add GF_Latin_Kernel / GF_Arabic_Core glyphs.

Run inside the build venv:  python3 scripts/add_gf_glyphs.py
Idempotent-ish: re-creating an existing glyph just overwrites it.
"""
import defcon

UFO = "sources/KanzAlMarjaan-Regular.ufo"
f = defcon.Font(UFO)

# ---------------------------------------------------------------- 1. unmap
# Remove Latin codepoints that are NOT in GF_Latin_Kernel (the minimal set an
# Arabic-primary family must ship). Glyphs are kept (features may use them),
# only their cmap entry is dropped.  0x00D0 ETH fixes case_mapping; 0x00AD
# soft-hyphen fixes the soft_hyphen warning.
# NB: guillemets (00AB/00BB) are kept — GF_Arabic_Core requires them.
REMOVE = {0x00A6, 0x00A7, 0x00A8, 0x00AD, 0x00B2, 0x00B3,
          0x00B4, 0x00B6, 0x00BC, 0x00BD, 0x00BE, 0x00D0}
for g in f:
    keep = [u for u in g.unicodes if u not in REMOVE]
    if keep != list(g.unicodes):
        g.unicodes = keep

def bounds(name):
    return f[name].bounds  # (xMin, yMin, xMax, yMax)

def make(name, unicode=None, width=0, components=(), contours=()):
    if name in f:
        del f[name]
    g = f.newGlyph(name)
    g.width = width
    if unicode is not None:
        g.unicode = unicode
    for base, dx, dy in components:
        g.appendComponent(_component(base, dx, dy))
    for pts in contours:
        _rect(g, *pts)
    return g

def _component(base, dx, dy):
    from defcon import Component
    c = Component()
    c.baseGlyph = base
    c.move((dx, dy))
    return c

def _rect(g, x0, y0, x1, y1):
    pen = g.getPen()
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0))
    pen.lineTo((x1, y1)); pen.lineTo((x0, y1))
    pen.closePath()

# ---------------------------------------------------------------- 2. Latin
# middle dot -> reuse the existing centred period
if "periodcentred" in f and 0x00B7 not in {u for gg in f for u in gg.unicodes}:
    f["periodcentred"].unicode = 0x00B7

# degree -> the cap ring
make("degree", 0x00B0, width=f["ring.cap"].width, components=[("ring.cap", 0, 0)])

# cent -> c with a vertical bar through it
cx0, cy0, cx1, cy1 = bounds("c")
barx = (cx0 + cx1) / 2
make("cent", 0x00A2, width=f["c"].width,
     components=[("c", 0, 0)],
     contours=[(barx - 28, cy0 - 110, barx + 28, cy1 + 110)])

# yen -> capital Y with two horizontal bars
yx0, yy0, yx1, yy1 = bounds("Y")
ymid = (yy0 + yy1) / 2
make("yen", 0x00A5, width=f["Y"].width,
     components=[("Y", 0, 0)],
     contours=[(yx0 + 40, ymid - 30, yx1 - 40, ymid + 30),
               (yx0 + 40, ymid - 170, yx1 - 40, ymid - 110)])

# pound -> capital L with a crossbar (simple, recognisable sterling)
lx0, ly0, lx1, ly1 = bounds("L")
make("sterling", 0x00A3, width=f["L"].width,
     components=[("L", 0, 0)],
     contours=[(lx0 - 10, (ly0 + ly1) / 2 - 30, lx0 + 360, (ly0 + ly1) / 2 + 30)])

# ---------------------------------------------------------------- 3. Arabic
# dotless beh / qaf -> existing isolated skeletons
make("uni066E", 0x066E, width=f["base.behisol"].width, components=[("base.behisol", 0, 0)])
make("uni066F", 0x066F, width=f["base.qafisol"].width, components=[("base.qafisol", 0, 0)])

# jeh  = reh + three dots above
make("uni0698", 0x0698, width=f["uni0631"].width,
     components=[("uni0631", 0, 0), ("dot.threeup", 0, 560)])

# keheh with three dots above = keheh + three dots above
kx0, ky0, kx1, ky1 = bounds("uni06A9")
make("uni0763", 0x0763, width=f["uni06A9"].width,
     components=[("uni06A9", 0, 0), ("dot.threeup", (kx0 + kx1) / 2 - 180, ky1 - 380)])

# Arabic per-mille -> reuse Latin per-thousand shape
make("uni0609", 0x0609, width=f["perthousand"].width, components=[("perthousand", 0, 0)])

# Arabic date separator -> small comma-like
make("uni060D", 0x060D, width=f["comma"].width, components=[("comma", 0, 0)])

# combining marks (zero advance; GPOS anchoring left for a designer pass)
# small high tah -> a small ta-like stroke reusing a dot cluster
make("uni0615", 0x0615, width=0, components=[("dot.one", 0, 700)])
# subscript alef -> superscript alef moved below the baseline
make("uni0656", 0x0656, width=0, components=[("uni0670", 0, -900)])
# noon ghunna mark -> small dot above
make("uni0658", 0x0658, width=0, components=[("dot.one", 0, 760)])

f.save()
print("done: added/updated glyphs; saved", UFO)
