"""Build places.json: continents, their member countries, and country names.

The dashboard lets you select continents or countries, so it needs the
containment hierarchy up front. Continents are first-class entities here with
their own aggregate observations, so a continent is both a *selection* and a
*data point* -- both are captured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from un_client import Rest

CONTINENTS = {
    "africa": "Africa",
    "asia": "Asia",
    "europe": "Europe",
    "northamerica": "North America",
    "southamerica": "South America",
    "oceania": "Oceania",
}


def main() -> int:
    rest = Rest()

    members: dict[str, list[str]] = {}
    for dcid in CONTINENTS:
        nodes = rest.arc([dcid], "<-containedInPlace{typeOf:Country}").get(dcid, [])
        members[dcid] = sorted({n["dcid"] for n in nodes if n.get("dcid")})
        print(f"  {dcid}: {len(members[dcid])} countries", file=sys.stderr)

    all_countries = sorted({c for ms in members.values() for c in ms})

    # Names come from the boundary file rather than the graph. Three country
    # dcids (ESH, GRC, SVN) are rejected with 403 whenever they appear literally
    # in a `nodes=` parameter -- alone, at any batch size, on any property -- so
    # asking the API for names loses Greece and Slovenia. adm0 already carries
    # name_en per ISO3, is local, and needs no request at all.
    names: dict[str, str] = {}
    topo_path = Path(__file__).resolve().parent.parent / "data" / "boundaries" / "adm0.min.topo.json"
    if topo_path.exists():
        topo = json.loads(topo_path.read_text(encoding="utf-8"))
        key = next(iter(topo["objects"]))
        for geom in topo["objects"][key]["geometries"]:
            props = geom.get("properties") or {}
            iso3, label = props.get("iso3"), props.get("name_en")
            if iso3 and label:
                names.setdefault(f"country/{iso3}", label)
    else:
        print("  WARNING: adm0.min.topo.json missing; names fall back to dcids", file=sys.stderr)

    # Invert for quick country -> continent lookup in the UI.
    continent_of = {c: cont for cont, ms in members.items() for c in ms}

    payload = {
        "continents": [
            {"dcid": d, "name": n, "countries": members[d]} for d, n in CONTINENTS.items()
        ],
        "countries": {
            dcid: {
                "name": names.get(dcid, dcid),
                "iso3": dcid.removeprefix("country/"),
                "continent": continent_of.get(dcid),
            }
            for dcid in all_countries
        },
    }

    out = Path(__file__).resolve().parent.parent / "data" / "places.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"{len(all_countries)} countries, {len(names)} named -> {out} "
        f"({out.stat().st_size / 1024:.0f} KB)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
