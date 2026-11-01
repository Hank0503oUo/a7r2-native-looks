#!/usr/bin/env python3
"""Draw the 144-patch calibration chart shown full-screen on a monitor and photographed in RAW+JPEG.

Rows 0-5: 16 hues x 6 saturation/value combinations; row 6: skin and memory colours;
rows 7-8: a 32-step neutral ramp that pins down each style's tone curve.
"""
import colorsys, sys
from PIL import Image, ImageDraw

out = sys.argv[1] if len(sys.argv) > 1 else 'color-chart-1920x1080.png'
W, H = 1920, 1080
im = Image.new('RGB', (W, H), (0, 0, 0)); d = ImageDraw.Draw(im)
cols, rows, m = 16, 9, 24
cw, ch = (W - 2 * m) // cols, (H - 2 * m) // rows
patches = []
combos = [(1.0, 1.0), (0.6, 1.0), (0.3, 1.0), (1.0, 0.7), (0.6, 0.55), (1.0, 0.4)]
for r, (s, v) in enumerate(combos):
    for c in range(cols):
        patches.append((r, c, tuple(round(255 * x) for x in colorsys.hsv_to_rgb(c / cols, s, v))))
memory = [(255, 224, 189), (234, 192, 134), (198, 134, 66), (141, 85, 36), (224, 172, 105), (255, 205, 148),
          (110, 150, 200), (135, 206, 235), (70, 110, 60), (120, 160, 70), (200, 60, 50), (240, 200, 60),
          (90, 60, 140), (40, 120, 120), (180, 120, 160), (230, 230, 210)]
for c, rgb in enumerate(memory):
    patches.append((6, c, rgb))
for i in range(32):
    v = round(255 * i / 31); patches.append((7 + i // 16, i % 16, (v, v, v)))
for r, c, rgb in patches:
    x0, y0 = m + c * cw + 3, m + r * ch + 3
    d.rectangle((x0, y0, x0 + cw - 6, y0 + ch - 6), fill=rgb)
im.save(out)
print(f'{len(patches)} patches -> {out}')
