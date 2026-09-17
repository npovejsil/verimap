"""HTTP client for the UN System Data Commons REST API.

The MCP server exposed to agents is not reachable from a standalone Streamlit
process. This client talks to the same backend's plain REST API instead, which
requires no MCP session and no auth.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://unsd-datacommons.gcp.un-icc.cloud"
SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "cache" / "snapshot"


class DataCommonsError(Exception):
    """Base error for all Data Commons client failures."""


class EmptyResponseError(DataCommonsError):
    """Raised when the API returns HTTP 200 with no data for a requested variable.

    A nonexistent or misspelled DCID returns 200 with an empty payload rather
    than a 4xx — this is the only defense against that silent failure mode.
    """

    def __init__(self, variable: str, endpoint: str) -> None:
        self.variable = variable
        self.endpoint = endpoint
        super().__init__(
            f"No data returned for variable '{variable}' from {endpoint}. "
            "Check the DCID is correct — a typo returns HTTP 200 with empty data."
        )


@dataclass(frozen=True)
class ObservationPayload:
    """Wraps a raw observations response, keeping the facet map attached.

    Attribution depends on the facet map, so downstream code must not discard
    it by unpacking only `data`.
    """

    data: dict[str, Any]
    facets: dict[str, Any] = field(default_factory=dict)
    requested_variables: tuple[str, ...] = ()

    def variable(self, dcid: str) -> dict[str, Any]:
        """Return the per-place observation dict for one requested variable."""
        return self.data.get(dcid, {})

    def facet(self, facet_id: str) -> dict[str, Any]:
        """Return provenance/unit metadata for one facet id."""
        return self.facets.get(facet_id, {})


class DataCommonsClient:
    """Thin REST client for the verified UN Data Commons endpoints.

    Only the endpoints confirmed live are exposed. `/api/v2/observation` does
    not exist on this deployment (404) and is intentionally omitted.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = 60,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or self._build_session(retries)

    @staticmethod
    def _build_session(retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            # 403 included: verified live that /api/place/name intermittently
            # returns 403 under back-to-back requests even for identical,
            # previously-successful params — a soft rate limit, not a real
            # access denial. Retrying with backoff clears it.
            status_forcelist=[403, 429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, path: str, params: Sequence[tuple[str, str]]) -> dict[str, Any]:
        """Issue a GET with repeated query params (not comma-joined).

        A comma-joined `variables=a,b,c` string silently returns empty data.
        `requests` handles gzip decompression on `.json()` automatically.
        """
        resp = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def _observations(
        self,
        path: str,
        variables: Sequence[str],
        extra_params: Sequence[tuple[str, str]],
    ) -> ObservationPayload:
        params = [("variables", v) for v in variables] + list(extra_params)
        payload = self._get(path, params)
        data = payload.get("data", {})
        for v in variables:
            var_data = data.get(v)
            if not var_data or not any(var_data.values()):
                raise EmptyResponseError(v, path)
        return ObservationPayload(
            data=data,
            facets=payload.get("facets", {}),
            requested_variables=tuple(variables),
        )

    def point(
        self, entities: Sequence[str], variables: Sequence[str]
    ) -> ObservationPayload:
        """Latest observation for specific entities."""
        extra = [("entities", e) for e in entities]
        return self._observations("/api/observations/point", variables, extra)

    def series(
        self, entities: Sequence[str], variables: Sequence[str]
    ) -> ObservationPayload:
        """Full time series for specific entities."""
        extra = [("entities", e) for e in entities]
        return self._observations("/api/observations/series", variables, extra)

    def point_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        """Latest observation for every child place of a given type in one call."""
        extra = [("parentEntity", parent), ("childType", child_type)]
        return self._observations("/api/observations/point/within", variables, extra)

    def series_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        """Full annual panel for every child place, for one or more variables.

        This is the single most important endpoint in the client: repeated
        `variables=` params return the whole global panel for several
        indicators in one HTTP call (verified: 17,923 observations across 3
        variables in one request).
        """
        extra = [("parentEntity", parent), ("childType", child_type)]
        return self._observations("/api/observations/series/within", variables, extra)

    def geojson(
        self, place_dcid: str = "Earth", place_type: str = "Country"
    ) -> dict[str, Any]:
        """Fetch the choropleth GeoJSON FeatureCollection for a place type."""
        params = [("placeDcid", place_dcid), ("placeType", place_type)]
        return self._get("/api/choropleth/geojson", params)

    def place_names(self, dcids: Sequence[str], batch_size: int = 25) -> dict[str, str]:
        """Resolve DCIDs to human-readable place names.

        Batched, with graceful per-item fallback. Verified live: a WAF layer
        in front of this endpoint 403s any request whose query string
        contains the literal substring "GRC" (Greece's ISO3 code) — a
        deterministic content match, not rate limiting, so retrying the
        whole batch never helps. When a batch fails, this falls back to
        one-DCID-at-a-time requests and skips (without crashing) any DCID
        that still 403s alone, so one blocked country never breaks name
        resolution for the other 24 in its batch.
        """
        result: dict[str, str] = {}
        for i in range(0, len(dcids), batch_size):
            batch = dcids[i : i + batch_size]
            params = [("dcids", d) for d in batch]
            try:
                result.update(self._get("/api/place/name", params))
            except requests.exceptions.RequestException:
                for dcid in batch:
                    try:
                        result.update(self._get("/api/place/name", [("dcids", dcid)]))
                    except requests.exceptions.RequestException:
                        pass  # leave unresolved; caller falls back to the raw dcid
        return result

    def place_descendents(
        self, dcids: Sequence[str], descendent_type: str
    ) -> dict[str, Any]:
        """List descendant places of a given type below the given places."""
        params = [("dcids", d) for d in dcids] + [("descendentType", descendent_type)]
        return self._get("/api/place/descendent", params)

    def variable_info(self, dcids: Sequence[str]) -> dict[str, Any]:
        """Batch metadata: unit, temporal range, value range, provenance."""
        params = [("dcids", d) for d in dcids]
        return self._get("/api/variable/info", params)

    def search_variables(self, query: str) -> list[dict[str, Any]]:
        """Free-text search over statistical variables (auto-discovery)."""
        params = [("query", query)]
        result = self._get("/api/stats/stat-var-search", params)
        return result.get("statVars") or result.get("results") or []


class OfflineDataCommonsClient:
    """Snapshot-backed client matching DataCommonsClient's method surface.

    Reads only from cache/snapshot/ (populated by scripts/snapshot.py) and
    never touches the network. Used when DATA_BEARS_OFFLINE=1, so a demo
    survives a dead connection.

    Caveat: this only removes the UN Data Commons API as a dependency.
    pydeck's basemap (Carto/OpenStreetMap tiles) still fetches tiles over
    the network on first render — the choropleth colors and data are fully
    offline, but the map background will be blank without any connectivity
    at all.
    """

    def __init__(self, snapshot_dir: Path = SNAPSHOT_DIR) -> None:
        self.snapshot_dir = snapshot_dir

    def _load(self, name: str) -> dict[str, Any]:
        path = self.snapshot_dir / name
        if not path.exists():
            raise DataCommonsError(
                f"No snapshot at {path}. Run `make snapshot` while online first."
            )
        return json.loads(path.read_text())

    def _indicator_key_for_dcid(self, dcid: str) -> str | None:
        # snapshot files are named point_<indicator_key>.json; scan for a
        # match rather than requiring the caller to know the key.
        for path in self.snapshot_dir.glob("point_*.json"):
            payload = json.loads(path.read_text())
            if dcid in payload.get("data", {}):
                return path.stem.removeprefix("point_")
        return None

    def point(
        self, entities: Sequence[str], variables: Sequence[str]
    ) -> ObservationPayload:
        return self.point_within("Earth", "Country", variables)

    def series(
        self, entities: Sequence[str], variables: Sequence[str]
    ) -> ObservationPayload:
        raise DataCommonsError("series() has no offline snapshot; use point_within.")

    def point_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        data: dict[str, Any] = {}
        facets: dict[str, Any] = {}
        for dcid in variables:
            key = self._indicator_key_for_dcid(dcid)
            if key is None:
                raise EmptyResponseError(dcid, "offline snapshot")
            payload = self._load(f"point_{key}.json")
            data.update(payload["data"])
            facets.update(payload["facets"])
        return ObservationPayload(
            data=data, facets=facets, requested_variables=tuple(variables)
        )

    def series_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        raise DataCommonsError(
            "series_within() has no offline snapshot; use point_within."
        )

    def geojson(
        self, place_dcid: str = "Earth", place_type: str = "Country"
    ) -> dict[str, Any]:
        return self._load("geojson_earth_country.json")

    def place_names(self, dcids: Sequence[str], batch_size: int = 25) -> dict[str, str]:
        names = self._load("place_names.json")
        return {d: names[d] for d in dcids if d in names}

    def place_descendents(
        self, dcids: Sequence[str], descendent_type: str
    ) -> dict[str, Any]:
        raise DataCommonsError("place_descendents() has no offline snapshot.")

    def variable_info(self, dcids: Sequence[str]) -> dict[str, Any]:
        raise DataCommonsError("variable_info() has no offline snapshot.")

    def search_variables(self, query: str) -> list[dict[str, Any]]:
        raise DataCommonsError("search_variables() has no offline snapshot.")


def get_client() -> DataCommonsClient | OfflineDataCommonsClient:
    """Return the offline snapshot client if DATA_BEARS_OFFLINE=1, else live."""
    if os.environ.get("DATA_BEARS_OFFLINE") == "1":
        return OfflineDataCommonsClient()
    return DataCommonsClient()
