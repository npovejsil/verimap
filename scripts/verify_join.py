"""Assert the choropleth join is clean: every observation has geometry.

This is the single most important check in the project. If it ever fails,
the map, priority table, and headline numbers all silently go wrong with no
error message.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recipe.datacommons_client import DataCommonsClient
from recipe.geography import audit_join, fetch_country_geojson


def main() -> None:
    client = DataCommonsClient()
    geojson = fetch_country_geojson(client)

    payload = client.point_within("Earth", "Country", ["undata/sdg/EG_ACS_ELEC"])
    places = set(payload.variable("undata/sdg/EG_ACS_ELEC").keys())

    audit = audit_join(geojson, places)
    print(f"observations: {audit.n_observations}")
    print(f"geometries:   {audit.n_geometries}")
    print(f"matched:      {audit.n_matched}")
    print(
        f"unmatched observation places (MUST be empty): "
        f"{audit.unmatched_observation_places}"
    )
    print(
        f"unmatched geometry places (expected, e.g. Antarctica): "
        f"{len(audit.unmatched_geometry_places)}"
    )
    for p in audit.unmatched_geometry_places:
        print(f"  - {p}")

    if not audit.is_clean:
        print("\nFAIL: observations exist with no matching geometry.")
        raise SystemExit(1)

    print("\nPASS: every observation has matching geometry.")


if __name__ == "__main__":
    main()
