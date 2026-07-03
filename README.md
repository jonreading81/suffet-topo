# Refuge du Suffet — bouldering topo generator

Turns a folder of **GPS-tagged boulder photos** plus a **spreadsheet of route data**
into two deliverables for the boulders around the Refuge du Suffet (Vallon d'Ambin,
Haute-Maurienne, French Alps):

- a print-ready **PDF topo**
- a standalone **offline HTML map** (IGN tiles + photos embedded — works with no phone signal)

Everything is styled to the refuge's identity (deep blue `#004AAD`, teal `#6AB0AB`,
lavender `#A096EF` for projects; logo in the headers).

---

## How it works

1. **Shoot** boulders with location services on (JPEG is smoother than HEIC).
2. **Annotate** each photo in `tools/boulder-line-annotator.html` — a standalone,
   offline page: open a photo, click each problem from base to top, set name + grade,
   and copy the spreadsheet-ready rows. Nothing uploads; HEIC is decoded in-browser.
3. **Record** the rows in a CSV (`templates/refuge-du-suffet-boulders-template.csv`
   is the starting shape), columns:
   `photo, boulder, no, problem, grade, notes, notes_fr, line`.
   Edit the CSV in any plain-text editor (VS Code, TextEdit) — Numbers can also open
   it, though pasting into an .xlsx-with-dropdown was flaky, which is why we're on CSV.
4. **Generate** the outputs:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python generate.py --input data --output output
   ```
   → `output/refuge-du-suffet-boulders.pdf`, `-fr.pdf`, and `-boulders.html`

   Useful flags: `--lang {en,fr,both}` (default `both`),
   `--no-html` (skip the ~10s tile bundle while iterating on PDF style).

### Data model

- **One row per problem.** A boulder with several problems = several rows sharing the
  same `photo` filename and `boulder` name.
- `photo` — filename in `data/photos/`; the key linking a row to its image and GPS.
- `no` — problem number on that boulder (sets the marker number and order).
- `grade` — Fontainebleau `4`–`8C`, or `Project` for unclimbed lines.
- `line` — the topo line from the annotator, as `x,y` points in **percent of the image**
  (e.g. `36.9,75.7 65.2,58.6 …`), so it renders identically at any size.
- **GPS is not in the sheet** — latitude/longitude/altitude/bearing/accuracy are read
  from each photo's EXIF at build time.

### Rendering conventions

- Lines: Catmull-Rom smoothing, white halo under a coloured line, numbered start marker.
- **Projects** render as a *dashed* line with a *hollow* marker (lavender), so unclimbed
  lines stand out from graded ones.
- Maps use **IGN Géoplateforme** WMTS tiles (orthophoto + PlanIGN topo) — open French
  national mapping. The offline HTML bundles a bounding-box of tiles as base64.

---

## Layout

```
suffet-topo/
├── generate.py            # thin CLI: parses args, orchestrates the topo/ modules
├── config.yaml            # refuge coords, brand palette, zoom range, PDF labels,
│                          # getting-there prose (edit this to tweak content/style)
├── requirements.txt
├── requirements-dev.txt   # + pytest, + playwright for HTML testing
├── topo/                  # library — imported by generate.py
│   ├── style.py           # loads config.yaml; hx()/font() helpers
│   ├── exif.py            # GPS EXIF reader
│   ├── lines.py           # parse_line, catmull, draw_dashed, render_boulder_photo
│   ├── tiles.py           # IGN fetch / stitch / bundle
│   ├── pdf.py             # print-ready PDF builder (EN + FR)
│   ├── html.py            # standalone offline HTML builder (EN)
│   └── data.py            # CSV / XLSX loading + boulder grouping
├── tools/
│   └── boulder-line-annotator.html   # draw problem lines, export TSV rows (offline)
├── templates/
│   └── refuge-du-suffet-boulders-template.csv  # starter CSV shape
├── assets/
│   ├── logo.svg / logo_white.svg / logo_white.png
│   └── vendor/leaflet.js, leaflet.css           # vendored for the offline map
├── data/                  # your project data (sample included)
│   ├── boulders.csv
│   └── photos/38.jpg
├── tests/                 # pytest — parse_line, catmull, EXIF fixture
├── examples/              # sample generated outputs
└── output/                # generated (gitignored)
```

## Notes & caveats

- Assumes **one photo per boulder** and needs **internet at build time** (to fetch IGN
  tiles for the getting-there map and the offline HTML bundle).
- Real photo sets contain the **GPS of specific boulders**. This repo is **public** and
  photos are **committed directly** (~30 max, so plain Git — no LFS needed); the coordinates
  are intentionally published as part of the topo.
- Map data © IGN / Géoplateforme. Leaflet is BSD-licensed (see `assets/vendor`).
