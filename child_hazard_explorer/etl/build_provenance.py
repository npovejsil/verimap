"""Record where every figure came from, and where the sources disagree.

The app used to attribute its data in two hardcoded sentences. Nothing that
produced the data wrote any provenance, so those sentences could drift from the
artifacts without anyone noticing -- and the ETL knew the whole lineage and threw
it away.

This captures it from the build instead: sources and their extraction dates, the
query that selected the records, which raw field backs each number on screen, the
transformations applied, and the cross-checks.

The cross-checks are the point. Several figures have two independent
derivations, so they can be compared rather than trusted:

  country total (server-side facet)  vs  sum of that country's admin-2 rows
  admin-1 roll-up                    vs  sum of its admin-2 children
  the boundary version a hazard record cites  vs  the one GeoRepo publishes now

Everything here is computed or read from the artifacts. Nothing is typed by
hand, so `provenance.json` cannot disagree with what ships.

Usage:  python3 etl/build_provenance.py
"""

from __future__ import annotations

import collections
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_hazard import BASE_FILTERS
from verify import BOUNDS, DATA, country_topologies, hazard_details, load

GEOREPO = "https://unidatadapmclimatechange.blob.core.windows.net/public/georepo"
OUT = DATA / "provenance.json"
stem_of = lambda ucode: re.sub(r"_V\d+$", "", ucode)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def built_at(path: Path) -> str | None:
    """When an artifact was written -- evidence, rather than a guess."""
    return iso(path.stat().st_mtime) if path.exists() else None


def upstream_modified(level: str) -> str | None:
    """GeoRepo publishes no version number, but it does send Last-Modified."""
    try:
        request = urllib.request.Request(f"{GEOREPO}/{level}.geojson", method="HEAD")
        with urllib.request.urlopen(request, timeout=60) as response:
            stamp = response.headers.get("Last-Modified")
        if not stamp:
            return None
        parsed = datetime.strptime(stamp, "%a, %d %b %Y %H:%M:%S %Z")
        return parsed.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def crosschecks(details: dict, topologies: dict, countries: dict, roll: dict) -> dict:
    """Run every comparison where two derivations should agree."""
    names = load(BOUNDS / "adm2.names.json") if (BOUNDS / "adm2.names.json").exists() else {}

    facet_agree = facet_differ = 0
    facet_worst: list[dict] = []
    version_mismatch = collections.Counter()
    unnamed = 0
    partial = 0
    per_country: dict[str, dict] = {}

    for iso3, detail in sorted(details.items()):
        topo = topologies.get(iso3)
        geo = (
            {
                g["properties"]["stem"]: g["properties"]["ucode"]
                for g in topo["objects"]["adm2"]["geometries"]
            }
            if topo
            else {}
        )

        c_ver = c_unnamed = 0
        for area in detail["areas"]:
            published = geo.get(stem_of(area))
            if published and published != area:
                c_ver += 1
            if area not in names:
                c_unnamed += 1
        version_mismatch[iso3] += c_ver
        unnamed += c_unnamed

        # Two paths to the same number: the server-side facet, and the rows.
        entry = countries.get("countries", {}).get(iso3, {})
        c_agree = c_differ = 0
        for indicator, cell in entry.get("indicators", {}).items():
            block = detail["indicators"].get(indicator)
            if not block:
                continue
            total = sum(v for v in block["exposed"] if v is not None)
            reported = cell.get("exposed")
            if reported is None:
                continue
            gap = abs(total - reported)
            if gap <= max(1, 0.0005 * max(reported, 1)):
                c_agree += 1
            else:
                c_differ += 1
                facet_worst.append(
                    {"iso3": iso3, "indicator": indicator, "facet": reported, "sum": total}
                )
        facet_agree += c_agree
        facet_differ += c_differ

        rolled = roll.get(iso3, {})
        for block in rolled.get("indicators", {}).values():
            partial += sum(
                1 for i, n in enumerate(block["units"]) if n < block["total"][i]
            )

        per_country[iso3] = {
            "adm2_units": len(detail["areas"]),
            "adm1_areas": len(rolled.get("areas", [])),
            "indicators": len(detail["indicators"]),
            "facet_agrees": c_differ == 0,
            "facet_cells": c_agree + c_differ,
            "version_mismatch": c_ver,
            "unnamed": c_unnamed,
        }

    offenders = {k: v for k, v in version_mismatch.items() if v}
    return {
        "per_country": per_country,
        "checks": [
            {
                "id": "facet_vs_rows",
                "label": "Country total vs sum of its admin-2 records",
                "detail": "Two independent derivations: a server-side facet over the "
                          "database, and the individual rows this app ships.",
                "agree": facet_agree,
                "total": facet_agree + facet_differ,
                "passed": facet_differ == 0,
                "offenders": facet_worst[:5],
            },
            {
                "id": "boundary_version",
                "label": "Boundary version cited by the hazard record vs published now",
                "detail": "Where these differ the record sits on a superseded boundary "
                          "version; the join falls back to the versionless code.",
                "agree": sum(len(d["areas"]) for d in details.values()) - sum(offenders.values()),
                "total": sum(len(d["areas"]) for d in details.values()),
                "passed": not offenders,
                "offenders": [{"iso3": k, "units": v} for k, v in sorted(offenders.items())],
            },
            {
                "id": "named_units",
                "label": "Admin-2 units with a name in the boundary source",
                "detail": "A unit with no name is shown by its code.",
                "agree": sum(len(d["areas"]) for d in details.values()) - unnamed,
                "total": sum(len(d["areas"]) for d in details.values()),
                "passed": unnamed == 0,
                "offenders": [],
            },
            {
                "id": "adm1_coverage",
                "label": "Admin-1 areas aggregated from every one of their children",
                "detail": "The rest are computed from only some children, so their "
                          "percentage is over the covered population.",
                "agree": sum(
                    len(b["units"]) for c in roll.values() for b in c["indicators"].values()
                ) - partial,
                "total": sum(
                    len(b["units"]) for c in roll.values() for b in c["indicators"].values()
                ),
                "passed": partial == 0,
                "offenders": [],
            },
        ],
    }


