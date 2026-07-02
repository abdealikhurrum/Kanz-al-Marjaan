#!/usr/bin/env python3
"""Audit (and fix) `curs` feature anchors against the actual outline geometry.

HarfBuzz aligns each glyph's EXIT anchor (left side, x~0) with the next
glyph's ENTRY anchor (right side, x~advance). If an anchor's y does not sit
at the vertical centre of the connecting stroke measured from the outlines,
the whole glyph gets shifted vertically at that join -- a step at the seam
even when the outlines themselves would have lined up perfectly (this is
what made the initial kaf sit 21u below the noon-zain ligature in كنز).

For every `pos cursive` rule this script measures the outline seam (a
vertical cross-section just inside the join line, within the baseline band)
and reports rules whose anchor y deviates from the stroke centre.

With --apply it rewrites the anchor y to the measured stroke centre, but
ONLY where the seam is unambiguously a canonical baseline connecting stub
(bottom within [-50, 60], thickness within [120, 235]). Intentional
non-baseline joins (jeem/ain-class top entries, bari-yeh cascades) and junk
rules on non-joining glyphs never measure as such a stub and are left alone.

  python scripts/curs_audit.py [--src UFO] [--tol 3] [--apply]
"""
import sys, os, re, argparse
from defcon import Font

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from join_diag import flat, _cross_pair

SRC = "sources/KanzAlMarjaan-Regular.ufo"
FEA = os.path.join(SRC, "features.fea")
YWIN = (-60, 470)   # baseline band where cursive connections live
INSET = 6           # measure this far inside the join line

RULE_RE = re.compile(
    r"pos cursive (\S+) "
    r"<anchor (?:(-?\d+) (-?\d+)|NULL)> "
    r"<anchor (?:(-?\d+) (-?\d+)|NULL)>;")


def parse_rules(fea_path):
    """-> list of (glyphname, entry(x,y)|None, exit(x,y)|None)"""
    rules = []
    for line in open(fea_path):
        m = RULE_RE.search(line)
        if m:
            n, ex_, ey, xx, xy = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            entry = (int(ex_), int(ey)) if ex_ is not None else None
            exit_ = (int(xx), int(xy)) if xx is not None else None
            rules.append((n, entry, exit_))
    return rules


def seam(font, name, side):
    """Outline cross-section at the join line. -> (bottom, top) or None."""
    g = font[name]
    polys = flat(font, g)
    if not polys:
        return None
    x = INSET if side == "exit" else g.width - INSET
    return _cross_pair(polys, x, YWIN)


def is_stub(bot, top):
    """A canonical baseline connecting stub: sits on the baseline with the
    standard connecting-stroke thickness."""
    return -50 <= bot <= 60 and 120 <= top - bot <= 235


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--tol", type=float, default=3.0)
    ap.add_argument("--apply", action="store_true",
                    help="rewrite anchor y to the stroke centre for stub seams")
    args = ap.parse_args()
    fea_path = os.path.join(args.src, "features.fea")
    font = Font(args.src)
    rules = parse_rules(fea_path)
    print(f"curs rules: {len(rules)}")

    bad, dead = [], []
    for name, entry, exit_ in rules:
        if name not in font:
            continue
        for side, a in (("entry", entry), ("exit", exit_)):
            if a is None:
                continue
            s = seam(font, name, side)
            if s is None:
                dead.append((name, side, a))
                continue
            bot, top = s
            center = (bot + top) / 2
            dy = a[1] - center
            if abs(dy) > args.tol:
                bad.append((abs(dy), name, side, a[1], center, top - bot,
                            is_stub(bot, top)))

    bad.sort(reverse=True)
    print(f"\nanchor y != outline stroke centre (|dy| > {args.tol}u): {len(bad)}")
    print(f"{'glyph':34s} {'side':5s} {'anchor_y':>8s} {'centre':>7s} {'thick':>6s} {'dy':>6s}  fix?")
    for dy, name, side, ay, c, th, stub in bad:
        print(f"{name:34s} {side:5s} {ay:8d} {c:7.1f} {th:6.1f} {ay - c:+6.1f}  {'STUB-FIX' if stub else 'keep'}")

    print(f"\nrules with NO outline seam at the join line (likely junk / non-joining): {len(dead)}")
    for name, side, a in dead[:60]:
        print(f"  {name:34s} {side:5s} anchor={a}")
    if len(dead) > 60:
        print(f"  ... and {len(dead) - 60} more")

    if not args.apply:
        return
    fix = {}
    for dy, name, side, ay, c, th, stub in bad:
        if stub:
            fix.setdefault(name, {})[side] = round(c)
    rules_by_name = {n: (e, x) for n, e, x in rules}
    out, n_edit = [], 0
    for line in open(fea_path):
        m = RULE_RE.search(line)
        if m and m.group(1) in fix:
            name = m.group(1)
            entry, exit_ = rules_by_name[name]
            want = fix[name]
            if "entry" in want:
                entry = (entry[0], want["entry"])
            if "exit" in want:
                exit_ = (exit_[0], want["exit"])
            en = "<anchor %d %d>" % entry if entry else "<anchor NULL>"
            ex = "<anchor %d %d>" % exit_ if exit_ else "<anchor NULL>"
            line = "  pos cursive %s %s %s;\n" % (name, en, ex)
            n_edit += 1
        out.append(line)
    open(fea_path, "w").writelines(out)
    print(f"\nAPPLIED: rewrote {n_edit} cursive rules ({sum(len(v) for v in fix.values())} anchors) in {fea_path}")


if __name__ == "__main__":
    main()
