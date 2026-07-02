#!/usr/bin/env python3
"""Phase 3: qalam smoothing — heal residual auto-trace kinks by modeling the
calligraphic intent of the reed pen.

A qalam cannot produce a shallow tangent break mid-stroke: the two rails of a
stroke are G1-continuous except at genuine pen events — terminal cuts, stroke
junctions, tooth tips — which show pronounced angles. After Phase 1's
geometric refit, a joint whose tangents break by 3–25 degrees is almost always
leftover trace wobble, not intent. Generic curve fitting cannot tell 5u of
wobble from 5u of detail; this pass decides by the pen model instead:

  1. WOBBLE RUNS — maximal chains of short faceted segments whose joints all
     break shallowly are re-fit as one smooth cubic span (Schneider fit, G1
     preserved into the untouched neighbours).
  2. KINK HEALING — a remaining shallow joint is healed by rotating its bezier
     handles onto a shared tangent. A straight segment is an authoritative pen
     edge: the curve handle aligns to the line, never the reverse. Line-line
     joints are never rotated (that would move on-curve points).
  3. INTENT FLAGS — UFO smooth flags are rewritten to match the healed
     geometry (smooth iff the joint is G1), so editors and downstream tools
     see the intent rather than Phase 1's both-sides-curve heuristic.

Every edit is guarded: the healed outline must stay within --guard units of
the original (max-deviation sampling); a run or joint that cannot be healed
within the guard is left untouched and counted. Only Arabic-script glyphs are
processed — the Latin/symbol set (from Source) is hand-designed and excluded.

  python scripts/qalam_smooth.py                    # dry run + QA renders
  python scripts/qalam_smooth.py --glyphs uniFB8F   # inspect one glyph
  python scripts/qalam_smooth.py --apply            # write source UFO
"""
import os
import sys
import math
import argparse
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curve_cleanup as cc
from curve_cleanup_run import _passthrough, _seg_path_points

SRC = "sources/KanzAlMarjaan-Regular.ufo"

MIN_KINK = 3.0     # deg; below this a joint already reads as smooth
MAX_KINK = 25.0    # deg; above this the angle is a deliberate pen event
FACET_MAX = 30.0   # u; segments this short around shallow joints are facets
LINE_AUTH = 1.0    # u; any real line is an authoritative straight pen edge
SMOOTH_FLAG_DEG = 1.0  # joints flatter than this get the UFO smooth flag


# ---------------------------------------------------------------------------
# Segment-list geometry (segs as produced by _passthrough / cc.process_*)
# ---------------------------------------------------------------------------

def seg_start(s):
    return s[1]


def seg_end(s):
    return s[-1]


def out_tangent(s):
    """Unit tangent leaving the START of segment s."""
    if s[0] == 'curve':
        v = s[2] - s[1]
        if np.hypot(*v) < 1e-9:
            v = s[3] - s[1]
    else:
        v = s[2] - s[1]
    return cc._normalize(v)


def in_tangent(s):
    """Unit tangent arriving at the END of segment s."""
    if s[0] == 'curve':
        v = s[4] - s[3]
        if np.hypot(*v) < 1e-9:
            v = s[4] - s[2]
    else:
        v = s[2] - s[1]
    return cc._normalize(v)


def joint_angle(segs, i):
    """Tangent break (deg) at the joint where segs[i-1] ends / segs[i] starts."""
    vi = in_tangent(segs[i - 1])
    vo = out_tangent(segs[i])
    if np.hypot(*vi) < 1e-9 or np.hypot(*vo) < 1e-9:
        return 0.0
    return abs(math.degrees(cc._angle_between(vi, vo)))


def chord_len(s):
    return float(np.hypot(*(seg_end(s) - seg_start(s))))


def seg_polyline(s, per_curve=12):
    """Points along a segment, start included, end included."""
    if s[0] == 'line':
        return [s[1], s[2]]
    return [s[1]] + cc.flatten_cubic(s[1], s[2], s[3], s[4], per_curve)


