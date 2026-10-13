// Downloads the IntelliStar basemap artwork (Mapbox tileset freakydreakylol.i1basemaphq) to tiles/archive,
// while the tileset is still online. Needs a Mapbox access token, from either:
//   MAPBOX_TOKEN=pk... node archive.mjs
//   node archive.mjs --config path/to/weatherscan-v2/main/configs/yourConfig.json   (uses its apiKeys.map_key)
// The token is never printed or saved.
//
//   node archive.mjs [token option]              lists the tileset's zooms, bounds and tile counts (downloads nothing)
//   node archive.mjs [token option] --go         downloads every tile (run again to resume; finished tiles are skipped)
//   node archive.mjs [token option] --go --max 8 stops at zoom 8
//
// Tiles land in tiles/archive/<z>/<x>/<y>.png (or under INTELLISTAR_TILES), with the tileset's metadata in
// tilejson.json. Tiles Mapbox has no data for are noted as <y>.none so a resume doesn't ask for them again.
import { readFile, writeFile, mkdir, access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const tileset = 'freakydreakylol.i1basemaphq';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(process.env.INTELLISTAR_TILES || path.join(here, 'tiles'), 'archive');
const args = process.argv.slice(2);
const option = (name) => (args.indexOf(name) >= 0 ? args[args.indexOf(name) + 1] : undefined);
const go = args.includes('--go');
const concurrency = 8;

let key = process.env.MAPBOX_TOKEN;
if (option('--config')) {
  key = JSON.parse(await readFile(option('--config'), 'utf8')).jsonSystemSettings?.apiKeys?.map_key;
}
if (!key) {
  console.error('needs a Mapbox token: set MAPBOX_TOKEN, or pass --config with the path to a weatherscan yourConfig.json');
  process.exit(1);
}
const hide = (s) => String(s).split(key).join('<token>');

const tjRes = await fetch(`https://api.mapbox.com/v4/${tileset}.json?secure&access_token=${key}`);
if (!tjRes.ok) throw new Error('tileset metadata: HTTP ' + tjRes.status + ' ' + hide(await tjRes.text()));
const tj = await tjRes.json();
const minzoom = tj.minzoom ?? 0;
const maxzoom = Math.min(tj.maxzoom ?? 22, option('--max') !== undefined ? Number(option('--max')) : Infinity);
const [west, south, east, north] = tj.bounds ?? [-180, -85.0511, 180, 85.0511];

const tileX = (lon, z) => Math.floor((lon + 180) / 360 * 2 ** z);
const tileY = (lat, z) => Math.floor((1 - Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / Math.PI) / 2 * 2 ** z);
const clamp = (v, z) => Math.max(0, Math.min(2 ** z - 1, v));
const ranges = [];
let total = 0;
for (let z = minzoom; z <= maxzoom; z++) {
  const r = { z, x0: clamp(tileX(west, z), z), x1: clamp(tileX(east, z), z), y0: clamp(tileY(north, z), z), y1: clamp(tileY(south, z), z) };
  r.count = (r.x1 - r.x0 + 1) * (r.y1 - r.y0 + 1);
  total += r.count;
  ranges.push(r);
}

console.log(`tileset ${tileset}: ${tj.name ?? ''}`);
console.log(`format ${tj.format ?? '?'}, zooms ${tj.minzoom}-${tj.maxzoom}, bounds ${JSON.stringify(tj.bounds)}`);
for (const r of ranges) console.log(`  z${r.z}: ${r.count.toLocaleString()} tiles`);
console.log(`total through z${maxzoom}: ${total.toLocaleString()} tiles`);

await mkdir(out, { recursive: true });
const saved = { ...tj, tiles: [`{z}/{x}/{y}.png`], archived: new Date().toISOString() };
await writeFile(path.join(out, 'tilejson.json'), hide(JSON.stringify(saved, null, 2)));

if (!go) {
  console.log('\nnothing downloaded. run again with --go to download them (or --go --max N to stop at zoom N).');
} else {
  const exists = (p) => access(p).then(() => true, () => false);
  const wait = (attempt) => new Promise((r) => setTimeout(r, 2000 * 2 ** attempt));
  async function* jobs() {
    for (const r of ranges) for (let x = r.x0; x <= r.x1; x++) for (let y = r.y0; y <= r.y1; y++) yield [r.z, x, y];
  }
  let done = 0, fetched = 0, empty = 0, failed = 0;
  const queue = jobs();
  async function worker() {
    for (let next = await queue.next(); !next.done; next = await queue.next()) {
      const [z, x, y] = next.value;
      const dir = path.join(out, String(z), String(x));
      const file = path.join(dir, `${y}.png`), none = path.join(dir, `${y}.none`);
      if (!(await exists(file)) && !(await exists(none))) {
        for (let attempt = 0; ; attempt++) {
          try {
            const res = await fetch(`https://api.mapbox.com/v4/${tileset}/${z}/${x}/${y}.png?access_token=${key}`);
            if (res.ok) {
              await mkdir(dir, { recursive: true });
              await writeFile(file, Buffer.from(await res.arrayBuffer()));
              fetched++;
            } else if (res.status == 404) {
              await mkdir(dir, { recursive: true });
              await writeFile(none, '');
              empty++;
            } else if ((res.status == 429 || res.status >= 500) && attempt < 6) {
              await wait(attempt);
              continue;
            } else {
              failed++;
              console.log(`z${z}/${x}/${y}: HTTP ${res.status}`);
            }
          } catch (e) {
            if (attempt < 6) { await wait(attempt); continue; }
            failed++;
            console.log(`z${z}/${x}/${y}: ${hide(e.message)}`);
          }
          break;
        }
      }
      if (++done % 500 == 0 || done == total) console.log(`${done.toLocaleString()}/${total.toLocaleString()} (new ${fetched}, no data ${empty}, failed ${failed})`);
    }
  }
  await Promise.all(Array.from({ length: concurrency }, worker));
  console.log(`finished: ${fetched} downloaded this run, ${empty} with no data, ${failed} failed${failed ? ' (run again to retry them)' : ''}`);
}
