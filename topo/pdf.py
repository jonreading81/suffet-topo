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

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from .style import ACCURACY_FLAG_M, ASSETS, BRAND, getting_there, labels


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
    SERIF = "Times-Bold"
    logo = ImageReader(os.path.join(ASSETS, "logo_white.png"))

    def header(t, s):
        c.setFillColor(BLUE)
        c.rect(0, H - 96, W, 96, fill=1, stroke=0)
        lw2 = 42 * 806 / 306
        c.drawImage(logo, W - M - lw2, H - 96 + (96 - 42) / 2, lw2, 42, mask="auto")
        c.setFillColor(HexColor("#ffffff"))
        c.setFont(SERIF, 21)
        c.drawString(M, H - 52, t)
        c.setFont("Helvetica", 10.5)
        c.setFillColor(HexColor("#cfe0ea"))
        c.drawString(M, H - 72, s)

    def footer(p):
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(M, 40, W - M, 40)
        c.setFont("Helvetica", 8.5)
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
        c.drawImage(ImageReader(path), M, top_y - h, cw, h)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.rect(M, top_y - h, cw, h, fill=0, stroke=1)
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
                if c.stringWidth(ln + " " + wd, "Helvetica", 10) < content_w:
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
        c.setFont("Helvetica", 10)
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
    c.drawImage(ImageReader(close_path), M, mtop - hm2, cw, hm2)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.rect(M, mtop - hm2, cw, hm2, fill=0, stroke=1)
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
        ly -= 6
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(M, ly, W - M, ly)
        ly -= 22
        row_h = 22
        r = 9
        for b in boulders:
            c.setFillColor(BLUE)
            c.circle(M + r, ly + 3, r, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff"))
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(M + r, ly, str(b["id"]))
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(M + 2 * r + 10, ly, b["name"])
            n = len(b["problems"])
            c.setFillColor(MUT)
            c.setFont("Helvetica", 9)
            c.drawRightString(W - M, ly, f"{n} problem{'s' if n != 1 else ''}")
            ly -= row_h
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
        c.drawImage(ImageReader(b["_render"]), px, py, pw, ph)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.rect(px, py, pw, ph, fill=0, stroke=1)
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
            c.setFont("Helvetica", 8.8)
            c.setFillColor(MUT)
            c.drawString(rx + 14, yy, label)
            c.setFont("Helvetica", 9.5)
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
            while c.stringWidth(msg, "Helvetica-Bold", fsize) > avail and fsize > 6:
                fsize -= 0.25
            c.setFont("Helvetica-Bold", fsize)
            c.drawString(rx + 22, yr - mh + 20, msg)

        yp = yr - mh - 26
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(rx, yp, L["problems"])
        yp -= 6
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(rx, yp, rx + rw, yp)
        yp -= 20
        for p in b["problems"]:
            r = 8
            col = HexColor(p["color"])
            if p["project"]:
                c.setFillColor(HexColor("#ffffff"))
                c.setStrokeColor(col)
                c.setLineWidth(2)
                c.circle(rx + r, yp + 3, r, fill=1, stroke=1)
                c.setFillColor(col)
            else:
                c.setFillColor(col)
                c.circle(rx + r, yp + 3, r, fill=1, stroke=0)
                c.setFillColor(HexColor("#ffffff"))
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(rx + r, yp, str(p["no"]))
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 10.5)
            c.drawString(rx + 24, yp, p["name"])
            c.setFillColor(LAV if p["project"] else BLUE)
            c.setFont("Helvetica-Bold", 10)
            grade = L["project_grade"] if p["project"] else p["grade"]
            c.drawRightString(rx + rw, yp, grade)
            c.setFillColor(MUT)
            c.setFont("Helvetica", 9)
            beta = p["notes_fr"] if lang == "fr" and p.get("notes_fr") else p["notes"]
            ln = ""
            ly = yp - 15
            for wd in (beta or "").split():
                if c.stringWidth(ln + " " + wd, "Helvetica", 9) < rw - 24:
                    ln = (ln + " " + wd).strip()
                else:
                    c.drawString(rx + 24, ly, ln)
                    ly -= 13
                    ln = wd
            c.drawString(rx + 24, ly, ln)
            # 14pt above the divider, 22pt below (more visual room before the
            # next problem's title starts).
            yp = ly - 36
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.line(rx, yp + 22, rx + rw, yp + 22)
        footer(pg)
        c.showPage()
        pg += 1
    c.setTitle("Refuge du Suffet boulders")
    c.save()
