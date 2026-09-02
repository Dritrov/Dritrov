# WIRMAN 25–220 kVA datasheets — redesigned, five themes

Redesigned technical datasheets for the WIRMAN diesel generator sets
(WM-25 … WM-220 kVA, 50 Hz). The data comes from the original 2023 PDFs in
Dropbox `/Specifikat/WIRMAN NEW 2023 -`; obvious spelling and unit errors were
corrected (see *Content corrections* below), everything else is unchanged.

```
wirman-specs/
├── build.py                 # renders HTML from the template and prints PDFs with headless Chromium
├── data/models.json         # all datasheet content (shared text + per-model values)
├── template/datasheet.html.j2
├── assets/fonts/            # Inter (variable) + Barlow Condensed, embedded in the PDFs
├── output/<theme>/          # WIRMAN <n> KVA.pdf — 3 A4 pages each
└── preview/<theme>/         # PNG page previews (not committed)
```

## Themes

| key          | look                                                                 |
|--------------|----------------------------------------------------------------------|
| `classic`    | navy band header, amber accents, ratings table in a white card       |
| `industrial` | charcoal + red, diagonal stripe, ratings as stat tiles, flat tables  |
| `minimal`    | white, black rules, teal accent, large editorial model number        |
| `premium`    | graphite + gold, layered 3D cards, isometric shaded genset illustration generated from each model's W×L×H |
| `graphite`   | dark graphite gradient, electric-blue accents, glass rating cards    |

All five share the same three-page structure: (1) ratings + engine /
alternator / dimensions, (2) scope of supply, compliance, rating definitions,
(3) DSE6120 MKIII control unit. Colours are defined in `THEMES` in
`build.py`; theme-specific layout rules live in `{% if t.key == ... %}`
blocks of the template.

## Build

Requirements: Python 3.10+, `jinja2`, a Chromium/Chrome binary
(`CHROME_BIN` env var, or the Playwright chromium under `/opt/pw-browsers`),
optionally `pymupdf` for PNG previews.

```bash
python3 build.py                     # all models, all themes
python3 build.py 25 220              # only the listed kVA sizes
python3 build.py classic minimal     # only the listed themes
python3 build.py --no-preview        # skip PNG previews
```

## Editing content

Everything printed on the sheets lives in `data/models.json`:

- `models[]` — per-size values (ratings, engine, alternator, dimensions).
  Values shared by every size live in `engine_common` / `alternator_common`
  and can be overridden per model.
- top-level keys — text shared by all sheets (certifications, PRP/ESP
  definitions, standard features, canopy specification, DSE6120 MKIII page).

Re-run `build.py` after editing.

## Content corrections applied to the 2023 originals

Spelling / wording: *Standart Voltage → Standard Voltage*, *Antifreezze →
antifreeze*, *Gurantee → guarantee*, *Residencial → Residential*,
*redressor → rectifier*, *Mechanic → Mechanical*, *Sound Proof → Soundproof*,
*THREE PHASES → THREE-PHASE*, *EC mark → CE marked*, *r.p.m → rpm*,
*1.500 rpm → 1500 rpm*, directive numbers normalised (2014/30/EU etc.),
trailing full stops removed from bullet lists.

Values:

- 25 kVA fuel tank: original read “09”, printed as 90 lt — please confirm.
- 90 kVA: injection / aspiration were swapped; now *Direct Injection* /
  *Turbo Charged*.
- 40–90 kVA: cylinders shown as “4 In line” (confirmed by bore × stroke ×
  4 = stated displacement).
- 125–220 kVA: “6 Stroke - Diesel” corrected to “4 Stroke - Diesel”; the
  cylinder count is left as “In line” because bore × stroke does not match
  the stated displacement for either 4 or 6 cylinders — please confirm.
- 180 kVA compression ratio “17:5” → 17.5:1; 220 kVA “16:4:1” → 16.4:1.
- 220 kVA displacement was a copy of the compression ratio in the original;
  it is printed as “—” until the real value is supplied.
- Bore × stroke written uniformly as “115 x 135”.
