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


def search(client: DataCommonsClient, query: str) -> None:
    hits = client.search_variables(query)
    undata_hits = [h for h in hits if str(h.get("dcid", "")).startswith("undata/")]
    print(f"'{query}': {len(hits)} total hits, {len(undata_hits)} undata\n")

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