def span_deviation(new_segs, orig_pts):
    """Max distance from the new span outline to the original span polyline."""
    op = [np.asarray(p, float) for p in orig_pts]
    seg_a = np.array(op[:-1])
    seg_b = np.array(op[1:])
    ab = seg_b - seg_a
    ab_len2 = np.sum(ab * ab, axis=1)
    ab_len2[ab_len2 < 1e-12] = 1e-12
    worst = 0.0
    for s in new_segs:
        for q in seg_polyline(s, 16):
            t = np.clip(np.sum((q - seg_a) * ab, axis=1) / ab_len2, 0, 1)
            proj = seg_a + t[:, None] * ab
            d = np.min(np.hypot(proj[:, 0] - q[0], proj[:, 1] - q[1]))
            worst = max(worst, d)
    return worst


# ---------------------------------------------------------------------------
# Pass 1: wobble runs — refit chains of shallow facets as one smooth span
# ---------------------------------------------------------------------------

def find_wobble_runs(segs):
    """Maximal circular runs of consecutive shallow-facet joints.

    A facet joint breaks by (MIN_KINK, MAX_KINK] and both adjacent segments
    are short. Runs of >=2 joints qualify always; a lone facet qualifies when
    both its segments are straight lines (a trace facet between two short
    lines — a reed edge never bends 3-25 degrees over a few units). Returns
    list of (first_joint, last_joint) segment-index pairs (joint i sits
    between segs[i-1] and segs[i])."""
    m = len(segs)
    facet = []
    for i in range(m):
        ang = joint_angle(segs, i)
        short = chord_len(segs[i - 1]) < FACET_MAX and chord_len(segs[i]) < FACET_MAX
        facet.append(MIN_KINK < ang <= MAX_KINK and short)
    if all(facet):
        return [(0, m - 1)]
    runs = []
    i = 0
    while i < m:
        if not facet[i]:
            i += 1
            continue
        # walk back over the circular boundary only from i==0
        start = i
        if i == 0:
            while facet[(start - 1) % m] and (start - 1) % m > i:
                start = (start - 1) % m
        j = i
        while facet[(j + 1) % m] and (j + 1) % m != start:
            j = (j + 1) % m
        length = (j - start) % m + 1
        if length >= 2 or (segs[(start - 1) % m][0] == 'line'
                           and segs[start][0] == 'line'):
            runs.append((start, j))
        i = j + 1 if j >= i else m
    return runs


def refit_run(segs, first, last, guard):
    """Refit segments (first-1 .. last) — the span P[first-1]..P[last+1] —
    into smooth cubics. Returns new full seg list or None if guarded off."""
    m = len(segs)
    span_idx = [(first - 1 + k) % m for k in range(((last - (first - 1)) % m) + 1)]
    if len(span_idx) >= m:            # would consume the whole contour: skip
        return None
    # original span polyline
    pts = []
    for k, si in enumerate(span_idx):
        pl = seg_polyline(segs[si], 12)
        pts.extend(pl if k == 0 else pl[1:])
    pts = [np.asarray(p, float) for p in pts]

    # end tangents: preserve continuity with the untouched neighbours when the
    # outer joint is not a genuine corner; otherwise let the polyline decide.
    prev_seg = segs[(span_idx[0] - 1) % m]
    next_seg = segs[(span_idx[-1] + 1) % m]
    left_t = (in_tangent(prev_seg)
              if joint_angle(segs, span_idx[0]) <= MAX_KINK
              else cc._end_tangent(pts))
    right_t = (-out_tangent(next_seg)
               if joint_angle(segs, (span_idx[-1] + 1) % m) <= MAX_KINK
               else cc._end_tangent(pts[::-1]))

    out = []
    cc._fit_cubic(pts, left_t, right_t, max(guard * 0.75, 2.0), out)
    if not out or len(out) > len(span_idx):
        return None
    new_span = [('curve', *bz) for bz in out]
    if span_deviation(new_span, pts) > guard:
        return None
    keep = [segs[i] for i in range(m) if i not in set(span_idx)]
    # reassemble in contour order starting after the span
    ordered = []
    k = (span_idx[-1] + 1) % m
    while k != span_idx[0]:
        ordered.append(segs[k])
        k = (k + 1) % m
    return ordered + new_span if keep else new_span


def _turn_sign(segs, i):
    vi = in_tangent(segs[i - 1])
    vo = out_tangent(segs[i])
    return np.sign(vi[0] * vo[1] - vi[1] * vo[0])


