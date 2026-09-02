# WIRMAN 25–220 kVA datasheets — 2023 series, redesigned layout

Redesigned technical datasheets for the WIRMAN diesel generator sets
(WM-25 … WM-220 kVA, 50 Hz). The content (every value, label, bullet and
paragraph) is the one from the original PDFs in Dropbox
`/Specifikat/WIRMAN NEW 2023 -`; only the layout, typography and colours
changed.

```
wirman-specs/
├── build.py                 # renders HTML from the template and prints PDFs with headless Chromium
├── data/models.json         # all datasheet content (shared text + per-model values)
├── template/datasheet.html.j2
├── assets/fonts/            # Inter (variable) + Barlow Condensed, embedded in the PDFs
└── output/                  # WIRMAN <n> KVA.pdf — the deliverables (3 A4 pages each)
```

## Build

Requirements: Python 3.10+, `jinja2`, a Chromium/Chrome binary
(`CHROME_BIN` env var, or the Playwright chromium under `/opt/pw-browsers`),
optionally `pymupdf` for PNG previews.

```bash
python3 build.py              # all nine models
python3 build.py 25 220       # only the listed kVA sizes
python3 build.py --no-preview # skip PNG previews (written to preview/)
```

## Editing content

Everything printed on the sheets lives in `data/models.json`:

- `models[]` — per-size values (ratings, engine, alternator, dimensions).
  Values shared by every size live in `engine_common` / `alternator_common`
  and can be overridden per model.
- top-level keys — text shared by all sheets (certifications, PRP/ESP
  definitions, standard features, canopy specification, DSE6120 MKIII page).

Re-run `build.py` after editing.

## Design

- A4 portrait, three pages: (1) ratings + engine/alternator/dimensions,
  (2) scope of supply, compliance and rating definitions, (3) DSE6120 MKIII
  control unit.
- Palette: navy `#0B2740` / amber `#F2A900`; type: Barlow Condensed for
  display, Inter for body copy.
- The canopy outline on page 1 is generated from each model's W×L×H, and the
  control-unit front panel is a stylised vector drawing with numbered
  callouts matching the original button labels.
