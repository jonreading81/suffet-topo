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
# Preserve EXIF (GPS / altitude / bearing / accuracy) — generate.py reads it
# at build time to place boulders on the map and set page headers. PIL drops
# it by default; explicitly pass it through.
exif = im.info.get("exif") or b""
if im.mode != "RGB":
    im = im.convert("RGB")
save_kwargs = {"quality": 90}
if exif:
    save_kwargs["exif"] = exif
im.save(sys.argv[2], "JPEG", **save_kwargs)
