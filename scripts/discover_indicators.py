"""Enrich the curated catalog from the live API, and search for new candidates.

--enrich   fills catalog/discovered.yml with unit/temporal/coverage metadata
           for every indicator in catalog/indicators.yml, using
           /api/variable/info and one /api/observations/point/within probe.
--search Q hits /api/stats/stat-var-search, filters to undata/ DCIDs, and
           appends matches to discovered.yml as status: candidate for a
           human to review and promote into indicators.yml.

This is the mechanism behind the "add an indicator with no new code" claim:
running --enrich after adding a stub entry to indicators.yml is the entire
workflow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recipe.catalog import CATALOG_DIR, load_yaml
from recipe.dcid_grammar import parse_dcid
from recipe.datacommons_client import DataCommonsClient, EmptyResponseError
from recipe.sources import DEFAULT_SOURCE, client_for
from recipe.worldbank_client import WorldBankClient, worldbank_code

DISCOVERED_PATH = CATALOG_DIR / "discovered.yml"


def _write_discovered(entries: dict[str, dict[str, Any]]) -> None:
    existing = load_yaml(DISCOVERED_PATH).get("indicators", {})
    existing.update(entries)
    with DISCOVERED_PATH.open("w") as f:
        yaml.safe_dump({"version": 1, "indicators": existing}, f, sort_keys=False)


def enrich(client: DataCommonsClient) -> None:
    curated = load_yaml(CATALOG_DIR / "indicators.yml").get("indicators", {})
    entries: dict[str, dict[str, Any]] = {}

    for key, spec in curated.items():
        dcid = spec["dcid"]
        parsed = parse_dcid(dcid)
        entry: dict[str, Any] = {
            "dcid": dcid,
            "label": spec["label"],
            "source_agency": parsed.agency,
            "code": parsed.code,
            "dimensions": parsed.dimensions,
        }

        source = spec.get("source", DEFAULT_SOURCE)
        if source == "world_bank":
            _enrich_worldbank(client_for(source), key, spec, entry)
            entries[key] = entry
            print(
                f"  enriched {key}: {entry.get('place_coverage', '?')} places, "
                f"upstream={entry.get('upstream_source')}"
            )
            continue

        try:
            info = client.variable_info([dcid])
            summaries = info.get(dcid, {}).get("provenanceSummary", {})
            if summaries:
                prov_id, prov = next(iter(summaries.items()))
                entry["provenance_id"] = prov_id
                series_summary = (prov.get("seriesSummary") or [{}])[0]
                key_info = series_summary.get("seriesKey", {})
                entry["unit"] = key_info.get("unit")
                entry["temporal_start"] = series_summary.get("earliestDate")
                entry["temporal_end"] = series_summary.get("latestDate")
                entry["value_min"] = series_summary.get("minValue")
                entry["value_max"] = series_summary.get("maxValue")
                entry["facet_count"] = len(summaries)
        except Exception as exc:  # noqa: BLE001 - report and continue enriching others
            print(f"  [warn] variable_info failed for {key}: {exc}")

        try:
            payload = client.point_within("Earth", "Country", [dcid])
            places = payload.variable(dcid)
            entry["place_coverage"] = len(places)
            facets = {o["facet"] for o in places.values()}
            entry.setdefault("facet_count", len(facets))
            if len(facets) == 1:
                facet_meta = payload.facet(next(iter(facets)))
                entry["unit_display"] = facet_meta.get("unitDisplayName")
                entry.setdefault("unit", facet_meta.get("unit"))
                entry.setdefault("provenance_url", facet_meta.get("provenanceUrl"))
        except EmptyResponseError as exc:
            print(f"  [warn] {key}: {exc}")
            entry["place_coverage"] = 0

        entries[key] = entry
        print(
            f"  enriched {key}: {entry.get('place_coverage', '?')} places, "
            f"unit={entry.get('unit_display') or entry.get('unit')}"
        )

    _write_discovered(entries)
    print(f"\nWrote {len(entries)} entries to {DISCOVERED_PATH}")


def _enrich_worldbank(
    client: WorldBankClient, key: str, spec: dict[str, Any], entry: dict[str, Any]
) -> None:
    """Fill the same discovered.yml schema from the World Bank API.

    Unit and unit_display are NOT written here: the API reports unit="" on
    every observation, so those are hand-declared in indicators.yml and the
    catalog loader lets curated values win.
    """
    code = worldbank_code(spec["dcid"])

    try:
        info = client.indicator_info(code)
        entry["provenance_id"] = "worldBank/WDI"
        entry["provenance_url"] = f"https://data.worldbank.org/indicator/{code}"
        # Who actually produced the numbers. The World Bank republishes a lot:
        # three of the four indicators we pull directly are IEA data, and
        # recording that is what stops "two sources" meaning one dataset twice.
        upstream = (info.get("sourceOrganization") or "").split(",")[0].strip()
        entry["upstream_source"] = upstream or info.get("source", {}).get("value")
        entry["facet_count"] = 1
    except Exception as exc:  # noqa: BLE001 - report and continue enriching others
        print(f"  [warn] indicator_info failed for {key}: {exc}")

    try:
        rows = client.raw_observations(code, most_recent=True)
        allowed = set(client.countries())
        values, dates = [], []
        for row in rows:
            if row.get("value") is None:
                continue
            iso3 = row.get("countryiso3code") or ""
            if f"country/{iso3.upper()}" not in allowed:
                continue
            values.append(float(row["value"]))
            dates.append(str(row["date"]))
        entry["place_coverage"] = len(values)
        if values:
            # Stored unrounded: rounding these inward puts the extreme
            # observation outside its own recorded range, which
            # check_range_violation then reports as drift.
            entry["value_min"] = min(values)
            entry["value_max"] = max(values)
            entry["temporal_start"] = min(dates)
            entry["temporal_end"] = max(dates)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] coverage probe failed for {key}: {exc}")
        entry["place_coverage"] = 0


def search(client: DataCommonsClient, query: str) -> None:
    hits = client.search_variables(query)
    undata_hits = [
        h for h in hits if str(h.get("dcid", "")).startswith(("undata/", "worldBank/"))
    ]
    print(f"'{query}': {len(hits)} total hits, {len(undata_hits)} catalogued\n")

    candidates: dict[str, dict[str, Any]] = {}
    for h in undata_hits:
        dcid = h["dcid"]
        parsed = parse_dcid(dcid)
        key = f"candidate_{parsed.code.lower()}_{dcid.split('/')[1]}"
        candidates[key] = {
            "dcid": dcid,
            "label": h.get("name", dcid),
            "source_agency": parsed.agency,
            "code": parsed.code,
            "dimensions": parsed.dimensions,
            "status": "candidate",
        }
        print(f"  {dcid}\n    {h.get('name', '')}")

    if candidates:
        _write_discovered(candidates)
        print(f"\nAppended {len(candidates)} candidates to {DISCOVERED_PATH}")
        print(
            "Promote a candidate by adding it to catalog/indicators.yml, "
            "then run `make enrich`."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--search", metavar="QUERY")
    args = parser.parse_args()

    client = DataCommonsClient()
    if args.enrich:
        enrich(client)
    elif args.search:
        search(client, args.search)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
