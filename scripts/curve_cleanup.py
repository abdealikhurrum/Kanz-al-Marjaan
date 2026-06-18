#!/usr/bin/env python3
"""Phase 1: correct curves — de-polygonize over-segmented outlines into clean cubics.

Strategy: flatten each contour to a dense polyline, detect genuine corners by
turning angle (so Arabic teeth/terminals are preserved), then fit smooth cubic
Beziers segment-by-segment with Schneider's algorithm, within a deviation
tolerance. A QA pass measures max deviation per glyph; nothing drifts silently.

Operates on a UFO in place (defcon). Components/anchors/width/lib untouched;
only contours are rebuilt. Composite glyphs (no contours) are left alone.
"""
import math
import argparse
import numpy as np
from fontTools.misc.bezierTools import segmentPointAtT  # noqa: F401 (sanity import)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _v(p):
    return np.asarray(p, dtype=float)


def cubic_point(p0, p1, p2, p3, t):
    mt = 1.0 - t
    return (mt * mt * mt) * p0 + 3 * (mt * mt * t) * p1 + 3 * (mt * t * t) * p2 + (t * t * t) * p3


def flatten_cubic(p0, p1, p2, p3, n):
    return [cubic_point(p0, p1, p2, p3, i / n) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# Schneider cubic-Bezier fitting (classic 1990 algorithm)
# ---------------------------------------------------------------------------

def _dedupe(pts, eps=1e-3):
    out = [pts[0]]
    for p in pts[1:]:
        if np.hypot(*(p - out[-1])) > eps:
            out.append(p)
    return out


def _end_tangent(pts, window=18.0):
    """Stable endpoint tangent: direction from a point ~`window` units away."""
    acc = 0.0
    ref = pts[-1]
    for i in range(1, len(pts)):
        acc += np.hypot(*(pts[i] - pts[i - 1]))
        ref = pts[i]
        if acc >= window:
            break
    return _normalize(ref - pts[0])


def fit_curve(points, error):
    """Fit a sequence of cubic Beziers to `points` (list of 2-vectors).

    Returns list of beziers, each (p0,p1,p2,p3) as np arrays.
    Endpoints of the polyline are honored exactly.
    """
    pts = _dedupe([_v(p) for p in points])
    if len(pts) < 2:
        return []
    left_t = _end_tangent(pts)
    right_t = _end_tangent(pts[::-1])
    out = []
    _fit_cubic(pts, left_t, right_t, error, out)
    return out


def _normalize(v):
    n = np.hypot(v[0], v[1])
    return v / n if n > 1e-12 else v


def _fit_cubic(pts, left_t, right_t, error, out, depth=0):
    if len(pts) == 2:
        dist = np.hypot(*(pts[1] - pts[0])) / 3.0
        bez = (pts[0], pts[0] + left_t * dist, pts[1] + right_t * dist, pts[1])
        out.append(bez)
        return

    u = _chord_length_param(pts)
    bez = _generate_bezier(pts, u, left_t, right_t)
    max_err, split = _compute_max_error(pts, bez, u)
    if max_err < error:
        out.append(bez)
        return

    # try reparameterization if we're reasonably close
    if max_err < error * error and depth < 24:
        for _ in range(4):
            u = _reparameterize(pts, u, bez)
            bez = _generate_bezier(pts, u, left_t, right_t)
            max_err, split = _compute_max_error(pts, bez, u)
            if max_err < error:
                out.append(bez)
                return

    # split at point of max error and recurse
    center_t = _normalize(pts[split - 1] - pts[split + 1])
    _fit_cubic(pts[:split + 1], left_t, center_t, error, out, depth + 1)
    _fit_cubic(pts[split:], -center_t, right_t, error, out, depth + 1)


def _chord_length_param(pts):
    u = [0.0]
    for i in range(1, len(pts)):
        u.append(u[-1] + np.hypot(*(pts[i] - pts[i - 1])))
    total = u[-1]
    if total <= 1e-12:
        return [i / (len(pts) - 1) for i in range(len(pts))]
    return [x / total for x in u]


def _bernstein(u):
    mu = 1.0 - u
    return (mu**3, 3 * u * mu**2, 3 * u**2 * mu, u**3)


def _generate_bezier(pts, u, left_t, right_t):
    p0, p3 = pts[0], pts[-1]
    A = []
    for ui in u:
        b0, b1, b2, b3 = _bernstein(ui)
        A.append((left_t * b1, right_t * b2))
    c00 = c01 = c11 = x0 = x1 = 0.0
    for i, ui in enumerate(u):
        a0, a1 = A[i]
        c00 += a0 @ a0
        c01 += a0 @ a1
        c11 += a1 @ a1
        b0, b1, b2, b3 = _bernstein(ui)
        tmp = pts[i] - (p0 * (b0 + b1) + p3 * (b2 + b3))
        x0 += a0 @ tmp
        x1 += a1 @ tmp
    det = c00 * c11 - c01 * c01
    det_a = c00 * x1 - c01 * x0
    det_b = x0 * c11 - x1 * c01
    alpha_l = det_b / det if abs(det) > 1e-12 else 0.0
    alpha_r = det_a / det if abs(det) > 1e-12 else 0.0
    seg = np.hypot(*(p3 - p0))
    # Near-singular/near-collinear systems can yield negative or blown-up
    # tangent magnitudes; clamp handles to the chord length and fall back to
    # the 1/3 heuristic when out of range. High-curvature spans get split by
    # the recursion instead of producing a wild control point.
    if not (1e-6 < alpha_l <= seg) or not (1e-6 < alpha_r <= seg):
        alpha_l = alpha_r = seg / 3.0
    return (p0, p0 + left_t * alpha_l, p3 + right_t * alpha_r, p3)


def _compute_max_error(pts, bez, u):
    max_err = 0.0
    split = len(pts) // 2
    for i in range(1, len(pts) - 1):
        pt = cubic_point(bez[0], bez[1], bez[2], bez[3], u[i])
        err = np.sum((pt - pts[i]) ** 2)
        if err > max_err:
            max_err = err
            split = i
    return math.sqrt(max_err), split


def _reparameterize(pts, u, bez):
    new = []
    for i, ui in enumerate(u):
        new.append(_newton_raphson(bez, pts[i], ui))
    return new


def _newton_raphson(bez, p, u):
    p0, p1, p2, p3 = bez
    d1 = [3 * (p1 - p0), 3 * (p2 - p1), 3 * (p3 - p2)]
    d2 = [6 * (p2 - 2 * p1 + p0), 6 * (p3 - 2 * p2 + p1)]
    q = cubic_point(p0, p1, p2, p3, u)
    mt = 1 - u
    q1 = mt * mt * d1[0] + 2 * mt * u * d1[1] + u * u * d1[2]
    q2 = mt * d2[0] + u * d2[1]
    num = (q - p) @ q1
    den = q1 @ q1 + (q - p) @ q2
    if abs(den) < 1e-12:
        return u
    return min(1.0, max(0.0, u - num / den))


# ---------------------------------------------------------------------------
# Surgical de-polygonization: keep existing curves, refit only line-runs
# ---------------------------------------------------------------------------

def _angle_between(v1, v2):
    a1 = math.atan2(v1[1], v1[0])
    a2 = math.atan2(v2[1], v2[0])
    d = a2 - a1
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def build_segments(contour):
    """Return (P, segs) for a closed defcon contour.

    P    : list of on-curve points (np 2-vec), cyclic (P[i] -> P[i+1] via segs[i]).
    segs : list, one per on-curve point, the segment FROM P[i] TO P[i+1]:
             ['line', smooth]                       a straight segment
             ['curve', off1, off2, smooth]          a cubic segment
           `smooth` is the smooth flag of the destination on-curve point P[i+1].
    """
    pts = list(contour)
    n = len(pts)
    start = next((i for i, p in enumerate(pts) if p.segmentType is not None), 0)
    order = [pts[(start + k) % n] for k in range(n)]
    order.append(order[0])
    P = [_v((order[0].x, order[0].y))]
    segs = []
    i = 0
    while i < len(order) - 1:
        j = i + 1
        offs = []
        while order[j].segmentType is None:
            offs.append(order[j])
            j += 1
        on = order[j]
        dest = _v((on.x, on.y))
        smooth = bool(on.smooth)
        if on.segmentType == "curve" and len(offs) >= 2:
            segs.append(['curve', _v((offs[0].x, offs[0].y)),
                         _v((offs[1].x, offs[1].y)), smooth])
        else:
            segs.append(['line', smooth])
        if j != len(order) - 1:
            P.append(dest)
        i = j
    return P, segs


def _run_corners(run_pts, angle_deg):
    """Interior indices (1..L-1) of run_pts that are sharp corners."""
    thresh = math.radians(angle_deg)
    corners = []
    for i in range(1, len(run_pts) - 1):
        v1 = run_pts[i] - run_pts[i - 1]
        v2 = run_pts[i + 1] - run_pts[i]
        if np.hypot(*v1) < 1e-9 or np.hypot(*v2) < 1e-9:
            continue
        if abs(_angle_between(v1, v2)) > thresh:
            corners.append(i)
    return corners


def _chord_dist(run_pts):
    """Max perpendicular distance of interior points from the end chord."""
    a, b = run_pts[0], run_pts[-1]
    ab = b - a
    L = np.hypot(*ab)
    if L < 1e-9:
        return max(np.hypot(*(p - a)) for p in run_pts)
    worst = 0.0
    for p in run_pts[1:-1]:
        d = abs(np.cross(ab, p - a)) / L
        worst = max(worst, d)
    return worst


def _fit_run(run_pts, error, angle_deg):
    """De-polygonize a line-run polyline into a list of segments.
    Output segs: ('curve', p0,p1,p2,p3) or ('line', p0, p3)."""
    out = []
    corners = [0] + _run_corners(run_pts, angle_deg) + [len(run_pts) - 1]
    for k in range(len(corners) - 1):
        sub = run_pts[corners[k]:corners[k + 1] + 1]
        if len(sub) == 2:
            out.append(('line', sub[0], sub[1]))
        elif _chord_dist(sub) <= error:
            out.append(('line', sub[0], sub[-1]))   # genuinely straight
        else:
            beziers = fit_curve(sub, error)
            if beziers:
                out.extend(('curve', *bz) for bz in beziers)
            else:
                out.append(('line', sub[0], sub[-1]))
    return out


def contour_polyline(contour, curve_samples=12):
    """Dense cyclic polyline of the whole contour, plus provenance.

    Returns (poly, P, segs, vtx_idx):
      poly    : list of np pts tracing the closed outline (no repeated close).
      P, segs : as build_segments.
      vtx_idx : vtx_idx[i] = index into `poly` of original on-curve point P[i].
    Curve segments are sampled into `curve_samples` steps.
    """
    P, segs = build_segments(contour)
    m = len(segs)
    poly = []
    vtx_idx = []
    for i in range(m):
        vtx_idx.append(len(poly))
        poly.append(P[i])
        if segs[i][0] == 'curve':
            _, o1, o2, _sm = segs[i]
            for fp in flatten_cubic(P[i], o1, o2, P[(i + 1) % m], curve_samples)[:-1]:
                poly.append(fp)
    return poly, P, segs, vtx_idx


def _vertex_corners(P, segs, angle_deg):
    """Corner indices among original on-curve points, from TRUE tangents
    (Bezier handles for curves, segment direction for lines). This ignores
    resampling noise so smooth bowls stay one span and cusps are kept."""
    m = len(segs)
    thresh = math.radians(angle_deg)
    corners = []
    for i in range(m):
        s = segs[i]                      # segment leaving P[i]
        out = (s[1] - P[i]) if s[0] == 'curve' else (P[(i + 1) % m] - P[i])
        ps = segs[(i - 1) % m]           # segment arriving at P[i]
        inc = (P[i] - ps[2]) if ps[0] == 'curve' else (P[i] - P[(i - 1) % m])
        if np.hypot(*out) < 1e-9 or np.hypot(*inc) < 1e-9:
            corners.append(i)            # degenerate -> keep as corner (safe)
            continue
        if abs(_angle_between(inc, out)) > thresh:
            corners.append(i)
    return corners


def process_contour_simplify(contour, error, angle_deg=30.0, curve_samples=12):
    """Unified clean-up: de-polygonize AND aggressively simplify dense curves.
    The contour is split only at genuine corners (true-tangent based); each
    smooth span is re-fit to the fewest cubics within `error`."""
    poly, P, segs, vtx_idx = contour_polyline(contour, curve_samples)
    n = len(poly)
    m = len(segs)
    if n < 4 or m < 2:
        return process_contour(contour, error, angle_deg)
    cverts = _vertex_corners(P, segs, angle_deg)

    def fit_chain(chain):
        if len(chain) == 2:
            return [('line', chain[0], chain[1])]
        if _chord_dist(chain) <= error:
            return [('line', chain[0], chain[-1])]
        bz = fit_curve(chain, error)
        return [('curve', *b) for b in bz] if bz else [('line', chain[0], chain[-1])]

    # Breakpoints (poly indices) where spans start/end. A fully smooth loop has
    # no corners; one lone corner gives a self-span. Both degenerate unless we
    # ensure at least two distinct breakpoints around the loop.
    bps = sorted({vtx_idx[c] for c in cverts})
    if len(bps) < 2:
        base = bps[0] if bps else 0
        bps = sorted({base, (base + n // 2) % n})

    out = []
    for idx in range(len(bps)):
        a = bps[idx]
        b = bps[(idx + 1) % len(bps)]
        chain = []
        k = a
        while True:
            chain.append(poly[k])
            if k == b:
                break
            k = (k + 1) % n
        out.extend(fit_chain(chain))
    return out


def process_contour(contour, error, angle_deg=42.0):
    """Surgically de-polygonize a contour. Existing curve segments are kept
    verbatim; maximal runs of line segments are refit to cubics where curved.

    Returns list of output segments, each ('curve', p0,p1,p2,p3) or
    ('line', p0, p3), tracing the closed contour. None if degenerate.
    """
    P, segs = build_segments(contour)
    m = len(segs)
    if m < 2 or len(P) < 2:
        return None
    types = [s[0] for s in segs]

    # Fully polygonal: one cyclic run.
    if all(t == 'line' for t in types):
        run = [P[k % m] for k in range(m + 1)]  # closed loop P0..P0
        return _fit_run(run, error, angle_deg) or None

    # Rotate so we start at the beginning of a curve segment; then no line-run
    # wraps across the array boundary.
    rot = types.index('curve')
    P = [P[(rot + k) % m] for k in range(m)]
    segs = [segs[(rot + k) % m] for k in range(m)]
    types = [s[0] for s in segs]

    out = []
    i = 0
    while i < m:
        p0 = P[i]
        if types[i] == 'curve':
            _, o1, o2, _sm = segs[i]
            out.append(('curve', p0, o1, o2, P[(i + 1) % m]))
            i += 1
        else:
            j = i
            while j < m and types[j] == 'line':
                j += 1
            run = [P[k % m] for k in range(i, j + 1)]  # P[i]..P[j] inclusive
            out.extend(_fit_run(run, error, angle_deg))
            i = j
    return out


# ---------------------------------------------------------------------------
# Deviation QA
# ---------------------------------------------------------------------------

def sample_segments(segs, per_curve=16):
    pts = []
    for s in segs:
        if s[0] == 'line':
            pts.append(s[1])
        else:
            _, p0, p1, p2, p3 = s
            pts.append(p0)
            pts.extend(flatten_cubic(p0, p1, p2, p3, per_curve)[:-1])
    return pts


def max_deviation(orig_poly, segs):
    """Max distance from sampled new outline to original polyline (closed)."""
    new_pts = sample_segments(segs)
    op = np.array(orig_poly + [orig_poly[0]])
    seg_a = op[:-1]
    seg_b = op[1:]
    ab = seg_b - seg_a
    ab_len2 = np.sum(ab * ab, axis=1)
    ab_len2[ab_len2 < 1e-12] = 1e-12
    worst = 0.0
    for q in new_pts:
        t = np.clip(np.sum((q - seg_a) * ab, axis=1) / ab_len2, 0, 1)
        proj = seg_a + (t[:, None] * ab)
        d = np.min(np.hypot(proj[:, 0] - q[0], proj[:, 1] - q[1]))
        if d > worst:
            worst = d
    return worst
