#!/usr/bin/env python3
"""Scan REAL shaped text for entry/exit misalignment at cursive joins.

Shapes a corpus of letter pairs and triples with HarfBuzz against the built
TTF, rasterizes each joining seam (both glyphs, with the actual cursive-
attachment offsets applied), and looks for a *staircase*: an abrupt jump of
BOTH the top and the bottom ink edge in the same direction right at the seam
column (e.g. the initial kaf sitting ~21u below the noon-zain ligature in
كنز). Because overlapping strokes merge in the raster exactly as the reader
sees them, intentional cascade joins (bari-yeh tails sweeping under, top
entries into jeem/ain heads) measure clean.

Also reports SPURIOUS attachments: cursive rules firing across a pair that
does not join per the shaper (junk anchors), displacing a glyph vertically.

Results are aggregated per (right-glyph, left-glyph) pair with an example
string, worst first. Run before/after an anchor fix to prove improvement.

  python scripts/join_scan.py [--ttf PATH] [--tol 8] [--out out/join/scan.txt]
"""
import sys, os, argparse, unicodedata
import numpy as np
import uharfbuzz as hb
import freetype
from fontTools.ttLib import TTFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
UFO = "sources/KanzAlMarjaan-Regular.ufo"
PPEM = 512                 # raster resolution (2 font units / px at upm 1024)
WIN = 5                    # columns to inspect either side of the seam
CANVAS_TOP = 1000          # font units covered above/below baseline
CANVAS_BOT = -800

# liga-forming tails: c2+c3 suffixes that produce medial/final ligature glyphs
TAILS = ["ے", "ی", "ي", "ى", "ھے", "ہے", "ھی", "ھا", "ما", "مد", "جے", "حے", "چے",
         "ئے", "ئی", "بے", "تے", "نے", "یے", "ھ", "ہ", "م", "ن", "ر", "ز", "د", "ج", "ح", "ع"]


def cmap_letters(tt):
    out = []
    for cp in tt.getBestCmap():
        ch = chr(cp)
        if not (0x0600 <= cp <= 0x077F or 0x08A0 <= cp <= 0x08FF):
            continue
        cat = unicodedata.category(ch)
        if cat == "Lo" or cp == 0x0640:
            out.append(ch)
    return sorted(out)


def runs_of(col):
    """Ink runs (top_px, bot_px) in a boolean column, top of image = 0."""
    idx = np.where(col)[0]
    if not len(idx):
        return []
    out = []
    start = prev = idx[0]
    for i in idx[1:]:
        if i > prev + 1:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    return out


