"""Aggregate the UNICEF Global Child Hazard Database into static JSON.

The Solr core holds 5,415,036 records over 41,023 admin-2 units, sends no CORS
headers, and needs HTTP Basic auth -- so the browser can never talk to it. This
script runs at build time and emits credential-free artifacts:

  data/hazard/countries.json   one row per country x indicator (choropleth)
  data/hazard/{ISO3}.json      admin-2 detail, lazy-loaded on drilldown

Credentials come from .env (gitignored). Run: python3 etl/build_hazard.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# Every record is admin-2, year 2025. Restrict to child totals and drop the
# rows Solr flags as No Data / Insufficient Data / Not Applicable.
BASE_FILTERS = ["sex:_T", "age:Y0T17", "-status:[* TO *]"]

FIELDS = [
    "ref_area",
    "indicator",
    "exposure_absolute",
    "exposure_relative",
    "hazard_mean",
    "population_val",
    "country_exposure_class",
]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


class Solr:
    def __init__(self) -> None:
        self.url = os.environ.get(
            "GCHD_SOLR_URL",
            "https://ss529626-pa5e13zk-westeurope-azure.searchstax.com/solr/hazard/select",
        )
        user = os.environ.get("GCHD_SOLR_USER", "")
        password = os.environ.get("GCHD_SOLR_PASSWORD", "")
        if not user or not password:
            raise SystemExit(
                "Missing GCHD_SOLR_USER / GCHD_SOLR_PASSWORD.\n"
                "Copy .env.example to .env and fill them in."
            )
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = f"Basic {token}"

    def query(self, params: list[tuple[str, str]], timeout: int = 300) -> dict:
        url = f"{self.url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Authorization": self.auth})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # UTF-8 matters: units include days >35°C, μg/m³, km⁻²·yr⁻¹.
            return json.loads(response.read().decode("utf-8"))


def country_rollup(solr: Solr) -> dict:
    """One faceted call: every country x indicator, aggregated server-side."""
    facet = {
        "countries": {
            "type": "terms",
            "field": "iso3_parent",
            "limit": 300,
            "facet": {
                "inds": {
                    "type": "terms",
                    "field": "indicator",
                    "limit": 30,
                    "facet": {
                        # Sum then divide -- averaging percentages across units
                        # of different sizes would be wrong.
                        "exposed": "sum(exposure_absolute)",
                        "pop": "sum(population_val)",
                        "hazard": "avg(hazard_mean)",
                        "worst": "max(hazard_max)",
                        "cls": "max(country_exposure_class)",
                        "units": "unique(ref_area)",
                    },
                }
            },
        }
    }
    params = [("q", "*:*"), ("rows", "0"), ("json.facet", json.dumps(facet))]
    params += [("fq", f) for f in BASE_FILTERS]
    data = solr.query(params)

    out: dict[str, dict] = {}
    for bucket in data["facets"]["countries"]["buckets"]:
        iso3 = bucket["val"]
        indicators = {}
        for ind in bucket.get("inds", {}).get("buckets", []):
            exposed = ind.get("exposed", 0.0) or 0.0
            pop = ind.get("pop", 0.0) or 0.0
            indicators[ind["val"]] = {
                "exposed": round(exposed),
                "pop": round(pop),
                "pct": round(exposed / pop * 100, 2) if pop else None,
                "hazard": round(ind["hazard"], 4) if ind.get("hazard") is not None else None,
                "worst": round(ind["worst"], 4) if ind.get("worst") is not None else None,
                "cls": ind.get("cls"),
                "units": ind.get("units"),
            }
        out[iso3] = {"records": bucket["count"], "indicators": indicators}
    return out


def hazard_units(solr: Solr) -> dict[str, str]:
    """The unit each indicator's hazard_mean is measured in.

    Without this the drilldown can only print a bare number: river flood is
    metres, PM2.5 is micrograms, heatwaves are per year. One faceted call, and
    every indicator turns out to carry exactly one unit.
    """
    facet = {
        "inds": {
            "type": "terms",
            "field": "indicator",
            "limit": 40,
            "facet": {"unit": {"type": "terms", "field": "unit_hazard", "limit": 1}},
        }
    }
    params = [("q", "*:*"), ("rows", "0"), ("json.facet", json.dumps(facet))]
    params += [("fq", f) for f in BASE_FILTERS]
    out = {}
    for bucket in solr.query(params)["facets"]["inds"]["buckets"]:
        units = bucket.get("unit", {}).get("buckets", [])
        if units:
            out[bucket["val"]] = units[0]["val"]
    return out


def trim(value, places: int | None = 0):
    """Round a Solr float for storage.

    The raw values carry more precision than anything downstream uses -- an
    exposure count arrives as 191.0 and a hazard mean as 6.25711 -- and across
    ~900,000 stored numbers those spare characters are megabytes of JSON.
    """
    if value is None:
        return None
    return int(round(value)) if places == 0 else round(value, places)


def country_detail(solr: Solr, iso3: str) -> dict:
    """Admin-2 rows for one country, in a columnar shape to keep files small."""
    params = [
        ("q", "*:*"),
        ("rows", "200000"),
        ("fl", ",".join(FIELDS)),
        ("wt", "json"),
        ("sort", "ref_area asc"),
    ]
    # Quote the code: Solr parses a bare AND / OR / NOT as a boolean operator,
    # so Andorra (AND) throws a 400 without the quotes.
    params += [("fq", f) for f in BASE_FILTERS + [f'iso3_parent:"{iso3}"']]
    docs = solr.query(params)["response"]["docs"]

    areas: list[str] = []
    area_index: dict[str, int] = {}
    series: dict[str, dict[str, list]] = {}
    for doc in docs:
        area = doc.get("ref_area")
        if area not in area_index:
            area_index[area] = len(areas)
            areas.append(area)
        indicator = doc.get("indicator")
        block = series.setdefault(
            indicator,
            {"area": [], "exposed": [], "pop": [], "pct": [], "hazard": [], "cls": []},
        )
        block["area"].append(area_index[area])
        block["exposed"].append(trim(doc.get("exposure_absolute")))
        # Population is what makes the unit aggregatable: rolling admin-2 up to
        # admin-1 means sum(exposed)/sum(pop), never an average of percentages.
        block["pop"].append(trim(doc.get("population_val")))
        block["pct"].append(trim(doc.get("exposure_relative"), 2))
        block["hazard"].append(trim(doc.get("hazard_mean"), 4))
        block["cls"].append(trim(doc.get("country_exposure_class")))
    return {"iso3": iso3, "areas": areas, "indicators": series}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/hazard")
    ap.add_argument("--countries-only", action="store_true")
    ap.add_argument("--units-only", action="store_true",
                    help="refresh units.json without the 6-minute rebuild")
    ap.add_argument("--limit", type=int, default=0, help="only N countries (testing)")
    args = ap.parse_args()

    load_env(Path(__file__).resolve().parent.parent / ".env")
    solr = Solr()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    units = hazard_units(solr)
    (out / "units.json").write_text(
        json.dumps(units, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  {len(units)} indicator units -> units.json", file=sys.stderr)
    if args.units_only:
        return 0

    print("Country rollup (single faceted query)...", file=sys.stderr)
    rollup = country_rollup(solr)
    indicators = sorted({i for c in rollup.values() for i in c["indicators"]})
    (out / "countries.json").write_text(
        json.dumps(
            {"indicators": indicators, "countries": rollup},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    size = (out / "countries.json").stat().st_size / 1024
    print(
        f"  {len(rollup)} countries x {len(indicators)} indicators -> countries.json ({size:.0f} KB)",
        file=sys.stderr,
    )

    if args.countries_only:
        return 0

    detail_dir = out / "admin2"
    detail_dir.mkdir(exist_ok=True)
    codes = sorted(rollup)
    if args.limit:
        codes = codes[: args.limit]
    total = 0
    for n, iso3 in enumerate(codes, 1):
        detail = country_detail(solr, iso3)
        path = detail_dir / f"{iso3}.json"
        path.write_text(
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        total += path.stat().st_size
        print(
            f"  [{n}/{len(codes)}] {iso3}: {len(detail['areas'])} units, "
            f"{path.stat().st_size / 1024:.0f} KB",
            file=sys.stderr,
        )
    print(f"admin-2 detail: {total / 1048576:.1f} MB total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
