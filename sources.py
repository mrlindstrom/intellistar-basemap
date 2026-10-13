# downloads the open map data generate.py paints from, into cache/sources (about 1.5 GB of downloads)
#   python sources.py
#     OpenStreetMap land polygons (shorelines), from osmdata.openstreetmap.de      ~930 MB
#     OpenStreetMap lakes and rivers for Alaska and Hawaii, from Geofabrik           ~470 MB
#     Natural Earth country borders (which land is outside the US)                   ~5 MB
# each is unpacked and its zip deleted; anything already unpacked is skipped
import os, sys, zipfile, urllib.request
from common import SOURCES

DOWNLOADS = [
    # url, folder, files to keep from the zip (by name start)
    ('https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip', 'land', ['land-polygons-split-4326/land_polygons.']),
    ('https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip', 'countries', ['ne_10m_admin_0_countries.']),
    ('https://download.geofabrik.de/north-america/us/alaska-latest-free.shp.zip', 'ak', ['gis_osm_water_a_free_1.']),
    ('https://download.geofabrik.de/north-america/us/hawaii-latest-free.shp.zip', 'hi', ['gis_osm_water_a_free_1.']),
]


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=120) as res, open(path + '.part', 'wb') as f:
        size = int(res.headers.get('Content-Length') or 0)
        got = 0
        while True:
            chunk = res.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if size:
                sys.stdout.write(f'\r  {got / 1e6:,.0f} / {size / 1e6:,.0f} MB')
                sys.stdout.flush()
    print()
    os.replace(path + '.part', path)


for url, folder, keep in DOWNLOADS:
    dest = os.path.join(SOURCES, folder)
    if os.path.isdir(dest) and os.listdir(dest):
        print(f'{folder}: already here')
        continue
    os.makedirs(dest, exist_ok=True)
    zpath = os.path.join(SOURCES, folder + '.zip')
    if not os.path.exists(zpath):
        print(f'{folder}: downloading {url}')
        fetch(url, zpath)
    print(f'{folder}: unpacking')
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if any(name.startswith(k) for k in keep):
                with z.open(name) as src, open(os.path.join(dest, os.path.basename(name)), 'wb') as out:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
    os.remove(zpath)
print('done')
