#!/usr/bin/env python3
"""Center-crop an image to a target aspect ratio and save as JPEG.

Usage:
    crop_portrait.py <input> <output> [ratio]

`ratio` is width / height (default 3/4 = 0.75, i.e. portrait 3024x4032).
Applies EXIF orientation first so phone photos land right-side up before the
crop, which is what most users expect from a "crop this to portrait" action.
"""
import sys

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass


def crop_center(im, target_ratio):
    w, h = im.size
    current = w / h
    if abs(current - target_ratio) < 0.001:
        return im
    if current > target_ratio:
        new_w = int(round(h * target_ratio))
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = int(round(w / target_ratio))
    top = (h - new_h) // 2
    return im.crop((0, top, w, top + new_h))


def main():
    if len(sys.argv) < 3:
        print("usage: crop_portrait.py <input> <output> [ratio]", file=sys.stderr)
        sys.exit(2)
    inp, out = sys.argv[1], sys.argv[2]
    ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 3 / 4
    im = Image.open(inp)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    im = crop_center(im, ratio)
    im.save(out, "JPEG", quality=88)


if __name__ == "__main__":
    main()
