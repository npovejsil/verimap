"""GeoJSON fetch and choropleth join auditing.

The join between observation data and map geometry is the foundation of the
whole geospatial pitch: GeoJSON `feature.id` / `properties.geoDcid` are the
same `country/XXX` DCIDs the observation API returns, so no crosswalk table
is needed. `audit_join` makes that fact visible and asserts it rather than
assuming it silently holds after a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recipe.datacommons_client import DataCommonsClient

_CONTINENTS = [
    "africa",
    "northamerica",
    "southamerica",
    "asia",
    "europe",
    "oceania",
    "antarctica",
]


@dataclass(frozen=True)
class JoinAudit:
    """Result of matching observation place DCIDs against map geometry."""

    n_observations: int
    n_geometries: int
    n_matched: int
    unmatched_observation_places: tuple[str, ...]
    unmatched_geometry_places: tuple[str, ...]

    @property
    def is_clean(self) -> bool:
        """True only if every observation has geometry to render on.

        Unmatched *geometries* (e.g. Antarctica, no reported statistic) are
        expected and rendered grey. Unmatched *observations* would mean data
        silently fails to appear on the map, which must never happen unnoticed.
        """
        return len(self.unmatched_observation_places) == 0


def fetch_country_geojson(client: DataCommonsClient) -> dict[str, Any]:
    """Fetch the world country GeoJSON FeatureCollection."""
    return client.geojson(place_dcid="Earth", place_type="Country")


def audit_join(geojson: dict[str, Any], observation_place_dcids: set[str]) -> JoinAudit:
    """Compare observation place DCIDs against GeoJSON feature ids."""
    geometry_places = {f["id"] for f in geojson["features"]}
    matched = observation_place_dcids & geometry_places
    return JoinAudit(
        n_observations=len(observation_place_dcids),
        n_geometries=len(geometry_places),
        n_matched=len(matched),
        unmatched_observation_places=tuple(
            sorted(observation_place_dcids - geometry_places)
        ),
        unmatched_geometry_places=tuple(
            sorted(geometry_places - observation_place_dcids)
        ),
    )


def continent_country_counts(client: DataCommonsClient) -> dict[str, int]:
    """Count countries under each continent, for the region filter."""
    counts: dict[str, int] = {}
    for continent in _CONTINENTS:
        try:
            result = client.place_descendents([continent], "Country")
            counts[continent] = len(result.get(continent, []))
        except Exception:  # noqa: BLE001 - region filter is best-effort
            counts[continent] = 0
    return counts
