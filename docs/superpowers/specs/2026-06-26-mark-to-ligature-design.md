# Mark-to-Ligature Attachment — Design Spec

**Date:** 2026-06-26
**Font:** Kanz al Marjaan (`sources/KanzAlMarjaan-Regular.ufo`)
**Status:** Design — pending feasibility gate (Phase 0)

## 1. Goal

Make every multi-component ligature carry **per-component harakat**: when a user
types a vocalised cluster (each consonant followed by its eraab), each haraka must
land over *its own* component letter, not pile onto a single anchor.

Example — typing lam+fatha, lam+kasra, heh+damma must put the fatha on the first
lam, the kasra under the second lam, and the damma on the heh of the **Allah**
ligature. Today all three stack at one point.

## 2. Current state / problem

- Ligature glyphs (e.g. `uniFDF2`, `MHMD.liga`, `uni0626062C0645.liga…`, the LD
  calligraphic set) carry a **single** `pos base <anchor> mark @t.uni064B / @b.uni064D_1`
  in lookup `mark_arab_1` of `features.fea`. One top anchor, one bottom anchor for
  the whole glyph.
- Verified behaviour: typing a ligature with interspersed harakat keeps them in one
  cluster and attaches **all** of them to that single anchor → they overlap.
- The font has **zero** `pos ligature` (mark-to-ligature) rules today.
- These ligature glyphs are GDEF-classed as **base (class 1)**, not **ligature
  (class 2)**.

## 3. Scope

**In scope:** all multi-component ligatures in the font (hundreds), primarily the
3-component LD calligraphic set plus core ligatures (Allah, Muhammad, lam-alef
where it takes marks, the bee/feh/hah families). A glyph is in scope if it is
formed by a GSUB ligature substitution of ≥2 inputs **and** can carry harakat.

**Out of scope:** single-component positional forms (already handled by
sub-project 1), glyph outline redesign, new ligatures, non-Arabic scripts.

## 4. Mechanism

OpenType **mark-to-ligature** (GPOS LigatureAttach), authored in `features.fea`:

```
pos ligature LIG
        <anchor x1t y1t> mark @t.uni064B  <anchor x1b y1b> mark @b.uni064D_1   # component 1
    ligComponent
        <anchor x2t y2t> mark @t.uni064B  <anchor x2b y2b> mark @b.uni064D_1   # component 2
    ligComponent
        <anchor x3t y3t> mark @t.uni064B  <anchor x3b y3b> mark @b.uni064D_1;  # component 3
```

- Reuses the existing mark classes `@t.uni064B` (top) and `@b.uni064D_1` (bottom);
  no new mark classes.
- Component **order is logical** (first-typed = `ligComponent` 1). For RTL Arabic,
  logical-first is the **rightmost** glyph visually, so anchor x-positions
  generally *descend* as the component index rises.
- HarfBuzz assigns each interspersed mark to a component via the ligature-component
  info recorded by the GSUB `LigatureSubst` that formed the glyph. This is the load-
  bearing assumption — see Phase 0.

**GDEF:** the ligature glyphs must be reclassified from base → **ligature (class 2)**.
In this UFO the GDEF GlyphClassDef is produced by ufo2ft; reclassification is done
by setting each glyph's `public.openTypeCategories` (or the relevant UFO
category/`GDEF` source) to `ligature`. Exact lever to be confirmed during Phase 0.

## 5. Phase 0 — feasibility spike (GATE)

Phase 0 proves the **table/mechanism** — that a `pos ligature` rule makes HarfBuzz
distribute interspersed marks to separate components. **Allah is the right POC for
this** (it forces the mark-distribution question), but it is **not** a good test of
the equal-spacing heuristic (its components are uneven — the tall lam stack with
shadda + dagger). Equal-spacing is validated separately in §6 on **yjm or MHMD**,
which have more uniform component layout.

Steps:

1. **Target the no-built-in-marks form.** When vocalised, the form *without* built-in
   marks must be used: typing Allah with interspersed marks forms
   `uni064406440647.isol` (plain lam-lam-heh), **not** the decorative `uniFDF2`
   (which carries a built-in shadda + dagger). HarfBuzz already selects this when
   marks are present; the spike confirms it and anchors that glyph (3 components:
   lam, lam, heh).
2. Hand-write a `pos ligature` rule for it (3 components). The **general anchor
   locations are inferred from the existing colored-oval annotations** on Allah.
