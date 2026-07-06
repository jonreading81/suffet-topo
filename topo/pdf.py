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
    """'6a', '5b+–6c+', 'Project', or '–' — a one-glance grade summary for a
    boulder's problems. Projects are folded in only when there's no graded
    problem to report; unparseable grades are skipped."""
    graded = []
    has_project = False
    for p in problems:
        if p.get("project"):
            has_project = True
            continue
        g = (p.get("grade") or "").strip()
        if not g or g == "–":
            continue
        k = _grade_key(g)
        if k is not None:
            graded.append((g, k))
    if not graded:
        return project_label if has_project else "–"
    graded.sort(key=lambda x: x[1])
    lo, hi = graded[0][0], graded[-1][0]
    return lo if lo == hi else f"{lo} – {hi}"


def build_pdf(boulders, out_path, lang="en"):
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
    M = 42
    SERIF = TITLE_FONT
    logo = ImageReader(os.path.join(ASSETS, "logo_white.png"))

    def header(t, s):
        c.setFillColor(BLUE)
        c.rect(0, H - 96, W, 96, fill=1, stroke=0)
        lw2 = 42 * 806 / 306
        c.drawImage(logo, W - M - lw2, H - 96 + (96 - 42) / 2, lw2, 42, mask="auto")
        c.setFillColor(HexColor("#ffffff"))
        c.setFont(SERIF, 21)
        c.drawString(M, H - 52, t)
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

    # Numbered legend below the map — pin number → boulder name, so readers
    # can cross-reference the map with the detail pages that follow.
    if boulders:
        ly = mtop - hm2 - 40
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(M, ly, L["boulders_heading"])
        ly -= 10
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(M, ly, W - M, ly)
        ly -= 30
        row_h = 24
        r = 7
        # Auto-column so all boulders fit on this page. Compute how many rows
        # fit above the footer at the row height, then bump the column count
        # until every boulder fits. Fonts shrink at higher column counts so
        # long names still clear the right-aligned grade.
        footer_top = 60
        avail_h = ly - footer_top
        rows_per_col = max(1, int(avail_h // row_h))
        n_cols = max(1, (len(boulders) + rows_per_col - 1) // rows_per_col)
        rows_per_col = (len(boulders) + n_cols - 1) // n_cols
        col_gap = 20
        col_w = (cw - col_gap * (n_cols - 1)) / n_cols
        name_font_size = 10 if n_cols == 1 else (9 if n_cols == 2 else 8)
        grade_font_size = 8.5 if n_cols <= 2 else 7.5
        ZEBRA = HexColor("#f2f4f8")
        for idx, b in enumerate(boulders):
            col = idx // rows_per_col
            row = idx % rows_per_col
            cx = M + col * (col_w + col_gap)
            cy = ly - row * row_h
            if row % 2 == 1:
                c.setFillColor(ZEBRA)
                # Rect is centred on the content: content spans cy-6 (pin
                # bottom) to cy+12 (pin top), midpoint cy+3, so the row_h
                # box goes from cy+3-row_h/2 to cy+3+row_h/2.
                c.rect(cx - 6, cy + 3 - row_h / 2, col_w + 12, row_h, fill=1, stroke=0)
            c.setFillColor(BLUE)
            c.circle(cx + r, cy + 3, r, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 7.5)
            c.drawCentredString(cx + r, cy, str(b["id"]))
            c.setFillColor(INK)
            c.setFont(BODY_BOLD, name_font_size)
            c.drawString(cx + 2 * r + 10, cy, b["name"])
            c.setFillColor(MUT)
            c.setFont(BODY_FONT, grade_font_size)
            grade_str = _grade_range(b["problems"], L["project_grade"])
            c.drawRightString(cx + col_w, cy, grade_str)
    footer(2)
    c.showPage()

    # one detail page per boulder
    pg = 3
    for b in boulders:
        header(b["name"], f"{b['lat']:.5f}°N, {b['lon']:.5f}°E  ·  {b.get('alt_str', '')}")
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
        rx = M + pw + 26
        rw = W - M - rx
        yr = H - 130
        mh = 140
        c.setFillColor(CARD)
        c.roundRect(rx, yr - mh, rw, mh, 8, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.setFont(SERIF, 12)
        c.drawString(rx + 14, yr - 20, L["location"])

        def meta(label, value, yy):
            c.setFont(BODY_FONT, 8.8)
            c.setFillColor(MUT)
            c.drawString(rx + 14, yy, label)
            c.setFont(BODY_FONT, 9.5)
            c.setFillColor(INK)
            c.drawRightString(rx + rw - 14, yy, value)

        meta(L["latitude"], f"{b['lat']:.5f}°N", yr - 42)
        meta(L["longitude"], f"{b['lon']:.5f}°E", yr - 60)
        meta(L["altitude"], b.get("alt_str", "–"), yr - 78)
        meta(L["photo_bearing"], b.get("bearing_str", "–"), yr - 96)
        if b.get("acc") is not None:
            flagged = b["acc"] >= ACCURACY_FLAG_M
            c.setFillColor(WARN if flagged else CARD)
            c.roundRect(rx + 14, yr - mh + 14, rw - 28, 18, 9, fill=1, stroke=0)
            c.setFillColor(AMBER if flagged else MUT)
            msg = (L["gps_warn"] if flagged else L["gps_ok"]) % b["acc"]
            # Auto-shrink to fit the pill so longer translations (e.g. the FR
            # accuracy warning) don't overflow.
            avail = rw - 36
            fsize = 8.5
            while c.stringWidth(msg, BODY_BOLD, fsize) > avail and fsize > 6:
                fsize -= 0.25
            c.setFont(BODY_BOLD, fsize)
            c.drawString(rx + 22, yr - mh + 20, msg)

        yp = yr - mh - 26
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(rx, yp, L["problems"])
        yp -= 6
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(rx, yp, rx + rw, yp)
        yp -= 22
        for p in b["problems"]:
            r = 7
            col = HexColor(p["color"])
            # Align circle centre with the name's cap-height mid (Helvetica-
            # Bold 10.5pt) so the number, name, and grade share one baseline.
            circle_cy = yp + 3.8
            if p["project"]:
                c.setFillColor(HexColor("#ffffff"))
                c.setStrokeColor(col)
                c.setLineWidth(2)
                c.circle(rx + r, circle_cy, r, fill=1, stroke=1)
                c.setFillColor(col)
            else:
                c.setFillColor(col)
                c.circle(rx + r, circle_cy, r, fill=1, stroke=0)
                c.setFillColor(HexColor("#ffffff"))
            c.setFont(BODY_BOLD, 8)
            # 8pt Helvetica-Bold cap height ≈ 5.75; half = 2.87.
            c.drawCentredString(rx + r, circle_cy - 2.87, str(p["no"]))
            c.setFillColor(INK)
            c.setFont(BODY_BOLD, 10.5)
            c.drawString(rx + 24, yp, p["name"])
            c.setFillColor(LAV if p["project"] else BLUE)
            c.setFont(BODY_BOLD, 10)
            grade = L["project_grade"] if p["project"] else p["grade"]
            c.drawRightString(rx + rw, yp, grade)
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
        footer(pg)
        c.showPage()
        pg += 1
    c.setTitle("Refuge du Suffet boulders")
    c.save()
