# downloads the open map data generate.py paints from, into cache/sources
#   python sources.py
#     OpenStreetMap land polygons (shorelines), from osmdata.openstreetmap.de                ~930 MB
#     OpenStreetMap lakes and rivers for Alaska, Hawaii and the territories, from Geofabrik   ~660 MB
#     Natural Earth country borders, and its world lakes (for countries without OSM lakes)   ~10 MB
#   python sources.py --country France [--country Belgium ...]
#     also OpenStreetMap lakes and rivers for those countries, from Geofabrik (sizes vary a lot: a few MB for a small
#     island, gigabytes for a big country, which Geofabrik splits into regions)
# each is unpacked and its zip deleted; anything already unpacked is skipped
import os, sys, json, zipfile, argparse, urllib.request
from common import SOURCES, find_countries, countries

DOWNLOADS = [
    # url, folder, files to keep from the zip (by name start)
    ('https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip', 'land', ['land-polygons-split-4326/land_polygons.']),
    ('https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip', 'countries', ['ne_10m_admin_0_countries.']),
    ('https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip', 'lakes', ['ne_10m_lakes.']),
    ('https://download.geofabrik.de/north-america/us/alaska-latest-free.shp.zip', 'ak', ['gis_osm_water_a_free_1.']),
    ('https://download.geofabrik.de/north-america/us/hawaii-latest-free.shp.zip', 'hi', ['gis_osm_water_a_free_1.']),
    ('https://download.geofabrik.de/north-america/us/puerto-rico-latest-free.shp.zip', 'pr', ['gis_osm_water_a_free_1.']),
    ('https://download.geofabrik.de/north-america/us/us-virgin-islands-latest-free.shp.zip', 'vi', ['gis_osm_water_a_free_1.']),
    # Guam, the Northern Mariana Islands and American Samoa
    ('https://download.geofabrik.de/australia-oceania/american-oceania-latest-free.shp.zip', 'oceania', ['gis_osm_water_a_free_1.']),
]
GEOFABRIK_INDEX = 'https://download.geofabrik.de/index-v1-nogeom.json'


def fetch(url, path):
    with urllib.request.urlopen(url, timeout=120) as res, open(path + '.part', 'wb') as f:
        size = int(res.headers.get('Content-Length') or 0)
        got, shown = 0, -1
        while True:
            chunk = res.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if size and got * 10 // size != shown:
                shown = got * 10 // size
                print(f'  {got / 1e6:,.0f} / {size / 1e6:,.0f} MB', flush=True)
    os.replace(path + '.part', path)


def download(url, folder, keep):
    dest = os.path.join(SOURCES, folder)
    if os.path.isdir(dest) and os.listdir(dest):
        print(f'{folder}: already here')
        return
    os.makedirs(dest, exist_ok=True)
    zpath = dest + '.zip'
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


def geofabrik_extracts(iso2, index):
    """Geofabrik's shapefile downloads covering a country: its own, or (for big countries it only offers in pieces)
    each of its regions'"""
    features = [f['properties'] for f in index['features']]
    children = {}
    for f in features:
        children.setdefault(f.get('parent'), []).append(f)

    def covering(f):
        if 'shp' in f.get('urls', {}):
            return [f]
        return [g for child in children.get(f['id'], []) for g in covering(child)]

    tagged = [f for f in features if iso2 in (f.get('iso3166-1:alpha2') or [])]
    #some downloads are tagged with more than one country (Bermuda is BM and GB); the country's own come first
    only = [f for f in tagged if f['iso3166-1:alpha2'] == [iso2]]
    out = [g for f in (only or tagged) for g in covering(f)]
    return {f['id']: f for f in out}.values()


parser = argparse.ArgumentParser(description='Download the map data generate.py paints from, into ' + SOURCES)
parser.add_argument('--country', action='append', default=[], help="also download a country's OpenStreetMap lakes, by name or code (FRA); repeat for more")
args = parser.parse_args()

for url, folder, keep in DOWNLOADS:
    download(url, folder, keep)

if args.country:
    table = countries()
    iso2 = {rec['ADM0_A3']: rec['ISO_A2_EH'] for rec, _ in table}
    print('reading the Geofabrik index')
    index = json.load(urllib.request.urlopen(GEOFABRIK_INDEX, timeout=120))
    for code in find_countries(args.country, table):
        extracts = list(geofabrik_extracts(iso2[code], index))
        if not extracts:
            print(f'{code}: Geofabrik has no download for it; generate.py will use Natural Earth\'s lakes')
        for f in extracts:
            download(f['urls']['shp'], os.path.join('osm', code, f['id'].replace('/', '_')), ['gis_osm_water_a_free_1.'])
print('done')
