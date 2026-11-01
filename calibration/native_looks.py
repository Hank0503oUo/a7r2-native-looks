"""Fit A7R II native colour-matrix slots (backup prop 0x00030001) to reference LUT looks.

Model (per shot, per pixel block):  JPEG = T_s( M_s . P . raw )
  raw  camera RGB after white balance (rawpy, output_color=raw, linear)
  P    fixed sensor->working 3x3, shared by every slot
  M_s  the slot's 3x3 from the colour table (known for every shot)
  T_s  the style's tone curve, one monotone curve shared by R, G and B
A look's target comes from the same RAW: XYZ -> vendor gamut -> vendor log -> official LUT.
The new slot matrix keeps the camera's own luminance and copies the LUT's chromaticity.
"""
import json, struct
import numpy as np
import rawpy
from PIL import Image

XYZ_TO_2020 = np.array([[1.7166512, -0.3556708, -0.2533663], [-0.6666844, 1.6164812, 0.0157685], [0.0176399, -0.0427706, 0.9421031]])
Y709 = np.array([0.2126, 0.7152, 0.0722])

def flog2(x):   # FUJIFILM F-Log2 (scene reflectance -> code value)
    a, b, c, d, e, f, cut = 5.555556, 0.064829, 0.245281, 0.384316, 8.799461, 0.092864, 0.000889
    x = np.asarray(x, dtype=np.float64)
    return np.where(x >= cut, c * np.log10(np.maximum(a * x + b, 1e-12)) + d, e * x + f)

def llog(x):    # Leica L-Log, Reference Manual V1.9 eq. (1)
    a, b, c, d, e, f = 8.0, 0.09, 0.27, 1.3, 0.0115, 0.6
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.006, a * x + b, c * np.log10(np.maximum(d * x + e, 1e-12)) + f)

ENC = {'flog2': flog2, 'llog': llog}

def load_cube(path):
    size, lo, hi, rows = None, np.zeros(3), np.ones(3), []
    for line in open(path, encoding='utf-8', errors='ignore'):
        t = line.split()
        if not t or t[0].startswith('#'): continue
        if t[0] == 'LUT_3D_SIZE': size = int(t[1])
        elif t[0] == 'DOMAIN_MIN': lo = np.array(list(map(float, t[1:4])))
        elif t[0] == 'DOMAIN_MAX': hi = np.array(list(map(float, t[1:4])))
        elif t[0] == 'LUT_3D_INPUT_RANGE': lo, hi = np.full(3, float(t[1])), np.full(3, float(t[2]))
        else:
            try: rows.append([float(v) for v in t[:3]])
            except ValueError: pass
    lut = np.array(rows).reshape(size, size, size, 3)   # index [b][g][r]: red varies fastest
    return lut, lo, hi

def apply_cube(cube, rgb):
    lut, lo, hi = cube; n = lut.shape[0]
    p = np.clip((rgb - lo) / (hi - lo), 0, 1) * (n - 1)
    i0 = np.minimum(np.floor(p).astype(int), n - 2); f = p - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]; fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (fr if dr else 1 - fr) * (fg if dg else 1 - fg) * (fb if db else 1 - fb)
                out = out + w * lut[b0 + db, g0 + dg, r0 + dr]
    return out