3. Reclassify it to GDEF ligature.
4. Rebuild (`fontmake -u … -o ttf --output-path /tmp/_kam_new.ttf`) and shape the
   realistic vocalisation: **lam + kasra, lam + shadda + kharo-zabar (superscript
   alef U+0670), heh + kasra** — i.e. component 1 takes a bottom mark, component 2 a
   stacked top mark, component 3 a bottom mark. (Mixing top and bottom across
   components is the real distribution test.)
5. **Pass criterion:** each mark lands on its own component at the authored anchors,
   no pile-up — kasra under lam 1, shadda+kharo-zabar over lam 2, kasra under heh.

If it passes → proceed to §6 rollout. If HarfBuzz does **not** distribute the marks
(e.g. component info missing, or the GSUB rule type doesn't carry it), **stop** and
redesign — possible fallbacks: adjust how the ligature is formed in GSUB, or accept
single-anchor with best-effort centering. No large build until this gate passes.

## 6. Anchor-derivation heuristic (Approach C)

For each in-scope ligature, auto-generate per-component anchors, then correct the
tail by annotation.

**Component count & identity:** read from the glyph name (the encoded 4-hex groups,
e.g. `uni0626062C0645.liga…` = 3 components) and/or the GSUB `sub … by LIG` inputs.

**Placement — equal-spacing first.** Per the agreed principle: *reasonably equal
spacing of the eraab across the ligature is more important than each mark sitting
exactly above its component's centroid.* So:

- Distribute N top anchors at evenly-spaced x across the ligature ink width
  (RTL-ordered: component 1 = rightmost), each at a y that clears the local ink
  column top + a fixed gap (reuse the gap calibrated in sub-project 1).
- Mirror for the N bottom anchors below the ink.
- Refine x using ink **mass-centroid** awareness per band (consistent with the
  sub-project-1 rule) but bounded by the equal-spacing constraint.

**Calibration:** tune the spacing/gap constants against **yjm and MHMD** (the
uniform-component ligatures that actually exercise equal spacing); use Allah only to
confirm the table works, not to tune spacing. The hand-annotated colored ovals are
the ground truth.

**Correction loop:** render batches with `liga_sheet.py`-style contact sheets;
annotate problem ligatures with the existing colored-oval convention; feed through
an adapted `read_liga_marks.py` that writes per-component anchors. Automation does
the bulk; annotation cleans the tail.

## 7. Tooling

- **Reuse:** `liga_sheet.py` (render vocalised ligatures), `read_liga_marks.py`
  (adapt: emit `pos ligature` component anchors, not single `pos base`),
  `collision_test.py` (+ `COLLISION_TTF` env), the `fontmake` fast loop.
- **New:** a generator that enumerates in-scope ligatures, derives per-component
  anchors (§6), and writes the `pos ligature` block + GDEF reclassification.

## 8. Validation

- **Per-component shaping check:** for each ligature, shape the vocalised form and
  assert each mark attaches to a distinct component near its anchor.
- **Collision test:** `collision_test.py` + supplementary scan over vocalised
  ligatures must stay at **0** (current baseline).
- **Visual:** contact sheets of vocalised ligatures, before/after.

## 9. Risks & open questions

- **R1 (highest):** HarfBuzz may not distribute marks to components for these
  glyphs → entire Phase 0 gate. 
- **R2:** vocalised forms differing from unvocalised forms (Allah). Mitigation:
  always target the glyph that appears *with* marks; enumerate by shaping vocalised
  input.
- **R3:** GDEF reclassification lever in this UFO/ufo2ft pipeline — confirm in Phase 0.
- **R4:** auto component-region location on merged/reshaped outlines is imprecise;
  mitigated by the equal-spacing heuristic + annotation correction.
- **R5:** scale (hundreds of glyphs, each 2×N anchors) — generated, not hand-written;
  keep the `features.fea` block machine-regenerable.

## 10. Workflow integration

All edits in `sources/KanzAlMarjaan-Regular.ufo` (`features.fea` + any UFO
category/GDEF source). Do **not** clobber the committed gftools binary; verify with
the `/tmp/_kam_new.ttf` fast build. Final font produced by the normal gftools
pipeline.

## 11. Build sequence (high level)

1. Phase 0 spike on Allah (table/mechanism) → gate.
2. Enumerate in-scope ligatures + component counts.
3. Build the anchor generator (equal-spacing heuristic, calibrated on yjm/MHMD).
4. Generate `pos ligature` block + GDEF reclassification; rebuild.
5. Validate (shaping + collision + visual); correction-loop the tail.
