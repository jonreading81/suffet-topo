"""Topo line parsing, smoothing, and drawing onto a boulder photo."""
import math

from PIL import Image, ImageDraw

from .style import hx, font


# ---------------------------------------------------------------------------
# Parse + smooth
# ---------------------------------------------------------------------------
def parse_line(s):
    """Parse the sheet's `line` column into [(x, y), ...] in percent-of-image.

    Format: whitespace-separated 'x,y' pairs (e.g. '10.5,20  40,80').
    Empty / None input returns [].
    """
    if not s:
        return []
    return [tuple(float(v) for v in pt.split(",")) for pt in str(s).split()]


def catmull(pts, steps=20):
    """Catmull-Rom spline through the given control points.

    Returns a list of interpolated (x, y) points suitable for `PIL.ImageDraw.line`.
    For <2 input points, returns the input unchanged.
    """
    if len(pts) < 2:
        return pts
    out = []
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        for s in range(steps + 1):
            t = s / steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    return out


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------
def draw_dashed(draw, pts, fill, width, dash, gap):
    """Draw a dashed polyline segment-by-segment, carrying phase between segments."""
    on = True
    carry = 0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        if seg == 0:
            continue
        d = 0
        while d < seg:
            step = (dash if on else gap) - carry
            end = min(d + step, seg)
            if on:
                draw.line(
                    [
                        (x1 + (x2 - x1) * d / seg, y1 + (y2 - y1) * d / seg),
                        (x1 + (x2 - x1) * end / seg, y1 + (y2 - y1) * end / seg),
                    ],
                    fill=fill,
                    width=width,
                )
            if end - d >= step:
                on = not on
                carry = 0
            else:
                carry += end - d
            d = end


def render_boulder_photo(photo_path, problems, max_px=1100):
    """Draw all problem lines onto the photo in the shared style.

    problems: iterable of dicts with keys
      no, project (bool), color (hex string), line_pts (list of percent x,y).

    Returns a PIL.Image (RGB) thumbnailed to `max_px` on the long side.
    """
    img = Image.open(photo_path).convert("RGB")
    W, H = img.size
    base = min(W, H)
    d = ImageDraw.Draw(img, "RGBA")
    lw = max(2, int(base * 0.009))
    halo = max(4, int(base * 0.016))
    r = int(base * 0.024)
    fnt = font(int(r * 1.2))
    for p in problems:
        pts = [(x / 100 * W, y / 100 * H) for x, y in p["line_pts"]]
        if len(pts) < 2:
            continue
        cu = catmull(pts)
        col = hx(p["color"])
        if p["project"]:
            draw_dashed(d, cu, (255, 255, 255, 210), halo, int(base * 0.03), int(base * 0.02))
            draw_dashed(d, cu, col + (255,), lw, int(base * 0.03), int(base * 0.02))
        else:
            d.line(cu, fill=(255, 255, 255, 210), width=halo, joint="curve")
            d.line(cu, fill=col + (255,), width=lw, joint="curve")
        x0, y0 = pts[0]
        if p["project"]:
            d.ellipse(
                [x0 - r, y0 - r, x0 + r, y0 + r],
                fill=(255, 255, 255, 235),
                outline=col + (255,),
                width=max(3, int(base * 0.008)),
            )
            tcol = col + (255,)
        else:
            d.ellipse(
                [x0 - r, y0 - r, x0 + r, y0 + r],
                fill=col + (255,),
                outline=(255, 255, 255, 255),
                width=max(2, int(base * 0.006)),
            )
            tcol = (255, 255, 255, 255)
        no = str(p["no"])
        tb = d.textbbox((0, 0), no, font=fnt)
        d.text(
            (x0 - (tb[2] - tb[0]) / 2, y0 - (tb[3] - tb[1]) / 2 - tb[1]),
            no,
            fill=tcol,
            font=fnt,
        )
    if max_px:
        img.thumbnail((max_px, int(max_px * 1.4)))
    return img
