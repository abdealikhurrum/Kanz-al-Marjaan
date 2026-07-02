#!/usr/bin/env python3
"""Outline lint: find (and fix) residual glyph-outline debris.

Targets the classes flagged by Font Bakery's outline checks that survived the
big cleanup passes, plus a few it doesn't cover:

  1. duplicate adjacent on-curve points (zero-length segments)
  2. micro line segments (<= --micro units) wedged between long segments --
     the "jaggy segment" debris; endpoints are merged to their midpoint
  3. semi-vertical / semi-horizontal LINE segments (long lines 1-3 units off
     axis, including cursive seam edges) -- snapped exactly on-axis
  4. degenerate contours (fewer than 3 points, or zero area)
  5. exact duplicate contours within a glyph

Everything moves points by at most a couple of units, far below visibility.
Default is a dry run report; --apply rewrites the UFO in place.

  python scripts/outline_lint.py            # report
  python scripts/outline_lint.py --apply
"""
import argparse
from collections import Counter
from defcon import Font

SRC = "sources/KanzAlMarjaan-Regular.ufo"


def contour_points(c):
    """[(x, y, segmentType, smooth), ...] in contour order."""
    return [(p.x, p.y, p.segmentType, p.smooth) for p in c]


def poly_area(pts):
    ons = [(x, y) for x, y, t, s in pts]
    n = len(ons)
    return sum(ons[i][0] * ons[(i + 1) % n][1] - ons[(i + 1) % n][0] * ons[i][1]
               for i in range(n)) / 2


def fix_contour(pts, micro, axis_tol, axis_ratio, log):
    """Return (new_pts, changed). pts as from contour_points()."""
    changed = False

    def prev_oncurve(i):
        j = (i - 1) % len(pts)
        while pts[j][2] is None:
            j = (j - 1) % len(pts)
        return j

    def next_oncurve(i):
        j = (i + 1) % len(pts)
        while pts[j][2] is None:
            j = (j + 1) % len(pts)
        return j

    def seg_len(a, b):
        return max(abs(pts[a][0] - pts[b][0]), abs(pts[a][1] - pts[b][1]))

    # 1+2: zero-length and micro line segments ------------------------------
    i = 0
    guard = 0
    while i < len(pts) and len(pts) > 3 and guard < 10000:
        guard += 1
        x, y, t, s = pts[i]
        if t == "line":
            j = prev_oncurve(i)
            px, py = pts[j][0], pts[j][1]
            dist = max(abs(x - px), abs(y - py))
            if dist == 0:
                log.append(f"dup point ({x},{y})")
                del pts[i]
                changed = True
                continue
            # merge only ISOLATED micro segments: both neighbouring segments
            # must be long, so chains of short segments (dense polylines,
            # ink traps) are never decimated with accumulating drift
            if (dist <= micro and pts[j][2] is not None
                    and seg_len(j, prev_oncurve(j)) > 2 * micro
                    and seg_len(next_oncurve(i), i) > 2 * micro):
                mx, my = round((x + px) / 2), round((y + py) / 2)
                log.append(f"micro line ({px},{py})-({x},{y}) -> ({mx},{my})")
                # merge: previous on-curve moves to midpoint, line point dies
                pts[j] = (mx, my, pts[j][2], pts[j][3])
                del pts[i]
                changed = True
                continue
            # CHAIN of micro line segments (a notch/step cut into an edge,
            # e.g. the top right of initial seen): collapse the whole run to
            # its midpoint, provided the total extent stays small so the
            # deviation is bounded by ~chain_max/2
            if dist <= micro and pts[j][2] == "line":
                run = [j, i]
                k = next_oncurve(i)
                while (pts[k][2] == "line" and seg_len(k, run[-1]) <= micro
                       and len(run) < 8):
                    run.append(k)
                    k = next_oncurve(k)
                if len(run) >= 3:
                    xs = [pts[r][0] for r in run]; ys = [pts[r][1] for r in run]
                    span = max(max(xs) - min(xs), max(ys) - min(ys))
                    if span <= 4 * micro:
                        mx, my = round(sum(xs) / len(xs)), round(sum(ys) / len(ys))
                        log.append(f"micro chain x{len(run)} around ({mx},{my})")
                        pts[run[0]] = (mx, my, "line", pts[run[0]][3])
                        for r in sorted(run[1:], reverse=True):
                            del pts[r]
                        changed = True
                        continue
        i += 1

    # 3: semi-vertical / semi-horizontal lines ------------------------------
    def near_axis(a, b, vertical):
        ax, ay = pts[a][0], pts[a][1]
        bx, by = pts[b][0], pts[b][1]
        dx, dy = abs(ax - bx), abs(ay - by)
        if vertical:
            return 0 < dx <= axis_tol and dy >= axis_ratio * dx
        return 0 < dy <= axis_tol and dx >= axis_ratio * dy

    for i, (x, y, t, s) in enumerate(pts):
        if t != "line":
            continue
        j = prev_oncurve(i)
        px, py, pt, ps = pts[j]
        dx, dy = abs(x - px), abs(y - py)
        for vertical in (True, False):
            if not near_axis(j, i, vertical):
                continue
            span = dy if vertical else dx
            if span <= 8:
                continue
            # skip CHAINS of near-axis lines: those are gentle design slopes
            # polygonized into segments; snapping each would staircase them
            k_prev, k_next = prev_oncurve(j), next_oncurve(i)
            if ((pts[j][2] == "line" and near_axis(k_prev, j, vertical))
                    or (pts[k_next][2] == "line" and near_axis(i, k_next, vertical))):
                continue
            if vertical:
                nx = round((x + px) / 2)
                log.append(f"semi-vertical ({px},{py})-({x},{y}) -> x={nx}")
                pts[i] = (nx, y, t, s)
                pts[j] = (nx, py, pt, ps)
            else:
                ny = round((y + py) / 2)
                log.append(f"semi-horizontal ({px},{py})-({x},{y}) -> y={ny}")
                pts[i] = (x, ny, t, s)
                pts[j] = (px, ny, pt, ps)
            changed = True
    return pts, changed


