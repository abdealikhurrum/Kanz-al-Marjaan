#!/usr/bin/env python3
"""Phase 2 diagnostic (read-only): measure the cursive connection anchors of
every joining glyph and flag the ones that don't match the canonical join.

Arabic joins on the baseline. A glyph's EXIT (left, x=0) connects to the next
letter; its ENTRY (right, x=advance) connects to the previous one. For seamless
joins every exit/entry should share one baseline bottom (~0) and one stroke
thickness. We measure both and report the spread + outliers. Nothing is changed.

  python scripts/join_diag.py [--src UFO] [--out out/join]
"""
import sys, os, argparse
import numpy as np
from defcon import Font
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from curve_cleanup_run import _passthrough, _seg_path_points

SRC = "sources/KanzAlMarjaan-Regular.ufo"
FORMS = ("init", "medi", "fina", "isol")


def flat(font, g, off=(0, 0), dep=0):
    out = []
    for c in g:
        pts = [(p[0] + off[0], p[1] + off[1]) for p in _seg_path_points(_passthrough(c), 8)]
        if len(pts) >= 3:
            out.append(pts)
    if dep < 4:
        for cp in g.components:
            if cp.baseGlyph in font:
                t = cp.transformation
                out += flat(font, font[cp.baseGlyph], (off[0] + t[4], off[1] + t[5]), dep + 1)
    return out


def join_flags(name):
    """(has_entry, has_exit) from the suffix sequence of joining forms.
    Entry = connects to previous letter (first form is medi/fina).
    Exit  = connects to next letter (last form is init/medi)."""
    forms = [s for s in name.split(".") if s in FORMS]
    if not forms:
        return (False, False)
    return (forms[0] in ("medi", "fina"), forms[-1] in ("init", "medi"))


def _cross_pair(polys, xline, ywin):
    """Lowest pair of y-crossings of the vertical line x=xline (the connecting
    stroke). Returns (bottom, top) or None."""
    cr = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
            if (x0 - xline) * (x1 - xline) < 0:
                t = (xline - x0) / (x1 - x0)
                y = y0 + t * (y1 - y0)
                if ywin[0] <= y <= ywin[1]:
                    cr.append(y)
    cr.sort()
    return (cr[0], cr[1]) if len(cr) >= 2 else None


