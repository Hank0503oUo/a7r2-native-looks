#!/usr/bin/env python3
"""Rebuild looks v1 (looks/v1.json) from a camera's original table.

v1 used two sources that were NOT fitted to this sensor, which is why it was replaced by v2:
  * Fuji slots: Film Studio's matrices, fitted to FUJIFILM LUTs relative to WDR-709 output.
  * Sony FL / IN, Leica, Hasselblad: Recipe Lab community recipes (creative style + saturation
    + WB shift) turned into a matrix on top of the factory Neutral or Standard matrix.
The recipe scale factors (10% per saturation step, 2.5% per A-B step, 2% per G-M step) are estimates.

  recipes_v1.py my_original.bin -o ../looks/v1.json
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'nativelooks'))
import table

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('base'); p.add_argument('-o', '--output', required=True)
a = p.parse_args()
v = table.load(a.base)
mat = lambda s: [x / 1024 for x in table.matrix(v, s)]
STANDARD, NEUTRAL = mat(0), mat(12)
LUMA = (0.2126, 0.7152, 0.0722)
def mul(x, y): return [sum(x[r * 3 + k] * y[k * 3 + c] for k in range(3)) for r in range(3) for c in range(3)]
def sat(f): return [f * (1 if r == c else 0) + (1 - f) * LUMA[c] for r in range(3) for c in range(3)]
def wb(ab=0, gm=0): return [1 + 0.025 * ab, 0, 0, 0, 1 + 0.02 * gm, 0, 0, 0, 1 - 0.025 * ab]
def recipe(base, s=0, ab=0, gm=0): return mul(wb(ab, gm), mul(sat(1 + 0.10 * s), base))
FS = {  # Film Studio fits of FUJIFILM's published LUTs (rows sum to 1024)
    'PROVIA': [1700, -628, -48, -110, 875, 259, -33, -240, 1297], 'Velvia': [1798, -754, -20, -65, 910, 179, -107, -438, 1569],
    'ASTIA': [1570, -262, -284, -190, 958, 256, -65, -240, 1329], 'Classic Chrome': [1391, -156, -211, 40, 726, 258, -43, 148, 919],
    'REALA ACE': [740, 362, -78, 59, 734, 231, -18, 279, 763], 'Classic Neg': [1054, -384, 354, -62, 671, 415, -313, 417, 920],
    'ETERNA': [1065, 19, -60, -38, 806, 256, -202, 110, 1116]}
FUJI_SRC = 'Film Studio matrix fitted to FUJIFILM F-Log2 LUT (relative to WDR-709, not to this sensor)'
RECIPE_SRC = 'Recipe Lab community recipe converted to a matrix (saturation/WB shift on the factory Neutral or Standard matrix)'
PLAN = [
    (12, '中性 Neutral', 'Fuji PROVIA', [x / 1024 for x in FS['PROVIA']], FUJI_SRC),
    (1, '鮮艷 Vivid', 'Fuji Velvia', [x / 1024 for x in FS['Velvia']], FUJI_SRC),
    (2, '人像 Portrait', 'Fuji ASTIA', [x / 1024 for x in FS['ASTIA']], FUJI_SRC),
    (13, '清晰 Clear', 'Fuji REALA ACE', [x / 1024 for x in FS['REALA ACE']], FUJI_SRC),
    (14, '深色 Deep', 'Fuji Classic Chrome', [x / 1024 for x in FS['Classic Chrome']], FUJI_SRC),
    (4, '日落 Sunset', 'Fuji Classic Neg', [x / 1024 for x in FS['Classic Neg']], FUJI_SRC),
    (7, 'PP4 ITU709 Matrix', 'Fuji ETERNA', [x / 1024 for x in FS['ETERNA']], FUJI_SRC),
    (15, '淡色 Light', 'Sony FL (Recipe Lab: Neutral sat-3 A1)', recipe(NEUTRAL, s=-3, ab=1), RECIPE_SRC),
    (6, 'PP1/PP3 Movie', 'Sony IN (Recipe Lab: Neutral sat-3 M1)', recipe(NEUTRAL, s=-3, gm=-1), RECIPE_SRC),
    (3, '風景 Landscape', 'Leica Contemporary (Recipe Lab: Std sat+1)', recipe(STANDARD, s=1), RECIPE_SRC),
    (11, 'PP5/PP6 Cine', 'Leica Eternal (Recipe Lab: Neutral sat-3 A1)', recipe(NEUTRAL, s=-3, ab=1), RECIPE_SRC),
    (16, '秋葉 Autumn', 'Hasselblad HNCS (Recipe Lab: Neutral sat-1)', recipe(NEUTRAL, s=-1), RECIPE_SRC),
]
slots = [dict(slot=s, menu=menu, look=look, source=src, matrix=[round(x * 1024) for x in m]) for s, menu, look, m, src in PLAN]
json.dump(dict(name='v1', camera='ILCE-7RM2, firmware 4.01', unit=1024, written='2026-10-25',
               notes='Superseded by v2. Kept for reference: the Fuji matrices were not fitted to this camera and oversaturate.',
               slots=slots), open(a.output, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'wrote {a.output} ({len(slots)} slots)')
