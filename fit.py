# learns how the archived IntelliStar artwork colors land and water, from its tiles and open elevation data
#   python fit.py <zoom>     writes model_z<zoom>.npz, with a lookup for US land and one for the darker land outside it
import sys, math
import numpy as np
from scipy import ndimage
from common import *

z = int(sys.argv[1]) if len(sys.argv) > 1 else 9
k = 2 ** (z - 8)


def boxes(spec):
    """z8 boxes (x0, x1, y0, y1) cut into 4x4-tile pieces at this zoom, spread over each box"""
    out = []
    for x0, x1, y0, y1 in spec:
        xs = range(x0 * k, (x1 + 1) * k - 3, max(4, (x1 - x0 + 1) * k // 4))
        ys = range(y0 * k, (y1 + 1) * k - 3, max(4, (y1 - y0 + 1) * k // 3))
        out += [(x, x + 3, y, y + 3) for x in xs for y in ys]
    return out


# interior US: west, mountains, plains, east. outside: southern Canada's mountains and prairies
regions = {
    'us': boxes([(40, 66, 92, 101), (67, 74, 93, 102)]),
    'foreign': boxes([(40, 62, 83, 86)]),
}
edges = np.array([-1e9, 0, 50, 100, 150, 200, 300, 400, 500, 650, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2250, 2500, 2750, 3000, 3300, 3600, 4000, 1e9])
rng = np.random.default_rng(0)


def collect(box_list):
    cols = {'rgb': [], 'elev': [], 'gx': [], 'gy': [], 'gx1': [], 'gy1': [], 'mpp': []}
    small_lakes = []
    for b in box_list:
        img, have = artwork(z, *b)
        if have.mean() < 0.9:
            continue
        elev = elevation(z, *b)
        mpp = meters_per_px(z, tile_lat((b[2] + b[3] + 1) / 2, z))
        water = is_water(img)
        ok = have & ~water & (elev > 0)
        lab, n = ndimage.label(water & have & (elev > 5))
        if n:
            sizes = ndimage.sum(water, lab, np.arange(1, n + 1))
            lk = ndimage.binary_erosion(np.isin(lab, 1 + np.flatnonzero(sizes * mpp ** 2 < 4e8)))
            if lk.sum():
                small_lakes.append(img[lk])
        idx = rng.choice(np.flatnonzero(ok), min(60000, ok.sum()), replace=False)
        gy, gx = np.gradient(elev, mpp)
        gy1, gx1 = np.gradient(ndimage.gaussian_filter(elev, 1), mpp)
        cols['rgb'].append(img.reshape(-1, 3)[idx])
        for name, a in (('elev', elev), ('gx', gx), ('gy', gy), ('gx1', gx1), ('gy1', gy1)):
            cols[name].append(a.ravel()[idx])
        cols['mpp'].append(np.full(len(idx), mpp))
        print(f'  box {b}: {len(idx)} samples')
    out = {k2: np.concatenate(v) for k2, v in cols.items()}
    out['small_lakes'] = np.concatenate(small_lakes) if small_lakes else np.zeros((0, 3))
    return out


def shade(gx, gy, az, alt, ex):
    slope = np.arctan(np.hypot(gx, gy) * ex)
    aspect = np.arctan2(-gx, gy)
    a, h = math.radians(az), math.radians(alt)
    return np.clip(math.sin(h) * np.cos(slope) + math.cos(h) * np.sin(slope) * np.cos(a - aspect), 0, 1)


hbins = 20
model = {'edges': edges, 'hbins': hbins}
for region, box_list in regions.items():
    print(f'{region}: {len(box_list)} boxes')
    d = collect(box_list)
    lum = d['rgb'].mean(1)
    eb = np.clip(np.digitize(d['elev'], edges) - 1, 0, len(edges) - 2)
    resid = lum.copy()
    for b in range(len(edges) - 1):
        m = eb == b
        if m.any():
            resid[m] -= lum[m].mean()
    if region == 'us':
        best = None
        for blur, gx, gy in ((0, d['gx'], d['gy']), (1, d['gx1'], d['gy1'])):
            for ex in (2, 4, 8, 12, 16, 24, 32, 48):
                for az in range(0, 360, 15):
                    for alt in (25, 35, 45, 55):
                        c = np.corrcoef(shade(gx, gy, az, alt, ex), resid)[0, 1]
                        if best is None or c > best[0]:
                            best = (c, az, alt, ex, blur)
        c, az, alt, ex, blur = best
        print(f'light: azimuth {az}, altitude {alt}, exaggeration {ex}, blur {blur} (correlation {c:.3f})')
        model.update(az=az, alt=alt, ex=ex, blur=blur)
        model['lake_color'] = np.median(d['small_lakes'], axis=0) if len(d['small_lakes']) > 50 else np.array([60, 85, 149])
        print('lake color:', model['lake_color'].round())
    gx, gy = (d['gx1'], d['gy1']) if model['blur'] else (d['gx'], d['gy'])
    hs = shade(gx, gy, model['az'], model['alt'], model['ex'])
    hb = np.clip((hs * hbins).astype(int), 0, hbins - 1)
    lut = np.full((len(edges) - 1, hbins, 3), np.nan)
    for b in range(len(edges) - 1):
        for h in range(hbins):
            m = (eb == b) & (hb == h)
            if m.sum() >= 30:
                lut[b, h] = np.median(d['rgb'][m], axis=0)
    for b in range(lut.shape[0]):
        good = ~np.isnan(lut[b, :, 0])
        if good.sum() >= 2:
            for c3 in range(3):
                lut[b, :, c3] = np.interp(np.arange(hbins), np.flatnonzero(good), lut[b, good, c3])
    for h in range(hbins):
        good = ~np.isnan(lut[:, h, 0])
        if good.any():
            for c3 in range(3):
                lut[:, h, c3] = np.interp(np.arange(lut.shape[0]), np.flatnonzero(good), lut[good, h, c3])
    model[f'lut_{region}'] = lut
    model[f'noise_{region}'] = np.std(d['rgb'] - lut[eb, hb], axis=0)
    print(f'{region} texture noise:', model[f'noise_{region}'].round(1))

# water: color by distance to land, in meters, from the California and Oregon coast
cb = (38 * k, 38 * k + 3, 95 * k, 95 * k + 7) if z >= 9 else (37, 41, 92, 102)
cimg, chave = artwork(z, *cb)
cw = is_water(cimg) & chave
dist = ndimage.distance_transform_edt(cw) * meters_per_px(z, tile_lat((cb[2] + cb[3] + 1) / 2, z))
dedges = np.concatenate([np.arange(0, 3000, 250), np.arange(3000, 20000, 1000), np.arange(20000, 60001, 5000)])
db = np.digitize(dist, dedges) - 1
prof = np.full((len(dedges), 3), np.nan)
for b in range(len(dedges)):
    m = cw & (db == b)
    if m.sum() >= 30:
        prof[b] = np.median(cimg[m], axis=0)
good = ~np.isnan(prof[:, 0])
for c3 in range(3):
    prof[:, c3] = np.interp(np.arange(len(dedges)), np.flatnonzero(good), prof[good, c3])
print('water by distance (m):', {int(d): tuple(c.round().astype(int)) for d, c in zip(dedges[::4], prof[::4])})
model.update(dedges=dedges, water_profile=prof)

# the open ocean isn't flat: it has a faint blotchy texture, a couple of shades either way, measured out in the Gulf
gb = tuple(int(v * 2 ** (z - 9)) for v in (124, 131, 216, 222))
gimg, ghave = artwork(z, *gb)
gulf = gimg - np.stack([ndimage.gaussian_filter(gimg[..., c3], 48) for c3 in range(3)], -1)
model['ocean_texture'] = gulf[ghave].std(axis=0)
print('ocean texture:', model['ocean_texture'].round(2))
np.savez(f'{HERE}/model_z{z}.npz', **model)