def rebuild(glyph, contours):
    """Replace glyph contours with the fixed point lists (components kept)."""
    comps = [(c.baseGlyph, c.transformation) for c in glyph.components]
    glyph.clearContours()
    pen = glyph.getPointPen()
    for pts in contours:
        pen.beginPath()
        for x, y, t, s in pts:
            pen.addPoint((x, y), segmentType=t, smooth=s)
        pen.endPath()
    assert [(c.baseGlyph, c.transformation) for c in glyph.components] == comps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--micro", type=float, default=3)
    ap.add_argument("--axis-tol", type=float, default=3)
    ap.add_argument("--axis-ratio", type=float, default=8)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    font = Font(args.src)
    stats = Counter()
    n_glyphs = 0
    for glyph in font:
        if len(glyph) == 0:
            continue
        log = []
        new_contours = []
        glyph_changed = False
        seen = set()
        for c in glyph:
            pts = contour_points(c)
            # 4: degenerate
            if len(pts) < 3 or poly_area(pts) == 0:
                log.append(f"degenerate contour ({len(pts)} pts, area {poly_area(pts):.0f})")
                stats["degenerate"] += 1
                glyph_changed = True
                continue
            # 5: exact duplicate contour
            key = tuple(pts)
            if key in seen:
                log.append("duplicate contour")
                stats["dup-contour"] += 1
                glyph_changed = True
                continue
            seen.add(key)
            pts, changed = fix_contour(pts, args.micro, args.axis_tol, args.axis_ratio, log)
            if changed:
                glyph_changed = True
            new_contours.append(pts)
        if glyph_changed:
            n_glyphs += 1
            for entry in log:
                stats[entry.split(" (")[0].split(" -")[0]] += 0  # keep keys tidy
                stats[entry.split(" (")[0]] += 1
            if args.verbose or not args.apply:
                print(f"{glyph.name}:")
                for entry in log:
                    print(f"    {entry}")
            if args.apply:
                rebuild(glyph, new_contours)

    print(f"\nglyphs needing fixes: {n_glyphs}")
    for k, v in stats.most_common():
        if v:
            print(f"  {k:20s} {v}")
    if args.apply:
        font.save(args.src)
        print(f"APPLIED -> {args.src}")


if __name__ == "__main__":
    main()