def find_arc_runs(segs):
    """Chord-approximated arcs: >=3 consecutive straight segments whose
    interior joints all turn shallowly in the SAME direction. A drawn arc
    traced as long chords produces exactly this; a deliberate single bend
    (kaf seat, terminal cut) does not. Returns (first_joint, last_joint)."""
    m = len(segs)
    arc = []
    for i in range(m):
        ok = (segs[i - 1][0] == 'line' and segs[i][0] == 'line'
              and MIN_KINK < joint_angle(segs, i) <= MAX_KINK)
        arc.append(_turn_sign(segs, i) if ok else 0.0)
    runs = []
    i = 0
    while i < m:
        if arc[i] == 0.0:
            i += 1
            continue
        start = i
        if i == 0:
            while arc[(start - 1) % m] == arc[i] and (start - 1) % m > i:
                start = (start - 1) % m
        j = i
        while arc[(j + 1) % m] == arc[start] and (j + 1) % m != start:
            j = (j + 1) % m
        if (j - start) % m + 1 >= 2:
            runs.append((start, j))
        i = j + 1 if j >= i else m
    return runs


def heal_wobble(segs, guard):
    healed = 0
    blocked = 0
    rounds = 0
    while rounds < 64:
        rounds += 1
        blocked = 0                   # count from the final full scan only
        progressed = False
        for first, last in find_wobble_runs(segs) + find_arc_runs(segs):
            new = refit_run(segs, first, last, guard)
            if new is not None:
                segs = new
                healed += 1
                progressed = True
                break                 # indices shifted; rescan
            blocked += 1
        if not progressed:
            break
    return segs, healed, blocked


# ---------------------------------------------------------------------------
# Pass 2: kink healing — rotate handles onto a shared tangent
# ---------------------------------------------------------------------------

def heal_kinks(segs, guard):
    """Heal isolated shallow joints. Returns (segs, healed, blocked)."""
    healed = 0
    blocked = 0
    rounds = 0
    while rounds < 200:
        rounds += 1
        blocked = 0                   # count from the final full scan only
        rescan = False
        m = len(segs)
        for i in range(m):
            ang = joint_angle(segs, i)
            if not (MIN_KINK < ang <= MAX_KINK):
                continue
            s_in = segs[i - 1]
            s_out = segs[i]
            t_in = in_tangent(s_in)
            t_out = out_tangent(s_out)
            P = seg_end(s_in)
            if s_in[0] == 'curve' and s_out[0] == 'curve':
                t = cc._normalize(t_in + t_out)
            elif s_in[0] == 'curve' and s_out[0] == 'line':
                t = t_out              # straight pen edge is authoritative
            elif s_in[0] == 'line' and s_out[0] == 'curve':
                t = t_in
            else:
                continue               # line-line: on-curve points would move
            if np.hypot(*t) < 1e-9:
                continue
            new_in, new_out = s_in, s_out
            orig_pts = seg_polyline(s_in, 12) + seg_polyline(s_out, 12)[1:]
            if s_in[0] == 'curve':
                h = s_in[3] - P
                new_in = ('curve', s_in[1], s_in[2],
                          P - t * np.hypot(*h), s_in[4])
            if s_out[0] == 'curve':
                h = s_out[2] - P
                new_out = ('curve', s_out[1], P + t * np.hypot(*h),
                           s_out[3], s_out[4])
            if span_deviation([new_in, new_out], orig_pts) <= guard:
                segs[i - 1] = new_in
                segs[i] = new_out
                healed += 1
                continue
            # rotating a long handle sweeps too far; refit the two segments
            # as one G1 span instead (more cubics = freedom to stay faithful)
            refit = _refit_pair(s_in, s_out, guard)
            if refit is None:
                blocked += 1
                continue
            # rotate the cyclic list so the pair sits at [0:2], then splice
            segs = segs[i - 1:] + segs[:i - 1] if i >= 1 else \
                [segs[-1]] + segs[:-1]
            segs[0:2] = refit
            healed += 1
            rescan = True
            break
        if not rescan:
            break
    return segs, healed, blocked


