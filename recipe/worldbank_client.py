"""HTTP client for the World Bank Open Data API.

Data Commons already republishes a good deal of World Bank data, so this client
exists for the indicators it does NOT carry -- verified absent from the UN
instance: transmission and distribution losses (EG.ELC.LOSS.ZS), firm outage
rates (IC.ELC.OUTG.ZS), electricity consumption per capita (EG.USE.ELEC.KH.PC)
and renewable electricity output (EG.ELC.RNEW.ZS). It is a coverage
supplement, not an independent second opinion: where both pipes carry the same
series they agree, because they are the same underlying dataset.

The client returns `ObservationPayload` -- the same type the Data Commons
client returns -- so every downstream consumer (frames, validation, keymatch,
attribution) works on World Bank data with no changes at all.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from recipe.datacommons_client import EmptyResponseError, ObservationPayload

BASE_URL = "https://api.worldbank.org/v2"

# The World Bank marks aggregates (WLD, EUU, AFE, ...) with region id "NA".
# Verified live: /v2/country returns 295 rows, 217 real countries and 78
# aggregates. Plotting an aggregate as if it were a country would double-count.
_AGGREGATE_REGION_ID = "NA"

# The API reports unit="" on every observation, so units come from the catalog.
# These are the family members declared in catalog/units.yml.
UNIT_PERCENT_OF_OUTPUT = "worldbank/PCT_OUTPUT"
UNIT_PERCENT_OF_FIRMS = "worldbank/PCT_FIRMS"
UNIT_KWH_PER_CAPITA = "worldbank/KWH_PER_CAPITA"


class WorldBankError(Exception):
    """Base error for all World Bank client failures."""


def is_real_country(row: dict[str, Any]) -> bool:
    """True for an actual country, False for a regional/income aggregate."""
    region = row.get("region") or {}
    return region.get("id") != _AGGREGATE_REGION_ID


def to_place_dcid(iso3: str | None) -> str | None:
    """Map a World Bank ISO3 code onto the `country/XXX` dcid used everywhere else.

    Returns None for anything that is not three ASCII letters. Some rows carry
    an empty `countryiso3code`, and the geo join in recipe/geography.py keys on
    exactly this format, so a malformed id must be dropped rather than guessed.
    """
    if not iso3 or len(iso3) != 3 or not iso3.isalpha():
        return None
    return f"country/{iso3.upper()}"


def _facet_for(indicator) -> tuple[str, dict[str, Any]]:  # noqa: ANN001 - Indicator
    """Build the single synthesized facet for a World Bank indicator.

    Keys are camelCase because recipe/frames.py reads them straight off the
    facet map (`provenanceId`, `provenanceUrl`, `unitDisplayName`), exactly as
    Data Commons spells them.
    """
    code = worldbank_code(indicator.dcid)
    facet_id = f"worldbank/{code}"
    return facet_id, {
        "observationPeriod": "P1Y",
        "provenanceId": "worldBank/WDI",
        "provenanceUrl": f"https://data.worldbank.org/indicator/{code}",
        "unit": indicator.unit,
        "unitDisplayName": indicator.unit_display,
    }


def worldbank_code(dcid: str) -> str:
    """`worldbank/EG.ELC.LOSS.ZS` -> `EG.ELC.LOSS.ZS`."""
    return dcid.split("/", 1)[1] if "/" in dcid else dcid


def _usable_rows(
    rows: Iterable[dict[str, Any]], allowed: set[str] | None
) -> list[tuple[str, str, float]]:
    """Filter raw observation rows to (place_dcid, date, value) triples.

    Drops null values (the API pads every series out to the current year with
    nulls), malformed country codes, and aggregates when an allow-list of real
    countries is supplied.
    """
    out: list[tuple[str, str, float]] = []
    for row in rows:
        if row.get("value") is None:
            continue
        place = to_place_dcid(row.get("countryiso3code"))
        if place is None:
            continue
        if allowed is not None and place not in allowed:
            continue
        out.append((place, str(row["date"]), float(row["value"])))
    return out


def rows_to_point_payload(
    rows: Iterable[dict[str, Any]],
    indicator,  # noqa: ANN001 - Indicator, avoids an import cycle
    allowed: set[str] | None = None,
) -> ObservationPayload:
    """Latest non-null observation per country, in Data Commons point shape."""
    facet_id, facet = _facet_for(indicator)
    latest: dict[str, tuple[str, float]] = {}
    for place, date, value in _usable_rows(rows, allowed):
        current = latest.get(place)
        if current is None or date > current[0]:
            latest[place] = (date, value)

    if not latest:
        raise EmptyResponseError(indicator.dcid, "/country/all/indicator")

    data = {
        indicator.dcid: {
            place: {"date": date, "facet": facet_id, "value": value}
            for place, (date, value) in latest.items()
        }
    }
    return ObservationPayload(
        data=data, facets={facet_id: facet}, requested_variables=(indicator.dcid,)
    )


def rows_to_series_payload(
    rows: Iterable[dict[str, Any]],
    indicator,  # noqa: ANN001 - Indicator, avoids an import cycle
    allowed: set[str] | None = None,
) -> ObservationPayload:
    """Full time series per country, in Data Commons series shape."""
    facet_id, facet = _facet_for(indicator)
    by_place: dict[str, list[dict[str, Any]]] = {}
    for place, date, value in _usable_rows(rows, allowed):
        by_place.setdefault(place, []).append({"date": date, "value": value})

    if not by_place:
        raise EmptyResponseError(indicator.dcid, "/country/all/indicator")

    data = {
        indicator.dcid: {
            place: {
                "facet": facet_id,
                "series": sorted(obs, key=lambda o: o["date"]),
            }
            for place, obs in by_place.items()
        }
    }
    return ObservationPayload(
        data=data, facets={facet_id: facet}, requested_variables=(indicator.dcid,)
    )


class WorldBankClient:
    """Mirrors the subset of DataCommonsClient's surface the app actually calls."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = 60,
        retries: int = 3,
        session: requests.Session | None = None,
        catalog=None,  # noqa: ANN001 - Catalog, avoids an import cycle
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or self._build_session(retries)
        self._countries: dict[str, str] | None = None
        self._catalog = catalog

    @staticmethod
    def _build_session(retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            status_forcelist=[403, 429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, path: str, params: Sequence[tuple[str, str]]) -> list[Any]:
        """GET and unwrap the API's `[meta, rows]` envelope.

        The World Bank signals errors inside a 200 response body as a dict with
        a "message" key rather than the usual two-element array, so the shape
        has to be checked rather than assumed.
        """
        resp = self.session.get(
            f"{self.base_url}{path}",
            params=list(params) + [("format", "json")],
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, list) or len(body) < 2:
            raise WorldBankError(f"Unexpected response from {path}: {body!r:.200}")
        return body[1] or []

    def countries(self) -> dict[str, str]:
        """{place_dcid: name} for the 217 real countries, aggregates excluded."""
        if self._countries is None:
            rows = self._get("/country", [("per_page", "400")])
            out: dict[str, str] = {}
            for row in rows:
                if not is_real_country(row):
                    continue
                place = to_place_dcid(row.get("id"))
                if place:
                    out[place] = row.get("name", "")
            self._countries = out
        return self._countries

    def _fetch(self, code: str, params: Sequence[tuple[str, str]]) -> list[Any]:
        return self._get(f"/country/all/indicator/{code}", params)

    def _indicator_for(self, dcid: str):  # noqa: ANN001 - Indicator
        """Resolve a dcid to its catalog Indicator, for units and labels.

        The API reports unit="" on every observation, so the unit has to come
        from the catalog. Holding the catalog here rather than taking it as a
        method argument is what keeps point_within/series_within
        signature-compatible with DataCommonsClient, so app.py can call either
        client without knowing which one it has.
        """
        if self._catalog is None:
            from recipe.catalog import load_catalog

            self._catalog = load_catalog()
        for indicator in self._catalog.indicators.values():
            if indicator.dcid == dcid:
                return indicator
        raise WorldBankError(
            f"No catalog Indicator for dcid {dcid!r}; units would be lost."
        )

    def _combine(
        self, variables: Sequence[str], most_recent: bool
    ) -> ObservationPayload:
        allowed = set(self.countries())
        convert = rows_to_point_payload if most_recent else rows_to_series_payload
        data: dict[str, Any] = {}
        facets: dict[str, Any] = {}
        for dcid in variables:
            indicator = self._indicator_for(dcid)
            params = [("per_page", "25000")]
            if most_recent:
                params.append(("mrnev", "1"))
            rows = self._fetch(worldbank_code(dcid), params)
            payload = convert(rows, indicator, allowed)
            data.update(payload.data)
            facets.update(payload.facets)
        return ObservationPayload(
            data=data, facets=facets, requested_variables=tuple(variables)
        )

    def point_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        return self._combine(variables, most_recent=True)

    def series_within(
        self, parent: str, child_type: str, variables: Sequence[str]
    ) -> ObservationPayload:
        return self._combine(variables, most_recent=False)

    def place_names(self, dcids: Sequence[str], batch_size: int = 25) -> dict[str, str]:
        known = self.countries()
        return {d: known[d] for d in dcids if d in known}

    def indicator_info(self, code: str) -> dict[str, Any]:
        """Metadata for one indicator, used by scripts/discover_indicators.py."""
        rows = self._get(f"/indicator/{code}", [])
        if not rows:
            raise WorldBankError(f"No metadata for indicator {code}")
        return rows[0]
