"""Brand tokens, config, and shared font/colour helpers.

Values here are loaded from `config.yaml` at the repo root so refuge coords,
brand palette, zoom range, and PDF label strings can be edited without
touching code.

Centralised so PDF, offline HTML, and the annotator preview stay in lock-step
(the annotator is a standalone HTML file — keep its colour list in sync with
`LINE_PALETTE` here whenever either changes).
"""
import os

import yaml
from PIL import ImageFont


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "assets")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
CONFIG_PATH = os.path.join(HERE, "config.yaml")


# ---------------------------------------------------------------------------
# Config load
# ---------------------------------------------------------------------------
with open(CONFIG_PATH, "r") as _f:
    _cfg = yaml.safe_load(_f)

REFUGE = _cfg["refuge"]
BRAND = _cfg["brand"]
LINE_PALETTE = list(_cfg["line_palette"])
ZOOM_MIN = int(_cfg["tiles"]["zoom_min"])
ZOOM_MAX = int(_cfg["tiles"]["zoom_max"])
ACCURACY_FLAG_M = int(_cfg["gps"]["accuracy_flag_m"])
LABELS = _cfg["labels"]
GETTING_THERE = _cfg.get("getting_there", {})

# IGN tile server / layer identifiers — code-level constants (not user config).
IGN = "https://data.geopf.fr/wmts"
IGN_AERIAL = "ORTHOIMAGERY.ORTHOPHOTOS"
IGN_TOPO = "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"


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


def labels(lang):
    """Return the translated label dict for `lang` ('en' or 'fr')."""
    return LABELS[lang]


def getting_there(lang):
    """Return the multi-paragraph getting-there prose for `lang`, or ''."""
    return GETTING_THERE.get(lang, "").strip()