def _refit_pair(s_in, s_out, guard):
    """Refit two adjacent segments as one smooth span, keeping the outer
    tangents so continuity with the neighbours is preserved."""
    pts = [np.asarray(p, float)
           for p in seg_polyline(s_in, 12) + seg_polyline(s_out, 12)[1:]]
    out = []
    cc._fit_cubic(pts, out_tangent(s_in), -in_tangent(s_out),
                  max(guard * 0.75, 2.0), out)
    if not out or len(out) > 3:
        return None
    new = [('curve', *bz) for bz in out]
    return new if span_deviation(new, pts) <= guard else None


# ---------------------------------------------------------------------------
# Write-back with geometry-true smooth flags
# ---------------------------------------------------------------------------

def _rnum(v):
    f = round(float(v), 2)
    return int(f) if f == int(f) else f


def _rpt(p):
    return (_rnum(p[0]), _rnum(p[1]))


def write_contours(glyph, contours_segs):
    """Replace glyph contours; smooth flag = the joint is actually G1."""
    glyph.clearContours()
    pen = glyph.getPointPen()
    for segs in contours_segs:
        pen.beginPath()
        n = len(segs)
        for i, s in enumerate(segs):
            nxt = segs[(i + 1) % n]
            ang = joint_angle(segs, (i + 1) % n)
            g1 = (ang <= SMOOTH_FLAG_DEG
                  and (s[0] == 'curve' or nxt[0] == 'curve'))
            if s[0] == 'curve':
                pen.addPoint(_rpt(s[2]), segmentType=None)
                pen.addPoint(_rpt(s[3]), segmentType=None)
                pen.addPoint(_rpt(s[4]), segmentType="curve", smooth=g1)
            else:
                pen.addPoint(_rpt(s[2]), segmentType="line", smooth=g1)
        pen.endPath()


# ---------------------------------------------------------------------------
# Glyph selection / QA
# ---------------------------------------------------------------------------

