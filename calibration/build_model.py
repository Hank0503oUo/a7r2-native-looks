#!/usr/bin/env python3
"""Pair each RAW with its JPEG and fit the camera model  JPEG = T_s(M_s . P . raw).

  build_model.py --photos DIR --shots example-shots.tsv --table table_when_shot.bin -o model.pkl

--table must be the 0x00030001 table that was in the camera WHEN THE CHART WAS SHOT
(M_s comes from it). shots.tsv lines: <file stem>\t<slot>\t<mode name>.
"""
import argparse, os, pickle, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import native_looks as nl

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--photos', required=True); p.add_argument('--shots', required=True)
p.add_argument('--table', required=True); p.add_argument('-o', '--output', default='model.pkl')
a = p.parse_args()

mats, _, _ = nl.table_matrices(a.table)
shots = []
for line in open(a.shots, encoding='utf-8'):
    if line.strip() and not line.startswith('#'):
        f, s, n = line.rstrip('\n').split('\t')[:3]; shots.append((f, int(s), n))
t0 = time.time(); pairs = []
for f, s, n in shots:
    pr = nl.load_pair(os.path.join(a.photos, f + '.ARW'), os.path.join(a.photos, f + '.JPG'))
    pairs.append((pr, s))
    print(f'{f} {n:9} slot {s:2d}: blocks {pr["n"]:5d} shift {pr["shift"]} corr {pr["corr"]}')
P, tones, errs = nl.fit_model(pairs, mats)
print('P =', np.round(P, 4).tolist())
for (f, s, n), e in zip(shots, errs):
    print(f'  {n:9} slot {s:2d}: RMSE {e:5.2f} code values')
pickle.dump(dict(pairs=[(f, s, n, pr) for (f, s, n), (pr, _) in zip(shots, pairs)], P=P, tones=tones, errs=errs),
            open(a.output, 'wb'))
print(f'wrote {a.output} in {time.time() - t0:.0f}s')
