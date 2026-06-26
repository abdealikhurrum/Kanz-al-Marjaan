"""Mark-positioning / collision evaluation for the built TTF using collidoscope.

Scans base x mark combinations, mark stacking, and realistic vocalised words,
reporting any glyph collisions (with a small area tolerance to ignore the
normal mark-on-its-own-base overlap).
"""
import os
from collidoscope import Collidoscope

# kurbopy renamed BezPath.fromDrawable -> from_drawable in newer builds; shim it
import kurbopy
if not hasattr(kurbopy.BezPath, "fromDrawable") and hasattr(kurbopy.BezPath, "from_drawable"):
    kurbopy.BezPath.fromDrawable = kurbopy.BezPath.from_drawable

TTF = os.environ.get("COLLISION_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")

BASES = list("بتثجحخدذرزسشصضطظعغفقكلمنهوي") + ["ک", "گ", "ہ", "ھ"]
TOP = {
    "fatha": "َ", "damma": "ُ", "sukun": "ْ", "shadda": "ّ",
    "fathatan": "ً", "dammatan": "ٌ", "hamza_above": "ٔ",
    "madda": "ٓ", "superscript_alef": "ٰ",
    "small_high_tah(NEW)": "ؕ", "noon_ghunna(NEW)": "٘",
}
BOT = {
    "kasra": "ِ", "kasratan": "ٍ",
    "subscript_alef(NEW)": "ٖ",
}
STACKS = {
    "shadda+fatha": "َّ", "shadda+kasra": "ِّ",
    "shadda+damma": "ُّ", "shadda+fathatan": "ًّ",
}
WORDS = {
    "Muhammad": "مُحَمَّدٌ", "Bismillah": "بِسْمِ", "Allah": "اللَّهِ",
    "al-rahman": "الرَّحْمٰنِ", "kitab": "كِتَابٌ", "qul": "قُلْ",
}

rules = {"marks": True, "bases": True, "faraway": True,
         "adjacent_clusters": True, "cursive": False, "area": 100}
c = Collidoscope(TTF, rules, direction="RTL")

def scan(label, mapping, base=None):
    hits = []
    for name, marks in mapping.items():
        text = (base + marks) if base else marks
        cols = c.has_collisions(c.get_glyphs(text))
        if cols:
            pairs = ", ".join("%s/%s" % (a["name"], b["name"]) for a, b in
                              [(x["glyph1"], x["glyph2"]) for x in cols])
            hits.append((name, text, len(cols), pairs))
    return hits

total = 0
collisions = []

# base x mark matrix
for b in BASES:
    for grp in (TOP, BOT):
        for mname, mk in grp.items():
            total += 1
            cols = c.has_collisions(c.get_glyphs(b + mk))
            if cols:
                collisions.append((b + mk, mname,
                                   [(x["glyph1"]["name"], x["glyph2"]["name"]) for x in cols]))

# stacking on a few bases
for b in ["ب", "ح", "م", "ل", "ك"]:
    for sname, sk in STACKS.items():
        total += 1
        cols = c.has_collisions(c.get_glyphs(b + sk))
        if cols:
            collisions.append((b + sk, sname,
                               [(x["glyph1"]["name"], x["glyph2"]["name"]) for x in cols]))

# realistic words
for wname, w in WORDS.items():
    total += 1
    cols = c.has_collisions(c.get_glyphs(w))
    if cols:
        collisions.append((w, wname,
                           [(x["glyph1"]["name"], x["glyph2"]["name"]) for x in cols]))

print("Tested %d shaped strings (area tolerance=%d)." % (total, rules["area"]))
print("Collisions found in %d strings:\n" % len(collisions))
for text, label, pairs in collisions:
    print("  %-12s [%s]  %s" % (text, label, pairs))
if not collisions:
    print("  NONE")
