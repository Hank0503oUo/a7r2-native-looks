#!/usr/bin/env python3
"""Match camera modes to table slots from two rounds of tinted test shots.

Write the round-1 test table (table.py testplan --round 1), photograph the same grey/white
target once in every creative style and picture profile, then repeat with round 2.
shots.tsv has one line per mode:  <mode>\t<round-1 JPEG>\t<round-2 JPEG>

  slotmap.py round1-plan.json round2-plan.json shots.tsv --photos DIR -o result.json
"""
import argparse, colorsys, json
from PIL import Image


def tint(path):
    """Hue (degrees) and saturation of the centre quarter of a JPEG."""
    im = Image.open(path)
    im.draft('RGB', (im.width // 8, im.height // 8))
    im = im.convert('RGB')
    w, h = im.size
    px = im.crop((w * 3 // 8, h * 3 // 8, w * 5 // 8, h * 5 // 8)).resize((32, 32)).tobytes()
    r, g, b = (sum(px[c::3]) / (len(px) // 3) / 255 for c in range(3))
    hue, sat, _ = colorsys.rgb_to_hsv(r, g, b)
    return hue * 360, sat


def circular(a, b):
    return min(abs(a - b), 360 - abs(a - b))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('plan1'); p.add_argument('plan2'); p.add_argument('shots')
    p.add_argument('--photos', default='.'); p.add_argument('-o', '--output', default='result.json')
    a = p.parse_args()
    p1, p2 = json.load(open(a.plan1)), json.load(open(a.plan2))
    result = []
    print(f"{'mode':20} {'hue1':>6} {'hue2':>6} {'sat':>5}  best slot (err)   runner-up (err)")
    for line in open(a.shots, encoding='utf-8'):
        if not line.strip() or line.startswith('#'):
            continue
        mode, f1, f2 = line.rstrip('\n').split('\t')[:3]
        (h1, s1), (h2, s2) = tint(f'{a.photos}/{f1}'), tint(f'{a.photos}/{f2}')
        if min(s1, s2) < 0.1:
            print(f'{mode:20} {h1:6.1f} {h2:6.1f} {min(s1, s2):5.2f}  no tint (monochrome output)')
            result.append([mode, None])
            continue
        # a slot must explain both rounds; summed hue error separates neighbours
        scores = sorted((circular(h1, p1[s]['hue_deg']) + circular(h2, p2[s]['hue_deg']), s) for s in range(len(p1)))
        (e, s), (e2, s_2) = scores[0], scores[1]
        print(f'{mode:20} {h1:6.1f} {h2:6.1f} {min(s1, s2):5.2f}  slot {s:2d} ({e:5.1f})   slot {s_2:2d} ({e2:5.1f})')
        result.append([mode, s, round(e, 1), s_2, round(e2, 1)])
    json.dump(result, open(a.output, 'w'), indent=1)
    print(f'wrote {a.output}')


if __name__ == '__main__':
    main()
