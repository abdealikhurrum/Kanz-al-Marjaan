#!/usr/bin/env python3
"""Run Phase-1 curve correction over a UFO with side-by-side QA renders.

Default is a DRY RUN: it writes cleaned glyphs to a *copy* UFO, renders
annotated before/after comparisons, and prints a deviation report. Nothing
in the source UFO changes unless --apply is given.

Usage:
  python scripts/curve_cleanup_run.py --tolerance 4 --glyphs uniFEDB,alef-ar.init
  python scripts/curve_cleanup_run.py --tolerance 4 --limit 30
  python scripts/curve_cleanup_run.py --tolerance 4 --apply      # write source in place
"""
import os
import sys
import argparse
import shutil
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curve_cleanup as cc

SRC = "sources/KanzAlMarjaan-Regular.ufo"


# ---------------------------------------------------------------------------
def process_glyph(glyph, tolerance, angle, samples, simplify=False):
    """Returns (new_contours, stats) where new_contours is a list of
    [(segtype, pts...), ...] per contour, or None if glyph has no contours."""
    if len(glyph) == 0:
        return None  # composite / empty
    new_contours = []
    pts_before = 0
    pts_after = 0
    worst_dev = 0.0
    fallbacks = 0
    blocked = False        # any contour's simplify rejected for deviation
    potential_removed = 0  # points simplify WOULD strip on blocked contours
    guard = max(2.5 * tolerance, 8.0)
    for contour in glyph:
        on_before = sum(1 for p in contour if p.segmentType is not None)
        pts_before += on_before
        orig_ref = _seg_path_points(_passthrough(contour), 24)
        orig_ref = [np.asarray(p, float) for p in orig_ref]

        def evaluate(segs):
            if not segs:
                return None
            # a closed contour needs >=2 segments; fewer is degenerate
            if on_before >= 3 and len(segs) < 2:
                return None
            return cc.max_deviation(orig_ref, segs), segs

        chosen = None
        if simplify:
            # Tolerance ladder: try aggressive first, then gentler retries. A
            # tighter tolerance hugs sharp features (teeth) closer, so it can
            # pass the deviation guard while still stripping bloat. Accept the
            # most aggressive fit that stays faithful AND reduces points.
            aggressive = evaluate(cc.process_contour_simplify(contour, tolerance, angle))
            if aggressive and aggressive[0] <= guard and len(aggressive[1]) <= on_before:
                chosen = aggressive
            else:
                # gentler retries vary BOTH tolerance and corner angle: a tighter
                # tolerance hugs curves, a smaller angle catches sharp features
                # (tooth tips) that otherwise get rounded mid-span. Each rung is
                # (tolerance, corner-angle, accept-guard); the final rung relaxes
                # the guard to 12u to accept a sub-1% bow on long edges rather
                # than leave the glyph bloated (teeth stay protected by then).
                ladder = [(tolerance * 0.5, angle, 8.0), (tolerance * 0.5, 22, 8.0),
                          (tolerance * 0.25, 22, 8.0), (tolerance * 0.25, 15, 8.0),
                          (tolerance * 0.25, 15, 12.0)]
                for tol_try, ang_try, g_try in ladder:
                    r = evaluate(cc.process_contour_simplify(contour, tol_try, ang_try))
                    if r and r[0] <= g_try and len(r[1]) <= on_before:
                        chosen = r
                        break
            if chosen is None:
                fallbacks += 1
                # still blocked after gentler retries -> genuinely hard
                if (aggressive is None) or (aggressive and aggressive[0] > guard):
                    blocked = True
                    if aggressive:
                        potential_removed += max(0, on_before - len(aggressive[1]))
        if chosen is None:
            r = evaluate(cc.process_contour(contour, tolerance, angle))
            # surgical must also be faithful; otherwise keep the original.
            if r and r[0] <= guard:
                chosen = r
        if chosen is None:
            new_contours.append(_passthrough(contour))
            pts_after += on_before
            continue
        dev, segs = chosen
        worst_dev = max(worst_dev, dev)
        new_contours.append(segs)
        pts_after += sum(1 for s in segs)  # on-curve endpoints (1 per seg)
    stats = dict(pts_before=pts_before, pts_after=pts_after,
                 removed=pts_before - pts_after, max_dev=worst_dev,
                 fallbacks=fallbacks, blocked=blocked,
                 potential_removed=potential_removed)
    return new_contours, None, stats


