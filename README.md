# Refuge du Suffet — bouldering topo generator

Turns a folder of **GPS-tagged boulder photos** plus a **spreadsheet of route data**
into two deliverables for the boulders around the Refuge du Suffet (Vallon d'Ambin,
Haute-Maurienne, French Alps):

- a print-ready **PDF topo**
- a standalone **offline HTML map** (IGN tiles + photos embedded — works with no phone signal)

Everything is styled to the refuge's identity (deep blue `#004AAD`, teal `#6AB0AB`,
lavender `#A096EF` for projects; logo in the headers).

---

## Getting started

### Requirements

- **Python 3.10+** (used by the topo generator + PDF builder)
- **Node 20+** (used by the local editor app)
- **Internet at build time** — the map layer fetches IGN tiles when generating

### First-time setup

Two one-off installs, from the repo root:

```bash
# 1. Python side — for generate.py (PDF/HTML build)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Node side — for the editor app
cd editor && npm install && cd ..
```

## Everyday workflow

Once set up, the whole loop lives inside the editor app:

```bash
cd editor && npm start
# open http://localhost:3000
```

The editor lets you:

- **Browse** every boulder in `data/boulders.csv` from the left-hand list (with a
  thumbnail of the associated photo).
- **Edit** a boulder's name, photo, and its problems' number / name / grade / notes
  (EN and FR); autosaves in memory, writes to CSV when you hit **Save Boulders**.
- **Draw lines** — click **Draw line** on a problem, click on the photo to add
  points, drag handles to nudge them, double-click a handle to remove it, hit
  Enter/Esc to finish. Lines are Catmull-Rom smoothed as you draw.
- **Upload photos** — click **Upload…** in the boulder header; the file is copied
  into `data/photos/` (spaces in filenames become underscores).
- **Add / delete boulders** — `+ Add boulder` in the sidebar; each row has an `×`
  on the right to delete.
- **Generate PDFs** — click **Generate PDFs** to shell out to `generate.py`; a
  panel shows a spinner while it runs (~10s) then links you straight to the
  resulting PDFs (EN + FR).

Everything the editor changes lands in `data/boulders.csv` on save and
`data/photos/` on upload — plain files you can also edit by hand or commit to
git.

## Generating outputs

Any time you hit **Generate PDFs** in the editor, this is what runs under the
hood. You can also run it directly:

```bash
.venv/bin/python generate.py --input data --output output
```

→ writes to `output/`:

- `refuge-du-suffet-boulders.pdf` (English)
- `refuge-du-suffet-boulders-fr.pdf` (French)
- `refuge-du-suffet-boulders.html` (offline map)

Useful flags:

- `--lang {en,fr,both}` — default `both`; skip a language if you don't need it.
- `--no-html` — skip the ~10s IGN tile bundle. Handy while iterating on PDF
  style; also the default when generating via the editor.

### Data model

- **One row per problem.** A boulder with several problems = several rows sharing the
  same `photo` filename and `boulder` name.
- `photo` — filename in `data/photos/`; the key linking a row to its image and GPS.
- `no` — problem number on that boulder (sets the marker number and order).
- `grade` — Fontainebleau `4`–`8C`, or `Project` for unclimbed lines.
- `line` — the topo line from the editor, as `x,y` points in **percent of the image**
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
├── editor/                # local Node/Express editor — browse/edit boulders +
│   │                      # upload photos + draw lines, writes to data/boulders.csv
│   ├── server.js
│   ├── package.json
│   └── public/            # vanilla-JS SPA served by server.js
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
