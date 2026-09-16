# data-bears-hackathon
UN System Data Commons Builders Day - Data Bears Team

## Connecting to the UN Data Commons MCP server

The server is already configured in [.mcp.json](.mcp.json) — Claude Code picks it up
automatically when you open this repo (approve it the first time you're prompted):

```json
{
  "mcpServers": {
    "un-datacommons": {
      "type": "http",
      "url": "https://unsd-datacommons.gcp.un-icc.cloud/mcp"
    }
  }
}
```

No credentials are needed against this deployment.

### Tools it exposes

| Tool | Use it for |
| --- | --- |
| `search_indicators` | Find statistical variables (and their DCIDs) by natural-language query |
| `search_child_indicators` | Same, scoped to sub-national / child places |
| `get_variable_metadata` | Definition, units, provenance for a variable |
| `get_observations` | Observations for a place + variable |
| `get_child_observations` | Observations broken down across child places |

Always resolve DCIDs with the search tools first — never guess or hardcode them.

### Poking at the graph directly (REST)

Handy for debugging what the MCP tools return. Same host, different base path:

```bash
REST=https://unsd-datacommons.gcp.un-icc.cloud/core/api/v2

curl -sG "$REST/node" \
  --data-urlencode 'nodes=undata/unicef/DM_POP.AGE--Y0T17__SEX--F' \
  --data-urlencode 'property=->populationType'
```

Use `--data-urlencode` — the `->` arrows and `{}` braces in a property expression have to
reach the server encoded.

Caveat: the REST API does **not** enforce the UN statistical boundary, so it can return
nodes from other publishers. Stick to the MCP tools for actual variable discovery.

Full docs: https://projects.officialstatistics.org/undata2/undatacommons-mcp/inspecting-the-graph-with-rest/

## The map prototype

[ui-prototypes/renewable-energy-share.html](ui-prototypes/renewable-energy-share.html) is a
choropleth atlas that renders **six UN Data Commons indicators** from one code path. The
picker in the masthead swaps indicator; the legend, units, scale breaks, ranking direction,
world reference and source attribution all swap with it, driven entirely by metadata in each
data file. Nothing about the page is specific to any one indicator.

Serve it from the repo root (the data files are loaded by relative path):

```bash
python3 -m http.server 8000
```

then open `http://localhost:8000/ui-prototypes/renewable-energy-share.html`. The URL hash
carries the view — `#energy-intensity&y=2015&c=DEU` — so any state is shareable.

| Indicator | DCID | Unit | Years | Source |
| --- | --- | --- | --- | --- |
| Renewable share | `undata/sdg/EG_FEC_RNEW` | percent | 1990–2023 | SDG portal |
| Electricity access | `undata/sdg/EG_ACS_ELEC` | percent | 2000–2024 | SDG portal |
| Energy intensity | `undata/sdg/EG_EGY_PRIM` | MJ per const. 2011 USD PPP | 1990–2023 | SDG portal |
| CO₂ per capita | `undata/undphdro/PHDI_co2_prod` | t CO₂-eq per person | 1990–2023 | UNDP HDRO |
| Renewable capacity | `undata/sdg/EG_EGY_RNEW` | watts per person | 2000–2024 | SDG portal |
| Electricity generation | `Annual_Generation_Electricity` | TWh | 1990–2024 | UNSD Energy Statistics |

Two of these are "lower is better", and they span three provenances, which is the point — it
forces the page to be genuinely indicator-agnostic rather than incidentally so.

### On indicators outside the undata namespace

`search_indicators` only ever returns `undata/*` variables: the MCP layer enforces the UN
statistical boundary. Electricity generation is a **base Data Commons variable**, so it is
not discoverable that way — it was resolved through the REST `/node` endpoint instead, and
its config entry records that in `resolvedVia`. Its data is still UN-sourced (UNSD Energy
Statistics), but it is reached outside the curated namespace, and the page says so under the
source line via the indicator's `sourceNote`.

Three config fields exist for these variables, and all three earn their keep here:

- **`requireUnit`** pins the facet by unit. `Annual_Generation_Electricity` lists an EIA
  facet in **GigawattHour** first for the USA and a UNSD **KilowattHour** facet for the other
  227 countries. Taking the preferred facet per country would put the USA on the map a
  million-fold out, silently, with only a generic multi-facet warning. Pinning the unit drops
  countries that have no facet in it rather than mixing.
- **`scale`** converts at generation time (`1e-9`, kWh → TWh).
- **`aggregate: "sum"`** builds the world reference by summing countries, since averaging an
  absolute total is meaningless. A total is only published for years whose reporters account
  for ≥95% of the best-covered year's output — counting countries is the wrong test, because
  most years miss only tiny states while 2019 and 2024 miss giants. Thin years stay on the
  map and simply carry no world figure.

Note that a choropleth of an absolute total is dominated by large countries by construction;
the quantile bins stay evenly filled, but the big generators are also the big landmasses.
A per-capita variant would read better cartographically.

Worth knowing if you go looking: **IPUMS is not on this instance** — no source node and no
provenance under any spelling. World Bank *is* present (six datasets including World
Development Indicators, 1960–2024) and reachable the same way generation was.

### Data layout

- `data/world-geo.js` — the 110m basemap and country names, loaded once (`window.UNGEO`).
- `data/indicators/<slug>.js` — one self-registering file per indicator, carrying its own
  metadata, year domain, scale breaks, series and world reference (`window.UNDATA[slug]`).

Generated files are ASCII-escaped on purpose: they load as classic `<script>` and most
servers send `.js` with no charset, so a raw UTF-8 country name would mojibake.

### Regenerating the atlas data

Two phases, because the MCP tools only exist inside a Claude session while the fetching is
better done by a script you can re-run.

**Phase A — resolve indicators (Claude, once per indicator).** Use `search_indicators` to
find the DCID and `get_variable_metadata` to confirm unit, coverage and provenance, then
record both in [scripts/indicators.config.json](scripts/indicators.config.json) along with
the display copy. Never hand-write a DCID — resolve it.

**Phase B — fetch observations (repeatable, no MCP).**

```bash
node scripts/fetch-indicator.mjs            # all indicators, or pass slugs
```

It only fetches observations for DCIDs already resolved in Phase A, from the REST endpoint
above. Per indicator it computes the year domain (dropping partial tail years below half the
indicator's peak country coverage — SDG 2024 is usually still filling in), quantile scale
breaks snapped to round numbers, and a world reference series: the reported `Earth` value
where one exists, otherwise a population-weighted average. `PHDI_co2_prod` has no `Earth`
aggregate, so it takes the weighted path and the page labels it as an estimate.

Supporting scripts: `scripts/fill-names.mjs` fills any missing country display name from
the `/node` endpoint. `scripts/split-geo.mjs` is the one-shot that produced
`data/world-geo.js` from the original fused data file; it is kept as a record of how the
basemap was derived and needs that file restored from git history to run again.

Warnings go to stderr — dropped years, countries with more than one facet, unresolved
names — so a regeneration that quietly changes shape is visible.
