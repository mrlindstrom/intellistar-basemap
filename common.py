import os, math, urllib.request
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
#where the tiles go: archive (downloaded), generated (painted here) and merged (both, for the simulator).
#INTELLISTAR_TILES moves them somewhere else, such as a bigger drive
TILES = os.environ.get('INTELLISTAR_TILES') or os.path.join(HERE, 'tiles')
ARCHIVE = os.path.join(TILES, 'archive')
GENERATED = os.path.join(TILES, 'generated')
MERGED = os.path.join(TILES, 'merged')
#downloaded source data and elevation tiles
CACHE = os.environ.get('INTELLISTAR_CACHE') or os.path.join(HERE, 'cache')
SOURCES = os.path.join(CACHE, 'sources')


def terrarium(z, x, y):
    """elevation in meters for one 256px web mercator tile (AWS open terrain tiles)"""
    p = os.path.join(CACHE, 'terrarium', str(z), str(x), f'{y}.png')
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        url = f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
        data = urllib.request.urlopen(url, timeout=60).read()
        with open(p, 'wb') as f:
            f.write(data)
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def elevation(z, x0, x1, y0, y1, pad=0):
    """mosaic of tiles x0..x1, y0..y1 with pad extra tiles around (for neighborhoods)"""
    n = 2 ** z
    rows = []
    for y in range(y0 - pad, y1 + pad + 1):
        row = []
        for x in range(x0 - pad, x1 + pad + 1):
            row.append(terrarium(z, x % n, y) if 0 <= y < n else np.zeros((256, 256)))
        rows.append(np.hstack(row))
    return np.vstack(rows)


def artwork(z, x0, x1, y0, y1, root=ARCHIVE):
    """mosaic of tiles as float RGB, with a mask of where tiles exist"""
    img = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256, 3))
    have = np.zeros(img.shape[:2], bool)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            p = os.path.join(root, str(z), str(x), f'{y}.png')
            if os.path.exists(p):
                t = np.asarray(Image.open(p).convert('RGBA')).astype(np.float64)
                sl = (slice((y - y0) * 256, (y - y0 + 1) * 256), slice((x - x0) * 256, (x - x0 + 1) * 256))
                img[sl] = t[..., :3]
                have[sl] = t[..., 3] > 0
    return img, have


def tile_lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def meters_per_px(z, lat):
    return 40075016.686 * math.cos(math.radians(lat)) / (256 * 2 ** z)


def hillshade(elev, mpp, azimuth, altitude, exaggeration):
    gy, gx = np.gradient(elev * exaggeration, mpp)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth), math.radians(altitude)
    hs = math.sin(alt) * np.cos(slope) + math.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


def is_water(rgb):
    """the artwork's water: clearly blue (its ocean is about rgb(0, 28, 110), small lakes about rgb(60, 85, 150))"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (b > 80) & (b > r + 50) & (b > g + 40)
