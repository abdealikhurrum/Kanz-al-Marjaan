# Kanz al Marjaan

![Kanz al Marjaan](documentation/sample-hero.png)

**Kanz al Marjaan** is an open-source Naskh typeface for the Arabic script. It is
built for fully **vocalised** text — every haraka, shadda, tanwīn and
dagger-alef is positioned with care, including across letters that join and
ligate — and it extends coverage to **Lisan al-Dawat**, an Arabic-script
orthography that adds a set of Gujarati-derived letters.

The family ships a single Regular weight as a static TTF, and is built with the
[Google Fonts](https://github.com/googlefonts/gftools) tooling.

## Samples

Fully vocalised Arabic (Universal Declaration of Human Rights, Article 1):

![Vocalised specimen](documentation/sample-vocalized.png)

Character coverage — Arabic and the Lisan al-Dawat extensions:

![Character set](documentation/sample-charset.png)

## Features

- **Full vocalisation.** Harakat, shadda, tanwīn and the dagger-alef are
  anchored to sit cleanly on each letter — placed on the letter's visual centre,
  always clearing the consonant dots (a mark never falls between the rasm and its
  nuqta).
- **Per-component marks on ligatures.** Where letters fuse into a ligature, each
  component still carries its own haraka at the right place — across the standard
  Arabic ligatures and several hundred Lisan al-Dawat calligraphic forms — with
  the marks kept evenly spaced.
- **Lisan al-Dawat support.** Gujarati-derived letters and the script's
  calligraphic joining forms, alongside the full Arabic set.
- **Connected Naskh.** Cursive attachment and contextual joining for smooth,
  continuous letterforms.
- **Google Fonts ready.** Naming, metadata, coverage and shaping follow the GF
  specification.

## Building from source

The font is built from the UFO source in `sources/` with the gftools builder.

```sh
# Python 3.10 is recommended (matches CI)
python3.10 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# full build -> fonts/ttf/ + fonts/webfonts/
gftools builder sources/config.yaml

# quick single-master build while iterating
fontmake -u sources/KanzAlMarjaan-Regular.ufo -o ttf --output-path /tmp/KanzAlMarjaan.ttf
```

The `scripts/` directory contains the tooling used to develop and validate mark
positioning (annotation-sheet generators, anchor calibrators, the
mark-to-ligature rollout generator, and a collision/nuqta-overlap checker).

## License

This font is licensed under the SIL Open Font License, Version 1.1 — see
[`OFL.txt`](OFL.txt). It may be used, studied, modified and redistributed freely
as long as it is not sold on its own. It includes work derived from Adobe's
Source family and from the Fatemi Maqala project (both OFL).

## Credits

Designed and maintained by the Kanz al Marjaan project authors (see
[`AUTHORS.txt`](AUTHORS.txt) and [`CONTRIBUTORS.txt`](CONTRIBUTORS.txt)).
Contributions and issue reports are welcome.
