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

from topo.data import build_boulders, cluster_by_lon_gap, load_rows
from topo.html import build_html
from topo.lines import render_boulder_photo
from topo.pdf import build_pdf
from topo.style import BRIDGES, IGN_TOPO, REFUGE
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

    # Two cover maps: a wider regional (getting-there) view using the IGN
    # topo layer for road / place-name legibility, and the close-up aerial
    # showing the refuge + boulders.
    map_points = [
        {"lat": b["lat"], "lon": b["lon"], "name": b["name"], "label": str(b["id"])}
        for b in boulders
    ]
    stitch_map(
        map_points,
        REFUGE,
        os.path.join(args.output, "_map_regional.jpg"),
        z=12,
        layer=IGN_TOPO,
        fmt="image/png",
        Hc=480,
        show_boulders=False,
    )
    # Cluster the boulders into 3 spatial groups (by natural longitude gaps)
    # so the overview can show 3 range-labelled markers instead of 26
    # overlapping pins. Each cluster then gets its own zoomed detail map.
    clusters, no_gps_boulders = cluster_by_lon_gap(boulders, n_clusters=3)
    # Stamp the cluster letter on each boulder so downstream code (PDF pages)
    # can reference it.
    cluster_letters = "ABCDEFGHIJKL"
    cluster_infos = []
    for idx, cluster in enumerate(clusters):
        letter = cluster_letters[idx]
        ids = sorted(int(b["id"]) for b in cluster)
        # Use U+2212 MINUS SIGN (not the en-dash) — the minus sign is designed
        # to sit at digit-centre height in most fonts, so the label reads
        # visually balanced with the numbers on either side.
        cluster_range = f"{ids[0]}−{ids[-1]}" if len(ids) > 1 else str(ids[0])
        problem_count = sum(len(b["problems"]) for b in cluster)
        lat_c = sum(b["lat"] for b in cluster) / len(cluster)
        lon_c = sum(b["lon"] for b in cluster) / len(cluster)
        for b in cluster:
            b["_cluster_letter"] = letter
            b["_cluster_range"] = cluster_range
        cluster_infos.append({
            "letter": letter,
            "range": cluster_range,
            "boulders": cluster,
            "problem_count": problem_count,
            "lat": lat_c,
            "lon": lon_c,
        })
    # Boulders with no GPS still deserve a mention in the legend but not on
    # any map — tag them so pdf.py can list them separately.
    for b in no_gps_boulders:
        b["_cluster_letter"] = None
        b["_cluster_range"] = None

    cluster_marker_points = [
        {"lat": ci["lat"], "lon": ci["lon"], "label": ci["range"]}
        for ci in cluster_infos
    ]
    stitch_map(
        cluster_marker_points,
        REFUGE,
        os.path.join(args.output, "_map.jpg"),
        layer=IGN_TOPO,
        fmt="image/png",
        marker_style="cluster",
        bridges=BRIDGES,
    )

    # One detail map per cluster — teardrop pins for the individual boulders,
    # auto-fit to the cluster's spatial extent. Boulders from other clusters
    # go in as `context_points` so any that fall inside the frame render as
    # ghosted markers, giving readers a sense of what's nearby.
    for ci in cluster_infos:
        detail_points = [
            {"lat": b["lat"], "lon": b["lon"], "name": b["name"], "label": str(b["id"])}
            for b in ci["boulders"]
        ]
        this_ids = {b["id"] for b in ci["boulders"]}
        other_points = [
            {"lat": b["lat"], "lon": b["lon"], "label": str(b["id"])}
            for b in boulders
            if b.get("_has_gps") and b["id"] not in this_ids
        ]
        stitch_map(
            detail_points,
            REFUGE,
            os.path.join(args.output, f"_map_cluster_{ci['letter']}.jpg"),
            layer=IGN_TOPO,
            fmt="image/png",
            fit_refuge=False,
            bridges=BRIDGES,
            context_points=other_points,
        )

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
        build_pdf(boulders, pdf_path, lang=lang, clusters=cluster_infos)

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
