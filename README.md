# VeriMap
UN System Data Commons Builders Day - Data Bears Team

## Data sources

Indicators declare which API they come from in `catalog/indicators.yml`; the
sources themselves are declared in `catalog/sources.yml`.

| Source | Used for |
|---|---|
| UN System Data Commons | SDG, WHO and UNICEF indicators, plus the World Bank series Data Commons republishes |
| World Bank Open Data (WDI) | Only the indicators Data Commons does not carry — transmission and distribution losses, firm outage rates, electricity consumption per capita, renewable electricity output |

The World Bank client is a **coverage supplement, not an independent second
opinion**. Where both pipes carry the same series they agree, because it is the
same underlying dataset: Data Commons' `worldBank/EG_ELC_ACCS_ZS` and the UN's
SDG 7.1.1 figure both descend from the SE4ALL / ESMAP Global Tracking
Framework. Three of the four direct World Bank pulls are republished IEA data.
The Sources tab shows each indicator's actual upstream producer for this
reason.

## Checking the data

```bash
make verify          # endpoint smoke tests, the geo join, then every pull
make verify-sources  # just the per-pull checks, grouped by source
```

`make verify-sources` re-fetches every catalog indicator and checks it against
what the catalog claims — units, value range, country coverage, and place ids
that will actually land on the map. It asserts no golden numbers, so it stays
meaningful when a source publishes a new year. The same results render in the
app's **Sources** tab.

## Running it

```bash
make setup    # python3.11 venv + dependencies
make app      # live, hits both APIs
make offline  # no network, serves from cache/snapshot/
make test
```

Adding an indicator is still catalog-only where Data Commons has the data: add
an entry to `catalog/indicators.yml`, run `make enrich`, then `make snapshot`.
A World Bank indicator adds `source: world_bank` and a hand-declared `unit`,
since that API reports an empty unit on every observation.