def _blocks(img, k):
    h, w = img.shape[0] // k * k, img.shape[1] // k * k
    v = img[:h, :w].reshape(h // k, k, w // k, k, 3)
    return v.mean((1, 3)), v.std((1, 3)).max(-1)

def load_pair(arw, jpg, block=12, search=16, centre=0.7):
    with rawpy.imread(arw) as r:
        kw = dict(use_camera_wb=True, no_auto_bright=True, gamma=(1, 1), output_bps=16, half_size=True, user_flip=0)
        raw = r.postprocess(output_color=rawpy.ColorSpace.raw, **kw).astype(np.float64) / 65535
        xyz = r.postprocess(output_color=rawpy.ColorSpace.XYZ, **kw).astype(np.float64) / 65535
        cw, ch = r.sizes.crop_width // 2, r.sizes.crop_height // 2
    oy, ox = (raw.shape[0] - ch) // 2, (raw.shape[1] - cw) // 2
    raw = raw[oy:oy + ch, ox:ox + cw]; xyz = xyz[oy:oy + ch, ox:ox + cw]
    # the JPEG may be L, M or S size: scale it onto the RAW crop area first
    jp = np.asarray(Image.open(jpg).convert('RGB').resize((cw, ch), Image.BOX), dtype=np.float64) / 255
    # integer shift from gradient correlation in the image centre (JPEG has lens corrections)
    def grad(img):
        g = img.mean(-1) ** 0.45; return np.hypot(np.diff(g, axis=0)[:, :-1], np.diff(g, axis=1)[:-1, :])
    ga, gb = grad(raw), grad(jp)
    y0, y1, x0, x1 = ch // 4, 3 * ch // 4, cw // 4, 3 * cw // 4
    A = ga[y0:y1, x0:x1]; A = (A - A.mean()) / (A.std() + 1e-9); best = (-1e9, 0, 0)
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            B = gb[y0 + dy:y1 + dy, x0 + dx:x1 + dx]; B = (B - B.mean()) / (B.std() + 1e-9)
            c = float(np.mean(A * B))
            if c > best[0]: best = (c, dy, dx)
    corr, dy, dx = best
    jp = np.roll(jp, (-dy, -dx), axis=(0, 1))
    # keep the central part only (distortion correction moves the edges)
    my, mx = int(ch * (1 - centre) / 2), int(cw * (1 - centre) / 2)
    raw, xyz, jp = raw[my:ch - my, mx:cw - mx], xyz[my:ch - my, mx:cw - mx], jp[my:ch - my, mx:cw - mx]
    rb, rs = _blocks(raw, block); xb, _ = _blocks(xyz, block); jb, js = _blocks(jp, block)
    ok = (rs < 0.02 + 0.08 * rb.max(-1)) & (js < 0.03) & (rb.max(-1) < 0.9) & (jb.max(-1) < 0.97) & (jb.min(-1) > 0.02) & (rb.mean(-1) > 0.002)
    return dict(raw=rb[ok], xyz=xb[ok], jpg=jb[ok], shift=(dy, dx), corr=round(corr, 3), n=int(ok.sum()))

class Tone:
    """Monotone curve, linear value -> display code, shared by R, G, B."""
    def __init__(self, v, c, knots=48):
        v = v.ravel(); c = c.ravel(); m = v > 1e-5
        lv = np.log2(v[m]); c = c[m]
        edges = np.quantile(lv, np.linspace(0, 1, knots + 1))
        xs, ys = [], []
        for i in range(knots):
            s = (lv >= edges[i]) & (lv <= edges[i + 1])
            if s.sum() > 3: xs.append(np.median(lv[s])); ys.append(np.median(c[s]))
        ys = np.maximum.accumulate(np.array(ys)); self.x = np.array(xs); self.y = ys + np.arange(len(ys)) * 1e-6
    def __call__(self, v): return np.interp(np.log2(np.maximum(v, 1e-6)), self.x, self.y)
    def inv(self, c): return 2 ** np.interp(c, self.y, self.x)

def fit_model(shots, mats, iters=6):
    """shots: list of (pair, slot); mats: slot -> 3x3. Returns P and per-shot tone curves."""
    # initial guess: sRGB-ish linearisation
    lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    tones = [None] * len(shots)
    for it in range(iters):
        X, Z = [], []
        for k, (p, s) in enumerate(shots):
            l = lin(p['jpg']) if tones[k] is None else tones[k].inv(p['jpg'])
            Z.append(l @ np.linalg.inv(mats[s]).T); X.append(p['raw'])
        X = np.vstack(X); Z = np.vstack(Z)
        P = np.linalg.lstsq(X, Z, rcond=None)[0].T
        for k, (p, s) in enumerate(shots):
            v = p['raw'] @ (mats[s] @ P).T
            tones[k] = Tone(v, p['jpg'])
    errs = []
    for k, (p, s) in enumerate(shots):
        pred = tones[k](p['raw'] @ (mats[s] @ P).T)
        errs.append(float(np.sqrt(np.mean((pred - p['jpg']) ** 2)) * 255))
    return P, tones, errs

def target_display(pair, cube, enc, exposure):
    rgb2020 = np.maximum(pair['xyz'] @ XYZ_TO_2020.T, 0) * exposure
    return np.clip(apply_cube(cube, ENC[enc](rgb2020)), 0, 1)

def fit_slot(pairs, P, tone, base_matrix, targets, weights=None):
    """Least squares for the slot matrix with every row summing to 1 (neutrals stay neutral)."""
    U = np.vstack([p['raw'] @ P.T for p in pairs]); T = np.vstack(targets)
    t = tone.inv(T)                                     # target in the slot's linear domain
    y_cam = (U @ base_matrix.T) @ Y709                   # keep the camera's own luminance
    t = t * (y_cam / np.maximum(t @ Y709, 1e-6))[:, None]
    w = np.ones(len(U)) if weights is None else weights
    M = np.zeros((3, 3)); one = np.ones(3)
    for i in range(3):
        A = U * np.sqrt(w)[:, None]; b = t[:, i] * np.sqrt(w)
        G = A.T @ A; h = A.T @ b
        K = np.block([[2 * G, one[:, None]], [one[None, :], np.zeros((1, 1))]])
        sol = np.linalg.solve(K, np.concatenate([2 * h, [1.0]]))
        M[i] = sol[:3]
    return M

def table_matrices(path):
    v = struct.unpack('<768h', open(path, 'rb').read())
    off = {0: 36, 1: 45, 2: 54, 3: 63, 4: 72, 5: 81, 6: 90, 7: 99, 8: 108, 9: 117, 10: 401, 11: 512, 12: 521, 13: 530, 14: 539, 15: 548, 16: 557}
    return {s: np.array(v[o:o + 9], dtype=np.float64).reshape(3, 3) / 1024 for s, o in off.items()}, list(v), off
