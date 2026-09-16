# data-bears-hackathon
UN System Data Commons Builders Day - Data Bears Team

Ground Truth: source triage across UN statistical data. When two authoritative
sources disagree about the same figure, we report the size of the gap and its
provenance rather than picking a winner.

## What's here

| File | What it is |
|---|---|
| `groundtruth_demo.html` | The demo. Self-contained — open it in a browser, no server needed. |
| `undc.py` | Zero-dependency client for the UN Data Commons MCP server. |
| `groundtruth_data.json` | Extracted dataset behind the demo. Regenerable; see below. |
| `GCHD_how_to_use_solr.md` | Organiser guide to the UNICEF hazard database. **Contains read-only credentials — keep this repo private.** |
| `.mcp.json` | Wires the MCP server into Claude Code automatically. |

## The demo

Open `groundtruth_demo.html` in any browser. Two cases:

- **Carbon dioxide** — UNSD vs UNDP across 2015–2023, reconciled through population.
  Drag the year to watch countries move between divergence bands.
- **Fine particulates** — one national figure vs every admin-2 unit in the country
  (11,662 units across twelve countries).

Divergence is banded low (<5%) / medium (5–20%) / high (>20%). The thresholds are one
constant in the page — search for `THRESHOLDS` to retune everything at once.

## Querying the data yourself

`undc.py` needs only Python 3.8+ and the standard library.

```bash
python3 undc.py tools                  # the six MCP tools
python3 undc.py playbook single        # the server's own research playbook
python3 undc.py search "renewable energy" --places Kenya
python3 undc.py obs --var undata/sdg/EN_ATM_CO2 --place country/KEN --start 2018 --end 2023
python3 undc.py research "life expectancy" --places India
```

Or from Python:

```python
from undc import DataCommons
dc = DataCommons()
hits = dc.search_indicators("maternal mortality", places=["Kenya"])
```

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
  still `"latest"` silently returns only the latest point. `undc.py` sets this for you.
- **Search takes human-readable names; observations take DCIDs.** `--places Kenya`, then
  `--place country/KEN`.
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

## Sources

- UN System Data Commons MCP — `https://unsd-datacommons.gcp.un-icc.cloud/mcp`
- Integration guide — https://projects.officialstatistics.org/undata2/undatacommons-mcp/
- UNICEF Global Child Hazard Database — Solr `hazard` core (see the guide in this repo)
