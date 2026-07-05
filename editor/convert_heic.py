"""HEIC -> JPEG converter, called from editor/server.js on upload.

Browsers can't render HEIC natively (Safari aside), so the editor converts
HEIC uploads to JPEG at ingest time. Same `pillow_heif` opener that
generate.py already uses, so no new Python dependency is introduced.

Usage:
    python convert_heic.py <input.heic> <output.jpg>
"""
import sys

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

if len(sys.argv) != 3:
    sys.exit("usage: convert_heic.py <input> <output>")

im = Image.open(sys.argv[1])
if im.mode != "RGB":
    im = im.convert("RGB")
im.save(sys.argv[2], "JPEG", quality=90)