ARABIC_BLOCKS = ((0x0600, 0x077F), (0x08A0, 0x08FF),
                 (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
# traced alongside the letters despite not being Arabic script
EXTRA_TRACED = {"uni25CC"}


def is_arabic_glyph(glyph):
    """Unencoded (positional/ligature form) or Arabic-block glyphs. The
    hand-designed Latin/symbol set from Source is never touched."""
    if glyph.name in (".notdef", "_notdef"):
        return False
    if glyph.name in EXTRA_TRACED:
        return True
    us = glyph.unicodes
    if not us:
        return True
    return all(any(a <= u <= b for a, b in ARABIC_BLOCKS) for u in us)


def kink_count(contours_segs):
    n = 0
    for segs in contours_segs:
        for i in range(len(segs)):
            if MIN_KINK < joint_angle(segs, i) <= MAX_KINK:
                n += 1
    return n


def render_compare(before, after, name, path, size=520):
    allpts = []
    for segs in before + after:
        allpts += _seg_path_points(segs, 8)
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    mnx, mny = min(xs), min(ys)
    w = max(max(xs) - mnx, 1)
    h = max(max(ys) - mny, 1)
    pad = 36
    sc = (size - 2 * pad) / max(w, h)
    img = Image.new("RGB", (size * 2 + 16, size + 30), "white")
    d = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        fnt = ImageFont.load_default()

    def draw(side_segs, ox, title):
        for segs in side_segs:
            poly = [(ox + pad + (p[0] - mnx) * sc,
                     pad + (h - (p[1] - mny)) * sc)
                    for p in _seg_path_points(segs, 16)]
            d.polygon(poly, outline=(70, 70, 70), fill=(235, 235, 235))
        for segs in side_segs:
            for i in range(len(segs)):
                ang = joint_angle(segs, i)
                p = seg_start(segs[i])
                x = ox + pad + (p[0] - mnx) * sc
                y = pad + (h - (p[1] - mny)) * sc
                if MIN_KINK < ang <= MAX_KINK:
                    d.ellipse([x - 4, y - 4, x + 4, y + 4],
                              outline=(210, 30, 30), width=2)
        d.text((ox + pad, 6), title, fill=(0, 0, 0), font=fnt)

    draw(before, 0, f"BEFORE {name}  kinks={kink_count(before)}")
    draw(after, size + 16, f"AFTER  kinks={kink_count(after)}")
    img.save(path)


# ---------------------------------------------------------------------------

def process_glyph(glyph, guard):
    """Returns (new_contours, stats) or None if the glyph is untouched."""
    if len(glyph) == 0:
        return None
    before = [_passthrough(c) for c in glyph]
    after = []
    healed_runs = blocked_runs = healed_kinks = blocked_kinks = 0
    worst = 0.0
    for c, orig in zip(glyph, before):
        orig_pts = [np.asarray(p, float) for p in _seg_path_points(orig, 16)]
        segs = [tuple(s) for s in orig]
        segs, hr, br = heal_wobble(list(segs), guard)
        segs, hk, bk = heal_kinks(list(segs), guard)
        # per-span guards can compound; back the whole contour out if the
        # accumulated drift exceeds 1.5x the guard
        dev = span_deviation(segs, orig_pts)
        if dev > guard * 1.5:
            segs, hr, br, hk, bk, dev = list(orig), 0, hr + br, 0, hk + bk, 0.0
        healed_runs += hr
        blocked_runs += br
        healed_kinks += hk
        blocked_kinks += bk
        worst = max(worst, dev)
        after.append(segs)
    stats = dict(kinks_before=kink_count(before), kinks_after=kink_count(after),
                 healed_runs=healed_runs, blocked_runs=blocked_runs,
                 healed_kinks=healed_kinks, blocked_kinks=blocked_kinks,
                 max_dev=worst)
    return before, after, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--guard", type=float, default=4.0,
                    help="max outline deviation per healed span (units)")
    ap.add_argument("--glyphs", default="",
                    help="comma-separated glyph names (default: all Arabic)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--renders", type=int, default=24,
                    help="how many most-improved glyphs to render")
    ap.add_argument("--outdir", default="out/qalam_qa")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    font = Font(args.src)
    names = ([n for n in args.glyphs.split(",") if n] if args.glyphs
             else [g.name for g in font
                   if len(g) > 0 and is_arabic_glyph(g)])
    if args.limit:
        names = names[:args.limit]

    total_before = total_after = 0
    healed_r = blocked_r = healed_k = blocked_k = 0
    results = []
    for name in names:
        r = process_glyph(font[name], args.guard)
        if r is None:
            continue
        before, after, st = r
        total_before += st['kinks_before']
        total_after += st['kinks_after']
        healed_r += st['healed_runs']
        blocked_r += st['blocked_runs']
        healed_k += st['healed_kinks']
        blocked_k += st['blocked_kinks']
        if st['kinks_before'] != st['kinks_after'] or st['healed_kinks']:
            results.append((name, before, after, st))
            if args.apply:
                write_contours(font[name], after)
        elif args.apply:
            # geometry unchanged; still rewrite so smooth flags match reality
            write_contours(font[name], after)

    print(f"glyphs scanned: {len(names)}   changed: {len(results)}")
    print(f"shallow kinks ({MIN_KINK:.0f}-{MAX_KINK:.0f} deg): "
          f"{total_before} -> {total_after} "
          f"({(total_before - total_after)} healed, "
          f"{(total_before - total_after) / max(total_before, 1):.0%})")
    print(f"wobble runs refit: {healed_r}   guarded off: {blocked_r}")
    print(f"joints healed: {healed_k}   guarded off: {blocked_k}")

    results.sort(key=lambda r: -(r[3]['kinks_before'] - r[3]['kinks_after']))
    print("\nMOST IMPROVED:")
    for name, _b, _a, st in results[:20]:
        print(f"  {name:42s} kinks {st['kinks_before']:3d} -> "
              f"{st['kinks_after']:3d}   dev={st['max_dev']:.1f}u")
    for name, b, a, _st in results[:args.renders]:
        safe = name.replace('.', '_')
        render_compare(b, a, name, os.path.join(args.outdir, f"{safe}.png"))
    if results[args.renders:]:
        print(f"(renders for top {args.renders} in {args.outdir})")

    if args.apply:
        font.save()
        print(f"\nAPPLIED -> {args.src}")
    else:
        print("\nDRY RUN (use --apply to write the source UFO)")


if __name__ == "__main__":
    main()
