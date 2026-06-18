#!/usr/bin/env python3
"""De-duplicate identical / near-identical glyph outlines by replacing the
redundant glyphs with a single-component reference to a canonical base.

Default is a DRY RUN: detects exact + near-duplicate groups (within --thresh,
translation-invariant), prints them, and renders overlays for the NON-exact
(near) pairs so they can be reviewed/vetoed. Nothing is written without --apply.

  python scripts/dedup.py --thresh 3            # detect + render overlays
  python scripts/dedup.py --thresh 3 --apply    # componentize (minus --veto)
  python scripts/dedup.py --thresh 3 --apply --veto glyphA,glyphB
"""
import sys, os, argparse
from collections import defaultdict
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curve_cleanup as cc
from curve_cleanup_run import _passthrough, _seg_path_points

SRC = "sources/KanzAlMarjaan-Regular.ufo"


def glyph_origin(g):
    xs = [p.x for c in g for p in c]
    ys = [p.y for c in g for p in c]
    return (min(xs), min(ys)) if xs else (0, 0)


def sampled_contours(g, translate=(0, 0)):
    dx, dy = translate
    out = []
    for c in g:
        out.append([np.array((p[0] - dx, p[1] - dy), float)
                    for p in _seg_path_points(_passthrough(c), 20)])
    return out


def _directed(a, b):
    """Max over points of a of distance to nearest contour of b (greedy)."""
    used = set()
    worst = 0.0
    for ca in a:
        best, bi = 1e9, -1
        for j, cb in enumerate(b):
            if j in used:
                continue
            segs = [('line', cb[k], cb[k + 1]) for k in range(len(cb) - 1)]
            d = cc.max_deviation(ca, segs)
            if d < best:
                best, bi = d, j
        if bi >= 0:
            used.add(bi)
        worst = max(worst, best)
    return worst


def glyph_dev(a, b):
    """True symmetric Hausdorff between two sampled contour lists (same contour
    count). Both directions, so mirrored shapes (bracketleft vs bracketright)
    score high and are NOT treated as duplicates."""
    if len(a) != len(b):
        return 1e9
    return max(_directed(a, b), _directed(b, a))


def detect(font, thresh):
    data = {}
    for g in font:
        if len(g) == 0:
            continue
        org = glyph_origin(g)
        data[g.name] = (sampled_contours(g, org), org, len(list(g)))
    # bucket to limit comparisons
    buckets = defaultdict(list)
    for nm, (sc, org, nc) in data.items():
        xs = [p[0] for c in sc for p in c]
        ys = [p[1] for c in sc for p in c]
        w = max(xs) - min(xs) if xs else 0
        h = max(ys) - min(ys) if ys else 0
        buckets[(nc, round(w / 12), round(h / 12))].append(nm)

    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    pair_dev = {}
    for names in buckets.values():
        if len(names) < 2:
            continue
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                d = glyph_dev(data[names[i]][0], data[names[j]][0])
                if d <= thresh:
                    parent.setdefault(names[i], names[i])
                    parent.setdefault(names[j], names[j])
                    parent[find(names[i])] = find(names[j])
                    pair_dev[(names[i], names[j])] = d
                    pair_dev[(names[j], names[i])] = d
    groups = defaultdict(set)
    for nm in list(parent):
        groups[find(nm)].add(nm)
    return [sorted(v) for v in groups.values() if len(v) > 1], pair_dev, data


def pick_base(font, members):
    def key(n):
        g = font[n]
        has_uni = 0 if (g.unicodes) else 1   # prefer encoded
        return (has_uni, len(n), n)
    return sorted(members, key=key)[0]


def group_max_dev(members, pair_dev):
    worst = 0.0
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            worst = max(worst, pair_dev.get((members[i], members[j]), 0.0))
    return worst


def render_overlay(font, base, member, path, size=420):
    pad = 30
    gb, gm = font[base], font[member]
    ob, om = glyph_origin(gb), glyph_origin(gm)
    pb = sampled_contours(gb, ob)
    pm = sampled_contours(gm, om)
    allp = [p for c in pb + pm for p in c]
    xs = [p[0] for p in allp]; ys = [p[1] for p in allp]
    minx, miny = min(xs), min(ys)
    w = max(max(xs) - minx, 1); h = max(max(ys) - miny, 1)
    sc = (size - 2 * pad) / max(w, h)
    img = Image.new("RGB", (size, size + 30), "white")
    d = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except Exception:
        fnt = ImageFont.load_default()

    def tx(p):
        return (pad + (p[0] - minx) * sc, size - pad - (p[1] - miny) * sc)
    for c in pb:
        d.line([tx(p) for p in c], fill=(210, 30, 30), width=3)
    for c in pm:
        d.line([tx(p) for p in c], fill=(30, 130, 30), width=1)
    d.text((pad, 6), f"base {base} (red)  vs  {member} (green)", fill="black", font=fnt)
    img.save(path)


def componentize(glyph, base_name, offset):
    glyph.clearContours()
    # remove any pre-existing components, then add the single reference
    for comp in list(glyph.components):
        glyph.removeComponent(comp)
    pen = glyph.getPointPen()
    pen.addComponent(base_name, (1, 0, 0, 1, offset[0], offset[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresh", type=float, default=3.0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--veto", default="", help="comma-separated glyph names to keep as-is")
    ap.add_argument("--outdir", default="out/dedup")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    veto = set(x for x in args.veto.split(",") if x)

    font = Font(SRC)
    groups, pair_dev, data = detect(font, args.thresh)
    groups.sort(key=lambda m: (-group_max_dev(m, pair_dev), -len(m)))

    n_members = sum(len(g) for g in groups)
    n_redundant = sum(len(g) - 1 for g in groups)
    print(f"groups: {len(groups)}  glyphs involved: {n_members}  redundant: {n_redundant}")

    plan = []   # (member, base, offset, dev)
    near_imgs = []
    for gi, members in enumerate(groups):
        base = pick_base(font, members)
        gmax = group_max_dev(members, pair_dev)
        kind = "EXACT" if gmax < 0.05 else f"NEAR {gmax:.1f}u"
        print(f"\n[{kind}] base={base}")
        ob = glyph_origin(font[base])
        for m in members:
            if m == base:
                continue
            om = glyph_origin(font[m])
            offset = (om[0] - ob[0], om[1] - ob[1])
            dev = pair_dev.get((base, m), gmax)
            star = " (VETOED)" if m in veto else ""
            print(f"    {m:42s} dev={dev:4.1f}u  offset={offset}{star}")
            p = os.path.join(args.outdir, f"{gi:02d}_{m.replace('/','_')}.png")
            render_overlay(font, base, m, p)
            near_imgs.append(p)
            if m not in veto:
                plan.append((m, base, offset, dev))

    print(f"\nnear-dup overlays rendered: {len(near_imgs)} in {args.outdir}/")
    if args.apply:
        for m, base, offset, dev in plan:
            componentize(font[m], base, offset)
        font.save(SRC)
        print(f"APPLIED: {len(plan)} glyphs componentized -> {SRC}")
    else:
        print(f"DRY RUN: would componentize {len(plan)} glyphs "
              f"(use --apply; --veto to exclude). EXACT merge automatically; "
              f"review near overlays first.")


if __name__ == "__main__":
    main()
