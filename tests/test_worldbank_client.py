"""Pure tests for the World Bank adapter -- no network, inline fixtures.

The numbers here are from live API responses recorded on 2026-09-20: Rwanda's
transmission and distribution losses were 18.27% in 2023, and /v2/country
returns 295 rows of which 217 are real countries and 78 are aggregates.
"""

from __future__ import annotations

import pytest

from recipe.catalog import Indicator
from recipe.datacommons_client import EmptyResponseError
from recipe.frames import point_within_to_long
from recipe.worldbank_client import (
    is_real_country,
    rows_to_point_payload,
    rows_to_series_payload,
    to_place_dcid,
    worldbank_code,
)

LOSSES = Indicator(
    key="wb_transmission_losses",
    dcid="worldbank/EG.ELC.LOSS.ZS",
    label="Transmission & distribution losses",
    topics=("energy_delivery",),
    polarity="lower_is_better",
    source="world_bank",
    unit="worldbank/PCT_OUTPUT",
    unit_display="% of output",
)


def _row(iso3: str, date: str, value: float | None) -> dict:
    return {
        "indicator": {"id": "EG.ELC.LOSS.ZS", "value": "..."},
        "country": {"id": iso3[:2], "value": iso3},
        "countryiso3code": iso3,
        "date": date,
        "value": value,
        "unit": "",
        "obs_status": "",
        "decimal": 0,
    }


def test_aggregates_are_not_real_countries() -> None:
    assert is_real_country({"id": "RWA", "region": {"id": "SSF"}})
    # Regional and income aggregates carry region id "NA".
    assert not is_real_country({"id": "WLD", "region": {"id": "NA"}})
    assert not is_real_country({"id": "AFE", "region": {"id": "NA"}})


def test_iso3_maps_to_place_dcid() -> None:
    assert to_place_dcid("RWA") == "country/RWA"
    assert to_place_dcid("rwa") == "country/RWA"


def test_malformed_country_codes_are_rejected_not_guessed() -> None:
    # The geo join keys on exactly `country/XXX`; a bad id must drop out rather
    # than produce a dcid that silently matches nothing.
    for bad in ("", None, "RW", "RWAN", "R1A"):
        assert to_place_dcid(bad) is None


def test_worldbank_code_strips_the_prefix() -> None:
    assert worldbank_code("worldbank/EG.ELC.LOSS.ZS") == "EG.ELC.LOSS.ZS"
    assert worldbank_code("EG.ELC.LOSS.ZS") == "EG.ELC.LOSS.ZS"


def test_point_payload_takes_the_latest_non_null_year() -> None:
    rows = [
        _row("RWA", "2025", None),  # API pads forward with nulls
        _row("RWA", "2024", None),
        _row("RWA", "2023", 18.27),
        _row("RWA", "2022", 19.4),
    ]
    payload = rows_to_point_payload(rows, LOSSES)
    obs = payload.variable(LOSSES.dcid)["country/RWA"]
    assert obs["date"] == "2023"
    assert obs["value"] == pytest.approx(18.27)


def test_aggregates_are_dropped_when_an_allow_list_is_given() -> None:
    rows = [_row("RWA", "2023", 18.27), _row("AFE", "2023", 25.76)]
    payload = rows_to_point_payload(rows, LOSSES, allowed={"country/RWA"})
    places = payload.variable(LOSSES.dcid)
    assert set(places) == {"country/RWA"}


def test_all_null_series_raises_rather_than_returning_empty() -> None:
    # Mirrors the Data Commons semantic: no data is an error, not a silent {}.
    rows = [_row("RWA", "2025", None), _row("RWA", "2024", None)]
    with pytest.raises(EmptyResponseError):
        rows_to_point_payload(rows, LOSSES)


def test_series_payload_is_sorted_and_null_free() -> None:
    rows = [
        _row("RWA", "2022", 19.4),
        _row("RWA", "2024", None),
        _row("RWA", "2020", 21.1),
        _row("RWA", "2023", 18.27),
    ]
    payload = rows_to_series_payload(rows, LOSSES)
    series = payload.variable(LOSSES.dcid)["country/RWA"]["series"]
    assert [o["date"] for o in series] == ["2020", "2022", "2023"]


def test_payload_round_trips_through_the_shared_frame_converter() -> None:
    # The whole point of emitting ObservationPayload: recipe/frames.py reads
    # camelCase facet keys straight off the map and must need no changes.
    payload = rows_to_point_payload([_row("RWA", "2023", 18.27)], LOSSES)
    df = point_within_to_long(payload, LOSSES)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["place_dcid"] == "country/RWA"
    assert row["value"] == pytest.approx(18.27)
    assert row["unit"] == "worldbank/PCT_OUTPUT"
    assert row["unit_display"] == "% of output"
    assert row["provenance_id"] == "worldBank/WDI"
    assert row["provenance_url"].endswith("EG.ELC.LOSS.ZS")
