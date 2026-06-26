# Kanz Al Marjaan: new Arabic typeface

## What

Adds **Kanz Al Marjaan**, a Naskh-style Arabic typeface (one Regular weight,
static TTF). Beyond standard Arabic it covers the extended letters used to write
**Lisan al-Dawat** (the Dawoodi Bohra register written in Arabic script) — e.g.
heh-goal, the doachashmee/jhatka heh final, gaf, tcheh, ddal, peh, jeh and
related forms — with full vocalisation (iʿrāb) support.

- **Upstream:** https://github.com/HatimMasvi/Kanz-al-Marjaan
- **Designer:** Sh Moiz Sh Zohair bhai
- **License:** SIL Open Font License 1.1
- **Category:** Sans Serif / Arabic (Naskh)
- **Primary script:** `Arab` (with a Latin kernel for fallback)
- **Version:** 2.00

## Scripts & coverage

- **Arabic** — design script. ~500 Arabic-block + presentation-form codepoints;
  GSUB (init/medi/fina/isol, rlig/liga/ccmp/calt) and GPOS (mark/curs/kern)
  shaping, vocalisation marks, and the Lisan al-Dawat extended set.
- **Latin** — minimal kernel for fallback only (GF_Latin_Kernel), drawn from
  **Source Sans 3** (OFL). The Reserved Font Name 'Source' is declared in
  OFL.txt; Adobe is credited in the description.
- `meta` table declares `dlng: Arab`, `slng: Arab,Latn`.

## QA

Built with `gftools builder`; checked with Font Bakery (GF profile).

**0 FATAL.** The remaining checks are known non-defects:

- `glyph_coverage` — expects GF_Latin_Core only when no METADATA.pb with
  `primary_script` is present; with `primary_script: Arab` the font fully
  covers the required GF_Latin_Kernel. Resolves once METADATA.pb is generated.
- `shape_languages` — flags edge cases for a complex Arabic font: mark-on-tatweel
  (HarfBuzz treats U+0640 as transparent), and shadda+vowel stacking (handled via
  precomposed combos rather than `mkmk`, which renders correctly in real
  vocalised text). Plus a niche Farsi saria-heh display preference.
- Remaining ERRORs require METADATA.pb / remote GF data to run (and CJK
  vertical-metrics checks are not applicable to this non-CJK font).

Recent fixes in this submission branch: corrected `arabic_high_hamza` (U+0675),
resolved the Allah-ligature double-diacritics, and added letter-spacing kerns
for non-joining finals before tight initials (daal/thaal/ddal → tooth letters;
alef and lam-alef → kaf/gaf).

## Checklist

- [ ] Upstream repo public, with sources and a build that reproduces the binaries
- [ ] OFL.txt present; license + Reserved Font Name correct
- [ ] `DESCRIPTION.en_us.html` present (credits Source Sans 3)
- [ ] `primary_script: Arab` to be set in METADATA.pb
- [ ] Font Bakery: 0 FATAL; remaining items documented above
