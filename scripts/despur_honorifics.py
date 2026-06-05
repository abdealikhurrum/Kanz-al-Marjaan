"""De-spur the emboldened honorific glyphs (tahain.honorific, sadain.honorific).

These were built by an 8-way pathops offset-union which left the boundary
massively over-noded (~1000+ pts / 2 contours) with hairline spurs on the
ain tails and sad/toi heads (fontbakery outline_jaggy_segments WARN).

Approach (curve-shape preserved, spurs removed):
  1. Flatten each UFO contour (cubic) to a fine polyline.
  2. Build a shapely (multi)polygon respecting holes via containment.
  3. Morphological OPEN (buffer -r then +r, round joins) erases hairline
     spurs without touching the thick bold strokes.
  4. Douglas-Peucker simplify(tol) to drop the redundant union nodes.
  5. Redraw as clean straight-segment contours (these are tiny superscript
     marks; a <=tol-unit facet on a 2048 UPM glyph is sub-perceptual).

Usage:  python3 scripts/despur_honorifics.py [--r 2.5] [--tol 2.0] [--check]
"""
import argparse
import defcon
from fontTools.pens.recordingPen import RecordingPen
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

GLYPHS = ["tahain.honorific", "sadain.honorific"]
STEPS = 24  # cubic subdivision steps


def _cubic(p0, p1, p2, p3, n=STEPS):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t**3*p3[0]
        y = mt**3*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t**3*p3[1]
        out.append((x, y))
    return out


def flatten(glyph):
    """Return list of closed polylines (one per contour)."""
    rp = RecordingPen()
    glyph.draw(rp)
    rings = []
    cur = None
    for cmd, args in rp.value:
        if cmd == "moveTo":
            cur = [args[0]]
        elif cmd == "lineTo":
            cur.append(args[0])
        elif cmd == "curveTo":
            p0 = cur[-1]
            *offs, end = args
            if len(offs) == 2:
                cur.extend(_cubic(p0, offs[0], offs[1], end))
            else:                       # qcurve / single offcurve fallback
                cur.append(end)
        elif cmd == "qCurveTo":
            p0 = cur[-1]
            pts = list(args)
            end = pts[-1]
            cur.append(end)
        elif cmd == "closePath":
            if cur and len(cur) >= 3:
                rings.append(cur)
            cur = None
    return rings


def build_polygon(rings):
    polys = [Polygon(r) for r in rings if len(r) >= 3]
    polys = [p.buffer(0) for p in polys]               # validate
    # nesting: a ring inside another is a hole
    shells, holes = [], []
    for i, p in enumerate(polys):
        inside = any(j != i and polys[j].contains(p.representative_point())
                     for j in range(len(polys)))
        (holes if inside else shells).append(p)
    geom = unary_union(shells)
    for h in holes:
        geom = geom.difference(h)
    return geom


def despur(geom, r, tol):
    g = geom.buffer(-r, join_style=1, resolution=16)   # open: erase spurs
    g = g.buffer(r, join_style=1, resolution=16)
    g = g.simplify(tol, preserve_topology=True)
    return g


def redraw(glyph, geom):
    width = glyph.width
    glyph.clearContours()
    pen = glyph.getPen()
    parts = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    for poly in parts:
        for ring in [poly.exterior, *poly.interiors]:
            coords = list(ring.coords)[:-1]            # drop closing dup
            if len(coords) < 3:
                continue
            pen.moveTo(coords[0])
            for c in coords[1:]:
                pen.lineTo(c)
            pen.closePath()
    glyph.width = width


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=float, default=2.5)
    ap.add_argument("--tol", type=float, default=2.0)
    ap.add_argument("--ufo", default="sources/KanzAlMarjaan-Regular.ufo")
    ap.add_argument("--check", action="store_true", help="report only, no save")
    A = ap.parse_args()
    f = defcon.Font(A.ufo)
    for nm in GLYPHS:
        g = f[nm]
        before = sum(len(c) for c in g)
        rings = flatten(g)
        geom = despur(build_polygon(rings), A.r, A.tol)
        if A.check:
            # count points without mutating
            n = 0
            parts = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
            for poly in parts:
                for ring in [poly.exterior, *poly.interiors]:
                    n += len(ring.coords) - 1
            print(f"{nm}: {before} -> {n} pts  (area={geom.area:.0f})")
            continue
        redraw(g, geom)
        after = sum(len(c) for c in g)
        print(f"{nm}: {before} -> {after} pts")
    if not A.check:
        f.save()
        print("saved", A.ufo)


if __name__ == "__main__":
    main()
