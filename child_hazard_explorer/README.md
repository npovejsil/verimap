# Child Hazard Explorer

A dashboard over the **UNICEF Global Child Hazard Database**: pick a country on
the world map, drop through its **admin-1 areas** into the **admin-2 units**,
and read every number the database holds for any one of them — children
exposed, the share that is, the hazard measure in its own unit, and the
exposure class.

A country opens at admin-1, which is the readable view (Kenya is 47 areas, not
290). Zooming past about one doubling of the country fit switches to admin-2 on
its own; the Admin 1 / Admin 2 control does it explicitly and stops the zoom
from overriding you.

> **Scope note.** This started as a two-dataset app: SDG indicators from the UN
> System Data Commons *and* child hazards. They answer different questions at
> different levels (a country time series versus a 2025 admin-2 snapshot), so
> the app is now the hazard side only. The SDG ETL, its catalog and the notes
> below are kept — they are still correct, and `verify.py` still checks them —
> but nothing in `src/` loads them any more. `GoalNav.tsx`, `TrendChart.tsx`,
> `data/datacommons.ts` and `sdg.ts` are unused as a result.

---

## Things that will bite you

All of these were found the hard way while building this. They are the reason
the ETL looks more defensive than a typical API client.

### 1. The REST API answers for the wrong publisher, silently

The deployment is **federated with the wider Data Commons graph**. The same
endpoint answers for other publishers with no warning, no error, and no flag in
the response:

| Variable | Kenya, 2021 |
|---|---|
| `sdg/SI_POV_DAY1` (wider graph) | **36.0** |
| `undata/sdg/SI_POV_DAY1` (UN-governed, `undata/p/SDG`) | **46.4** |

Same endpoint, same indicator, same year, different numbers. Both return HTTP 200.

**The rule:** only `undata/`-prefixed identifiers, and only ones reached by
walking down from a UN root (`undata/topic/Root`, `undata/topic/theme/Root`).
Never hand-construct a dcid — a plausible guess like `undata/sdg_si_pov_dayt1`
returns an empty `200`, not an error. Per the official guidance, variable
*discovery* belongs to the MCP server; REST is for structural navigation only.

Both `etl/un_client.py` and `src/data/datacommons.ts` refuse non-`undata/`
identifiers, and `build_catalog.py` fails the build if one reaches the output.

### 2. Batched `node` requests truncate without telling you

The `/node` endpoint paginates across the **whole batch**. A node whose arcs did
not fit on the current page is returned **present but with an empty `arcs`
object** — not omitted. Nothing signals this except a top-level `nextToken`.

Asking for 40 topics returns 40 keys with **26 of them silently empty**. Ignoring
the token produces a catalog that is structurally valid and mostly hollow — which
is exactly what happened on the first run here (17 goals, 0 variables).

`Rest.node()` follows `nextToken` to completion and merges pages.

### 3. Boundary versions don't always match

`ref_area` in the hazard data and `ucode` in GeoRepo are the same identifier —
but the version suffix can differ. The hazard database is pinned to whichever
boundary version was current when it was built, which is not always GeoRepo's
latest:

```
hazard SLB_0001_0001_V2   vs   GeoRepo is_latest  SLB_0001_0001_V3
```

Filtering GeoRepo to `is_latest = true` and joining on the full ucode therefore
loses every Solomon Islands unit — 0 of 50 — while the global rate still looks
like a healthy 99.88%, so it is easy to miss. `build_area_names.py` keeps all
versions, and the lookup falls back to the versionless stem. That takes the
join to **40,640 / 40,641**.

### 4. Three country dcids are rejected outright

`country/ESH`, `country/GRC` and `country/SVN` (Western Sahara, Greece,
Slovenia) return **403** whenever they appear literally in a `nodes=` or
`entity.dcids=` parameter — alone, at any batch size, on both the node and
observation endpoints, with any property and any casing.

They are *not* missing from the data. The same countries come back normally
through an `entity.expression`:

