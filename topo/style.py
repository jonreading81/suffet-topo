"""Brand tokens, config, and shared font/colour helpers.

Centralised so PDF, offline HTML, and the annotator preview stay in lock-step
(the annotator is a standalone HTML file — keep its colour list in sync with
`LINE_PALETTE` here whenever either changes).
"""
import os

from PIL import ImageFont


# ---------------------------------------------------------------------------
# Refuge, brand palette, IGN tile config
# ---------------------------------------------------------------------------
REFUGE = {
    "name": "Refuge du Suffet",
    "lat": 45.206031,
    "lon": 6.845828,
    "alt": 1690,
}

BRAND = {
    "blue":   "#004AAD",  # primary
    "teal":   "#6AB0AB",  # refuge marker / secondary
    "lav":    "#A096EF",  # projects
    "orange": "#E4572E",  # high-contrast line
    "amber":  "#E0A21B",
}

# problem line colours (graded); projects always use lavender + dashed
LINE_PALETTE = [
    BRAND["blue"],
    BRAND["orange"],
    BRAND["teal"],
    BRAND["lav"],
    BRAND["amber"],
]

IGN = "https://data.geopf.fr/wmts"
IGN_AERIAL = "ORTHOIMAGERY.ORTHOPHOTOS"
IGN_TOPO = "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
ZOOM_MIN, ZOOM_MAX = 16, 18       # bundled zoom range for the offline map
ACCURACY_FLAG_M = 15              # GPS accuracy above this = low-confidence warn


# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "assets")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"


# ---------------------------------------------------------------------------
# Colour + font helpers
# ---------------------------------------------------------------------------
def hx(c):
    """Hex string ('#004AAD') -> (r, g, b) tuple."""
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def font(size, bold=True):
    """Load DejaVu at `size`; fall back to Pillow's default if unavailable."""
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except Exception:
        return ImageFont.load_default()
