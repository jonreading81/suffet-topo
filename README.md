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
3. **Record** the rows in a spreadsheet (`templates/…-template.xlsx`), columns:
   `photo, boulder, no, problem, grade, notes, line`.
4. **Generate** the outputs:
   ```bash
   pip install -r requirements.txt
   python generate.py --input data --output output
   ```
   → `output/refuge-du-suffet-boulders.pdf` and `…-boulders.html`

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
├── generate.py            # build script: folder in → PDF + offline HTML out
├── requirements.txt
├── tools/
│   └── boulder-line-annotator.html   # draw problem lines, export sheet rows (offline)
├── templates/
│   └── refuge-du-suffet-boulders-template.xlsx  # blank sheet w/ grade dropdown
├── assets/
│   ├── logo.svg / logo_white.svg / logo_white.png
│   └── vendor/leaflet.js, leaflet.css           # vendored for the offline map
├── data/                  # your project data (sample included)
│   ├── boulders.xlsx
│   └── photos/38.jpg
├── examples/              # sample generated outputs
└── output/                # generated (gitignored)
```

## Notes & caveats

- `generate.py` is an early, working starting point reconstructed from prototype code.
  It currently assumes **one photo per boulder** and needs **internet at build time**
  (to fetch IGN tiles). Refactoring into modules + tests is expected.
- Real photo sets contain the **GPS of specific boulders**. This repo is **public** and
  photos are **committed directly** (~30 max, so plain Git — no LFS needed); the coordinates
  are intentionally published as part of the topo.
- Map data © IGN / Géoplateforme. Leaflet is BSD-licensed (see `assets/vendor`).
