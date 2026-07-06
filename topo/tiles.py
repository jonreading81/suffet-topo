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


def _fit_zoom(all_pts, Wc, Hc, padding_frac=0.15, zmax=19, zmin=10):
    """Pick the highest integer zoom where every point fits inside a Wc×Hc
    canvas with `padding_frac` on each side. Falls back to `zmin` if nothing
    fits (very spread-out points).
    """
    if len(all_pts) < 2:
        return 17
    avail_w = Wc * (1 - 2 * padding_frac)
    avail_h = Hc * (1 - 2 * padding_frac)
    for z in range(zmax, zmin - 1, -1):
        xs = [global_px(la, lo, z)[0] for la, lo in all_pts]
        ys = [global_px(la, lo, z)[1] for la, lo in all_pts]
        if (max(xs) - min(xs)) <= avail_w and (max(ys) - min(ys)) <= avail_h:
            return z
    return zmin


def _nice_scale_bar_m(target_m):
    """Round a target metres value to a 'nice' 1/2/5·10^n so the bar reads
    cleanly (100 m, 200 m, 500 m, 1 km, 2 km, …)."""
    import math as _m

    if target_m <= 0:
        return 100
    e = _m.floor(_m.log10(target_m))
    base = target_m / (10 ** e)
    if base < 1.5:
        pick = 1
    elif base < 3.5:
        pick = 2
    elif base < 7.5:
        pick = 5
    else:
        pick = 10
    return int(pick * 10 ** e)


def stitch_map(
    points,
    refuge,
    out_path,
    z=None,
    Wc=1200,
    Hc=720,
    layer=None,
    fmt=None,
    show_boulders=True,
):
    """Compose a stitched map JPEG.

    points: list of dicts with lat/lon/label (+ optional name). Ignored for
            pin-drawing when `show_boulders=False`; still used for framing
            when `z=None` (auto-fit).
    refuge: dict with lat/lon/name (see style.REFUGE).
    z:      tile zoom. If None (the default), picks the highest zoom that
            fits every point in the canvas with 15% padding.
    layer:  IGN layer identifier — default aerial. Pass IGN_TOPO for the
            regional / getting-there map to get road & place-name legibility.
    fmt:    tile MIME type — default 'image/jpeg' (matches aerial). For
            IGN_TOPO pass 'image/png'.
    show_boulders: draw a numbered pin for each entry in `points`. Off for
                   the regional map, where all pins would cluster on the
                   refuge marker.
    """
    if layer is None:
        layer = IGN_AERIAL
    if fmt is None:
        fmt = "image/jpeg"
    all_pts = [(refuge["lat"], refuge["lon"])] + [(p["lat"], p["lon"]) for p in points]
    if z is None:
        # Auto-fit against all points when we're actually going to render them;
        # otherwise just the refuge and let the caller pick a wider zoom.
        z = _fit_zoom(all_pts if show_boulders else [all_pts[0]], Wc, Hc)
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
                    io.BytesIO(fetch_tile(layer, z, col, row, fmt))
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
    # boulder pins — numbered circles only. When two pins would overlap, we
    # push them apart with a short repulsion pass and draw a leader from the
    # true GPS spot to the offset pin so the number stays readable.
    if show_boulders:
        rr = 15
        min_dist = 2 * rr + 4
        pins = []
        for p in points:
            px, py = global_px(p["lat"], p["lon"], z)
            pins.append([px - ox, py - oy])
        anchors = [(x, y) for x, y in pins]
        for _ in range(120):
            moved = False
            for i in range(len(pins)):
                for j in range(i + 1, len(pins)):
                    dx = pins[j][0] - pins[i][0]
                    dy = pins[j][1] - pins[i][1]
                    dist = math.hypot(dx, dy)
                    if dist < min_dist:
                        if dist < 1e-6:
                            dx, dy, dist = 1.0, 0.0, 1.0
                        push = (min_dist - dist) / 2 + 0.5
                        ux, uy = dx / dist, dy / dist
                        pins[i][0] -= ux * push
                        pins[i][1] -= uy * push
                        pins[j][0] += ux * push
                        pins[j][1] += uy * push
                        moved = True
            if not moved:
                break
        for i, p in enumerate(points):
            ax, ay = anchors[i]
            bx, by = pins[i]
            if math.hypot(bx - ax, by - ay) > 1.5:
                d.line([(ax, ay), (bx, by)], fill=(255, 255, 255, 230), width=2)
                d.ellipse([ax - 3, ay - 3, ax + 3, ay + 3], fill=blue + (255,), outline=(255, 255, 255, 255), width=1)
            label = p.get("label", str(i + 1))
            d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=blue + (255,), outline=(255, 255, 255, 255), width=3)
            tb = d.textbbox((0, 0), label, font=f2)
            d.text(
                (bx - (tb[2] - tb[0]) / 2, by - (tb[3] - tb[1]) / 2 - tb[1]),
                label,
                fill=(255, 255, 255, 255),
                font=f2,
            )
    # scale bar (adaptive: bar target ~12% of canvas width, snapped to 1/2/5)
    mpp = 156543.03392 * math.cos(math.radians(all_pts[0][0])) / (2 ** z)
    bar_m = _nice_scale_bar_m(Wc * 0.12 * mpp)
    seg = bar_m / mpp
    bar_label = f"{bar_m} m" if bar_m < 1000 else f"{bar_m // 1000} km"
    bxs, bys = 30, Hc - 40
    d.rectangle([bxs - 6, bys - 24, bxs + seg + 14, bys + 16], fill=(0, 0, 0, 130))
    d.line([(bxs, bys), (bxs + seg, bys)], fill=(255, 255, 255, 255), width=3)
    for xx in (bxs, bxs + seg):
        d.line([(xx, bys - 5), (xx, bys + 5)], fill=(255, 255, 255, 255), width=3)
    d.text((bxs, bys - 22), bar_label, fill=(255, 255, 255, 255), font=f2)
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