```
entity.dcids=country/GRC                            -> 403
entity.expression=Earth<-containedInPlace+{typeOf:Country}
                                                    -> 200, Greece = 0.6 (2022)
```

So this reads like a request-filtering rule on the literal string rather than
anything about the data. I first mis-diagnosed it as rate limiting, because it
looks exactly like throttling and no amount of retrying clears it.

Two consequences, both of which happen to be improvements:

- Country data is always fetched **in bulk** via the expression, never per
  entity. One request returns all 170 countries with full history in 89 KB /
  0.3 s, and it feeds the map, the bars and the trend chart alike.
- Country *names* come from the local boundary file, not the graph — otherwise
  Greece and Slovenia would be unnamed.

`src/data/datacommons.ts` keeps the blocklist; `etl/un_client.py` retries only
genuine transients.

### 5. Bundling the hazard files orphaned everything that read them

`bundle_hazard.py` packs the 229 per-country admin-2 files into 12 chunks and
deletes the directory. Nothing that read that directory was updated, and nothing
failed loudly:

- `src/data/hazard.ts` fetched `hazard/admin2/<ISO3>.json`, got a 404, and
  returned `null` — which the panel renders as the perfectly ordinary sentence
  "No subnational detail for KEN".
- `verify.py` guarded its names check on `if detail_dir.exists()`, so the
  advertised 99.998% join stopped running and the suite still printed all-pass.

Both now go through `admin2-index.json`, and the check is unconditional. A
build step that moves files should be assumed to have broken its readers.

### 6. There is no admin-1 data — the level is derived

Every one of the database's **5,415,036 records is `admin_level: 2`**, and every
one is `time_period: 2025`. So there is no admin-1 row to fetch and no time
series to plot; the only other dimensions it carries are `sex` (F/M/\_T) and
`age` (Y0T17/\_T), which the ETL pins to total children.

Admin-1 exists anyway because GeoRepo puts the parent admin-1 code on every
admin-2 boundary. Both halves are derived from that one field:

- **Geometry** — `build_adm2.py` dissolves the *already simplified* admin-2
  layer on `adm1`. Simplifying the two levels independently would leave a
  county's outline disagreeing with its own sub-counties' along every shared
  border.
- **Numbers** — `build_adm1_hazard.py` sums `exposed` and `pop`, then
  **re-derives** the percentage from those totals. Averaging the children's
  percentages would weight a village like a city. `hazard` takes the plain mean
  and `cls` the max, matching what `build_hazard.py` already does for countries.

That is also why `build_hazard.py` now keeps `population_val` per unit: without
it, a parent's percentage cannot be re-derived at all, only averaged.

**Coverage is uneven, and a partial aggregate looks exactly like a whole one.**
Of the 71,962 admin-1 cells, **4,706 are computed from only some of their
children** — Nairobi's river-flood figure comes from 2 of its 17 sub-counties,
so its percentage is over the *covered* population, not the county's. The
remaining 7,391 empty cells are empty because **none** of their children
reported: there is nothing to aggregate, so the map leaves them as no-data
rather than inventing a zero.

Non-reporting is not zero exposure, so the denominator stays the covered
population and every cell carries `units`/`total` instead. The readout then says
which it is, in as many words:

```
KEN_0004 · River flood · calculated from 6 of 7 admin-2 units
                         — the rest have no record for this indicator
KEN_0014_0006_V1 · River flood · as recorded in the database
```

`verify.py` asserts the guarantee behind that first line: **every** admin-1 area
with a reporting child has a value, so a gap is never a dropped aggregate.

### 7. mapshaper's `-clean` deletes polygons, and says so only in a count

Simplifying admin-2 with `-simplify ... -clean` — the same pipeline that is
right for admin-0 — silently returned **106 of Saint Lucia's 556 units**. The
only sign is a line in mapshaper's own output ("Retained 106 of 556 features");
the exit code is 0 and the file is valid TopoJSON, just missing four fifths of
the country.

