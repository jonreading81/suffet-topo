"""Print-ready PDF builder.

Cover page = getting-there aerial map. One detail page per boulder.

Chrome (headings, labels, footer, the accuracy warning, the project legend) is
translated via `LABELS[lang]` from config.yaml. Content (boulder names, problem
names, grades, GPS numbers) stays language-neutral. The single exception is
the `Project` grade string, mapped via `labels['project_grade']` (en: 'Project',
fr: 'Projet'). Beta / notes uses the `notes_fr` field in FR when present, else
falls back to `notes`.
"""
import os
import re

from PIL import Image, ImageDraw
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

from .style import ACCURACY_FLAG_M, ASSETS, BRAND, getting_there, labels


CORNER_RADIUS_PT = 8


# Aleo (serif) is the headings font on the Refuge du Suffet website; Roboto
# is the body face. We pull both from Google Fonts (statics stored under
# assets/fonts/) so the topo shares the brand's typography. If either file
# is missing we fall back to Times/Helvetica so builds keep working.
_FONT_DIR = os.path.join(ASSETS, "fonts")


def _register(name, filename):
    try:
        pdfmetrics.registerFont(TTFont(name, os.path.join(_FONT_DIR, filename)))
        return True
    except Exception as e:
        print(f"  Font {name} unavailable ({e})")
        return False


if _register("Aleo", "Aleo-Regular.ttf") and _register("Aleo-Bold", "Aleo-Bold.ttf"):
    pdfmetrics.registerFontFamily("Aleo", normal="Aleo", bold="Aleo-Bold")
    TITLE_FONT = "Aleo-Bold"
else:
    TITLE_FONT = "Times-Bold"

if _register("Roboto", "Roboto-Regular.ttf") and _register("Roboto-Bold", "Roboto-Bold.ttf"):
    pdfmetrics.registerFontFamily("Roboto", normal="Roboto", bold="Roboto-Bold")
    BODY_FONT = "Roboto"
    BODY_BOLD = "Roboto-Bold"
else:
    BODY_FONT = "Helvetica"
    BODY_BOLD = "Helvetica-Bold"


def _rounded_reader(path, display_w, display_h, radius_pt=CORNER_RADIUS_PT):
    """Return an ImageReader whose alpha mask rounds the image's corners.
    Radius is expressed in PDF points and rescaled to source pixels so the
    curve visually matches the rounded border we draw at the display size.
    """
    im = Image.open(path).convert("RGBA")
    px_w, px_h = im.size
    r = max(1, int(round(radius_pt * min(px_w / display_w, px_h / display_h))))
    mask = Image.new("L", (px_w, px_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, px_w - 1, px_h - 1), radius=r, fill=255)
    im.putalpha(mask)
    return ImageReader(im)


def _grade_key(g):
    """Sort key for a French bouldering grade like 5a, 6b+, 7a. Returns None
    for anything that doesn't parse."""
    m = re.match(r"^(\d+)([a-cA-C])?(\+)?", g.strip())
    if not m:
        return None
    return (int(m.group(1)), (m.group(2) or "a").lower(), 1 if m.group(3) else 0)


def _grade_range(problems, project_label):
    """'6A', '5B+ – 6C+', 'Project', or '–' — a one-glance grade summary
    for a boulder's problems. Projects contribute their *proposed* grade to
    the range too; if there's no numeric grade at all but there is at least
    one project, fall back to the project label. Unparseable grades are
    skipped."""
    graded = []
    for p in problems:
        g = (p.get("grade") or "").strip()
        if not g or g == "–":
            continue
        k = _grade_key(g)
        if k is not None:
            graded.append((g, k))
    if not graded:
        return project_label if any(p.get("project") for p in problems) else "–"
    graded.sort(key=lambda x: x[1])
    lo, hi = graded[0][0], graded[-1][0]
    return lo if lo == hi else f"{lo} − {hi}"


