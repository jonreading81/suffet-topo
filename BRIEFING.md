# Briefing for Claude CLI

Read this to understand the project, then help me set it up as a Git repo and evolve it.

## What this is

A generator that turns **GPS-tagged boulder photos + a spreadsheet** into a **PDF topo**
and a **standalone offline HTML map** for the boulders around the Refuge du Suffet
(Vallon d'Ambin, Haute-Maurienne, French Alps). It's branded to the refuge
(`refugedusuffet.fr`): blue `#004AAD`, teal `#6AB0AB`, lavender `#A096EF`, logo in headers.

See `README.md` for the full workflow and data model. Quick version:

- One spreadsheet row per **problem**; columns `photo, boulder, no, problem, grade, notes, line`.
- `photo` filename links a row to its image and to GPS (read from EXIF, not the sheet).
- `line` = topo line as `x,y` points in **percent of the image**, produced by the annotator.
- `grade` = Fontainebleau `4`–`8C` or `Project`.
- Maps = **IGN Géoplateforme** WMTS tiles (orthophoto + PlanIGN topo), open data.
- Offline HTML embeds tiles + photos as base64 (Leaflet, vendored).

## Current state

- `generate.py` — a single **working** script (folder in → PDF + HTML out). Verified on
  the sample in `data/`. It's reconstructed from prototype code and is deliberately
  monolithic.
- `tools/boulder-line-annotator.html` — standalone offline annotator (draw lines, export
  rows; decodes HEIC in-browser).
- `templates/…-template.xlsx` — blank sheet with an in-sheet grade dropdown.
- `assets/` — logos + vendored Leaflet.
- `data/` — one sample boulder (`38.jpg` + `boulders.xlsx`).
- `examples/` — sample generated PDF + HTML.

## What I'd like help with

1. **Initialise the Git repo** with a sensible first commit.
   - **The repo is public.**
   - **Photos are committed directly** into `data/photos/` (normal Git, **no Git LFS**).
     There will only ever be ~30 photos, so plain Git is fine; do not set up LFS.
   - GPS in the photos is intentionally public (it's a topo).
   - `.gitignore` already excludes `output/`. Leave the commented `data/photos/` block
     commented (photos ARE committed). The `data/photos/.gitkeep` placeholder can be deleted
     once real photos are present.
2. **Refactor `generate.py`** from one file into modules, roughly:
   `topo/exif.py`, `topo/lines.py` (smoothing + drawing), `topo/tiles.py` (IGN fetch/stitch/
   bundle), `topo/pdf.py`, `topo/html.py`, `topo/style.py` (brand tokens/config), with
   `generate.py` as a thin CLI entry point. Keep behaviour identical; add a couple of tests
   (e.g. `parse_line`, `catmull`, EXIF parsing on a fixture).
3. **Config**: lift the hard-coded bits (refuge coordinates, brand palette, zoom range,
   line palette) into a small config module or a `config.yaml`.
4. **Known limitations to keep in mind / fix later**: assumes one photo per boulder; needs
   internet at build time; no caching of tiles between runs (there's an in-memory cache
   only); intermediate `_map.jpg` / `_boulder_N.jpg` are written into `output/`.

## Expect to iterate on style

The visual design (line colours, project styling, fonts, layout) is not final — we'll keep
tweaking it. Please keep styling centralised (in `style.py` / config) so changes are one-touch
and stay consistent across the PDF, the offline HTML, and the annotator preview.

## French PDF (specced — please build into the modular version)

Generate the PDF in **French as well as English** from the same data:

- CLI: `--lang {en,fr,both}`, default `both` → writes
  `refuge-du-suffet-boulders.pdf` and `refuge-du-suffet-boulders-fr.pdf`.
- **Translatable labels** (the template chrome only) live in a `LABELS = {"en": {...},
  "fr": {...}}` dict in `style.py`/config: e.g. Location→Localisation, Altitude→Altitude,
  Photo bearing→Orientation photo, Problems→Voies, "getting there"→"accès",
  "From the refuge"→"Depuis le refuge", the accuracy warning
  ("low confidence, verify on map"→"faible précision, à vérifier sur la carte"),
  and the project legend ("Dashed line + open marker = project (unclimbed)"→
  "Ligne pointillée + marqueur ouvert = projet (non réalisé)").
- **Grades**: map `Project` → `Projet` in FR; Font grades (6B, etc.) are unchanged.
- **Content**: boulder names, problem names, grades, GPS and the map are **identical**
  across languages (language-neutral identifiers — do not translate them).
- **Only `notes` (beta) is content-translatable**, via an optional **`notes_fr`** column:
  the FR PDF uses `notes_fr` when it has a value, else falls back to `notes`. The template
  already includes this column.
- The offline HTML can stay English for now (or gain the same treatment later).
- **Annotator parity:** `tools/boulder-line-annotator.html` already exports the 8-column
  row (`photo, boulder, no, problem, grade, notes, notes_fr, line`) and uses the brand
  line palette. Keep the annotator's columns and preview colours in lock-step with the
  template and the renderer whenever either changes.

## Nice-to-haves (later)

- Embed the real **Aleo** font (the site's heading typeface) into PDF + HTML instead of the
  serif fallback currently used.
- Keep the annotator's preview palette in sync with the render palette.
- Optional GPX export; optional per-boulder inset maps; multi-photo boulders.