`-clean` resolves overlapping polygons by dropping them, and some countries'
admin-2 units overlap in the source. `-clean allow-overlaps` keeps all 556.

The first build shipped this: the per-country join looked like a healthy 99.98%
because the countries it ruined are small, and the aggregate drowned them. So
`build_adm2.py` now compares its own input and output feature counts per country
and fails loudly on any drop, and `verify.py` reports the join in aggregate *and*
names the countries that are short.

### Also worth knowing

- Walking the *entire* graph under `undata/topic/Root` (all 42 roots, including
  every agency corpus) is ~33,000 nodes and ~20 minutes. This build walks only
  the goal and theme subtrees — 2,768 requests, ~15 minutes.
- The raw crawl is ~46 MB, mostly repetition: the themes axis alone is 36 MB
  because it indexes the whole UN corpus (84,893 variables) and repeats each
  variable under many branches. `compact_catalog.py` hoists names into one
  lookup and splits themes out, taking the shipped catalog to **2.44 MB**.

---

## Shipping it

The app is static, so it publishes as one page anyone can open — no install, no
server, no account. Getting there is a budget exercise, because a published
artifact allows **255 files and 64 MB** and a plain `npm run build` produces
**501 files and 132 MB**. Four things close that gap, none of which cost a
feature:

| | before | after |
|---|---|---|
| retired SDG artifacts (`sdg/`, `catalog.json`) — nothing loads them | 39 MB | dropped from the bundle |
| boundaries: two files per country at 8% | 47.1 MB, 458 files | **25.5 MB**, 229 files |
| hazard + boundary files bundled into chunks | 458 files | 150 chunks |
| hazard numbers stored at source precision | 24.8 MB | trimmed |

The boundary saving is the interesting one. Both levels now live in **one
TopoJSON per country** as objects `adm2` and `adm1`: TopoJSON shares an arc pool
between objects, and admin-1 is dissolved from admin-2, so the coarser level
rides on arcs the finer one already paid for. Kenya is 147 KB for the pair
against 244 KB as two files — and switching level in the app now costs no fetch
at all.

Chunking is what keeps the file count legal, and the chunk *count* stays high
(60 boundary, 90 hazard) on purpose: packed largest-first into the emptiest bin,
Brazil ends up alone in its chunk and small countries share, so opening a
country still fetches roughly that country (mean 436 KB) rather than a tenth of
the world.

```bash
npm run build
python3 etl/bundle_boundaries.py     # 229 country files -> 60 chunks + index
python3 etl/stage_artifact.py        # drop retired artifacts, write the page,
                                     # print the file/size budget
```

`stage_artifact.py` also writes the page itself, because the artifact host
supplies the document skeleton: the file it emits is page *content* starting at
`<title>`, naming whichever hashed asset filenames vite just produced.

One thing that is not a size problem and would still have broken the published
map: **MapLibre's default build runs its worker from a `blob:` URL**, which a
published page's Content-Security-Policy blocks — the map comes up blank with
nothing useful in the console. The app imports MapLibre's **CSP build** and
points `setWorkerUrl` at the worker emitted as an ordinary hashed asset, which
works under either policy.

## Data sources

| Source | What | Access |
|---|---|---|
| UN System Data Commons | 17 SDG goals, indicators, observations — *ETL only, not in the app* | Public REST, CORS `*`, no key |
| UNICEF Global Child Hazard DB | 22 hazard indicators, 41,023 admin-2 units, 241 countries, 2025 | Solr, **Basic auth, no CORS** |
| UNICEF GeoRepo | adm0–adm4 boundaries | Static GeoJSON on Azure (CC BY 4.0) |

The hazard Solr **cannot** be called from a browser: no CORS headers, and its
credentials must never ship to the client. It is queried only at build time.

`ref_area` in the hazard data and `ucode` in GeoRepo are the same identifier
(`EGY_0016_0001_V1`), so they join with no crosswalk.

---

## Architecture

