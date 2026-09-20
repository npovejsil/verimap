from __future__ import annotations

import pandas as pd

from analytics.trends import (
    fit_trend,
    fit_trends_excluding_saturated,
    is_saturated,
    years_to_target,
)


def test_is_saturated_respects_tolerance() -> None:
    assert is_saturated(99.6, ceiling=100, tolerance=0.5)
    assert not is_saturated(99.0, ceiling=100, tolerance=0.5)


def test_fit_trend_returns_none_with_too_few_observations() -> None:
    df = pd.DataFrame(
        {"place_dcid": ["A", "A"], "date": ["2020", "2021"], "value": [1.0, 2.0]}
    )
    assert fit_trend(df) is None


def test_fit_trend_recovers_a_clear_linear_slope() -> None:
    years = list(range(2000, 2025))
    df = pd.DataFrame(
        {
            "place_dcid": ["A"] * len(years),
            "date": [str(y) for y in years],
            "value": [10 + 2 * (y - 2000) for y in years],
        }
    )
    result = fit_trend(df)
    assert result is not None
    assert result.n_obs == 25
    assert abs(result.slope - 2.0) < 0.01
    assert result.slope_ci_low < 2.0 < result.slope_ci_high


def test_fit_trends_excluding_saturated_separates_ceiling_places() -> None:
    years = [str(y) for y in range(2000, 2025)]
    saturated = pd.DataFrame(
        {
            "place_dcid": ["SAT"] * len(years),
            "date": years,
            "value": [100.0] * len(years),
        }
    )
    improving = pd.DataFrame(
        {
            "place_dcid": ["IMP"] * len(years),
            "date": years,
            "value": [10 + i for i in range(len(years))],
        }
    )
    long_df = pd.concat([saturated, improving], ignore_index=True)

    results, saturated_places = fit_trends_excluding_saturated(long_df, ceiling=100)

    assert saturated_places == ["SAT"]
    assert len(results) == 1
    assert results[0].place_dcid == "IMP"


def test_years_to_target_positive_slope() -> None:
    years = years_to_target(
        latest_value=80.0, latest_year=2023, slope=2.0, target=100.0
    )
    assert abs(years - 10.0) < 0.01


def test_years_to_target_nonpositive_slope_is_infinite() -> None:
    assert years_to_target(latest_value=80.0, latest_year=2023, slope=0.0) == float(
        "inf"
    )
    assert years_to_target(latest_value=80.0, latest_year=2023, slope=-1.0) == float(
        "inf"
    )


def test_years_to_target_already_at_target() -> None:
    assert years_to_target(latest_value=100.0, latest_year=2023, slope=1.0) == 0.0


def test_years_to_target_caps_far_future_at_infinity() -> None:
    # An extremely slow slope pushes the projected year past 2100
    years = years_to_target(
        latest_value=1.0, latest_year=2023, slope=0.001, target=100.0
    )
    assert years == float("inf")