def build_pdf(boulders, out_path, lang="en", clusters=None):
    L = labels(lang)
    W, H = A4
    c = pdfcanvas.Canvas(out_path, pagesize=A4)
    BLUE = HexColor(BRAND["blue"])
    TEAL = HexColor(BRAND["teal"])  # noqa: F841 - kept for future use
    LAV = HexColor(BRAND["lav"])
    ORANGE = HexColor(BRAND["orange"])  # noqa: F841
    INK = HexColor("#1d1d1b")
    MUT = HexColor("#6b6b66")
    LINE = HexColor("#dbe1ec")
    CARD = HexColor("#eef2f8")
    AMBER = HexColor("#B5751A")
    WARN = HexColor("#FAEEDA")
    OK_TEXT = HexColor("#1c6a34")
    OK_BG = HexColor("#d9f5df")
    M = 42
    SERIF = TITLE_FONT
    logo = ImageReader(os.path.join(ASSETS, "logo_white.png"))

    def header(t, s, number=None):
        c.setFillColor(BLUE)
        c.rect(0, H - 96, W, 96, fill=1, stroke=0)
        lw2 = 42 * 806 / 306
        c.drawImage(logo, W - M - lw2, H - 96 + (96 - 42) / 2, lw2, 42, mask="auto")
        title_x = M
        if number is not None:
            # Brand-blue circle with white ring + white digit, sitting on
            # the title's cap-height midline just left of the name.
            circ_r = 12
            circ_cx = M + circ_r
            circ_cy = H - 52 + 6
            c.setFillColor(BLUE)
            c.setStrokeColor(HexColor("#ffffff"))
            c.setLineWidth(1.4)
            c.circle(circ_cx, circ_cy, circ_r, fill=1, stroke=1)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 12)
            # Baseline offset so digit sits on circle's optical centre.
            c.drawCentredString(circ_cx, circ_cy - 4.3, str(number))
            title_x = M + 2 * circ_r + 10
        c.setFillColor(HexColor("#ffffff"))
        c.setFont(SERIF, 21)
        c.drawString(title_x, H - 52, t)
        c.setFont(BODY_FONT, 10.5)
        c.setFillColor(HexColor("#cfe0ea"))
        c.drawString(M, H - 72, s)

    def footer(p):
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(M, 44, W - M, 44)
        c.setFont(BODY_FONT, 8.5)
        c.setFillColor(MUT)
        c.drawString(M, 30, L["footer"])
        c.drawRightString(W - M, 30, str(p))

    # Page 1: getting-there — wide regional map + prose
    header(L["title"], L["subtitle_getting_there"])
    cw = W - 2 * M
    mtop = H - 116
    out_dir = os.path.dirname(out_path)

    def _draw_map(path, top_y, caption):
        im = Image.open(path)
        iw, ih = im.size
        h = cw * ih / iw
        c.drawImage(_rounded_reader(path, cw, h), M, top_y - h, cw, h, mask="auto")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.roundRect(M, top_y - h, cw, h, CORNER_RADIUS_PT, fill=0, stroke=1)
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(MUT)
        c.drawString(M, top_y - h - 12, caption)
        return top_y - h - 22  # next y (below caption + a bit of gap)

    y_after_maps = _draw_map(
        os.path.join(out_dir, "_map_regional.jpg"),
        mtop,
        L["regional_map_caption"],
    )

    # Getting-there prose below the map, inside a soft card (same visual
    # language as the Location card on the boulder pages). Paragraphs come
    # from `config.yaml -> getting_there.{en,fr}`, split by blank lines.
    gt = getting_there(lang)
    if gt:
        padx, pady = 16, 14
        card_w = W - 2 * M
        content_w = card_w - 2 * padx
        line_h = 14
        para_gap = 8

        # Word-wrap first so we know the card's total height.
        wrapped = []
        for para in gt.split("\n\n"):
            words = para.split()
            lines = []
            ln = ""
            for wd in words:
                if c.stringWidth(ln + " " + wd, BODY_FONT, 10) < content_w:
                    ln = (ln + " " + wd).strip()
                else:
                    if ln:
                        lines.append(ln)
                    ln = wd
            if ln:
                lines.append(ln)
            wrapped.append(lines)
        prose_h = sum(len(p) * line_h for p in wrapped) + para_gap * max(
            0, len(wrapped) - 1
        )
        heading_block_h = 26  # heading baseline + accent underline + gap
        card_h = pady + heading_block_h + prose_h + pady

        card_top = y_after_maps
        card_bottom = card_top - card_h

        # Card background + left accent bar
        c.setFillColor(CARD)
        c.roundRect(M, card_bottom, card_w, card_h, 10, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.roundRect(M, card_bottom, 4, card_h, 2, fill=1, stroke=0)

        # Heading
        hy = card_top - pady - 4
        c.setFillColor(BLUE)
        c.setFont(SERIF, 13)
        c.drawString(M + padx, hy - 10, L["getting_there_heading"])

        # Short accent underline under the heading
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(M + padx, hy - 16, M + padx + 44, hy - 16)

        # Prose
        py = hy - 30
        c.setFillColor(INK)
        c.setFont(BODY_FONT, 10)
        for lines in wrapped:
            for ln in lines:
                c.drawString(M + padx, py, ln)
                py -= line_h
            py -= para_gap
    footer(1)
    c.showPage()

    # Page 2: boulders overview — close-up aerial map + numbered legend
    header(L["title"], L["subtitle_boulders"])
    close_path = os.path.join(out_dir, "_map.jpg")
    im = Image.open(close_path)
    iw, ih = im.size
    hm2 = cw * ih / iw
    c.drawImage(_rounded_reader(close_path, cw, hm2), M, mtop - hm2, cw, hm2, mask="auto")
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.roundRect(M, mtop - hm2, cw, hm2, CORNER_RADIUS_PT, fill=0, stroke=1)
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(MUT)
    c.drawString(M, mtop - hm2 - 12, L["map_caption"])

    # Cluster summary below the overview map — 3 rows, one per cluster,
    # showing the range of boulder numbers, how many boulders sit in that
    # cluster, and the total number of problems. The per-boulder legend
    # moves to each cluster's own page.
    if clusters:
        ly = mtop - hm2 - 40
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(M, ly, L.get("clusters_heading", L["boulders_heading"]))
        ly -= 10
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(M, ly, W - M, ly)
        ly -= 30
        ZEBRA = HexColor("#f2f4f8")
        row_h = 34
        pad_h = 22
        r = 12
        # Fixed column x-positions so every row's letter/range/count/grade
        # line up in the same place regardless of text width.
        col_letter_x = M + r
        col_range_x = M + 2 * r + 12
        col_boulder_x = M + int(cw * 0.40)
        col_problem_x = M + int(cw * 0.60)
        col_grade_x = M + int(cw * 0.82)
        for idx, ci in enumerate(clusters):
            cy = ly - idx * row_h
            if idx % 2 == 1:
                c.setFillColor(ZEBRA)
                c.rect(M - 6, cy + 3 - row_h / 2, cw + 12, row_h, fill=1, stroke=0)
            c.setFillColor(BLUE)
            c.circle(col_letter_x, cy + 3, r, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 12)
            # Text is anchored to the baseline while the circle is centred on
            # cy+3; drop the baseline by half of Roboto-Bold's cap height so
            # the letter's optical centre matches the circle's.
            c.drawCentredString(col_letter_x, cy + 3 - 4.3, ci["letter"])
            c.setFillColor(INK)
            c.setFont(BODY_BOLD, 12)
            primary = ci.get("name") or ci["range"]
            c.drawString(col_range_x, cy, primary)
            # If the cluster carries a custom name, tuck the id range after
            # it in muted grey so the numeric identifier isn't lost.
            if ci.get("name"):
                w_prim = c.stringWidth(primary, BODY_BOLD, 12)
                c.setFillColor(MUT)
                c.setFont(BODY_FONT, 10)
                c.drawString(col_range_x + w_prim + 8, cy, ci["range"])
            c.setFillColor(MUT)
            c.setFont(BODY_FONT, 10)
            n_b = len(ci["boulders"])
            n_p = ci["problem_count"]
            c.drawString(col_boulder_x, cy, f"{n_b} boulder{'s' if n_b != 1 else ''}")
            c.drawString(col_problem_x, cy, f"{n_p} problem{'s' if n_p != 1 else ''}")
            all_problems = [p for b in ci["boulders"] for p in b["problems"]]
            grade_str = _grade_range(all_problems, L["project_grade"])
            c.setFillColor(BLUE)
            c.setFont(BODY_BOLD, 11)
            c.drawString(col_grade_x, cy, grade_str)
        ly -= len(clusters) * row_h + pad_h
        # Note boulders that don't appear on any map because they lack GPS.
        no_gps = [b for b in boulders if not b.get("_has_gps")]
        if no_gps:
            c.setFillColor(MUT)
            c.setFont(BODY_FONT, 9)
            names = ", ".join(f"{b['id']}. {b['name']}" for b in no_gps)
            c.drawString(M, ly, f"No GPS: {names}")
    footer(2)
    c.showPage()

    # Per-cluster detail pages — one page per cluster with a zoomed detail
    # map and the full boulder legend for that cluster.
    pg = 3

    def _cluster_page(ci, page_num):
        title = ci.get("name") or f"Cluster {ci['letter']}"
        header(title, f"Boulders {ci['range']}")
        cluster_map_path = os.path.join(out_dir, f"_map_cluster_{ci['letter']}.jpg")
        im2 = Image.open(cluster_map_path)
        iw2, ih2 = im2.size
        hh = cw * ih2 / iw2
        c.drawImage(
            _rounded_reader(cluster_map_path, cw, hh),
            M, mtop - hh, cw, hh, mask="auto",
        )
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.roundRect(M, mtop - hh, cw, hh, CORNER_RADIUS_PT, fill=0, stroke=1)
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(MUT)
        c.drawString(M, mtop - hh - 12, L["map_caption"])

        ly2 = mtop - hh - 40
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(M, ly2, L["boulders_heading"])
        ly2 -= 10
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(M, ly2, W - M, ly2)
        ly2 -= 30
        row_h_c = 24
        rr = 7
        footer_top = 60
        avail_h = ly2 - footer_top
        rows_per_col = max(1, int(avail_h // row_h_c))
        n_cols = max(1, (len(ci["boulders"]) + rows_per_col - 1) // rows_per_col)
        rows_per_col = (len(ci["boulders"]) + n_cols - 1) // n_cols
        col_gap = 20
        col_w = (cw - col_gap * (n_cols - 1)) / n_cols
        name_font_size = 11 if n_cols == 1 else (10 if n_cols == 2 else 9)
        grade_font_size = 9 if n_cols <= 2 else 8
        ZEBRA = HexColor("#f2f4f8")
        for idx, b in enumerate(ci["boulders"]):
            col = idx // rows_per_col
            row = idx % rows_per_col
            cxp = M + col * (col_w + col_gap)
            cyp = ly2 - row * row_h_c
            if row % 2 == 1:
                c.setFillColor(ZEBRA)
                c.rect(cxp - 6, cyp + 3 - row_h_c / 2, col_w + 12, row_h_c, fill=1, stroke=0)
            c.setFillColor(BLUE)
            c.circle(cxp + rr, cyp + 3, rr, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 7.5)
            # Same cap-height correction as the cluster overview so the digit
            # sits at the circle's optical centre, not on its baseline.
            c.drawCentredString(cxp + rr, cyp + 3 - 2.7, str(b["id"]))
            c.setFillColor(INK)
            c.setFont(BODY_BOLD, name_font_size)
            c.drawString(cxp + 2 * rr + 10, cyp, b["name"])
            c.setFillColor(MUT)
            c.setFont(BODY_FONT, grade_font_size)
            grade_str = _grade_range(b["problems"], L["project_grade"])
            c.drawRightString(cxp + col_w, cyp, grade_str)
        footer(page_num)
        c.showPage()

    def _boulder_page(b, page_num):
        header(
            b["name"],
            f"{b['lat']:.5f}°N, {b['lon']:.5f}°E  ·  {b.get('alt_str', '')}",
            number=b["id"],
        )
        im = Image.open(b["_render"])
        iw, ih = im.size
        pw = 250
        ph = pw * ih / iw
        px = M
        py = H - 130 - ph
        c.drawImage(_rounded_reader(b["_render"], pw, ph), px, py, pw, ph, mask="auto")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.roundRect(px, py, pw, ph, CORNER_RADIUS_PT, fill=0, stroke=1)

        # GPS accuracy chip — overlaid at the bottom of the boulder photo so
        # it reads like a caption. Slightly translucent (alpha 0.85) so the
        # image texture shows through; green for a good fix, amber for a
        # warning. Text is drawn at full opacity to stay crisp.
        if b.get("acc") is not None:
            flagged = b["acc"] >= ACCURACY_FLAG_M
            chip_inset = 8
            chip_h = 18
            chip_x = px + chip_inset
            chip_y = py + chip_inset
            chip_w = pw - 2 * chip_inset
            c.saveState()
            c.setFillAlpha(0.85)
            c.setFillColor(WARN if flagged else OK_BG)
            c.roundRect(chip_x, chip_y, chip_w, chip_h, 4, fill=1, stroke=0)
            c.restoreState()
            c.setFillColor(AMBER if flagged else OK_TEXT)
            msg = (L["gps_warn"] if flagged else L["gps_ok"]) % b["acc"]
            avail = chip_w - 20
            fsize = 8.5
            while c.stringWidth(msg, BODY_BOLD, fsize) > avail and fsize > 6:
                fsize -= 0.25
            c.setFont(BODY_BOLD, fsize)
            c.drawString(chip_x + 10, chip_y + 6, msg)

        rx = M + pw + 26
        rw = W - M - rx
        yr = H - 130
        # Problems section starts near the top of the right column now that
        # the location card is gone.
        yp = yr - 22
        c.setFillColor(INK)
        c.setFont(SERIF, 16)
        c.drawString(rx, yp, L["problems"])
        yp -= 10
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(rx, yp, rx + rw, yp)
        yp -= 32
        for p in b["problems"]:
            r = 7
            col = HexColor(p["color"])
            # Align circle centre with the name's cap-height mid (Helvetica-
            # Bold 10.5pt) so the number, name, and grade share one baseline.
            # Projects use the same filled-circle treatment; their palette
            # colour is just black so they read as "unclimbed" at a glance.
            circle_cy = yp + 3.8
            c.setFillColor(col)
            c.circle(rx + r, circle_cy, r, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 8)
            # 8pt Helvetica-Bold cap height ≈ 5.75; half = 2.87.
            c.drawCentredString(rx + r, circle_cy - 2.87, str(p["no"]))
            c.setFillColor(INK)
            c.setFont(BODY_BOLD, 10.5)
            c.drawString(rx + 24, yp, p["name"])
            # Grade cell: blue like a regular problem for climbed lines, dark
            # grey for projects (the grade is only proposed) — no trailing "?"
            # since the muted colour already signals "unconfirmed".
            grade_val = (p.get("grade") or "").strip()
            grade_val = "" if grade_val == "–" else grade_val
            if p["project"]:
                # Projects wrap the (proposed) grade in parentheses and use
                # a soft grey — the shape and colour both flag "unconfirmed".
                c.setFillColor(HexColor("#6a6a6a"))
                grade_text = f"({grade_val})" if grade_val else "(–)"
            else:
                c.setFillColor(BLUE)
                grade_text = grade_val or "–"
            c.setFont(BODY_BOLD, 10)
            c.drawRightString(rx + rw, yp, grade_text)
            c.setFillColor(MUT)
            c.setFont(BODY_FONT, 9)
            beta = p["notes_fr"] if lang == "fr" and p.get("notes_fr") else p["notes"]
            if beta:
                ly = yp - 15
                ln = ""
                for wd in beta.split():
                    if c.stringWidth(ln + " " + wd, BODY_FONT, 9) < rw - 24:
                        ln = (ln + " " + wd).strip()
                    else:
                        c.drawString(rx + 24, ly, ln)
                        ly -= 13
                        ln = wd
                c.drawString(rx + 24, ly, ln)
                last_baseline = ly
            else:
                last_baseline = yp
            # Cell is centred on its content: divider sits 12pt below the last
            # drawn baseline (title or last note), next title 18pt below the
            # divider — so top and bottom margins are equal.
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.line(rx, last_baseline - 16, rx + rw, last_baseline - 16)
            yp = last_baseline - 38

        # Gallery — up to three extra boulder photos rendered as a wide
        # 3-column row anchored to the bottom of the page. Image widths are
        # fixed by the column, heights are natural (aspect preserved) and
        # each image sits bottom-aligned to the panel floor. The blue
        # divider slides up to sit a fixed distance above the *tallest*
        # image, so the header rides on the content rather than on a fixed
        # baseline that leaves whitespace under short landscape photos.
        gallery = (b.get("gallery") or [])[:3]
        if gallery:
            col_gap = 12
            space_below_divider = 16   # divider → top of images
            heading_to_divider = 12    # heading baseline → divider line
            grid_w = W - 2 * M
            cols = 3
            thumb_w = (grid_w - col_gap * (cols - 1)) / cols
            # Match the whitespace between header and the boulder photo
            # (header bottom H-96, photo top H-130 → 34pt) so the page
            # reads visually balanced top ↔ bottom.
            footer_line = 44
            panel_bottom = footer_line + 34
            # Reserve headroom for the heading/divider block above the tallest
            # image. Cap image heights so nothing overlaps the boulder photo.
            panel_top_ceiling = py - 14
            reserved_head = space_below_divider + heading_to_divider + 6
            max_image_h = panel_top_ceiling - reserved_head - panel_bottom
            if max_image_h > 30:
                rendered = []
                for img_path in gallery:
                    try:
                        im2 = Image.open(img_path)
                        iw2, ih2 = im2.size
                        scale = min(thumb_w / iw2, max_image_h / ih2)
                        rendered.append((img_path, iw2 * scale, ih2 * scale))
                    except Exception as e:
                        print(f"  gallery photo error {img_path}: {e}")
                if rendered:
                    tallest = max(dh for _, _, dh in rendered)
                    divider_y = panel_bottom + tallest + space_below_divider
                    heading_y = divider_y + heading_to_divider
                    c.setFillColor(INK)
                    c.setFont(SERIF, 13)
                    c.drawString(M, heading_y, L.get("gallery", "Gallery"))
                    c.setStrokeColor(BLUE)
                    c.setLineWidth(1.2)
                    c.line(M, divider_y, M + grid_w, divider_y)
                    for i, (img_path, dw, dh) in enumerate(rendered):
                        dx = M + i * (thumb_w + col_gap)
                        dy = panel_bottom
                        c.drawImage(
                            _rounded_reader(img_path, dw, dh),
                            dx, dy, dw, dh, mask="auto",
                        )
                        c.setStrokeColor(LINE)
                        c.setLineWidth(0.5)
                        c.roundRect(dx, dy, dw, dh, CORNER_RADIUS_PT, fill=0, stroke=1)

        footer(page_num)
        c.showPage()

    if clusters:
        # Interleave: each cluster's overview page followed by its boulder
        # detail pages, then any boulders with no cluster (missing GPS) at
        # the end.
        for ci in clusters:
            _cluster_page(ci, pg)
            pg += 1
            for b in ci["boulders"]:
                _boulder_page(b, pg)
                pg += 1
        for b in [b for b in boulders if not b.get("_has_gps")]:
            _boulder_page(b, pg)
            pg += 1
    else:
        for b in boulders:
            _boulder_page(b, pg)
            pg += 1

    c.setTitle("Refuge du Suffet boulders")
    c.save()