Build-time ETL produces static artifacts; the browser reads those plus the live
(CORS-open) Data Commons API. No backend, no secrets in the bundle.

```
BUILD TIME (Python)                      RUNTIME (browser)
  Solr    -> hazard/countries.json  -->  world choropleth
          -> hazard/admin2-*.json   -->  admin-2 drilldown (lazy, by chunk)
          -> hazard/units.json      -->  units for the detail readout
  GeoRepo -> adm0.min.topo.json     -->  country geometry
          -> adm2/<ISO3>.topo.json  -->  admin-2 geometry (lazy, by country)
```

Nothing is fetched from a third party at runtime any more: with the SDG side
retired, every byte the app reads is a static artifact it ships with. That also
means the app works offline and the integration test needs no network.

---

## Running it

```bash
# 1. Credentials for the hazard ETL only (skip if you don't need hazard data)
cp .env.example .env && $EDITOR .env

# 2. Build the data artifacts.
./etl/build_boundaries.sh adm0 3%  # 224 MB -> ~3 MB TopoJSON  (do this first:
                                   #   build_places.py reads it for names)
python3 etl/build_catalog.py       # 17 goals -> variables    (~15 min, 46 MB raw)
python3 etl/compact_catalog.py     # 46 MB -> 2.4 MB shipped
python3 etl/build_places.py        # continents + countries   (~1 min)
python3 etl/build_hazard.py        # Solr -> static JSON      (~6 min, 19 MB)
python3 etl/build_area_names.py    # adm2 ucode -> name       (optional)
python3 etl/build_adm2.py --all    # adm2 + adm1 polygons, every country (~25 min)
python3 etl/build_area_names.py --level adm1   # adm1 ucode -> name
python3 etl/build_adm1_hazard.py  # roll the adm2 records up to adm1

# 3. Check everything landed
python3 etl/verify.py

# 4. Run the app
npm install && npm run dev
```

`etl/build_boundaries.sh` needs `npx` only — mapshaper is fetched on demand.

`build_area_names.py` gives the admin-2 drilldown real place names instead of
raw ucodes. It streams the 1.34 GB adm2 file with a regex over the `properties`
objects rather than parsing it, so it never holds the coordinates in memory, and
deletes the download afterwards. The panel degrades to showing ucodes if you
skip it.

`build_adm2.py` draws that drilldown on the map instead of only in the bars. It
streams the same 1.34 GB file in one pass — the file is one feature per line, so
each line is filed under its country as it goes — and writes one TopoJSON per
country. Kenya is 290 polygons and 172 KB; the median country is 49 KB and the
largest, Brazil's 5,570 units, is 2.5 MB. Per country this is an ordinary
GeoJSON source; it is drawing all 40,641 units *at once* that would need
`tippecanoe` and vector tiles. Countries you have not built keep the country
outline, and the map names the command that would add them.

Phase 2 is resumable: the download happens once, and a country whose output
already exists is skipped unless `--force`.

### Directories

- `data/` is the app's served directory (vite `publicDir`). Everything in it
  ships to `dist/`, so it holds only small published artifacts. Boundaries are
  62 MB of that (admin-2 34.5 MB, admin-1 12.6 MB, admin-0 3.1 MB, name lookups
  ~11 MB), fetched one country and one level at a time. `dist/` is 132 MB over
  501 files in total, of which **39 MB is the retired SDG side** (`sdg/` and
  `catalog.json`) that nothing loads any more.
- `.cache/` holds raw downloads (hundreds of MB) and logs, and is gitignored.
  Keeping these apart matters: with the raw GeoJSON inside `data/`, `dist/`
  came out at 275 MB instead of ~24 MB.

---

## Layout