def _passthrough(contour):
    """Re-express a contour unchanged as our seg format (for rendering)."""
    pts = list(contour)
    n = len(pts)
    start = next((i for i, p in enumerate(pts) if p.segmentType is not None), 0)
    order = [pts[(start + k) % n] for k in range(n)]
    order.append(order[0])
    segs = []
    i = 0
    while i < len(order) - 1:
        j = i + 1
        offs = []
        while order[j].segmentType is None:
            offs.append(order[j]); j += 1
        on = order[j]
        p0 = np.array((order[i].x, order[i].y), float)
        if on.segmentType == 'curve' and len(offs) >= 2:
            segs.append(('curve', p0,
                         np.array((offs[0].x, offs[0].y), float),
                         np.array((offs[1].x, offs[1].y), float),
                         np.array((on.x, on.y), float)))
        else:
            segs.append(('line', p0, np.array((on.x, on.y), float)))
        i = j
    return segs


def write_contours(glyph, new_contours):
    """Replace glyph contours with new_contours (rounded). Components kept.

    Each seg's on-curve END point becomes a contour point; the contour wraps,
    so the last seg's endpoint is the start of the first seg. Off-curve handles
    are emitted before their owning curve's endpoint.
    """
    glyph.clearContours()
    pen = glyph.getPointPen()
    for segs in new_contours:
        pen.beginPath()
        n = len(segs)
        # Determine smoothness at each junction (curve->curve, non-corner)
        for i, s in enumerate(segs):
            prev = segs[(i - 1) % n]
            if s[0] == 'curve':
                _, p0, p1, p2, p3 = s
                pen.addPoint(_r(p1), segmentType=None)
                pen.addPoint(_r(p2), segmentType=None)
                smooth = (s[0] == 'curve' and segs[(i + 1) % n][0] == 'curve')
                pen.addPoint(_r(p3), segmentType="curve", smooth=smooth)
            else:
                _, p0, p3 = s
                pen.addPoint(_r(p3), segmentType="line", smooth=False)
        pen.endPath()


def _r(p):
    return (int(round(float(p[0]))), int(round(float(p[1]))))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _seg_path_points(segs, per_curve=16):
    path = []
    for s in segs:
        if s[0] == 'line':
            path.append(tuple(s[1]))
            path.append(tuple(s[2]))
        else:
            _, p0, p1, p2, p3 = s
            path.append(tuple(p0))
            for fp in cc.flatten_cubic(p0, p1, p2, p3, per_curve):
                path.append(tuple(fp))
    return path


def _oncurve_offcurve(segs):
    on = []
    off = []
    for s in segs:
        if s[0] == 'line':
            on.append(tuple(s[2]))
        else:
            on.append(tuple(s[3]))
            off.append(tuple(s[1]))
            off.append(tuple(s[2]))
    return on, off


