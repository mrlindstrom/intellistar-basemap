# paints IntelliStar-style tiles for an area at zoom 9 into tiles/generated, from OpenStreetMap shorelines and lakes
# (sources.py) and open elevation data (downloaded as needed into cache/terrarium), colored by model_z9.npz
#   python generate.py <region> [<region> ...]     regions: see REGIONS, or all
# run again to resume: areas whose tiles are all there are skipped
import sys, os, math, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import shapefile
from scipy import ndimage
from PIL import Image, ImageDraw
from common import *

Z = 9
#each with open ocean around it, so maps centered there aren't cut off
REGIONS = {
    # west, south, east, north, lakes folders in cache/sources
    'alaska': (-180.0, 50.5, -125.0, 72.0, ['ak']),
    'aleutians': (172.0, 50.5, 180.0, 54.0, ['ak']),  # Alaska west of the 180th meridian
    'hawaii': (-165.0, 15.5, -150.5, 25.5, ['hi']),
    # the original artwork has these islands but stops just south of them
    'puerto-rico': (-68.5, 12.5, -63.5, 20.5, ['pr', 'vi']),
    'guam': (143.0, 11.5, 147.5, 21.0, ['oceania']),  # and the Northern Mariana Islands
    'american-samoa': (-172.5, -16.0, -167.5, -10.0, ['oceania']),
}
#land Natural Earth puts in these gets the brighter US colors (the original paints Puerto Rico that way);
#the rest gets the darker colors the original uses outside the US
US = ('USA', 'PRI', 'VIR', 'GUM', 'MNP', 'ASM', 'UMI')
CHUNK = 8  # tiles per side painted together (plus a tile of margin all around, for shading and the coastal glow)
SS = 2  # supersampling for smooth edges
BIG_LAKE_M2 = 4e8  # lakes this big are painted like the ocean, as the Great Lakes are

m = np.load(os.path.join(HERE, f'model_z{Z}.npz'))
edges, hbins = m['edges'], int(m['hbins'])
world = 256 * 2 ** Z

# open ocean is one flat color in the artwork; keep tiny wobbles in the fitted profile from drawing rings
profile = m['water_profile'].copy()
far_water = np.median(profile[m['dedges'] >= 15000], axis=0)
profile[m['dedges'] >= 15000] = far_water
for i in range(len(profile) - 2, -1, -1):
    if m['dedges'][i] >= 1000:
        profile[i] = np.maximum(profile[i], profile[i + 1])


def px(lon, lat):
    x = (lon + 180) / 360 * world
    y = (1 - np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) / np.pi) / 2 * world
    return x, y


def tx(lon):
    return int((lon + 180) / 360 * 2 ** Z)


def ty(lat):
    return int((1 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / math.pi) / 2 * 2 ** Z)


class Layer:
    """polygons in world pixel coordinates, with bounding boxes for quick lookup"""

    def __init__(self):
        self.rings, self.boxes = [], []

    def add(self, shape):
        pts = np.asarray(shape.points, dtype=np.float64)
        if not len(pts):
            return
        parts = list(shape.parts) + [len(pts)]
        rings = []
        for a, b in zip(parts[:-1], parts[1:]):
            r = pts[a:b]
            x, y = px(r[:, 0], np.clip(r[:, 1], -85, 85))
            # shapefiles wind outer rings clockwise and holes counterclockwise (in lon/lat, y up)
            area = 0.5 * np.sum(r[:-1, 0] * r[1:, 1] - r[1:, 0] * r[:-1, 1])
            rings.append((np.stack([x, y], 1).astype(np.float32), area > 0))
        allx = np.concatenate([r[0][:, 0] for r in rings])
        ally = np.concatenate([r[0][:, 1] for r in rings])
        self.rings.append(rings)
        self.boxes.append((allx.min(), ally.min(), allx.max(), ally.max()))

    def done(self):
        self.boxes = np.array(self.boxes).reshape(-1, 4)

    def draw(self, x0, y0, w, h, keep=None):
        """coverage 0..1 of the window at world px (x0, y0) size w x h"""
        img = Image.new('L', (w * SS, h * SS), 0)
        d = ImageDraw.Draw(img)
        b = self.boxes
        hit = np.flatnonzero((b[:, 2] >= x0) & (b[:, 0] <= x0 + w) & (b[:, 3] >= y0) & (b[:, 1] <= y0 + h))
        for i in hit:
            if keep is not None and not keep[i]:
                continue
            for ring, hole in sorted(self.rings[i], key=lambda r: r[1]):
                if len(ring) < 3:
                    continue
                pts = ((ring - (x0, y0)) * SS).ravel().tolist()
                d.polygon(pts, fill=0 if hole else 255)
        a = np.asarray(img, dtype=np.float32) / 255
        return a.reshape(h, SS, w, SS).mean(axis=(1, 3))