```
etl/
  un_client.py         REST + MCP clients; pagination, backoff, corpus guard
  build_catalog.py     goal/theme graph -> raw catalog (~46 MB)
  compact_catalog.py   raw catalog -> data/catalog.json (2.4 MB) + themes
  build_places.py      continents + country names -> data/places.json
  build_hazard.py      Solr -> data/hazard/{countries,admin2/*}.json
  build_boundaries.sh  GeoRepo GeoJSON -> simplified TopoJSON
  build_area_names.py  streams adm2 -> ucode/name map (no geometry parsed)
  build_adm2.py        streams adm2 -> one file per country (adm2 + adm1)
  bundle_boundaries.py 229 country files -> chunks + index (artifact limits)
  stage_artifact.py    dist/ -> publishable bundle + page, with a budget check
  build_adm1_hazard.py adm2 records -> adm1 roll-ups (data/hazard/adm1.json)
  bundle_hazard.py     229 per-country hazard files -> 12 chunks + index
  verify.py            end-to-end checks; gates the build
src/
  data/datacommons.ts  (unused) observation client (guards the corpus)
  store.ts             selection state
  WorldMap.tsx         MapLibre choropleth, country select, adm2 drilldown
  HazardNav.tsx        22 hazard indicators
  HazardAreas.tsx      admin-2 ranked bars for one selected country
  useHazardDetail.ts   one country's admin-2 records + names, shared by both
  StatRow.tsx          the numbers for one clicked unit
  RankedBars.tsx       magnitude comparison across selected places
  GoalNav.tsx          (unused) 17 goals -> targets -> indicators
  TrendChart.tsx       (unused) change over time
  data/hazard.ts       static hazard artifacts (no credentials)
  scale.ts             validated sequential + categorical palettes
```

## The detail readout

Clicking an admin-2 unit shows what the database actually holds for it:

```
Exposed children 37,233 | Exposure 32.7 % | Flood depth 4.61 m | Exposure class 5.0
```

Bare stat tiles, not a chart: four numbers with no common scale, where bars
would invite a comparison that means nothing. The hazard measure changes name
and unit per indicator — metres of flood, µg/m³ of PM2.5, heatwaves a year — so
the unit is read from the database (`data/hazard/units.json`, one faceted query
in `build_hazard.py --units-only`) rather than written into the front end.

## Charts

Palettes are validated, not eyeballed — the categorical slots pass the
colourblind-separation, chroma and lightness checks in both light and dark mode.
Magnitude uses a single-hue sequential ramp; the SDG goal colours are brand
identity on chips only and never encode data. Every value shows its observation
year and provenance, because coverage is uneven and the latest year differs by
country.

## Verification

```bash
python3 etl/verify.py       # artifacts + live regressions (16 checks)
node test/integration.mjs   # the app's real data flow, end to end
node test/scale.mjs         # choropleth class-break edge cases
```

`verify.py` checks the things that fail silently:

- every variable in the catalog is `undata/`-scoped
- 17 goals, none of them empty (the hollow-catalog failure mode)
- a live regression: Kenya `SI_POV_DAY1` must be **46.4**, not the wider
  graph's 36.0, with `undata/`-prefixed provenance
- hazard ISO3 codes join to the boundary file
- exposure percentages inside 0–100
- admin-2 ucodes resolve to names (99.998%)
- admin-2 hazard units have geometry, in aggregate, naming any country that is
  short — the check that catches a country quietly losing polygons
- no admin-2 file stacks two versions of the same unit
- every indicator has a hazard unit, so the detail readout never prints a bare
  number
- every admin-1 roll-up has geometry, and its exposure **sums to** the admin-2
  records it came from, with its percentage re-derived from the totals rather
  than averaged — the checks that would catch a bad aggregation
- every admin-1 area with a reporting child has a value (a gap is never a
  dropped aggregate), and its coverage counts stay inside its parent
- no Solr credentials anywhere in `dist/`

`integration.mjs` walks the catalog to a real variable, issues the same bulk
request the app makes, builds the choropleth map, and asserts it joins to the
boundary features — including the two countries that cannot be fetched by dcid.

## Attribution

Boundaries: UNICEF GeoRepo (CC BY 4.0). Statistics: UN System Data Commons.
Hazard data: UNICEF Global Child Hazard Database.
