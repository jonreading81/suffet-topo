"""IGN Géoplateforme WMTS fetching, stitching, and bundling.

Two responsibilities:
  * `stitch_map` renders a single large getting-there JPEG (aerial + refuge and
    boulder pins) for the PDF cover.
  * `bundle_tiles` collects every tile within a bounding box and returns them
    as base64 data URIs — the offline HTML embeds them so it works without
    signal.

Tiles are held in an in-memory cache within a single run; there's no
between-runs cache yet.
"""
import base64
import io
import math
import urllib.request

from PIL import Image, ImageDraw

from .style import (
    BRAND,
    IGN,
    IGN_AERIAL,
    IGN_TOPO,
    ZOOM_MAX,
    ZOOM_MIN,
    font,
    hx,
)


_TILE_CACHE = {}


def tile_url(layer, z, x, y, fmt):
    return (
        f"{IGN}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}"
        f"&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT={fmt}"
    )


def fetch_tile(layer, z, x, y, fmt):
    key = (layer, z, x, y)
    if key in _TILE_CACHE:
        return _TILE_CACHE[key]
    req = urllib.request.Request(
        tile_url(layer, z, x, y, fmt),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    data = urllib.request.urlopen(req, timeout=25).read()
    _TILE_CACHE[key] = data
    return data


def deg2tile(lat, lon, z):
    n = 2 ** z
    la = math.radians(lat)
    return (
        int((lon + 180) / 360 * n),
        int((1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2 * n),
    )


def global_px(lat, lon, z):
    n = 2 ** z
    la = math.radians(lat)
    return (
        (lon + 180) / 360 * n * 256,
        (1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2 * n * 256,
    )


def stitch_map(points, refuge, out_path, z=17, Wc=1200, Hc=720):
    """Compose the getting-there map JPEG.

    points: list of dicts with lat/lon/label (+ optional name).
    refuge: dict with lat/lon/name (see style.REFUGE).
    """
    all_pts = [(refuge["lat"], refuge["lon"])] + [(p["lat"], p["lon"]) for p in points]
    cx = sum(global_px(la, lo, z)[0] for la, lo in all_pts) / len(all_pts)
    cy = sum(global_px(la, lo, z)[1] for la, lo in all_pts) / len(all_pts)
    ox, oy = cx - Wc / 2, cy - Hc / 2
    canvas = Image.new("RGB", (Wc, Hc), (200, 200, 200))
    c0, c1 = int(ox // 256), int((ox + Wc) // 256)
    r0, r1 = int(oy // 256), int((oy + Hc) // 256)
    for col in range(c0, c1 + 1):
        for row in range(r0, r1 + 1):
            try:
                t = Image.open(
                    io.BytesIO(fetch_tile(IGN_AERIAL, z, col, row, "image/jpeg"))
                ).convert("RGB")
                canvas.paste(t, (int(col * 256 - ox), int(row * 256 - oy)))
            except Exception as e:
                print("  tile miss", z, col, row, e)
    d = ImageDraw.Draw(canvas, "RGBA")
    f1, f2 = font(22), font(17)
    teal, blue = hx(BRAND["teal"]), hx(BRAND["blue"])
    # refuge marker (teal square, house)
    sx, sy = global_px(refuge["lat"], refuge["lon"], z)
    sx -= ox
    sy -= oy
    w = 17
    d.rectangle([sx - w, sy - w, sx + w, sy + w], fill=teal + (255,), outline=(255, 255, 255, 255), width=3)
    d.polygon([(sx - 9, sy - 1), (sx, sy - 10), (sx + 9, sy - 1)], fill=(255, 255, 255, 255))
    d.rectangle([sx - 6, sy - 1, sx + 6, sy + 8], fill=(255, 255, 255, 255))
    lb = d.textbbox((0, 0), refuge["name"], font=f2)
    d.rectangle(
        [sx + w + 3, sy - 11, sx + w + (lb[2] - lb[0]) + 11, sy + 13],
        fill=(255, 255, 255, 230),
    )
    d.text((sx + w + 7, sy - 9), refuge["name"], fill=teal + (255,), font=f2)
    # boulder pins
    for i, p in enumerate(points):
        bx, by = global_px(p["lat"], p["lon"], z)
        bx -= ox
        by -= oy
        rr = 15
        label = p.get("label", str(i + 1))
        d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=blue + (255,), outline=(255, 255, 255, 255), width=3)
        tb = d.textbbox((0, 0), label, font=f2)
        d.text(
            (bx - (tb[2] - tb[0]) / 2, by - (tb[3] - tb[1]) / 2 - tb[1]),
            label,
            fill=(255, 255, 255, 255),
            font=f2,
        )
        nm = p.get("name", "")
        if nm:
            lb = d.textbbox((0, 0), nm, font=f2)
            d.rectangle(
                [bx + rr + 2, by - 11, bx + rr + (lb[2] - lb[0]) + 10, by + 13],
                fill=(255, 255, 255, 220),
            )
            d.text((bx + rr + 6, by - 9), nm, fill=blue + (255,), font=f2)
    # scale bar + N + attribution
    mpp = 156543.03392 * math.cos(math.radians(all_pts[0][0])) / (2 ** z)
    seg = 100 / mpp
    bxs, bys = 30, Hc - 40
    d.rectangle([bxs - 6, bys - 24, bxs + seg + 14, bys + 16], fill=(0, 0, 0, 130))
    d.line([(bxs, bys), (bxs + seg, bys)], fill=(255, 255, 255, 255), width=3)
    for xx in (bxs, bxs + seg):
        d.line([(xx, bys - 5), (xx, bys + 5)], fill=(255, 255, 255, 255), width=3)
    d.text((bxs, bys - 22), "100 m", fill=(255, 255, 255, 255), font=f2)
    d.text((Wc - 40, 18), "N", fill=(255, 255, 255, 255), font=f1)
    d.line([(Wc - 33, 58), (Wc - 33, 28)], fill=(255, 255, 255, 255), width=3)
    d.polygon([(Wc - 33, 24), (Wc - 38, 34), (Wc - 28, 34)], fill=(255, 255, 255, 255))
    at = "© IGN / Géoplateforme"
    ab = d.textbbox((0, 0), at, font=f2)
    d.rectangle([Wc - (ab[2] - ab[0]) - 14, Hc - 26, Wc, Hc], fill=(0, 0, 0, 130))
    d.text((Wc - (ab[2] - ab[0]) - 8, Hc - 24), at, fill=(255, 255, 255, 255), font=f2)
    canvas.save(out_path, "JPEG", quality=88)


def bundle_tiles(bbox):
    """bbox = (latmin, lonmin, latmax, lonmax). Returns {'layer/z/x/y': dataURI}."""
    latmin, lonmin, latmax, lonmax = bbox
    tiles = {}
    for key, layer, fmt, _ext in [
        ("aerial", IGN_AERIAL, "image/jpeg", "jpeg"),
        ("topo", IGN_TOPO, "image/png", "png"),
    ]:
        for z in range(ZOOM_MIN, ZOOM_MAX + 1):
            x0, y1 = deg2tile(latmin, lonmin, z)
            x1, y0 = deg2tile(latmax, lonmax, z)
            for x in range(min(x0, x1), max(x0, x1) + 1):
                for y in range(min(y0, y1), max(y0, y1) + 1):
                    try:
                        data = fetch_tile(layer, z, x, y, fmt)
                        tiles[f"{key}/{z}/{x}/{y}"] = (
                            f"data:{fmt};base64," + base64.b64encode(data).decode()
                        )
                    except Exception as e:
                        print("  bundle miss", key, z, x, y, e)
    return tiles