def load(path, bbox, want=None):
    layer, extra = Layer(), []
    r = shapefile.Reader(path)
    fields = [f[0] for f in r.fields[1:]]
    t = time.time()
    for sr in r.iterShapeRecords(bbox=bbox):
        rec = dict(zip(fields, sr.record))
        if want and not want(rec):
            continue
        n = len(layer.rings)
        layer.add(sr.shape)
        if len(layer.rings) > n:
            extra.append(rec)
    layer.done()
    print(f'  {os.path.basename(path)}: {len(layer.rings)} polygons ({time.time() - t:.0f}s)')
    return layer, extra


def ring_area_m2(ring):
    # world px -> meters at the ring's latitude
    y = ring[:, 1].mean()
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / world))))
    mpp = 40075016.686 * math.cos(math.radians(lat)) / world
    x, yy = ring[:, 0].astype(np.float64), ring[:, 1].astype(np.float64)
    return abs(0.5 * np.sum(x[:-1] * yy[1:] - x[1:] * yy[:-1])) * mpp ** 2


def value_noise(x0, y0, w, h, cell, seed):
    """smooth random values, -1..1, at world px; the same everywhere a window lands, so areas join without seams"""
    wrap = world // cell
    xs, ys = (np.arange(w) + x0) / cell, (np.arange(h) + y0) / cell
    ix, iy = np.floor(xs).astype(np.int64), np.floor(ys).astype(np.int64)
    fx, fy = xs - ix, ys - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def corner(cx, cy):
        hsh = ((cx[None, :] % wrap) * 73856093) ^ (cy[:, None] * 19349663) ^ (seed * 83492791)
        hsh = (hsh ^ (hsh >> 13)) * 1274126177 & 0xFFFFFFFF
        return (hsh ^ (hsh >> 16)) % 2048 / 1023.5 - 1

    top = corner(ix, iy) * (1 - fx) + corner(ix + 1, iy) * fx
    bottom = corner(ix, iy + 1) * (1 - fx) + corner(ix + 1, iy + 1) * fx
    return top * (1 - fy[:, None]) + bottom * fy[:, None]


#the ocean's blotches show at every size from a few pixels to a few dozen, so a few sizes of noise are added up,
#each made the same strength, then scaled to the texture measured in the original
OCEAN_CELLS = (2, 8, 32)
_scale = [value_noise(0, 0, 512, 512, c, i).std() for i, c in enumerate(OCEAN_CELLS)]


def ocean_texture(x0, y0, w, h):
    n = sum(value_noise(x0, y0, w, h, c, i) / s for i, (c, s) in enumerate(zip(OCEAN_CELLS, _scale)))
    return (n / math.sqrt(len(OCEAN_CELLS)))[..., None] * m['ocean_texture']


def tile_path(x, y):
    return os.path.join(GENERATED, str(Z), str(x), f'{y}.png')