def render_compare(orig_segs_list, new_segs_list, label, stats, path, size=460):
    pad = 40
    # bbox over both
    allpts = []
    for segs in orig_segs_list + new_segs_list:
        allpts += _seg_path_points(segs, 6)
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = max(maxx - minx, 1); h = max(maxy - miny, 1)
    scale = (size - 2 * pad) / max(w, h)

    def tx(p, ox):
        return (ox + pad + (p[0] - minx) * scale,
                size - pad - (p[1] - miny) * scale)

    img = Image.new("RGB", (size * 2 + 20, size + 40), "white")
    d = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
        fnt_s = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    except Exception:
        fnt = fnt_s = ImageFont.load_default()

    def draw_side(segs_list, ox, title, dot_on, dot_off):
        # outline
        for segs in segs_list:
            path = [tx(p, ox) for p in _seg_path_points(segs, 18)]
            if len(path) > 1:
                d.line(path + [path[0]], fill=(60, 60, 60), width=2)
            on, off = _oncurve_offcurve(segs)
            for p in on:
                x, y = tx(p, ox)
                d.rectangle([x - 3, y - 3, x + 3, y + 3], fill=dot_on)
            for p in off:
                x, y = tx(p, ox)
                r = 2.5
                d.ellipse([x - r, y - r, x + r, y + r], outline=dot_off, width=1)
        d.text((ox + pad, 8), title, fill="black", font=fnt)

    draw_side(orig_segs_list, 0, f"BEFORE  on-curve={stats['pts_before']}",
              (200, 0, 0), (230, 150, 150))
    draw_side(new_segs_list, size + 20, f"AFTER  on-curve={stats['pts_after']}",
              (0, 120, 0), (150, 200, 150))
    d.line([(size + 10, 0), (size + 10, size)], fill=(220, 220, 220), width=1)
    sub = (f"{label}   removed {stats['removed']} pts "
           f"({stats['removed']/max(stats['pts_before'],1):.0%})   "
           f"max deviation {stats['max_dev']:.1f} u")
    d.text((pad, size + 14), sub, fill=(40, 40, 40), font=fnt_s)
    img.save(path)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=4.0)
    ap.add_argument("--angle", type=float, default=30.0)
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--glyphs", type=str, default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--simplify", action="store_true",
                    help="also simplify dense curve runs (not just line-runs)")
    ap.add_argument("--src", type=str, default=SRC,
                    help="source UFO to read (defaults to the in-repo source)")
    ap.add_argument("--outdir", type=str, default="out/curve_qa")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    font = Font(args.src)

    names = [n for n in font.keys()]
    if args.glyphs:
        wanted = set(args.glyphs.split(","))
        names = [n for n in names if n in wanted]
    # only glyphs with contours
    names = [n for n in names if len(font[n]) > 0]
    if args.limit:
        names = names[:args.limit]

    report = []
    total_before = total_after = total_fallback = 0
    for name in names:
        g = font[name]
        orig_segs = [_passthrough(c) for c in g]
        res = process_glyph(g, args.tolerance, args.angle, args.samples,
                            simplify=args.simplify)
        if res is None:
            continue
        new_contours, orig_polys, stats = res
        total_before += stats['pts_before']; total_after += stats['pts_after']
        total_fallback += stats.get('fallbacks', 0)
        report.append((name, stats))
        safe = name.replace("/", "_")
        render_compare(orig_segs, new_contours, name, stats,
                       os.path.join(args.outdir, f"{safe}.png"))
        if args.apply:
            write_contours(g, new_contours)

    print(f"\nProcessed {len(report)} glyphs.")
    print(f"on-curve points: {total_before} -> {total_after} "
          f"({(total_before-total_after)/max(total_before,1):.1%} removed)")
    print(f"contours that fell back from simplify: {total_fallback}")

    def frac(st):
        return st['removed'] / max(st['pts_before'], 1)

    # Most changed: biggest on-curve reduction (ties broken by raw count).
    most = sorted(report, key=lambda r: (frac(r[1]), r[1]['removed']), reverse=True)
    print("\nMOST CHANGED (largest point reduction):")
    for name, st in most[:20]:
        print(f"  {name:40s} pts {st['pts_before']:4d}->{st['pts_after']:4d}"
              f"  (-{frac(st):.0%})  dev={st['max_dev']:5.1f}u")

    # Glyphs left unchanged split by REASON:
    #  - well-traced: already efficient, re-fit can't beat the existing drawing
    #  - blocked:     simplify would distort (deviation guard tripped) -> kept
    # A blocked glyph only "needs attention" if simplify would have stripped a
    # meaningful fraction of points (i.e. it's bloated). Blocked-but-efficient
    # glyphs (good kaf/gaf ligatures etc.) count as already well-traced.
    def bloated(st):
        return (st.get('blocked')
                and st['pts_before'] >= 20
                and st.get('potential_removed', 0) >= 0.25 * max(st['pts_before'], 1))
    unchanged = [(n, st) for n, st in report if st['removed'] <= 0]
    well_traced = [(n, st) for n, st in unchanged if not bloated(st)]
    blocked = [(n, st) for n, st in unchanged if bloated(st)]

    print(f"\nALREADY WELL-TRACED (no change needed): {len(well_traced)} glyphs")
    for name, st in sorted(well_traced, key=lambda r: -r[1]['pts_before'])[:15]:
        print(f"  {name:40s} pts={st['pts_before']:4d}")
    print(f"\nBLOCKED — would distort, needs manual attention: {len(blocked)} glyphs")
    for name, st in sorted(blocked, key=lambda r: -r[1]['pts_before'])[:20]:
        print(f"  {name:40s} pts={st['pts_before']:4d}")

    # Copy the relevant comparison images into category folders for review.
    for cat, items in [("most_changed", most[:20]),
                       ("well_traced", sorted(well_traced,
                        key=lambda r: -r[1]['pts_before'])[:20]),
                       ("blocked", sorted(blocked,
                        key=lambda r: -r[1]['pts_before'])[:20])]:
        d = os.path.join(args.outdir, cat)
        os.makedirs(d, exist_ok=True)
        for rank, (name, st) in enumerate(items):
            safe = name.replace("/", "_")
            src_img = os.path.join(args.outdir, f"{safe}.png")
            if os.path.exists(src_img):
                shutil.copy(src_img, os.path.join(d, f"{rank:02d}_{safe}.png"))

    print(f"\nQA images in {args.outdir}/  "
          f"(categorized in {args.outdir}/most_changed and /unchanged)")

    if args.apply:
        font.save(SRC)
        print(f"APPLIED to {SRC}")
    else:
        print("DRY RUN (use --apply to write source UFO)")


if __name__ == "__main__":
    main()
