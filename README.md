# IntelliStar basemap tools

Tools for the IntelliStar basemap artwork that the [Weatherscan v2](https://github.com/mrlindstrom/weatherscan-v2) simulator's `intellistar` map look draws:

- **Archive** the artwork from its Mapbox tileset to plain tile files, while that tileset is still online.
- **Generate** matching artwork for Alaska and Hawaii, which the tileset never covered. The tiles are painted from open elevation data and OpenStreetMap shorelines and lakes, in colors learned from the original artwork.
- **Merge** the two into one tile folder that the simulator can load in place of the online tileset.

No tiles are included here, only the tools and the fitted color model (`model_z9.npz`).

## What you need

- [Node.js](https://nodejs.org/) 18 or newer (for `archive.mjs`)
- Python 3.8 or newer, with `pip install -r requirements.txt`
- About 6 GB of free disk space: roughly 2.5 GB of downloaded source data in `cache/`, and the tiles in `tiles/`
- A Mapbox access token, for the archive step only. A public (`pk.`) token is enough, such as the `map_key` in your Weatherscan `yourConfig.json`.

To keep the tiles or the downloads somewhere else, set `INTELLISTAR_TILES` or `INTELLISTAR_CACHE` to another folder before running the steps.

## Steps

### 1. Archive the original artwork

```
node archive.mjs --config path/to/weatherscan-v2/main/configs/yourConfig.json
```

This reads the token from that config. You can set `MAPBOX_TOKEN` instead of passing `--config`. Either way, the token is never printed or saved.

This first run downloads nothing. It lists the tileset's zoom levels, area and tile counts: 48,792 tiles through zoom 10, about 770 MB. Add `--go` to download them into `tiles/archive`, or `--go --max 8` to stop at zoom 8. If it stops partway, run it again and it carries on where it left off.

Each tile is one request on your Mapbox token. Mapbox's free allowance has covered the full download, but check your account's limits.

### 2. Download the map data

```
python sources.py
```

This downloads about 1.4 GB into `cache/sources`:

- OpenStreetMap land polygons, which give the shorelines;
- the OpenStreetMap lakes and rivers for Alaska and Hawaii;
- Natural Earth's country borders.

Elevation tiles are downloaded later, as each area is painted.

### 3. Paint Alaska and Hawaii

```
python generate.py alaska aleutians hawaii
```

This writes zoom 9 tiles to `tiles/generated`.
- `aleutians` is the part of Alaska west of the 180th meridian.
- Hawaii includes open ocean around the islands, so maps centered there aren't cut off.

Alaska is about 5,400 tiles and takes 10–15 minutes, plus a few hundred MB of elevation data. If it stops partway, run it again and it skips what's already done.

### 4. Build the other zooms and merge

```
python pyramid.py
```

This fills in the generated set's other zooms:
- zoom 10 is zoom 9 enlarged, as the original's zoom 10 is;
- zooms 0–8 are scaled down from zoom 9.

It then writes `tiles/merged`: the generated tiles with the archived artwork laid over them, so the original wins wherever it has paint. That's about 50,000 tiles at zoom 10, about 1.6 GB in total.

To look over any block of tiles, stitch it into one picture:

```
python preview.py tiles/merged 4 0 5 3 7 preview.png
```

### 5. Use it in Weatherscan

In the simulator's `yourConfig.json`, set the folder under `appearanceSettings`:

```json
"mapLook": "intellistar",
"intellistarTiles": "C:/path/to/intellistar-basemap/tiles/merged"
```

Then restart the simulator's server. The `intellistar` look now draws its artwork from that folder, and a blank `intellistarTiles` goes back to the online tileset.

## How the painting works

`fit.py` compares the archived US artwork with elevation data for the same places, and saves what it learns in `model_z9.npz`:

- **Land colors:** a color for each pairing of elevation and terrain shading, for US land and for the darker land outside the US. The light comes from the west.
- **The ocean:** its color by distance from shore, from a lighter blue at the shore to the deep navy beyond about 15 km.
- **Lakes:** the lighter blue of small lakes. Lakes over about 400 km², like Iliamna, are painted like the ocean, as the Great Lakes are in the original.

`generate.py` then paints each area:

- shorelines and lakes from OpenStreetMap;
- elevation and shading from the open terrain tiles, colored by the model;
- the darker tint for land that Natural Earth puts outside the US;
- a little fine grain, like the original's texture.

You only need to run `fit.py` again to refit the model, and that requires `tiles/archive`.

## Limits

- Only the areas in `generate.py`'s `REGIONS` are painted. Northern Canada east of 125°W, and everything beyond North America, stays blank.
- Glaciers and icefields are painted by elevation like any other land, because the original artwork has nothing to copy for ice.
- Where the original artwork stops, at 53°N on the British Columbia coast, its tint and the generated tint meet at a faint edge.
- The generated tiles are look-alikes, not recovered originals. Keep the archive and generated folders separate.

## Credits

The generated tiles are made from:

- **OpenStreetMap** shorelines, lakes and rivers: © OpenStreetMap contributors, available under the [Open Database License](https://www.openstreetmap.org/copyright). Anywhere the generated tiles are shown or shared needs this credit. Land polygons are from [osmdata.openstreetmap.de](https://osmdata.openstreetmap.de/), and the lakes and rivers from [Geofabrik](https://download.geofabrik.de/).
- **Elevation** from the [Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) on AWS Open Data, which list their [data sources and credits](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
- **Country borders** from [Natural Earth](https://www.naturalearthdata.com/), which is public domain.

The IntelliStar artwork itself belongs to its creators. These tools only save a copy of it from the tileset it's published in.

## License

The tools are under the [MIT License](LICENSE). The data they download and the tiles they make carry the terms above.