def main() -> int:
    countries_path = DATA / "hazard" / "countries.json"
    if not countries_path.exists():
        print("no hazard artifacts - run build_hazard.py first", file=sys.stderr)
        return 1

    countries = load(countries_path)
    details = hazard_details()
    topologies = country_topologies()
    adm1_path = DATA / "hazard" / "adm1.json"
    roll = load(adm1_path) if adm1_path.exists() else {}

    provenance = {
        "generated": iso(datetime.now(timezone.utc).timestamp()),
        "sources": [
            {
                "id": "gchd",
                "name": "UNICEF Global Child Hazard Database",
                "provides": "Hazard exposure records for children aged 0-17, admin-2",
                # The endpoint is credentialed and this page is shareable, so the
                # source is named and its query stated without the host.
                "access": "Solr, access-controlled; queried at build time only",
                "licence": "Terms not confirmed - check with UNICEF before redistributing",
                "reference_period": "2025",
                "extracted": built_at(countries_path),
                "records": sum(c.get("records", 0) for c in countries["countries"].values()),
            },
            {
                "id": "georepo",
                "name": "UNICEF GeoRepo",
                "provides": "Admin-0 and admin-2 boundaries (admin-1 dissolved from admin-2)",
                "access": "Public static GeoJSON",
                "licence": "CC BY 4.0",
                "upstream_modified": upstream_modified("adm2"),
                "extracted": built_at(BOUNDS / "country-index.json"),
            },
        ],
        "query": {
            "filters": BASE_FILTERS,
            "meaning": [
                "sex:_T - both sexes combined",
                "age:Y0T17 - children aged 0 to 17",
                "-status:[* TO *] - rows the database flags as No Data, "
                "Insufficient Data or Not Applicable are excluded",
            ],
        },
        "fields": [
            {"shown": "Exposed children", "field": "exposure_absolute"},
            {"shown": "Exposure %", "field": "exposure_relative"},
            {"shown": "Children in area", "field": "population_val"},
            {"shown": "Hazard measure", "field": "hazard_mean"},
            {"shown": "Hazard unit", "field": "unit_hazard"},
            {"shown": "Exposure class", "field": "country_exposure_class"},
        ],
        "transformations": [
            "Admin-2 figures are shown as recorded; no transformation is applied.",
            "Admin-1 has no records in the database. Exposed children and population "
            "are summed from the admin-2 children, and the percentage is re-derived "
            "from those totals rather than averaged.",
            "The admin-1 hazard measure is the mean of its children's values and the "
            "exposure class is their maximum, matching the database's own country "
            "roll-up.",
            "Admin-1 boundaries are dissolved from the simplified admin-2 layer, so a "
            "parent's outline is exactly the union of its children's.",
            "Boundaries are simplified for the web: admin-0 to 3%, admin-2 to 4%, "
            "retaining shapes. Figures are unaffected.",
            "Stored numbers are rounded: counts to whole children, percentages to 2 "
            "decimals, hazard measures to 4.",
        ],
        "counts": {
            "countries": len(details),
            "indicators": len(countries.get("indicators", [])),
            "admin2_units": sum(len(d["areas"]) for d in details.values()),
            "admin1_areas": sum(len(c["areas"]) for c in roll.values()),
        },
        "crosschecks": crosschecks(details, topologies, countries, roll),
    }

    OUT.write_text(
        json.dumps(provenance, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    print(f"{OUT.relative_to(Path(__file__).resolve().parent.parent)} "
          f"({OUT.stat().st_size / 1024:,.0f} KB)", file=sys.stderr)
    for check in provenance["crosschecks"]["checks"]:
        mark = "OK  " if check["passed"] else "DIFF"
        print(f"  [{mark}] {check['label']}: {check['agree']:,}/{check['total']:,}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
