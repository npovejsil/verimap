"""Smoke-test every endpoint the client uses, against known-good values.

Run with: make verify (or .venv/bin/python scripts/verify_endpoints.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recipe.datacommons_client import DataCommonsClient, EmptyResponseError

RWANDA_ELEC = "undata/sdg/EG_ACS_ELEC"
WHO_CLEAN_COOK = "undata/who/COOKFUEL_PROP.COOK_FUEL--CLEAN"
SDG_RENEW_SHARE = "undata/sdg/EG_FEC_RNEW"


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    client = DataCommonsClient()

    payload = client.series(["country/RWA"], [RWANDA_ELEC])
    series = payload.variable(RWANDA_ELEC)["country/RWA"]["series"]
    check(
        "series: Rwanda electricity access",
        len(series) == 25 and series[0]["date"] == "2000",
        f"obsCount={len(series)}",
    )

    payload = client.point_within("Earth", "Country", [RWANDA_ELEC])
    places = payload.variable(RWANDA_ELEC)
    facets = {o["facet"] for o in places.values()}
    check(
        "point/within: all countries, one facet",
        len(places) == 217 and len(facets) == 1,
        f"places={len(places)} facets={len(facets)}",
    )

    payload = client.series_within(
        "Earth", "Country", [RWANDA_ELEC, WHO_CLEAN_COOK, SDG_RENEW_SHARE]
    )
    total_obs = sum(
        len(v.get("series", []))
        for var in payload.requested_variables
        for v in payload.variable(var).values()
    )
    check(
        "series/within: multi-variable single call",
        total_obs == 17_923,
        f"total_obs={total_obs}",
    )

    geo = client.geojson()
    features = geo["features"]
    bad_ids = [
        f["id"]
        for f in features
        if not f["id"].startswith("country/") or len(f["id"]) != 11
    ]
    check(
        "geojson: 238 country features, well-formed ids",
        len(features) == 238 and not bad_ids,
        f"n={len(features)} bad_ids={bad_ids[:5]}",
    )

    names = client.place_names(["country/RWA"])
    check("place/name: resolves Rwanda", "country/RWA" in names)

    info = client.variable_info([RWANDA_ELEC])
    check("variable/info: returns metadata", RWANDA_ELEC in info)

    hits = client.search_variables("clean cooking fuel")
    undata_hits = [h for h in hits if str(h.get("dcid", "")).startswith("undata/")]
    check(
        "stat-var-search: finds undata hits",
        len(undata_hits) > 0,
        f"n_undata={len(undata_hits)}",
    )

    try:
        client.point(["country/KEN"], ["undata/sdg/NOT_A_VAR"])
        check("negative: bogus DCID raises EmptyResponseError", False)
    except EmptyResponseError:
        check("negative: bogus DCID raises EmptyResponseError", True)

    print("\nAll endpoint checks passed.")


if __name__ == "__main__":
    main()
