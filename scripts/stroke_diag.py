#!/usr/bin/env python3
"""Phase 2 diagnostic (read-only): measure stroke widths across all glyphs by
opposite-edge ray casting, and report the consistency landscape.

At each sampled outline point we find the inward normal (into the ink) and cast
a ray to the nearest opposing edge; that distance is the local stroke width.
Per glyph we summarise the distribution; across the font we look at how much the
dominant stroke weight varies and flag outliers. Outputs a histogram + a heatmap
contact sheet. Nothing is modified.

  python scripts/stroke_diag.py [--src UFO] [--out out/stroke]
"""
import sys, os, argparse, math
from collections import defaultdict
import numpy as np
np.seterr(divide='ignore', invalid='ignore')
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curve_cleanup as cc
from curve_cleanup_run import _passthrough, _seg_path_points

SRC = "sources/KanzAlMarjaan-Regular.ufo"


def flatten_glyph(glyph, per_curve=10):
    """Return list of closed polylines (each a list of np pts) for contours."""
    polys = []
    for c in glyph:
        pts = [np.asarray(p, float) for p in _seg_path_points(_passthrough(c), per_curve)]
        if len(pts) >= 3:
            polys.append(pts)
    return polys


def segments_array(polys):
    A, B = [], []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            A.append(poly[i]); B.append(poly[(i + 1) % n])
    return np.array(A), np.array(B)


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def point_inside(p, A, B):
    """Even-odd test: ray +x from p, count edge crossings."""
    x, y = p
    ay = A[:, 1]; by = B[:, 1]
    ax = A[:, 0]; bx = B[:, 0]
    cond = ((ay > y) != (by > y))
    with np.errstate(divide='ignore', invalid='ignore'):
        xint = ax + (y - ay) / (by - ay) * (bx - ax)
    hits = cond & (xint > x)
    return (np.count_nonzero(hits) % 2) == 1


def ray_hit(o, d, A, B, min_s=1.0, max_s=2000.0):
    """Nearest intersection distance of ray o+s*d (s>min_s) with segments."""
    E = B - A
    den = _cross(d[0], d[1], E[:, 0], E[:, 1])
    ao = A - o
    with np.errstate(divide='ignore', invalid='ignore'):
        s = _cross(ao[:, 0], ao[:, 1], E[:, 0], E[:, 1]) / den
        u = _cross(ao[:, 0], ao[:, 1], d[0], d[1]) / den
    ok = np.isfinite(s) & (np.abs(den) > 1e-9) & (s > min_s) & (s < max_s) & (u >= 0) & (u <= 1)
    if not np.any(ok):
        return None
    return float(np.min(s[ok]))


def is_arabic_letter(glyph):
    """Arabic letterform: unencoded (ligature/positional form) or all codepoints
    in the Arabic range. Excludes Latin, Latin-1 symbols, general punctuation."""
    us = glyph.unicodes
    if not us:
        return True
    return all(u >= 0x600 and not (0x2000 <= u <= 0x206F) for u in us)


def sample_points_normals(polys, A, B, step=2):
    """Sample points along contours with inward (into-ink) unit normals."""
    P, N = [], []
    for poly in polys:
        n = len(poly)
        for i in range(0, n, step):
            p = poly[i]
            t = poly[(i + 1) % n] - poly[(i - 1) % n]
            L = math.hypot(*t)
            if L < 1e-6:
                continue
            nrm = np.array([-t[1] / L, t[0] / L])
            inward = nrm if point_inside(p + nrm * 2.0, A, B) else -nrm
            P.append(p); N.append(inward)
    return np.array(P), np.array(N)


def stroke_widths(P, N, anti=-0.55, max_w=400.0):
    """Width at each point = min distance to a point on the OPPOSITE edge: one
    that faces antiparallel (normal dot < anti) and lies inward. This measures
    the stroke, not the diameter across a counter/wide fill."""
    if len(P) < 2:
        return np.array([])
    widths = []
    for i in range(len(P)):
        diff = P - P[i]
        dist = np.hypot(diff[:, 0], diff[:, 1])
        facing = N @ N[i] < anti                      # opposite-facing edge
        inward = diff @ N[i] > 0                       # on the inward side
        ok = facing & inward & (dist > 1.0) & (dist < max_w)
        if np.any(ok):
            widths.append(float(np.min(dist[ok])))
    return np.array(widths)


def glyph_widths(glyph):
    polys = flatten_glyph(glyph)
    if not polys:
        return []
    A, B = segments_array(polys)
    P, N = sample_points_normals(polys, A, B, step=2)
    return list(stroke_widths(P, N))


def _width_color(w, target):
    """blue (thin) -> grey (on target) -> red (thick)."""
    r = w / target
    if r < 1:
        t = max(0.0, r)  # 0..1
        return (int(60 + 60 * t), int(90 + 80 * t), 220)
    t = min(1.0, (r - 1) / 1.0)
    return (220, int(150 - 110 * t), int(120 - 110 * t))


