#!/usr/bin/env python3
"""Fit one 3x3 per table slot so the camera's own rendering matches an official LUT look.

  fit_looks.py --model model.pkl --base my_original.bin --plan v2-plan.json \
      --fuji-luts DIR --leica-luts DIR [--compare ../looks/v1.json] -o ../looks/v2.json

1. Target: RAW -> XYZ -> BT.2020 -> vendor log (F-Log2 / L-Log) -> official LUT -> display RGB.
2. Linear fit: least squares with every row summing to 1 (greys stay grey), keeping the camera's
   luminance from the factory matrix so only chromaticity changes.
3. Refinement: Levenberg-Marquardt on the 6 free coefficients, minimising display chromaticity error
   through the style's own tone curve; then round to 1/1024 and fix the row sums exactly.
--base supplies the factory matrices (the "factory_style" comparison and the luminance reference).
"""
import argparse, json, os, pickle, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import native_looks as nl

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('--model', required=True); p.add_argument('--base', required=True); p.add_argument('--plan', required=True)
p.add_argument('--fuji-luts', default='.'); p.add_argument('--leica-luts', default='.')
p.add_argument('--compare', help='previous looks JSON to report errors for'); p.add_argument('-o', '--output', required=True)
a = p.parse_args()

model = pickle.load(open(a.model, 'rb'))
pairs, P, tones = model['pairs'], model['P'], model['tones']
factory, _, _ = nl.table_matrices(a.base)
plan = json.load(open(a.plan, encoding='utf-8'))
previous = {}
if a.compare:
    previous = {e['slot']: np.array(e['matrix']).reshape(3, 3) / 1024 for e in json.load(open(a.compare, encoding='utf-8'))['slots']}
tone_of = {}
for (f, s, n, pr), t in zip(pairs, tones):
    tone_of.setdefault(s, t)                      # first shot of each slot carries that style's tone curve
use = [pr for (f, s, n, pr) in pairs if n != 'PP7']   # S-Log2 is far from the other curves; leave it out
xyz = np.vstack([pr['xyz'] for pr in use]); raw = np.vstack([pr['raw'] for pr in use]); U = raw @ P.T
Yw = np.percentile(xyz[:, 1], 99.5); exposure = 0.9 / Yw   # chart white -> 0.9 scene reflectance
print(f'samples {len(U)}  chart white Y={Yw:.4f}  exposure x{exposure:.2f}')
lut_dirs = dict(fuji=(a.fuji_luts, 'FLog2_to_{}_33grid_V.1.00.cube'), leica=(a.leica_luts, '{}_Rec709.cube'))


def chroma(v): return v / np.maximum(v.sum(1, keepdims=True), 1e-6)
def err(M, tone, Us, tg): return chroma(tone(Us @ M.T)) - chroma(tg)


def build(theta):
    """Six free coefficients; each row's remaining entry makes the row sum exactly 1."""
    M = np.zeros((3, 3))
    for i in range(3):
        u, v = theta[2 * i], theta[2 * i + 1]
        M[i] = [u, v, 1 - u - v] if i == 0 else ([u, 1 - u - v, v] if i == 1 else [u, v, 1 - u - v])
    return M


def unbuild(M): return np.array([M[0, 0], M[0, 1], M[1, 0], M[1, 2], M[2, 0], M[2, 1]])


def refine(M0, tone, Us, tg, iters=40):
    th = unbuild(M0); lam = 1e-3
    r = err(build(th), tone, Us, tg).ravel(); cost = r @ r
    for _ in range(iters):
        J = np.zeros((r.size, 6)); h = 1e-4
        for k in range(6):
            t2 = th.copy(); t2[k] += h; J[:, k] = (err(build(t2), tone, Us, tg).ravel() - r) / h
        A = J.T @ J; g = J.T @ r
        while True:
            t2 = th + np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -g)
            r2 = err(build(t2), tone, Us, tg).ravel(); c2 = r2 @ r2
            if c2 < cost: th, r, cost, lam = t2, r2, c2, lam * 0.3; break
            lam *= 10
            if lam > 1e8: return build(th)
    return build(th)


rng = np.random.default_rng(0)
out = []
for e in plan['slots']:
    slot = e['slot']; tone = tone_of[slot]
    d, pattern = lut_dirs[e['lut']]
    cube = nl.load_cube(os.path.join(d, pattern.format(e['name'])))
    tg = np.clip(nl.apply_cube(cube, nl.ENC[e['encoding']](np.maximum(xyz @ nl.XYZ_TO_2020.T, 0) * exposure)), 0, 1)
    ycam = (U @ factory[slot].T) @ nl.Y709
    mask = (tg.max(1) < 0.995) & (tg.min(1) > 0.005) & (ycam > np.percentile(ycam, 5))   # skip clipped and darkest blocks
    # step 2: constrained linear fit, quantised like the table
    M_lin = nl.fit_slot([dict(raw=raw[mask])], P, tone, factory[slot], [tg[mask]])
    M0 = np.round(M_lin * 1024) / 1024
    # step 3: refine on a fixed random subsample
    keep = np.where(mask)[0]
    sub = rng.choice(keep, size=min(25000, len(keep)), replace=False)
    M = refine(M0, tone, U[sub], tg[sub])
    q = np.round(M * 1024).astype(int)
    for i in range(3):
        q[i, i] += 1024 - q[i].sum()                 # exact row sums after rounding
    score = lambda MM: round(float(np.sqrt(np.mean(np.sum(err(MM, tone, U[keep], tg[keep]) ** 2, 1))) * 1000), 1)
    errs = dict(v2=score(q / 1024), v2_linear_fit=score(M0))
    if slot in previous: errs['v1'] = score(previous[slot])
    errs['factory_style'] = score(factory[slot])
    src = ('official FUJIFILM GFX ETERNA 55 LUT v1.00 (F-Log2 input)' if e['lut'] == 'fuji' else 'official Leica L-Log LUT (Rec709 output)')
    out.append(dict(slot=slot, menu=e['menu'], look=e['look'], source=src + '; fitted to this camera from RAW+JPEG chart shots',
                    matrix=q.ravel().tolist(), chroma_err_x1000=errs))
    print(f"slot {slot:2d} {e['look']:22} " + ' | '.join(' '.join('%5d' % x for x in q[k]) for k in range(3)) + f'   err {errs}')
if plan.get('keep_from'):
    kept = json.load(open(os.path.join(os.path.dirname(os.path.abspath(a.plan)), plan['keep_from']), encoding='utf-8'))['slots']
    for e in kept:
        if e['slot'] in plan.get('keep_slots', []):
            out.append(dict(e, source=e['source'] + (' (kept from v1)' if 'kept from' not in e['source'] else '')))
result = dict(name='v2', camera='ILCE-7RM2, firmware 4.01', unit=1024,
              notes='chroma_err_x1000 is the predicted RMS chromaticity error against the target LUT on the calibration chart (lower is better); '
                    'factory_style is the unmodified style compared with the same target. Verification shots after writing are still pending.',
              calibration=dict(exposure=exposure, P=P.tolist()), slots=out)
json.dump(result, open(a.output, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'wrote {a.output}')
