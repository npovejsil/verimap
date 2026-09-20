from __future__ import annotations

import pandas as pd

from recipe.catalog import Indicator
from recipe.datacommons_client import ObservationPayload
from recipe.validation import (
    check_ceiling_effect,
    check_empty_variable,
    check_mixed_dates,
    check_multi_facet,
    check_range_violation,
    check_unit_drift,
    cross_check_weighted_mean,
    drop_missing,
    log_filter_result,
)


def _indicator(**overrides) -> Indicator:
    base = dict(
        key="test_ind",
        dcid="undata/sdg/TEST",
        label="Test",
        topics=(),
        polarity="higher_is_better",
    )
    base.update(overrides)
    return Indicator(**base)


def test_multi_facet_flags_heterogeneous_provenance() -> None:
    payload = ObservationPayload(
        data={
            "Count_Person": {
                "country/A": {"facet": "f1", "date": "2024", "value": 1},
                "country/B": {"facet": "f2", "date": "2024", "value": 2},
            }
        },
        facets={"f1": {}, "f2": {}},
    )
    finding = check_multi_facet(payload, "Count_Person")
    assert finding is not None
    assert finding.code == "MULTI_FACET"


def test_multi_facet_silent_when_uniform() -> None:
    payload = ObservationPayload(
        data={
            "undata/unicef/DM_POP": {
                "country/A": {"facet": "f1", "date": "2025", "value": 1},
                "country/B": {"facet": "f1", "date": "2025", "value": 2},
            }
        },
        facets={"f1": {}},
    )
    assert check_multi_facet(payload, "undata/unicef/DM_POP") is None


def test_mixed_dates_flags_heterogeneous_dates() -> None:
    payload = ObservationPayload(
        data={
            "Count_Person": {
                "country/A": {"facet": "f1", "date": "1989"},
                "country/B": {"facet": "f1", "date": "2026"},
            }
        }
    )
    finding = check_mixed_dates(payload, "Count_Person")
    assert finding is not None
    assert finding.evidence["dates"] == ["1989", "2026"]


def test_unit_drift_flags_mismatch() -> None:
    indicator = _indicator(unit="Percent")
    payload = ObservationPayload(
        data={indicator.dcid: {"country/A": {"facet": "f1", "value": 50}}},
        facets={"f1": {"unit": "undata/UNIT_MEASURE-COUNT_PERSONS"}},
    )
    finding = check_unit_drift(payload, indicator)
    assert finding is not None
    assert finding.code == "UNIT_DRIFT"


def test_unit_drift_silent_when_matching() -> None:
    indicator = _indicator(unit="Percent")
    payload = ObservationPayload(
        data={indicator.dcid: {"country/A": {"facet": "f1", "value": 50}}},
        facets={"f1": {"unit": "Percent"}},
    )
    assert check_unit_drift(payload, indicator) is None


def test_range_violation_flags_out_of_bounds() -> None:
    indicator = _indicator(value_min=0, value_max=100)
    payload = ObservationPayload(data={indicator.dcid: {"country/A": {"value": 150}}})
    finding = check_range_violation(payload, indicator)
    assert finding is not None
    assert finding.code == "RANGE_VIOLATION"


def test_empty_variable_flags_zero_places() -> None:
    payload = ObservationPayload(data={"undata/sdg/X": {}})
    finding = check_empty_variable(payload, "undata/sdg/X")
    assert finding is not None
    assert finding.code == "EMPTY_VARIABLE"


def test_ceiling_effect_fires_above_threshold() -> None:
    # 140 of 217 saturated is the verified real case (~65%)
    values = pd.Series([100.0] * 140 + [50.0] * 77)
    finding = check_ceiling_effect(values, ceiling=100)
    assert finding is not None
    assert finding.evidence["n_saturated"] == 140


def test_ceiling_effect_silent_below_threshold() -> None:
    values = pd.Series([100.0] * 10 + [50.0] * 90)
    assert check_ceiling_effect(values, ceiling=100) is None


def test_drop_missing_reports_count_and_places() -> None:
    df = pd.DataFrame(
        {
            "place_dcid": ["country/A", "country/B", "country/C"],
            "value": [1.0, None, 3.0],
        }
    )
    result, report = drop_missing(df, ["value"], reason="no observation")
    assert report.n_before == 3
    assert report.n_after == 2
    assert report.n_dropped == 1
    assert report.dropped_places == ("country/B",)
    assert "no observation" in report.message()


def test_log_filter_result_reports_delta() -> None:
    df = pd.DataFrame({"x": [1, 2, 3]})
    filtered = df[df["x"] > 1]
    finding = log_filter_result(len(df), filtered, "drop x<=1")
    assert finding.evidence["n_before"] == 3
    assert finding.evidence["n_after"] == 2


def test_cross_check_within_tolerance() -> None:
    # Mirrors the verified real numbers: weighted mean 91.6, published 91.7
    long_df = pd.DataFrame(
        {"place_dcid": ["country/A", "country/B"], "value": [90.0, 100.0]}
    )
    pop_df = pd.DataFrame(
        {"place_dcid": ["country/A", "country/B"], "value": [9.0, 1.0]}
    )
    finding = cross_check_weighted_mean(long_df, pop_df, published_value=91.0)
    assert finding.level == "info"
    assert finding.code == "HEADLINE_CROSS_CHECK"


def test_cross_check_fails_outside_tolerance() -> None:
    long_df = pd.DataFrame({"place_dcid": ["country/A"], "value": [10.0]})
    pop_df = pd.DataFrame({"place_dcid": ["country/A"], "value": [1.0]})
    finding = cross_check_weighted_mean(long_df, pop_df, published_value=90.0)
    assert finding.level == "error"
