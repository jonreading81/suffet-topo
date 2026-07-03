"""Print-ready PDF builder.

Cover page = getting-there aerial map. One detail page per boulder.
"""
import os

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from .style import ACCURACY_FLAG_M, ASSETS, BRAND


def build_pdf(boulders, out_path):
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
        c.drawString(M, 30, "Refuge du Suffet boulders · built from photo GPS + spreadsheet")
        c.drawRightString(W - M, 30, str(p))

    # page 1: getting there map
    header("Refuge du Suffet boulders", "Haute-Maurienne · getting there")
    cw = W - 2 * M
    mtop = H - 116
    map_path = os.path.join(os.path.dirname(out_path), "_map.jpg")
    im = Image.open(map_path)
    iw, ih = im.size
    hm = cw * ih / iw
    c.drawImage(ImageReader(map_path), M, mtop - hm, cw, hm)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.rect(M, mtop - hm, cw, hm, fill=0, stroke=1)
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(MUT)
    c.drawString(M, mtop - hm - 12, "IGN aerial · the refuge and the boulders")
    footer(1)
    c.showPage()

    # one detail page per boulder
    pg = 2
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
        c.drawString(rx + 14, yr - 20, "Location")

        def meta(label, value, yy):
            c.setFont("Helvetica", 8.8)
            c.setFillColor(MUT)
            c.drawString(rx + 14, yy, label)
            c.setFont("Helvetica", 9.5)
            c.setFillColor(INK)
            c.drawRightString(rx + rw - 14, yy, value)

        meta("Latitude", f"{b['lat']:.5f}°N", yr - 42)
        meta("Longitude", f"{b['lon']:.5f}°E", yr - 60)
        meta("Altitude", b.get("alt_str", "–"), yr - 78)
        meta("Photo bearing", b.get("bearing_str", "–"), yr - 96)
        if b.get("acc") is not None:
            flagged = b["acc"] >= ACCURACY_FLAG_M
            c.setFillColor(WARN if flagged else CARD)
            c.roundRect(rx + 14, yr - mh + 14, rw - 28, 18, 9, fill=1, stroke=0)
            c.setFillColor(AMBER if flagged else MUT)
            c.setFont("Helvetica-Bold", 8.5)
            msg = (
                "⚠  GPS ±%d m — low confidence, verify on map" % b["acc"]
                if flagged
                else "GPS ±%d m" % b["acc"]
            )
            c.drawString(rx + 22, yr - mh + 20, msg)

        yp = yr - mh - 26
        c.setFillColor(INK)
        c.setFont(SERIF, 13)
        c.drawString(rx, yp, "Problems")
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
            c.drawRightString(rx + rw, yp, p["grade"])
            c.setFillColor(MUT)
            c.setFont("Helvetica", 9)
            ln = ""
            ly = yp - 15
            for wd in (p["notes"] or "").split():
                if c.stringWidth(ln + " " + wd, "Helvetica", 9) < rw - 24:
                    ln = (ln + " " + wd).strip()
                else:
                    c.drawString(rx + 24, ly, ln)
                    ly -= 13
                    ln = wd
            c.drawString(rx + 24, ly, ln)
            yp = ly - 18
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.line(rx, yp + 8, rx + rw, yp + 8)
        footer(pg)
        c.showPage()
        pg += 1
    c.setTitle("Refuge du Suffet boulders")
    c.save()
