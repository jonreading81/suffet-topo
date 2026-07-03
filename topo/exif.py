"""EXIF GPS extraction."""
from PIL import Image
from PIL.ExifTags import GPSTAGS


def _dms_to_dd(v, ref):
    d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    return -d if ref in ("S", "W") else d


def read_gps(path):
    """Return dict(lat, lon, alt, bearing, acc) or None.

    Fields present when the corresponding EXIF tag exists:
      lat, lon     - decimal degrees
      alt          - metres (float) or None
      bearing      - degrees True (float) or None
      acc          - horizontal accuracy in metres (float) or None
    """
    img = Image.open(path)
    exif = img.getexif()
    gi = exif.get_ifd(0x8825)  # GPS IFD
    if not gi:
        return None
    g = {GPSTAGS.get(k, k): v for k, v in gi.items()}
    if "GPSLatitude" not in g or "GPSLongitude" not in g:
        return None
    return {
        "lat": _dms_to_dd(g["GPSLatitude"], g.get("GPSLatitudeRef", "N")),
        "lon": _dms_to_dd(g["GPSLongitude"], g.get("GPSLongitudeRef", "E")),
        "alt": float(g["GPSAltitude"]) if "GPSAltitude" in g else None,
        "bearing": float(g["GPSImgDirection"]) if "GPSImgDirection" in g else None,
        "acc": float(g["GPSHPositioningError"]) if "GPSHPositioningError" in g else None,
    }
