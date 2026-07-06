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


def _draw_cluster_labels(d, points, ox, oy, z, blue, base_font):
    """Draw one wide pill-shaped label per cluster, with a triangular tail
    pointing to the cluster's centroid. `points` are the cluster centroids
    (list of dicts with lat/lon/label). Labels repel each other."""
    from .style import font as _f

    fill_col = blue + (240,)
    text_col = (255, 255, 255, 255)
    lbl_font = _f(20)
    tail_len = 10
    pad_x, pad_y = 12, 6
    corner_r = 10

    boxes = []  # {anchor, pos:[cx,cy], w, h, text, tb}
    for p in points:
        px, py = global_px(p["lat"], p["lon"], z)
        ax, ay = px - ox, py - oy
        text = p["label"]
        tb = d.textbbox((0, 0), text, font=lbl_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        w, h = tw + 2 * pad_x, th + 2 * pad_y
        # Initial label position: above the anchor with the tail_len gap
        boxes.append({
            "anchor": (ax, ay),
            "pos": [ax, ay - h / 2 - tail_len],
            "w": w, "h": h, "text": text, "tb": tb,
        })

    # Rectangle-based repulsion between labels.
    for _ in range(400):
        moved = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                dx = b["pos"][0] - a["pos"][0]
                dy = b["pos"][1] - a["pos"][1]
                min_x = (a["w"] + b["w"]) / 2 + 8
                min_y = (a["h"] + b["h"]) / 2 + 6
                overlap_x = min_x - abs(dx)
                overlap_y = min_y - abs(dy)
                if overlap_x > 0 and overlap_y > 0:
                    if overlap_x < overlap_y:
                        push = overlap_x / 2 + 0.5
                        if dx >= 0:
                            a["pos"][0] -= push
                            b["pos"][0] += push
                        else:
                            a["pos"][0] += push
                            b["pos"][0] -= push
                    else:
                        push = overlap_y / 2 + 0.5
                        if dy >= 0:
                            a["pos"][1] -= push
                            b["pos"][1] += push
                        else:
                            a["pos"][1] += push
                            b["pos"][1] -= push
                    moved = True
        if not moved:
            break

    for box in boxes:
        ax, ay = box["anchor"]
        lx, ly = box["pos"]
        w, h = box["w"], box["h"]
        bx0, by0 = lx - w / 2, ly - h / 2
        bx1, by1 = lx + w / 2, ly + h / 2

        # Tail: triangle whose base sits on the closest edge of the label
        # facing the anchor, apex at the anchor.
        vx, vy = ax - lx, ay - ly
        vlen = math.hypot(vx, vy)
        if vlen < 1e-6:
            ux, uy = 0.0, 1.0
        else:
            ux, uy = vx / vlen, vy / vlen
        # Where the vector head→anchor exits the box.
        tx = ux / max(abs(ux), 1e-6) if abs(ux) > 1e-6 else 0
        ty = uy / max(abs(uy), 1e-6) if abs(uy) > 1e-6 else 0
        # Choose the box side pierced by the vector, then place the base on
        # that side.
        exit_scale_x = (w / 2) / abs(ux) if abs(ux) > 1e-6 else float("inf")
        exit_scale_y = (h / 2) / abs(uy) if abs(uy) > 1e-6 else float("inf")
        exit_scale = min(exit_scale_x, exit_scale_y)
        rim_x = lx + ux * exit_scale
        rim_y = ly + uy * exit_scale
        base_w = 14
        perp_x, perp_y = -uy, ux
        base_l = (rim_x - perp_x * base_w / 2, rim_y - perp_y * base_w / 2)
        base_r = (rim_x + perp_x * base_w / 2, rim_y + perp_y * base_w / 2)
        tip = (ax, ay)
        d.polygon([base_l, base_r, tip], fill=fill_col)
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=corner_r, fill=fill_col)
        tb = box["tb"]
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        d.text(
            (lx - tw / 2 - tb[0], ly - th / 2 - tb[1]),
            box["text"], fill=text_col, font=lbl_font,
        )


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
    marker_style="pin",
    fit_refuge=True,
    bridges=None,
    context_points=None,
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
    # For a zoomed-in map of a cluster we don't want the refuge dragging the
    # frame outward; caller sets fit_refuge=False and we fit just the pins.
    fit_pts = all_pts if fit_refuge or not show_boulders else all_pts[1:]
    if z is None:
        # Auto-fit against all points when we're actually going to render them;
        # otherwise just the refuge and let the caller pick a wider zoom.
        z = _fit_zoom(fit_pts if show_boulders else [all_pts[0]], Wc, Hc)
    cx = sum(global_px(la, lo, z)[0] for la, lo in fit_pts) / len(fit_pts)
    cy = sum(global_px(la, lo, z)[1] for la, lo in fit_pts) / len(fit_pts)
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
    # Refuge marker (brand-blue square, white house). Text label sits in a
    # semi-transparent white pill next to the square, in the same blue.
    sx, sy = global_px(refuge["lat"], refuge["lon"], z)
    sx -= ox
    sy -= oy
    w = 17
    d.rectangle([sx - w, sy - w, sx + w, sy + w], fill=blue + (255,), outline=(255, 255, 255, 255), width=3)
    d.polygon([(sx - 9, sy - 1), (sx, sy - 10), (sx + 9, sy - 1)], fill=(255, 255, 255, 255))
    d.rectangle([sx - 6, sy - 1, sx + 6, sy + 8], fill=(255, 255, 255, 255))
    lb = d.textbbox((0, 0), refuge["name"], font=f2)
    d.rectangle(
        [sx + w + 3, sy - 11, sx + w + (lb[2] - lb[0]) + 11, sy + 13],
        fill=(255, 255, 255, 230),
    )
    d.text((sx + w + 7, sy - 9), refuge["name"], fill=blue + (255,), font=f2)

    # Bridge glyphs — draw them BEFORE the boulder pins so any pin that
    # lands over a bridge stays on top and remains readable. The on-map key
    # is drawn later (below, after the pin/marker block) so it always sits
    # on top of everything.
    bridge_col = (117, 74, 34, 245)
    bridge_edge = (255, 255, 255, 240)

    def _draw_footbridge(cx, cy):
        d.rectangle([cx - 6, cy - 14, cx + 6, cy + 14], fill=bridge_edge)
        d.rectangle([cx - 5, cy - 13, cx - 3, cy + 13], fill=bridge_col)
        d.rectangle([cx + 3, cy - 13, cx + 5, cy + 13], fill=bridge_col)
        for py in (cy - 11, cy - 6, cy - 1, cy + 4, cy + 9):
            d.rectangle([cx - 5, py, cx + 5, py + 2], fill=bridge_col)

    if bridges:
        for br in bridges:
            bx, by = global_px(br["lat"], br["lon"], z)
            bx -= ox
            by -= oy
            if bx < -20 or by < -20 or bx > Wc + 20 or by > Hc + 20:
                continue
            _draw_footbridge(bx, by)
    # Context markers — boulders from OTHER clusters that fall within this
    # map's frame. Drawn as ghosted teardrops (50% opacity, no repulsion) so
    # readers can see how their cluster sits relative to nearby ones.
    if context_points:
        ctx_head_r = 14
        ctx_tail_len = 9
        ctx_fill = blue + (128,)  # 50% alpha
        ctx_font = font(16)
        for p in context_points:
            px, py = global_px(p["lat"], p["lon"], z)
            ax, ay = px - ox, py - oy
            if ax < -30 or ay < -30 or ax > Wc + 30 or ay > Hc + 30:
                continue
            hx_, hy_ = ax, ay - ctx_head_r - ctx_tail_len
            # Tail
            vx, vy = ax - hx_, ay - hy_
            vlen = math.hypot(vx, vy)
            ux, uy = (vx / vlen, vy / vlen) if vlen > 1e-6 else (0.0, 1.0)
            rim_x = hx_ + ux * (ctx_head_r - 1)
            rim_y = hy_ + uy * (ctx_head_r - 1)
            base_w = ctx_head_r * 0.75
            perp_x, perp_y = -uy, ux
            base_l = (rim_x - perp_x * base_w / 2, rim_y - perp_y * base_w / 2)
            base_r = (rim_x + perp_x * base_w / 2, rim_y + perp_y * base_w / 2)
            d.polygon([base_l, base_r, (ax, ay)], fill=ctx_fill)
            d.ellipse(
                [hx_ - ctx_head_r, hy_ - ctx_head_r, hx_ + ctx_head_r, hy_ + ctx_head_r],
                fill=ctx_fill,
            )
            label = p.get("label", "")
            tb = d.textbbox((0, 0), label, font=ctx_font)
            d.text(
                (hx_ - (tb[2] - tb[0]) / 2, hy_ - (tb[3] - tb[1]) / 2 - tb[1]),
                label, fill=(255, 255, 255, 160), font=ctx_font,
            )

    # Boulder pins — Google-Maps-style: the head sits above the anchor with
    # a triangular tail that tapers to the exact GPS point. Heads repel each
    # other to avoid overlap; the tail stretches so the tip still touches
    # the true position no matter how far the head is pushed.
    if show_boulders and marker_style == "cluster":
        _draw_cluster_labels(d, points, ox, oy, z, blue, f2)
    elif show_boulders:
        head_r = 14
        tail_len = 9              # default head-bottom to anchor gap
        min_dist = 2 * head_r + 12  # 12px clear gap between adjacent heads
        label_font = font(16)     # sized for the roomier cluster detail maps
        anchors, heads = [], []
        for p in points:
            px, py = global_px(p["lat"], p["lon"], z)
            ax, ay = px - ox, py - oy
            anchors.append((ax, ay))
            heads.append([ax, ay - head_r - tail_len])  # head starts above
        # Enforce a minimum head→anchor distance so every pin keeps a
        # visible tail — otherwise repulsion can shove a head onto its own
        # anchor and it stops looking like a marker.
        min_tail = head_r + tail_len
        for _ in range(500):
            moved = False
            for i in range(len(heads)):
                for j in range(i + 1, len(heads)):
                    dx = heads[j][0] - heads[i][0]
                    dy = heads[j][1] - heads[i][1]
                    dist = math.hypot(dx, dy)
                    if dist < min_dist:
                        if dist < 1e-6:
                            dx, dy, dist = 1.0, 0.0, 1.0
                        push = (min_dist - dist) / 2 + 0.5
                        ux, uy = dx / dist, dy / dist
                        heads[i][0] -= ux * push
                        heads[i][1] -= uy * push
                        heads[j][0] += ux * push
                        heads[j][1] += uy * push
                        moved = True
            for i in range(len(heads)):
                ax, ay = anchors[i]
                dx = heads[i][0] - ax
                dy = heads[i][1] - ay
                dist = math.hypot(dx, dy)
                if dist < min_tail:
                    if dist < 1e-6:
                        dx, dy, dist = 0.0, -1.0, 1.0  # default: push up
                    ux, uy = dx / dist, dy / dist
                    heads[i][0] = ax + ux * min_tail
                    heads[i][1] = ay + uy * min_tail
                    moved = True
            if not moved:
                break

        fill_col = blue + (235,)
        for (ax, ay), (headx, heady), p in zip(anchors, heads, points):
            # Vector head → anchor, used to place the tail's base perpendicular
            # to that direction on the head's rim.
            vx, vy = ax - headx, ay - heady
            vlen = math.hypot(vx, vy)
            if vlen < 1e-6:
                ux, uy = 0.0, 1.0
            else:
                ux, uy = vx / vlen, vy / vlen
            rim_x = headx + ux * (head_r - 1)
            rim_y = heady + uy * (head_r - 1)
            base_w = head_r * 0.75
            perp_x, perp_y = -uy, ux
            base_l = (rim_x - perp_x * base_w / 2, rim_y - perp_y * base_w / 2)
            base_r = (rim_x + perp_x * base_w / 2, rim_y + perp_y * base_w / 2)
            tip = (ax, ay)
            d.polygon([base_l, base_r, tip], fill=fill_col)
            d.ellipse(
                [headx - head_r, heady - head_r, headx + head_r, heady + head_r],
                fill=fill_col,
            )
            label = p.get("label")
            tb = d.textbbox((0, 0), label, font=label_font)
            d.text(
                (headx - (tb[2] - tb[0]) / 2, heady - (tb[3] - tb[1]) / 2 - tb[1]),
                label, fill=(255, 255, 255, 255), font=label_font,
            )
    # Footbridge on-map key (bridge icons themselves are drawn earlier so
    # boulder pins render on top of them; the key belongs on top of
    # everything, so it lives here).
    if bridges:
        key_text = "Footbridge"
        text_bb = d.textbbox((0, 0), key_text, font=f2)
        text_w = text_bb[2] - text_bb[0]
        text_h = text_bb[3] - text_bb[1]
        icon_w = 12
        pad_x, pad_y, gap = 10, 6, 8
        box_w = pad_x + icon_w + gap + text_w + pad_x
        box_h = max(20, text_h + 2 * pad_y) + 8
        # Anchored bottom-right, above the © IGN attribution strip.
        box_x = Wc - box_w - 24
        box_y = Hc - 70
        d.rectangle(
            [box_x, box_y - box_h / 2, box_x + box_w, box_y + box_h / 2],
            fill=(0, 0, 0, 140),
        )
        _draw_footbridge(box_x + pad_x + icon_w / 2, box_y)
        d.text(
            (box_x + pad_x + icon_w + gap, box_y - text_h / 2 - text_bb[1]),
            key_text, fill=(255, 255, 255, 255), font=f2,
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
