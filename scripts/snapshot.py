"""Freeze demo payloads to cache/snapshot/ so the demo survives a dead network.

Run before any live demo. `make offline` then serves entirely from these
files with the network disabled.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recipe.catalog import load_catalog
from recipe.datacommons_client import DataCommonsClient, EmptyResponseError

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "cache" / "snapshot"


def main() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    client = DataCommonsClient()
    catalog = load_catalog()

    geo = client.geojson()
    (SNAPSHOT_DIR / "geojson_earth_country.json").write_text(json.dumps(geo))
    print(f"snapshot: geojson ({len(geo['features'])} features)")

    all_place_dcids: set[str] = set()
    for key, indicator in catalog.indicators.items():
        try:
            payload = client.point_within("Earth", "Country", [indicator.dcid])
        except EmptyResponseError as exc:
            print(f"  [skip] {key}: {exc}")
            continue
        places = payload.variable(indicator.dcid)
        all_place_dcids.update(places.keys())
        out = {
            "data": {indicator.dcid: places},
            "facets": payload.facets,
        }
        (SNAPSHOT_DIR / f"point_{key}.json").write_text(json.dumps(out))
        print(f"snapshot: {key} ({len(places)} places)")

    names = client.place_names(sorted(all_place_dcids))
    (SNAPSHOT_DIR / "place_names.json").write_text(json.dumps(names))
    print(f"snapshot: place_names ({len(names)} resolved of {len(all_place_dcids)})")

    print(f"\nWrote snapshot to {SNAPSHOT_DIR}")


if __name__ == "__main__":
    main()