def render_heatmaps(font, per_glyph, target, outdir):
    """Draw representative glyphs with sample points colored by local stroke
    width (blue thin -> red thick), to visualize modulation/consistency."""
    want = ["uni0628", "uni0633", "uni0635", "uni0639", "uni0643",
            "uni0645", "uni0647", "uni0644", "uni0646", "uniFD0F", "uni0648", "uni062D"]
    want = [n for n in want if n in font and len(font[n]) > 0]
    if not want:
        return
    cell = 300; cols = 4; rows = (len(want) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell, rows * cell + 30), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except Exception:
        f = ImageFont.load_default()
    d.text((10, 8), f"Local stroke width  (blue=thin  grey=target {target:.0f}u  red=thick)",
           fill=(20, 20, 20), font=f)
    for k, name in enumerate(want):
        g = font[name]
        polys = flatten_glyph(g, 8)
        A, B = segments_array(polys)
        allp = [p for poly in polys for p in poly]
        xs = [p[0] for p in allp]; ys = [p[1] for p in allp]
        mnx, mny = min(xs), min(ys)
        w = max(max(xs) - mnx, 1); h = max(max(ys) - mny, 1)
        sc = (cell - 50) / max(w, h)
        ox = (k % cols) * cell + 25
        oy = (k // cols) * cell + 40
        def tx(p):
            return (ox + (p[0] - mnx) * sc, oy + (h - (p[1] - mny)) * sc)
        for poly in polys:
            d.line([tx(p) for p in poly] + [tx(poly[0])], fill=(210, 210, 210), width=1)
        P, N = sample_points_normals(polys, A, B, step=2)
        for i in range(len(P)):
            diff = P - P[i]
            dist = np.hypot(diff[:, 0], diff[:, 1])
            ok = (N @ N[i] < -0.55) & (diff @ N[i] > 0) & (dist > 1.0) & (dist < 400)
            if np.any(ok):
                x, y = tx(P[i])
                c = _width_color(float(np.min(dist[ok])), target)
                d.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=c)
        d.text((ox, oy - 16), name, fill=(90, 90, 90), font=f)
    img.save(os.path.join(outdir, "heatmap.png"))
    print(f"heatmap -> {outdir}/heatmap.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default="out/stroke")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    font = Font(args.src)

    per_glyph = {}
    for g in font:
        if len(g) == 0:
            continue
        bb = g.bounds  # (xmin,ymin,xmax,ymax)
        if not bb:
            continue
        height = bb[3] - bb[1]
        ws = glyph_widths(g)
        if len(ws) >= 4:
            arr = np.array(ws)
            # a letterform = Arabic block + reasonably tall (excludes tiny marks)
            letter = is_arabic_letter(g) and height >= 400
            per_glyph[g.name] = dict(
                med=float(np.median(arr)),
                thin=float(np.percentile(arr, 20)),
                thick=float(np.percentile(arr, 80)),
                n=len(ws), samples=arr, letter=letter, height=height)

    letters = {n: v for n, v in per_glyph.items() if v['letter']}
    thicks = np.array([v['thick'] for v in letters.values()])
    meds = np.array([v['med'] for v in letters.values()])
    font_med = float(np.median(meds))
    font_thick = float(np.median(thicks))
    print(f"glyphs measured: {len(per_glyph)}   Arabic letterforms: {len(letters)}")
    print(f"[letters] median stroke width: {font_med:.0f} u   "
          f"(IQR {np.percentile(meds,25):.0f}-{np.percentile(meds,75):.0f})")
    print(f"[letters] dominant 'thick' stroke (p80): {font_thick:.0f} u   "
          f"(IQR {np.percentile(thicks,25):.0f}-{np.percentile(thicks,75):.0f})")
    print(f"[letters] thick-stroke spread stdev/median = {thicks.std()/font_thick:.0%}")

    # outliers among letterforms only (thick stroke vs font thick)
    devs = [(n, v['thick'], (v['thick'] - font_thick) / font_thick)
            for n, v in letters.items()]
    heavy = sorted(devs, key=lambda x: -x[2])[:15]
    light = sorted(devs, key=lambda x: x[2])[:15]
    print("\nHEAVIEST letterform strokes (thick p80 vs font thick):")
    for n, m, dv in heavy:
        print(f"  {n:42s} {m:5.0f}u  {dv:+.0%}")
    print("\nLIGHTEST letterform strokes:")
    for n, m, dv in light:
        print(f"  {n:42s} {m:5.0f}u  {dv:+.0%}")

    # ---- heatmap contact sheet of representative letters ----
    render_heatmaps(font, per_glyph, font_thick, args.out)

    # ---- histogram image ----
    W, H = 1100, 460
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except Exception:
        f = ImageFont.load_default()
    lo, hi = 0, np.percentile(meds, 99)
    bins = 60
    hist, edges = np.histogram(meds, bins=bins, range=(lo, hi))
    bw = (W - 80) / bins
    mh = max(hist)
    for i, c in enumerate(hist):
        x = 60 + i * bw
        bh = (H - 80) * c / mh
        d.rectangle([x, H - 50 - bh, x + bw - 1, H - 50], fill=(70, 110, 200))
    # mark font median
    mx = 60 + (font_med - lo) / (hi - lo) * (W - 80)
    d.line([(mx, 20), (mx, H - 50)], fill=(210, 40, 40), width=2)
    d.text((mx + 4, 24), f"median {font_med:.0f}u", fill=(210, 40, 40), font=f)
    d.text((60, 6), "Per-glyph median stroke width (font units)", fill=(20, 20, 20), font=f)
    d.text((60, H - 44), f"{lo:.0f}", fill=(80, 80, 80), font=f)
    d.text((W - 80, H - 44), f"{hi:.0f}u", fill=(80, 80, 80), font=f)
    img.save(os.path.join(args.out, "histogram.png"))
    print(f"\nhistogram -> {args.out}/histogram.png")
    print(f"(spread: stdev/median = {meds.std()/font_med:.0%})")


if __name__ == "__main__":
    main()
