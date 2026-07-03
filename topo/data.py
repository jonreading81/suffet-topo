"""Spreadsheet loading and boulder grouping.

Rows are one problem each; boulders are the unique `boulder` values, keyed in
insertion order. GPS/altitude/bearing/accuracy come from each boulder's photo
(EXIF), not the sheet.
"""
import csv
import os

from .exif import read_gps
from .lines import parse_line
from .style import BRAND, LINE_PALETTE, REFUGE


def load_rows(sheet_path):
    """Load rows from an .xlsx or .csv spreadsheet into a list of dicts."""
    rows = []
    if sheet_path.lower().endswith(".csv"):
        with open(sheet_path, newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    else:
        from openpyxl import load_workbook

        wb = load_workbook(sheet_path)
        ws = wb["Boulders"] if "Boulders" in wb.sheetnames else wb.active
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        for r in range(2, ws.max_row + 1):
            row = {headers[c - 1]: ws.cell(r, c).value for c in range(1, ws.max_column + 1)}
            if any(v not in (None, "") for v in row.values()):
                rows.append(row)
    return rows


def build_boulders(rows, photos_dir):
    """Group rows into boulders keyed by boulder name; attach GPS + rendered photo."""
    order = []
    groups = {}
    for row in rows:
        name = (row.get("boulder") or "").strip()
        if not name:
            continue
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(row)

    boulders = []
    for i, name in enumerate(order, 1):
        grp = groups[name]
        photo_file = str(grp[0].get("photo") or "").strip()
        photo_path = os.path.join(photos_dir, photo_file)
        problems = []
        for row in grp:
            grade = str(row.get("grade") or "").strip()
            no = row.get("no")
            try:
                no = int(no)
            except Exception:
                no = len(problems) + 1
            project = grade.lower() == "project"
            color = BRAND["lav"] if project else LINE_PALETTE[(no - 1) % len(LINE_PALETTE)]
            problems.append(
                {
                    "no": no,
                    "name": str(row.get("problem") or "").strip(),
                    "grade": grade or "–",
                    "notes": str(row.get("notes") or "").strip(),
                    "notes_fr": str(row.get("notes_fr") or "").strip(),
                    "line_pts": parse_line(row.get("line")),
                    "project": project,
                    "color": color,
                }
            )
        problems.sort(key=lambda p: p["no"])

        gps = None
        if os.path.exists(photo_path):
            try:
                gps = read_gps(photo_path)
            except Exception as e:
                print("  EXIF fail", photo_file, e)

        b = {
            "id": i,
            "name": name,
            "photo": photo_file,
            "photo_path": photo_path,
            "problems": problems,
        }
        if gps:
            b.update(
                lat=gps["lat"],
                lon=gps["lon"],
                alt=gps["alt"],
                bearing=gps["bearing"],
                acc=gps["acc"],
            )
            b["alt_str"] = f"{gps['alt']:.0f} m" if gps["alt"] else "–"
            b["bearing_str"] = (
                f"{gps['bearing']:.0f}°" if gps["bearing"] is not None else "–"
            )
        else:
            print(f"  WARNING: no GPS for boulder '{name}' (photo: {photo_file})")
            b.update(lat=REFUGE["lat"], lon=REFUGE["lon"], alt=None, bearing=None, acc=None)
            b["alt_str"] = "–"
            b["bearing_str"] = "–"
        boulders.append(b)
    return boulders
