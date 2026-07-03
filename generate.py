#!/usr/bin/env python3
"""Refuge du Suffet bouldering topo generator — CLI entry point.

Turns a folder of GPS-tagged boulder photos + a spreadsheet of route data into:
  - a print-ready PDF topo (`topo.pdf`)
  - a standalone offline HTML map (`topo.html`)

Usage:
    python generate.py --input data --output output

Input folder layout:
    data/
      boulders.xlsx            (or .csv) with columns:
                               photo, boulder, no, problem, grade, notes, line
      photos/<the image files referenced in the `photo` column>

Notes:
  - GPS/altitude/bearing/accuracy are read from each photo's EXIF (not the sheet).
  - `line` is a list of "x,y" points as PERCENT of the image (from the annotator).
  - Needs internet at build time to fetch IGN map tiles.
"""
import argparse
import base64
import io
import os
import sys

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pass

from topo.data import build_boulders, load_rows
from topo.html import build_html
from topo.lines import render_boulder_photo
from topo.pdf import build_pdf
from topo.style import REFUGE
from topo.tiles import bundle_tiles, stitch_map


def main():
    ap = argparse.ArgumentParser(
        description="Generate the Refuge du Suffet bouldering topo (PDF + offline HTML)."
    )
    ap.add_argument(
        "--input",
        default="data",
        help="input folder (spreadsheet + photos/)",
    )
    ap.add_argument(
        "--output",
        default="output",
        help="output folder",
    )
    ap.add_argument(
        "--lang",
        choices=("en", "fr", "both"),
        default="both",
        help="PDF language(s). 'both' writes -fr.pdf alongside the EN one.",
    )
    ap.add_argument(
        "--no-html",
        action="store_true",
        help="Skip the offline HTML build (skips the ~10s IGN tile bundle — "
        "handy while iterating on the PDF).",
    )
    args = ap.parse_args()

    photos_dir = os.path.join(args.input, "photos")
    sheets = [
        f
        for f in os.listdir(args.input)
        if f.lower().endswith((".xlsx", ".csv")) and not f.startswith("~")
    ]
    if not sheets:
        sys.exit("No .xlsx/.csv spreadsheet found in " + args.input)
    sheet_path = os.path.join(args.input, sheets[0])
    print("Spreadsheet:", sheet_path)

    os.makedirs(args.output, exist_ok=True)
    rows = load_rows(sheet_path)
    boulders = build_boulders(rows, photos_dir)
    print(
        f"{len(boulders)} boulder(s), "
        f"{sum(len(b['problems']) for b in boulders)} problem(s)"
    )

    # render each boulder photo with its lines (full-res for PDF, small for HTML)
    for b in boulders:
        if os.path.exists(b["photo_path"]):
            big = render_boulder_photo(b["photo_path"], b["problems"], max_px=1100)
            b["_render"] = os.path.join(args.output, f"_boulder_{b['id']}.jpg")
            big.save(b["_render"], "JPEG", quality=88)
            small = render_boulder_photo(b["photo_path"], b["problems"], max_px=560)
            buf = io.BytesIO()
            small.save(buf, "JPEG", quality=72)
            b["_photo_uri"] = (
                "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            )
        else:
            b["_render"] = None
            b["_photo_uri"] = None
            print("  photo missing:", b["photo_path"])

    # getting-there map
    map_points = [
        {"lat": b["lat"], "lon": b["lon"], "name": b["name"], "label": str(b["id"])}
        for b in boulders
    ]
    stitch_map(map_points, REFUGE, os.path.join(args.output, "_map.jpg"))

    # bounding box for offline tiles (around refuge + boulders, padded)
    lats = [REFUGE["lat"]] + [b["lat"] for b in boulders]
    lons = [REFUGE["lon"]] + [b["lon"] for b in boulders]
    padlat, padlon = 0.004, 0.006
    bbox = (
        min(lats) - padlat,
        min(lons) - padlon,
        max(lats) + padlat,
        max(lons) + padlon,
    )

    langs = ("en", "fr") if args.lang == "both" else (args.lang,)
    for lang in langs:
        suffix = "" if lang == "en" else f"-{lang}"
        pdf_path = os.path.join(
            args.output, f"refuge-du-suffet-boulders{suffix}.pdf"
        )
        print(f"Building PDF ({lang}) -> {os.path.basename(pdf_path)}")
        build_pdf(boulders, pdf_path, lang=lang)

    if args.no_html:
        print("Skipping offline HTML (--no-html).")
    else:
        print("Bundling offline tiles (needs internet)...")
        tiles = bundle_tiles(bbox)
        print(f"  {len(tiles)} tiles bundled")
        print("Building offline HTML...")
        build_html(
            boulders,
            REFUGE,
            tiles,
            bbox,
            os.path.join(args.output, "refuge-du-suffet-boulders.html"),
        )
    print("Done ->", args.output)


if __name__ == "__main__":
    main()