def seam_staircase(img, seam_px, sc):
    """Largest same-direction jump (font units) of both edges of a matched
    ink run between adjacent columns around the seam. img: bool [H, W]."""
    H, W = img.shape
    worst = 0.0
    for c in range(max(0, seam_px - WIN), min(W - 1, seam_px + WIN)):
        a, b = runs_of(img[:, c]), runs_of(img[:, c + 1])
        for ra in a:
            for rb in b:
                if ra[0] > rb[1] or rb[0] > ra[1]:
                    continue                      # no vertical overlap
                dtop = (rb[0] - ra[0]) / sc       # px -> font units
                dbot = (rb[1] - ra[1]) / sc
                if dtop * dbot > 0:
                    s = min(abs(dtop), abs(dbot)) * (1 if dtop > 0 else -1)
                    if abs(s) > abs(worst):
                        worst = s
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ttf", default=TTF)
    ap.add_argument("--ufo", default=UFO)
    ap.add_argument("--tol", type=float, default=8.0)
    ap.add_argument("--out", default="out/join/scan.txt")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    tt = TTFont(args.ttf)
    names = tt.getGlyphOrder()
    with open(args.ttf, "rb") as fh:
        hbfont = hb.Font(hb.Face(fh.read()))
    face = freetype.Face(args.ttf)
    upm = face.units_per_EM
    face.set_pixel_sizes(0, PPEM)
    sc = PPEM / upm

    bcache = {}

    def bitmap(gid):
        """(bool array, bitmap_left, bitmap_top) at PPEM, unhinted."""
        if gid not in bcache:
            face.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            g = face.glyph
            bm = g.bitmap
            a = (np.frombuffer(bytes(bm.buffer), "uint8")
                 .reshape(bm.rows, bm.width) > 128) if bm.width and bm.rows else np.zeros((0, 0), bool)
            bcache[gid] = (a, g.bitmap_left, g.bitmap_top)
        return bcache[gid]

    def shape(text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hbfont, buf)
        return buf

    joins_cache = {}

    def joins_left(span):
        """Does this character span connect to a following letter? True iff
        its last glyph changes when a tatweel is appended (data-driven; no
        Unicode joining tables needed). Tatweel itself always joins."""
        if span not in joins_cache:
            if span.endswith("ـ"):
                joins_cache[span] = True
            else:
                a = shape(span).glyph_infos
                b = shape(span + "ـ").glyph_infos
                # visual order: the span's last (leftmost) glyph is a[0]
                joins_cache[span] = len(b) < len(a) + 1 or a[0].codepoint != b[1].codepoint
        return joins_cache[span]

    letters = cmap_letters(tt)
    corpus = [a + b for a in letters for b in letters]
    corpus += [a + t for a in letters for t in TAILS]
    common = [c for c in "بتنیکلمسعحجدرزوقفطصغخشضظثہھءةگپچڈڑژٹ" if c in letters]
    corpus += [a + "ـ" + b for a in common for b in common]
    corpus += ["ب" + a + "ب" for a in letters]              # a in MEDIAL form
    corpus += ["ب" + a + t for a in letters for t in TAILS]  # medial exit into ligature
    corpus += [a + b + "ب" for a in common for b in common]  # init-liga exits, medial chains
    print(f"letters: {len(letters)}   corpus strings: {len(corpus)}")

    PAD = 600                      # font units of slack either side of the pen run
    H = int((CANVAS_TOP - CANVAS_BOT) * sc)

    agg = {}         # (rname, lname) -> (staircase, example)  real joins only
    spurious = {}    # (rname, lname) -> (dy, example)  attachment on non-joining pair
    for text in corpus:
        buf = shape(text)
        infos, poss = buf.glyph_infos, buf.glyph_positions
        pen = 0
        placed = []      # (gid, name, origin, cluster, seam_x_right_edge)
        for info, pos in zip(infos, poss):
            nm = names[info.codepoint]
            placed.append((info.codepoint, nm, (pen + pos.x_offset, pos.y_offset),
                           info.cluster, pen + pos.x_advance))
            pen += pos.x_advance
        seams = []       # (j, seam_x) needing raster measurement
        for j in range(len(placed) - 1):
            _, lname, lorig, lcl, seam = placed[j]
            _, rname, rorig, rcl, _ = placed[j + 1]
            key = (rname, lname)
            rspan = text[rcl:lcl]          # chars of the right glyph
            if not rspan:                  # same cluster: no evaluable seam
                continue
            if not joins_left(rspan):
                dy = rorig[1] - lorig[1]
                if abs(dy) > 2 and (key not in spurious or abs(dy) > abs(spurious[key][0])):
                    spurious[key] = (dy, text)
                continue
            seams.append((j, seam))
        if not seams:
            continue
        # rasterize the whole string once
        W = int((pen + 2 * PAD) * sc) + 2
        img = np.zeros((H, W), bool)
        for gid, nm, (gx, gy), _, _ in placed:
            a, bl, bt = bitmap(gid)
            if not a.size:
                continue
            x0 = int(round((gx + PAD) * sc)) + bl
            y0 = int(round((CANVAS_TOP - gy) * sc)) - bt
            x1, y1 = x0 + a.shape[1], y0 + a.shape[0]
            cx0, cy0 = max(0, x0), max(0, y0)
            cx1, cy1 = min(W, x1), min(H, y1)
            if cx0 >= cx1 or cy0 >= cy1:
                continue
            img[cy0:cy1, cx0:cx1] |= a[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        for j, seam in seams:
            _, lname, _, _, _ = placed[j]
            _, rname, _, _, _ = placed[j + 1]
            key = (rname, lname)
            s = seam_staircase(img, int(round((seam + PAD) * sc)), sc)
            if key not in agg or abs(s) > abs(agg[key][0]):
                agg[key] = (s, text)

    bad = [(abs(s), s, rn, ln, ex) for (rn, ln), (s, ex) in agg.items() if abs(s) > args.tol]
    bad.sort(reverse=True)
    spur = sorted(((abs(d), d, rn, ln, ex) for (rn, ln), (d, ex) in spurious.items()), reverse=True)
    with open(args.out, "w") as fh:
        fh.write(f"joining seam pairs measured: {len(agg)}   staircase > {args.tol}u: {len(bad)}\n")
        fh.write(f"{'right glyph (exit)':38s} {'left glyph (entry)':38s} {'step':>7s}  example\n")
        for _, s, rn, ln, ex in bad:
            fh.write(f"{rn:38s} {ln:38s} {s:+7.1f}  {ex}\n")
        fh.write(f"\nSPURIOUS attachments on non-joining pairs: {len(spur)}\n")
        for _, d, rn, ln, ex in spur:
            fh.write(f"{rn:38s} {ln:38s} {d:+7d}  {ex}\n")
    print(f"joining seam pairs measured: {len(agg)}   staircase > {args.tol}u: {len(bad)}")
    print(f"spurious attachments on non-joining pairs: {len(spur)}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