def anchor(polys, side, off=4, span=40, ywin=(-40, 470)):
    """Connection anchor + edge slopes. Crosses a line just inside the edge for
    height/thickness, and a second line `span` further into the glyph to get the
    top- and bottom-edge slopes (dy/dx, screen space) of the connecting stroke.
    A truly seamless join needs matching slopes across the seam, not just height."""
    allx = [p[0] for poly in polys for p in poly]
    if side == "entry":
        x1 = max(allx) - off; x2 = x1 - span
    else:
        x1 = min(allx) + off; x2 = x1 + span
    a1 = _cross_pair(polys, x1, ywin)
    a2 = _cross_pair(polys, x2, ywin)
    if not a1:
        return None
    bot, top = a1
    res = dict(edge_x=x1, bottom=bot, top=top, center=(bot + top) / 2, thick=top - bot)
    if a2 and (x1 - x2) != 0:
        res["bot_slope"] = (a1[0] - a2[0]) / (x1 - x2)
        res["top_slope"] = (a1[1] - a2[1]) / (x1 - x2)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default="out/join")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    font = Font(args.src)

    entries, exits = {}, {}     # name -> anchor
    for g in font:
        he, hx = join_flags(g.name)
        if not (he or hx):
            continue
        polys = flat(font, g)
        if not polys:
            continue
        if he:
            a = anchor(polys, "entry")
            if a:
                entries[g.name] = a
        if hx:
            a = anchor(polys, "exit")
            if a:
                exits[g.name] = a

    def stats(d, key):
        return np.array([v[key] for v in d.values()])

    ent_thick = stats(entries, "thick"); ent_bot = stats(entries, "bottom")
    exi_thick = stats(exits, "thick"); exi_bot = stats(exits, "bottom")
    canon_thick = float(np.median(np.concatenate([ent_thick, exi_thick])))
    print(f"joining glyphs with ENTRY: {len(entries)}   with EXIT: {len(exits)}")
    print(f"canonical connection thickness (median): {canon_thick:.0f} u")
    print(f"  ENTRY thick  median={np.median(ent_thick):.0f}  IQR={np.percentile(ent_thick,25):.0f}-{np.percentile(ent_thick,75):.0f}")
    print(f"  EXIT  thick  median={np.median(exi_thick):.0f}  IQR={np.percentile(exi_thick,25):.0f}-{np.percentile(exi_thick,75):.0f}")
    print(f"  ENTRY bottom median={np.median(ent_bot):.0f}  (should be ~0; baseline)")
    print(f"  EXIT  bottom median={np.median(exi_bot):.0f}")

    # --- edge-angle (tangent) continuity ---
    import math
    def angles(d, key):
        v = [math.degrees(math.atan(a[key])) for a in d.values() if key in a]
        return np.array(v)
    print("\nJOIN EDGE ANGLES (deg from horizontal; for seamless joins entry & "
          "exit must MATCH):")
    for key, lbl in (("top_slope", "top edge"), ("bot_slope", "bottom edge")):
        e = angles(entries, key); x = angles(exits, key)
        print(f"  {lbl:11s} ENTRY median={np.median(e):+5.1f}deg (sd {e.std():4.1f})   "
              f"EXIT median={np.median(x):+5.1f}deg (sd {x.std():4.1f})   "
              f"mismatch={abs(np.median(e)-np.median(x)):.1f}deg")
    print("  -> nonzero sd = kinks within a class; entry/exit mismatch = step at the seam")

    # outliers: connection off the baseline, or thickness far from canonical
    def outliers(d, kind):
        out = []
        for n, a in d.items():
            off_base = abs(a["bottom"]) > 30
            bad_thick = abs(a["thick"] - canon_thick) > 0.25 * canon_thick
            if off_base or bad_thick:
                why = []
                if off_base: why.append(f"bottom={a['bottom']:.0f}")
                if bad_thick: why.append(f"thick={a['thick']:.0f}")
                out.append((n, kind, ", ".join(why)))
        return out

    outs = outliers(entries, "ENTRY") + outliers(exits, "EXIT")
    print(f"\nOUTLIER connections (off-baseline or wrong thickness): {len(outs)}")
    for n, k, why in sorted(outs)[:40]:
        print(f"  {k:5s} {n:40s} {why}")

    # histograms
    W, H = 1000, 360
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except Exception:
        f = ImageFont.load_default()

    def hist(vals, x0, y0, w, h, title, lo, hi, mark=None):
        bins = 50
        hh, _ = np.histogram(vals, bins=bins, range=(lo, hi))
        bw = w / bins; mh = max(hh.max(), 1)
        for i, c in enumerate(hh):
            bh = h * c / mh
            d.rectangle([x0 + i * bw, y0 + h - bh, x0 + (i + 1) * bw - 1, y0 + h],
                        fill=(70, 110, 200))
        if mark is not None:
            mx = x0 + (mark - lo) / (hi - lo) * w
            d.line([(mx, y0), (mx, y0 + h)], fill=(210, 40, 40), width=2)
        d.text((x0, y0 - 18), title, fill=(20, 20, 20), font=f)
        d.text((x0, y0 + h + 4), f"{lo:.0f}", fill=(120, 120, 120), font=f)
        d.text((x0 + w - 30, y0 + h + 4), f"{hi:.0f}", fill=(120, 120, 120), font=f)

    hist(np.concatenate([ent_thick, exi_thick]), 60, 40, 400, 230,
         "connection thickness (u)", 0, 300, mark=canon_thick)
    hist(np.concatenate([ent_bot, exi_bot]), 540, 40, 400, 230,
         "connection bottom / baseline offset (u)", -120, 200, mark=0)
    img.save(os.path.join(args.out, "join_hist.png"))
    print(f"\nhistograms -> {args.out}/join_hist.png")
    print(f"canonical join target:  bottom=0, thickness={canon_thick:.0f}u")


if __name__ == "__main__":
    main()
