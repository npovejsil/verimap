from __future__ import annotations

import pandas as pd

from views.bivariate import weighted_median


def test_weighted_median_equal_weights_matches_plain_median() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    weights = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
    assert weighted_median(values, weights) == 3.0


def test_weighted_median_shifts_toward_heavier_weight() -> None:
    # one huge-population country should pull the "median" toward its value
    values = pd.Series([10.0, 20.0, 90.0])
    weights = pd.Series([1.0, 1.0, 100.0])
    assert weighted_median(values, weights) == 90.0


def test_weighted_median_reproduces_verified_population_weighted_mean_case() -> None:
    # Mirrors the verified real case: 2 countries, weighted mean landed near
    # the higher-population country's value (91.6 vs published 91.7).
    values = pd.Series([90.0, 100.0])
    weights = pd.Series([9.0, 1.0])  # country A has 9x the population of B
    # weighted median of a 2-point series with 90% weight on the lower value
    # should land on the lower value
    assert weighted_median(values, weights) == 90.0


def test_missing_size_values_are_dropped_and_reported_not_passed_to_plotly() -> None:
    """Regression: a NaN marker size crashed the Gap analysis tab.

    Population is merged onto the comparison frame with a left join, so a
    country the denominator does not cover arrives as NaN. plotly rejects that
    outright ("Invalid elements include: [nan]") rather than skipping the
    point, which took down the whole tab. Surfaced live by comparing rural
    against urban electricity access, which cover 213 countries including some
    with no UNICEF population figure.
    """
    from recipe.validation import drop_missing

    df = pd.DataFrame(
        {
            "place_dcid": ["country/RWA", "country/XKX", "country/KEN"],
            "x": [10.0, 20.0, 30.0],
            "y": [1.0, 2.0, 3.0],
            "population": [1000.0, None, 3000.0],
        }
    )
    kept, report = drop_missing(df, ["population"], "no population figure")

    assert len(kept) == 2
    assert not kept["population"].isna().any()
    assert report.n_dropped == 1
    assert "country/XKX" in report.dropped_places
    assert "1" in report.message()
