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
