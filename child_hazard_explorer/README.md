# Child Hazard Explorer

An interactive map of **how many children are exposed to climate and
environmental hazards, and where** — down to the sub-district level, for every
country the UNICEF hazard database covers.

Pick a country on the world map, drop through its admin-1 areas into the
admin-2 units, and read every number the database holds for any one of them.

**Live:** https://claude.ai/artifact/JfpsFbhpKWJn4Z6NEiHh75
*(private — the owner has to grant access before it opens for you)*

---

## What it does

**22 hazard indicators** — river and coastal flood, drought, heatwaves, extreme
heat, air pollution, malaria, landslides, wildfire, earthquakes, conflict, and
more — for **children aged 0–17**, across **229 countries** and about **41,000
admin-2 units**.

- **World view.** Every country shaded by the selected indicator, as either the
  *share* of children exposed or the *count* of them. The two answer different
  questions: share compares countries fairly, count shows where the most
  children actually are.
- **Drill in.** Click a country and the map drops to its **admin-1 areas**
  (Kenya's 47 counties). Zoom in — or use the **Admin 1 / Admin 2** switch — and
  it drops again to **admin-2** (Kenya's 290 sub-counties), which is the level
  the database actually records.
- **Read one place.** Click any area for its numbers:

  ```
  Buret · KEN_0012_0003_V1 · River flood · as recorded in the database
  Exposed children 191 | Exposure 0.2% | Children in area 97,626
  Flood depth 6.26 m   | Exposure class 1.0
  ```

  The hazard measure changes with the indicator — metres of flood depth,
  µg/m³ of PM2.5, heatwaves per year — and the unit comes from the database, not
  from a lookup table in the front end.
- **Compare.** Select several countries for a ranked comparison, as a chart or
  a table.

### One thing worth understanding

The database holds **admin-2 records only**. Admin-1 is **calculated** here, not
quoted — so every admin-1 readout says so, and says how much of the area it
covers:

```
Busia · KEN_0004 · River flood · calculated from 6 of 7 admin-2 units
                                 — the rest have no record for this indicator
```

That matters more than it sounds: 4,706 of the admin-1 cells are computed from
only *some* of their children, and a partial aggregate otherwise looks exactly
like a complete one.

---

## How to use it

### Just looking

Open the link above. Nothing to install.

You need a **browser with WebGL** (the map renders through it) and about
**4.9 MB** for the first load, then ~0.4–0.7 MB per country you open. No
account, no API keys, no credentials.

### Running it locally

```bash
npm install
npm run dev
```

That is all — the built data is committed, so the app runs without any
credentials. Needs **Node 18+**.

### Rebuilding the data

Only if you want to refresh from source. Needs **Python 3.11+**, `npx`
(mapshaper is fetched on demand), and **Solr credentials** for the UNICEF
database in a `.env` file (see `.env.example`). Budget about 45 minutes.

```bash
cp .env.example .env && $EDITOR .env    # credentials, ETL only

./etl/build_boundaries.sh adm0 3%       # world outlines      (do this first)
python3 etl/build_catalog.py            # SDG catalog         (~15 min)
python3 etl/compact_catalog.py          # 46 MB -> 2.4 MB
python3 etl/build_places.py             # country names
python3 etl/build_hazard.py             # Solr -> JSON        (~6 min)
python3 etl/bundle_hazard.py --chunks 90
python3 etl/build_adm2.py --all         # adm2 + adm1 polygons (~25 min)
python3 etl/build_area_names.py --level adm1
python3 etl/build_area_names.py --level adm2
python3 etl/build_adm1_hazard.py        # roll admin-2 up to admin-1
python3 etl/bundle_boundaries.py

python3 etl/verify.py                   # 27 checks; gates the build
```

---

## Where the data comes from

| Source | What it provides | How it is accessed |
|---|---|---|
| **UNICEF Global Child Hazard Database** | 22 indicators × ~41,000 admin-2 units, children 0–17, 2025 | Solr, **Basic auth, no CORS** — build time only |
| **UNICEF GeoRepo** | admin-0/1/2 boundaries | Static GeoJSON (CC BY 4.0) |
| **UN System Data Commons** | SDG indicators — *ETL only, not used by the app* | Public REST, no key |

The hazard Solr **cannot** be called from a browser: it sends no CORS headers,
and its credentials must never reach the client. It is queried only at build
time, and the published bundle contains no credentials — `verify.py` checks.

### What the data is, and is not

- **One year.** Every one of the database's 5,415,036 records is `time_period:
  2025`. It is a snapshot, so **there is no time series to chart** at any level.
- **One level.** Every record is `admin_level: 2`. Admin-1 is derived (above);
  admin-3 and admin-4 boundaries exist in GeoRepo but carry no hazard data.
- **Uneven coverage.** Not every indicator reaches every unit. An area with no
  record is drawn as no-data rather than as a zero — absence of a record is not
  a measurement of zero exposure.
- **Other dimensions.** The database also splits by sex and by all-ages vs
  children; the ETL pins these to total children 0–17.

---

## How it is put together

Build-time ETL produces static artifacts; the browser reads only those. No
backend, no secrets in the bundle, and nothing fetched from a third party at
runtime — so it works offline and the tests need no network.

```
BUILD TIME (Python)                      RUNTIME (browser)
  Solr    -> hazard/countries.json  -->  world choropleth
          -> hazard/admin2-*.json   -->  admin-2 records (lazy, by chunk)
          -> hazard/adm1.json       -->  admin-1 roll-ups
          -> hazard/units.json      -->  units for the readout
  GeoRepo -> adm0.min.topo.json     -->  country outlines
          -> country-*.json         -->  both admin levels (lazy, by country)
```

Each country's boundary file holds **both levels in one TopoJSON** (objects
`adm2` and `adm1`) sharing one arc pool, so switching level costs no fetch.

```
etl/
  build_hazard.py       Solr -> countries.json + per-country admin-2 detail
  bundle_hazard.py      229 country files -> chunks + index
  build_adm2.py         streams GeoRepo adm2 -> one file per country, both levels
  bundle_boundaries.py  229 country files -> chunks + index
  build_adm1_hazard.py  rolls admin-2 records up to admin-1
  build_area_names.py   streams boundaries -> ucode/name map (no geometry parsed)
  build_boundaries.sh   GeoRepo GeoJSON -> simplified TopoJSON (admin-0)
  build_provenance.py   sources, field map and cross-checks -> provenance.json
  stage_artifact.py     dist/ -> publishable bundle, with a size/file budget
  verify.py             27 end-to-end checks; gates the build
src/
  App.tsx               layout, selection, the drilldown wiring
  WorldMap.tsx          MapLibre choropleth, both admin levels, zoom switching
  HazardNav.tsx         the 22 indicators
  HazardAreas.tsx       ranked bars for one country
  StatRow.tsx           the numbers for one clicked unit
  useHazardDetail.ts    one country's records + names, either level
  data/                 hazard records, boundary chunks, scales
```

---

## Verification

```bash
python3 etl/verify.py        # 27 checks over the artifacts
node test/integration.mjs    # the app's real data flow, end to end
node test/scale.mjs          # choropleth class-break edge cases
```

`verify.py` checks the things that fail *silently* — a hollow catalog, a
boundary join that quietly drops units, an aggregate that does not add up:

- every hazard unit has geometry (40,641 / 40,641)
- every admin-1 roll-up has geometry, its exposure **sums to** the admin-2
  records it came from, and its percentage is re-derived from totals rather
  than averaged
- every admin-1 area with a reporting child has a value — a gap is never a
  dropped aggregate
- every indicator has a hazard unit, so no readout prints a bare number
- no Solr credentials anywhere in the built bundle

---

## Things that will bite you

Found the hard way. They are why the ETL looks more defensive than a typical
API client.

1. **The REST API answers for the wrong publisher, silently.** The deployment is
   federated with the wider Data Commons graph, and the same endpoint answers
   for other publishers with no flag: Kenya `SI_POV_DAY1` is 36.0 from the wider
   graph and **46.4** from the UN-governed one. Both return HTTP 200. Only
   `undata/`-prefixed identifiers are trusted, and never hand-constructed —
   a plausible guess returns an empty 200, not an error.

2. **Batched `node` requests truncate without telling you.** Pagination spans
   the whole batch, and a node whose arcs did not fit comes back *present but
   empty*. Asking for 40 topics returned 40 keys with 26 silently hollow. Only
   a top-level `nextToken` reveals it.

3. **Boundary versions don't always match.** `ref_area` in the hazard data and
   `ucode` in GeoRepo are the same identifier, but the version suffix can
   differ (`SLB_0001_0001_V2` vs `_V3`). Filtering to `is_latest` and joining on
   the full ucode loses every Solomon Islands unit while the global rate still
   looks like 99.88%. Everything joins on the versionless stem.

4. **Three country dcids are rejected outright.** `country/ESH`, `country/GRC`
   and `country/SVN` return 403 whenever they appear literally in a `nodes=` or
   `entity.dcids=` parameter — but come back fine through an
   `entity.expression`. It reads as request filtering on the literal string.

5. **Bundling orphaned everything that read the files.** `bundle_hazard.py`
   packed the per-country files into chunks and deleted the directory; the
   client kept fetching the old path and rendered the 404 as the ordinary
   sentence "No subnational detail", and `verify.py` guarded its check on
   `if dir.exists()` so it simply stopped running. A build step that moves
   files should be assumed to have broken its readers.

6. **There is no admin-1 data — the level is derived.** See above. Geometry is
   dissolved from the *already simplified* admin-2 layer so a parent's outline
   is exactly the union of its children's; numbers sum, and percentages are
   re-derived from the totals.

7. **mapshaper's `-clean` deletes polygons and says so only in a count.**
   Simplifying admin-2 with `-clean` returned **106 of Saint Lucia's 556
   units** — exit code 0, valid TopoJSON, four fifths of the country gone.
   `-clean allow-overlaps` keeps them. `build_adm2.py` now compares its own
   input and output counts per country and fails loudly on any drop.

8. **MapLibre's default build runs its worker from a `blob:` URL**, which a
   published page's Content-Security-Policy blocks — the map comes up blank
   with nothing useful in the console. The app uses MapLibre's **CSP build**
   with the worker emitted as an ordinary asset.

---

## Publishing it

The app is static, so it ships as one page with nothing to install. A published
artifact allows **255 files and 64 MB**; a plain build is 501 files and 132 MB.

```bash
npm run build
python3 etl/bundle_boundaries.py
python3 etl/stage_artifact.py      # prints the budget, fails if over
```

Current bundle: **163 files, 54.1 MB**. The savings came from dropping the
retired SDG artifacts, putting both boundary levels in one shared-arc file per
country, chunking, and trimming stored number precision. Chunk counts stay high
(60 boundary, 90 hazard) and are packed largest-first, so opening a country
still fetches roughly that country rather than a tenth of the world.

---

## Citation and lineage

The app carries its own provenance. **Sources & lineage**, under the map, is
rendered from `data/provenance.json`, which `etl/build_provenance.py` computes
*from the artifacts themselves* — so it cannot drift from what ships the way a
hardcoded attribution line can. (It had: the sidebar claimed 41,023 admin-2
units while the data carried 40,641.)

It shows each source with its licence and retrieval date, which records were
selected (`sex:_T`, `age:Y0T17`, error-status rows excluded), **which field
backs each number on screen**, what was done to it, and a copyable citation.
Each figure in the readout names its own source field, so `Exposed children`
is visibly `exposure_absolute` and an admin-1 figure says it is a sum rather
than a record.

### Cross-checks

Several figures have **two independent derivations**, so they are compared
rather than trusted. Computed at build time and shown in the panel:

| Check | Result |
|---|---|
| Country total (server-side facet) vs Σ its admin-2 rows | **4,380 / 4,380 agree** |
| Admin-1 roll-up vs Σ its admin-2 children | exact |
| Boundary version cited by the record vs published now | **49 differ** — all Solomon Islands, `_V2` against GeoRepo's `_V3` |
| Admin-2 units with a published name | 50 of 40,641 missing |
| Admin-1 areas aggregated from *every* child | 4,706 from only some |

The first is gated by `verify.py`, so a future ETL change that breaks the
identity fails the build instead of surfacing as a quiet contradiction on
screen. The disagreements are shown rather than silently absorbed — the version
mismatch is resolved by matching on the versionless code, and the panel says so.

```bash
python3 etl/build_provenance.py   # regenerate after any data rebuild
```

## Attribution

Boundaries: **UNICEF GeoRepo** (CC BY 4.0). Hazard data: **UNICEF Global Child
Hazard Database** — licence terms not confirmed; check with UNICEF before
redistributing. SDG statistics: **UN System Data Commons**.
