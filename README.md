# data-bears-hackathon
UN System Data Commons Builders Day - Data Bears Team

Ground Truth: source triage across UN statistical data. When two authoritative
sources disagree about the same figure, we report the size of the gap and its
provenance rather than picking a winner.

## What's here

| File | What it is |
|---|---|
| `groundtruth_demo.html` | The demo. Self-contained — open it in a browser, no server needed. |
| `groundtruth_data.json` | Extracted dataset behind the demo. Regenerable; see below. |
| `.mcp.json` | Wires the MCP server into Claude Code automatically. |

## The demo

Open `groundtruth_demo.html` in any browser. Three cases:

- **Carbon dioxide** — UNSD vs UNDP across 2015–2023, reconciled through population.
  Drag the year to watch countries move between divergence bands.
- **Fine particulates** — one national figure vs every admin-2 unit in the country
  (11,662 units across twelve countries).
- **Electricity access** — SDG indicator 7.1.1 against Target 7.1's promise of universal
  access by 2030. One source checked against itself, because only UNSD publishes it annually.

Divergence is banded low (<5%) / medium (5–20%) / high (>20%). The thresholds are one
constant in the page — search for `THRESHOLDS` to retune everything at once.

### The three tests behind the electricity case

The first two cases need two publishers to disagree. The third needs only one, because a
series can contradict itself:

| Test | What it catches | Threshold |
|---|---|---|
| **Implausible** | Access *falling*, in a stock that only grows | decline worse than −0.5 pp |
| **Discontinuous** | A jump far outside the series' own habit | >3× its median move, and ≥5 pp |
| **Interpolated** | A run of identical steps — a straight line drawn between anchors | ≥3 consecutive deltas within 0.1 pp, each ≥0.3 pp |

Every test needs an absolute floor, because a saturated series (≥99%) wobbles by rounding
rather than by methodology. Without those floors Brazil ranks worst in the set — at 99.8%
access. That is an artefact, not a finding, and it is the first thing a reviewer will catch.

A country is flagged **unprojectable** when more than 40% of its transitions fail a test and
it has not already saturated: Ethiopia, Nigeria, Kenya.

The result that makes the case: **the countries furthest from universal access have the least
trustworthy series about reaching it.** Kenya is the sharpest — the margin between on-track and
off-track is 0.40 pp a year, while its own series moves a median of 2.70 pp a year and has
reversed by 7.3 pp in a single step. The verdict sits inside the noise of the data it rests on.

## Querying the data yourself

`.mcp.json` wires the UN Data Commons MCP server into Claude Code automatically, so its
six tools are available in any session opened from this directory.

Discovery is always three steps: `search_indicators` → `get_variable_metadata` →
`get_observations`. Never hardcode a DCID; resolve it through a search call. A guessed
DCID returns an empty result set rather than an error, so it fails silently.

## Regenerating `groundtruth_data.json`

The CO₂ half comes from the MCP server, the PM2.5 half from the UNICEF Solr endpoint,
and boundaries from the Data Commons REST node API (`geoJsonCoordinatesUN` — UN-approved
boundaries, which matter for disputed borders in front of this audience). The extraction
is not yet a committed script; it walks these steps per country:

1. Resolve the place DCID via `search_indicators` — **one country at a time**, because an
   unresolvable name 500s the whole batch (see gotchas).
2. `get_observations` for `undata/sdg/EN_ATM_CO2`, `undata/undphdro/PHDI_co2_prod`
   and `undata/unicef/DM_POP`, 2015–2023.
3. Solr query on the `hazard` core: `indicator:PM25`, `age:_T`, `sex:_T`,
   `-status:[* TO *]`, for per-unit `hazard_mean` and `population_val`.
4. Fetch `->geoJsonCoordinatesUNDP2` from the REST node API for each country DCID.

## Gotchas that cost us time

- **Place-name resolution 500s on names it can't resolve.** The server falls back to a
  Google Maps legacy API that isn't enabled. `"Vietnam"` works, `"Viet Nam"` — the UN's own
  official spelling — returns a 500. So does `"Turkiye"`. One bad name kills the whole batch,
  so resolve places one at a time. Reported to the organisers.
- **Date ranges need `date="range"`.** Passing `date_range_start`/`_end` while `date` is
  still `"latest"` silently returns only the latest point.
- **Search takes human-readable names; observations take DCIDs.** Search for `Kenya`, then
  request observations on `country/KEN`.
- **`get_variable_metadata` caps `entity_dcids` at 10.** Eleven or more returns
  `400 — entity_dcids cannot exceed 10`. Chunk the request and merge the facet lists, keyed
  on facet `id` so a facet spanning two chunks is not counted twice.
- **The REST API is federated** and does not enforce the UN statistical boundary — it will
  answer with other publishers' data without warning. Discover through MCP; use REST only
  for structural paths from identifiers you already hold.
- **GCHD has no geometry and no names** — only `ref_area` codes like `KEN_0030_0008_V1`.
  Mapping admin-2 units needs a boundary file from the GCHD team; requested on Discord.

## What the numbers do and don't show

The two CO₂ series are not identical measures — UNSD reports emissions from fuel
combustion, UNDP reports production-based CO₂ including cement and industrial process.
A standing offset is expected. The argument is about **instability**: Pakistan moves from
+2.9% to +49.4% and back within eight years, which a definitional difference doesn't explain.

For PM2.5 the national and subnational layers are different years (2019 vs 2025) and are
never aligned. The test asks only whether a national figure is internally possible given its
own subnational spread. Egypt fails outright — its national figure exceeds all 404 of its
admin-2 units, and no weighted mean can sit beyond every value it averages.

The population-weighted subnational means are **our** aggregation; UNICEF publishes no
national figure in that index. Units flagged `No Data` / `Insufficient Data` /
`Not Applicable` are excluded.

For electricity access, UNSD and UNFPA agree closely wherever UNFPA publishes at all — a mean
gap of 0.80 pp for Kenya across its two census years — and UNFPA publishes *only* in census
years (Kenya 2009/2019, Brazil 2000/2010, Bangladesh 2001/2011, Mexico 2000–2020 at five-year
steps). That agreement is **not independent corroboration**: both trace back to the same census
instrument, and the two measures use different denominators (population vs households) yet land
within 0.24% in 2019 — closer than two genuinely different measures should. Read it as evidence
that measurement happened, not that the figure is right. The 2030 projections are a straight
five-year trend carried forward; they are deliberately naive, because the argument is about
whether the underlying series can support *any* projection.

## Sources

- UN System Data Commons MCP — `https://unsd-datacommons.gcp.un-icc.cloud/mcp`
- Integration guide — https://projects.officialstatistics.org/undata2/undatacommons-mcp/
- UNICEF Global Child Hazard Database — Solr `hazard` core (access details from the organisers)
- SDG 7.1.1 electricity access — `undata/sdg/EG_ACS_ELEC` (UN Statistics Division) and
  `undata/unfpa/PCT_HH_WITH_BASIC_SERVICE…ELECTRICITY` (UNFPA), both via the MCP server
