# IntelliStar basemap tools

Tools for the IntelliStar basemap artwork that the [Weatherscan v2](https://github.com/mrlindstrom/weatherscan-v2) simulator's `intellistar` map look draws:

- **Archive** the artwork from its Mapbox tileset to plain tile files, while that tileset is still online.
- **Generate** matching artwork for Alaska, Hawaii and the US territories, which the tileset never covered (or, for Puerto Rico and the Virgin Islands, cuts off just south of). The tiles are painted from open elevation data and OpenStreetMap shorelines and lakes, in colors learned from the original artwork.
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

This downloads about 1.6 GB into `cache/sources`:

- OpenStreetMap land polygons, which give the shorelines;
- the OpenStreetMap lakes and rivers for Alaska, Hawaii, Puerto Rico, the US Virgin Islands, and Guam, the Northern Mariana Islands and American Samoa;
- Natural Earth's country borders, and its world lakes.

Elevation tiles are downloaded later, as each area is painted.

To paint other countries (see [Other countries](#other-countries)), add their lakes and rivers too:

```
python sources.py --country France --country Belgium
```

### 3. Paint Alaska, Hawaii and the territories

```
python generate.py all
```

This writes zoom 9 tiles to `tiles/generated`. You can also name regions instead of `all`:

| Region | Covers |
|---|---|
| `alaska` | Alaska east of the 180th meridian, with the Yukon and northern British Columbia beside it |
| `aleutians` | The part of Alaska west of the 180th meridian |
| `hawaii` | The main Hawaiian islands |
| `puerto-rico` | Puerto Rico and the US Virgin Islands. The original artwork has these, but stops just south of them. |
| `guam` | Guam and the Northern Mariana Islands |
| `american-samoa` | American Samoa |

Each region includes open ocean around it, so maps centered there aren't cut off. Alaska is most of the work: about 5,400 tiles, 10–15 minutes and a few hundred MB of elevation data. If it stops partway, run it again and it skips what's already done.

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

## Other countries

The original artwork paints the US in brighter colors and everything outside it, like Canada and Mexico, darker. `generate.py` can paint any country in those brighter "home" colors instead, with every other country dark:

```
python sources.py --country France --country Belgium
python generate.py --country France --country Belgium
python pyramid.py --no-archive
```

**Naming countries:** use the country's name (`France`, `"United Kingdom"`) or its three-letter code (`FRA`, `GBR`), as Natural Earth lists them.

**Which areas get painted:** each country's land and the sea around it, out to 1.5°. Far-off islands, like France's overseas regions, become separate small areas rather than one huge box.

**Home colors:**
- Every `--country` is a home country.
- To choose the home countries separately, use `--home FRA,BEL`. For example, `python generate.py --country Belgium --home FRA,BEL` paints the area around Belgium with both countries in the home colors.
- Without `--country` or `--home`, the home colors go to the US and its territories, as in the original.

**Lakes:** `sources.py --country` downloads each country's OpenStreetMap lakes and rivers from [Geofabrik](https://download.geofabrik.de/). Big countries come in regional pieces and can run to several GB. Neighboring countries, and any country Geofabrik doesn't cover, get Natural Earth's lakes, which only include the larger ones.

**Keep the original out:** `--no-archive` builds `tiles/merged` from the generated tiles alone. Otherwise the original artwork, which paints Canada, Mexico and the Caribbean dark, would cover any of them you made a home country. Leave it off when you're adding to the US set.

**Use a separate folder for each set of home countries.** `generate.py` skips tiles that already exist, so tiles painted with one set of home countries would otherwise stay mixed in with the next. For example:

```
set INTELLISTAR_TILES=D:\intellistar-france
```

on Windows, or `export INTELLISTAR_TILES=...` elsewhere, before running the steps.

Big countries take a while. `generate.py` prints how many zoom 9 tiles it's about to paint: Alaska's 5,400 took 10–15 minutes. France is about 960, of which 730 are the mainland and Corsica and the rest its overseas regions, and Germany is about 470.

## How the painting works

`fit.py` compares the archived US artwork with elevation data for the same places, and saves what it learns in `model_z9.npz`:

- **Land colors:** a color for each pairing of elevation and terrain shading, for US land and for the darker land outside the US. The light comes from the west.
- **The ocean:** its color by distance from shore, from a lighter blue at the shore to the deep navy beyond about 15 km, and the faint blotchy texture of its open water.
- **Lakes:** the lighter blue of small lakes. Lakes over about 400 km², like Iliamna, are painted like the ocean, as the Great Lakes are in the original.

`generate.py` then paints each area:

- shorelines and lakes from OpenStreetMap;
- elevation and shading from the open terrain tiles, colored by the model;
- the darker tint for land that Natural Earth puts outside the US and its territories (the original paints Puerto Rico in the US colors);
- a little fine grain on the land, and the ocean's blotches, like the original's texture.

You only need to run `fit.py` again to refit the model, and that requires `tiles/archive`.

## Limits

- Only the areas you ask for are painted: `REGIONS` in `generate.py`, or the `--country` ones. Northern Canada east of 125°W, and the rest of the world, stays blank. So do the small US Minor Outlying Islands, such as Midway and Wake.
- The colors come from North American artwork, where they follow elevation. Deserts, tropics and ice are painted the same greens and browns as anywhere else at the same height.
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
