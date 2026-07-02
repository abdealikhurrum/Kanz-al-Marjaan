#!/usr/bin/env python3
"""Detect residual outline bumps: notches, steps and lone facet creases of the
kind called out in the Google Fonts review ("top of final feh", "top right of
initial seen") that survived the big curve-correction pass because the corner
detector pinned them as genuine corners.

Method: flatten every contour densely, resample to a fixed arc step, then walk
the turning angles:

  * ZIGZAG  -- opposite-sign turns (each >= zig deg) within a short arc window:
               a step / notch cut into an otherwise continuous edge
  * CREASE  -- an isolated moderate corner (crease..corner deg) whose
               surroundings are near-straight/smooth: a lone facet. Real design
               corners (teeth apexes, stub corners) turn far harder and are
               excluded by the upper bound.

Prints a ranked report and (with --render) writes a zoomed silhouette crop per
event for eyeballing.

  python scripts/bump_scan.py [--render] [--top 40]
"""
import sys, os, math, argparse
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curve_cleanup_run import _passthrough, _seg_path_points
from join_diag import flat

SRC = "sources/KanzAlMarjaan-Regular.ufo"
STEP = 5.0          # arc-length resample step (font units)
WINDOW = 40.0       # zigzag window (units of arc)
ZIG = 9.0           # min |turn| for each leg of a zigzag (deg)
CREASE = (10.0, 42.0)   # isolated facet corner band (deg)
QUIET = 3.0         # "smooth surroundings" max |turn| (deg)
QUIET_SPAN = 25.0   # how far surroundings must stay quiet (units of arc)


def resample(poly, step=STEP):
    pts = [np.asarray(p, float) for p in poly]
    if len(pts) < 3:
        return None
    pts.append(pts[0])
    out = [pts[0]]
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = np.linalg.norm(b - a)
        if seg == 0:
            continue
        d = (b - a) / seg
        while acc + seg >= step:
            t = step - acc
            out.append(a + d * t)
            a = out[-1]
            seg -= t
            acc = 0.0
        acc += seg
    return np.array(out) if len(out) >= 8 else None


def turns(rs):
    v = np.diff(rs, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    t = np.diff(np.concatenate([ang, ang[:1]]))
    return (t + 180) % 360 - 180


def scan_contour(rs):
    """-> list of (severity, kind, point)"""
    t = turns(rs)
    n = len(t)
    win = max(2, int(WINDOW / STEP))
    quiet_n = max(1, int(QUIET_SPAN / STEP))
    events = []
    for i in range(n):
        ti = t[i]
        # zigzag: opposite-sign partner within the window
        if abs(ti) >= ZIG:
            for k in range(1, win + 1):
                tj = t[(i + k) % n]
                if abs(tj) >= ZIG and ti * tj < 0:
                    sev = min(abs(ti), abs(tj))
                    events.append((sev, "zigzag", tuple(rs[(i + 1) % len(rs)])))
                    break
        # lone crease
        if CREASE[0] <= abs(ti) <= CREASE[1]:
            around = [t[(i + d) % n] for d in range(-quiet_n, quiet_n + 1) if d != 0]
            if max(abs(a) for a in around) <= QUIET:
                events.append((abs(ti), "crease", tuple(rs[(i + 1) % len(rs)])))
    return events


def dedupe(events, radius=25.0):
    events.sort(reverse=True)
    kept = []
    for sev, kind, p in events:
        if all(math.dist(p, q[2]) > radius for q in kept):
            kept.append((sev, kind, p))
    return kept


def render_event(font, gname, p, path, span=220):
    g = font[gname]
    polys = flat(font, g)
    x0, y0 = p[0] - span, p[1] - span
    S = 480
    sc = S / (2 * span)
    img = Image.new("RGB", (S, S), "white")
    d = ImageDraw.Draw(img)
    for poly in polys:
        d.polygon([((x - x0) * sc, S - (y - y0) * sc) for x, y in poly], fill=(15, 15, 15))
    d.ellipse([S / 2 - 6, S / 2 - 6, S / 2 + 6, S / 2 + 6], outline=(220, 50, 50), width=2)
    img.save(path)


def facets(contour):
    """Straight line segments embedded in a curved run at facet angles --
    polygonized curve remnants (e.g. the crest of the final feh head)."""
    pts = [(p.x, p.y, p.segmentType) for p in contour]
    n = len(pts)
    if n < 4:
        return []

    def oncurve(i, step):
        j = (i + step) % n
        while pts[j][2] is None:
            j = (j + step) % n
        return j

    def tangent_in(i):
        """Direction arriving at on-curve i."""
        j = (i - 1) % n
        ref = pts[j] if pts[j][2] is None else pts[oncurve(i, -1)]
        return math.atan2(pts[i][1] - ref[1], pts[i][0] - ref[0])

    def tangent_out(i):
        j = (i + 1) % n
        ref = pts[j] if pts[j][2] is None else pts[oncurve(i, 1)]
        return math.atan2(ref[1] - pts[i][1], ref[0] - pts[i][0])

    out = []
    for i, (x, y, t) in enumerate(pts):
        if t != "line":
            continue
        j = oncurve(i, -1)
        px, py = pts[j][0], pts[j][1]
        length = math.hypot(x - px, y - py)
        if not (12 <= length <= 150):
            continue
        line_dir = math.atan2(y - py, x - px)
        t_in = math.degrees(abs((line_dir - tangent_in(j) + math.pi) % (2 * math.pi) - math.pi))
        t_out = math.degrees(abs((tangent_out(i) - line_dir + math.pi) % (2 * math.pi) - math.pi))
        if 6 <= t_in <= 32 and 6 <= t_out <= 32 and t_in + t_out >= 15:
            out.append(((t_in + t_out) / 2, "facet", ((x + px) / 2, (y + py) / 2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", default="out/bumps")
    args = ap.parse_args()
    font = Font(args.src)

    per_glyph = {}
    for glyph in font:
        if len(glyph) == 0:
            continue
        events = []
        for contour in glyph:
            poly = _seg_path_points(_passthrough(contour), 24)
            rs = resample(poly)
            if rs is None:
                continue
            events += scan_contour(rs)
            events += facets(contour)
        events = dedupe(events)
        if events:
            per_glyph[glyph.name] = events

    ranked = sorted(per_glyph.items(),
                    key=lambda kv: -max(e[0] for e in kv[1]))
    print(f"glyphs with bump events: {len(per_glyph)}   "
          f"total events: {sum(len(v) for v in per_glyph.values())}")
    for name, events in ranked[:args.top]:
        top = ", ".join(f"{k}@({p[0]:.0f},{p[1]:.0f}) {s:.0f}deg" for s, k, p in events[:4])
        print(f"  {name:36s} {len(events):3d} events   {top}")

    if args.render:
        os.makedirs(args.out, exist_ok=True)
        for name, events in ranked[:args.top]:
            for i, (sev, kind, p) in enumerate(events[:3]):
                render_event(font, name,  p,
                             os.path.join(args.out, f"{name}.{i}.{kind}.png"))
        print(f"renders -> {args.out}/")


if __name__ == "__main__":
    main()