def run(name):
    west, south, east, north, lake_dirs = REGIONS[name]
    tx0, tx1, ty0, ty1 = tx(west), min(tx(east - 1e-9), 2 ** Z - 1), ty(north), ty(south)
    print(f'{name}: z{Z} tiles x {tx0}-{tx1}, y {ty0}-{ty1} ({(tx1 - tx0 + 1) * (ty1 - ty0 + 1)} tiles)')

    bbox = [west - 0.5, south - 0.5, east + 0.5, north + 0.5]
    land, _ = load(os.path.join(SOURCES, 'land', 'land_polygons.shp'), bbox)
    lakes = Layer()
    for d in lake_dirs:
        part, _ = load(os.path.join(SOURCES, d, 'gis_osm_water_a_free_1.shp'), bbox,
                       lambda rec: rec['fclass'] in ('water', 'reservoir', 'riverbank'))
        lakes.rings += part.rings
        lakes.boxes += [tuple(b) for b in part.boxes]
    lakes.done()
    countries, crec = load(os.path.join(SOURCES, 'countries', 'ne_10m_admin_0_countries.shp'), bbox)
    foreign = np.array([rec['ADM0_A3'] not in US for rec in crec], bool)
    big = np.array([max((ring_area_m2(r) for r, hole in rings if not hole), default=0) >= BIG_LAKE_M2
                    for rings in lakes.rings], bool)
    print(f'  {big.sum()} lakes big enough to paint like the ocean')

    def chunk(cx0, cy0):
        cx1, cy1 = min(cx0 + CHUNK - 1, tx1), min(cy0 + CHUNK - 1, ty1)
        pad = 1
        wx0, wy0 = (cx0 - pad) * 256, (cy0 - pad) * 256
        w, h = (cx1 - cx0 + 1 + 2 * pad) * 256, (cy1 - cy0 + 1 + 2 * pad) * 256
        landc = land.draw(wx0, wy0, w, h)
        mpp = meters_per_px(Z, tile_lat((cy0 + cy1 + 1) / 2, Z))
        tiles = [(x, y) for x in range(cx0, cx1 + 1) for y in range(cy0, cy1 + 1)]
        if landc.max() == 0:
            rgb = np.clip(np.round(far_water + ocean_texture(wx0, wy0, w, h)), 0, 255).astype(np.uint8)
            return [(x, y, rgb[(y - cy0 + pad) * 256:(y - cy0 + pad + 1) * 256, (x - cx0 + pad) * 256:(x - cx0 + pad + 1) * 256])
                    for x, y in tiles]
        # elevation for the area, fetched 16 at a time
        jobs = [(x % 2 ** Z, y) for x in range(cx0 - pad, cx1 + pad + 1) for y in range(cy0 - pad, cy1 + pad + 1) if 0 <= y < 2 ** Z]
        with ThreadPoolExecutor(16) as ex:
            list(ex.map(lambda j: terrarium(Z, *j), jobs))
        bigc = lakes.draw(wx0, wy0, w, h, keep=big)
        smallc = lakes.draw(wx0, wy0, w, h, keep=~big)
        forc = countries.draw(wx0, wy0, w, h, keep=foreign)
        # Natural Earth's borders are coarse; spread the foreign mask a little so its coasts are covered
        forc = ndimage.maximum_filter(forc, size=int(3000 / mpp) * 2 + 1)
        landc = landc * (1 - bigc)
        smallc = np.minimum(smallc, landc)

        elev = elevation(Z, cx0, cx1, cy0, cy1, pad)
        e = ndimage.gaussian_filter(elev, float(m['blur'])) if float(m['blur']) else elev
        hs = hillshade(e, mpp, float(m['az']), float(m['alt']), float(m['ex']))
        eb = np.clip(np.digitize(np.maximum(elev, 1), edges) - 1, 0, len(edges) - 2)
        hb = np.clip((hs * hbins).astype(int), 0, hbins - 1)
        f = forc[..., None]
        land_rgb = m['lut_us'][eb, hb] * (1 - f) + m['lut_foreign'][eb, hb] * f
        # the artwork's fine texture, as a little blurred noise
        rng = np.random.default_rng(cx0 * 100003 + cy0)
        grain = ndimage.gaussian_filter(rng.normal(0, 1, elev.shape), 0.7)
        land_rgb = land_rgb + grain[..., None] * (m['noise_us'] * (1 - f) + m['noise_foreign'] * f) * 0.8

        # water by distance from shore: the lighter glow along the coast fading out to the deep ocean color
        dist = ndimage.distance_transform_edt(~(landc > 0.5)) * mpp
        water_rgb = np.stack([np.interp(dist, m['dedges'], profile[:, k]) for k in range(3)], -1) + ocean_texture(wx0, wy0, w, h)
        a = landc[..., None]
        rgb = land_rgb * a + water_rgb * (1 - a)
        s = smallc[..., None]
        rgb = np.clip(rgb * (1 - s) + m['lake_color'] * s, 0, 255).astype(np.uint8)
        out = []
        for x, y in tiles:
            r0, c0 = (y - cy0 + pad) * 256, (x - cx0 + pad) * 256
            out.append((x, y, rgb[r0:r0 + 256, c0:c0 + 256]))
        return out

    chunks = [(x, y) for y in range(ty0, ty1 + 1, CHUNK) for x in range(tx0, tx1 + 1, CHUNK)]
    t = time.time()
    for i, (cx, cy) in enumerate(chunks):
        if all(os.path.exists(tile_path(x, y)) for x in range(cx, min(cx + CHUNK, tx1 + 1)) for y in range(cy, min(cy + CHUNK, ty1 + 1))):
            continue
        for x, y, rgb in chunk(cx, cy):
            p = tile_path(x, y)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Image.fromarray(np.ascontiguousarray(rgb)).save(p)
        print(f'  area {i + 1}/{len(chunks)} ({time.time() - t:.0f}s)', flush=True)
    print(f'{name}: done')


names = list(REGIONS) if sys.argv[1:] == ['all'] else sys.argv[1:]
if not names or any(n not in REGIONS for n in names):
    sys.exit('usage: python generate.py <region> [<region> ...]   regions: ' + ', '.join(REGIONS))
for n in names:
    run(n)
