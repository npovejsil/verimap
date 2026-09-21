from __future__ import annotations

import pandas as pd

from analytics.progress import compute_progress


def _series(
    place_dcid: str, values: list[float], start_year: int = 2000
) -> pd.DataFrame:
    years = [str(start_year + i) for i in range(len(values))]
    return pd.DataFrame(
        {"place_dcid": [place_dcid] * len(values), "date": years, "value": values}
    )


def test_higher_is_better_on_track() -> None:
    # +2/yr from 80 in 2023 reaches 100 in 2033 -- on track for a 2035 target.
    df = _series("A", [80.0 + 2 * i for i in range(24)], start_year=2000)
    results = compute_progress(
        df, polarity="higher_is_better", target_value=100.0, target_year=2035
    )
    assert len(results) == 1
    r = results[0]
    assert r.latest_value == 126.0
    assert r.gap is not None and r.gap < 0  # already past 100 by 2023
    assert r.projected_year == 2010.0  # actual year it first crossed 100
    assert r.on_track is True


def test_higher_is_better_off_track_when_slope_too_shallow() -> None:
    years = list(range(2000, 2024))
    df = _series("B", [50.0 + 0.1 * i for i in range(len(years))])
    results = compute_progress(
        df, polarity="higher_is_better", target_value=100.0, target_year=2030
    )
    r = results[0]
    assert r.gap is not None and r.gap > 0
    assert r.on_track is False


def test_lower_is_better_uses_sign_flip_correctly() -> None:
    # Energy intensity falling by 1/yr from 10 in 2000; target 5 by 2010.
    years = list(range(2000, 2024))
    df = _series("C", [10.0 - 1.0 * i for i in range(len(years))])
    results = compute_progress(
        df, polarity="lower_is_better", target_value=5.0, target_year=2010
    )
    r = results[0]
    # Falling 1/yr from 10 crosses 5 five years in (2005) -- on track for a 2010
    # target, even though the series keeps falling well past it by the last
    # observation (2023), which is why gap (measured at the latest point) is
    # negative while on_track (measured at first crossing) is still True.
    assert r.gap is not None and r.gap < 0
    assert r.projected_year == 2005.0
    assert r.on_track is True


def test_lower_is_better_off_track_when_value_is_rising() -> None:
    years = list(range(2000, 2024))
    df = _series("D", [10.0 + 0.5 * i for i in range(len(years))])
    results = compute_progress(
        df, polarity="lower_is_better", target_value=5.0, target_year=2030
    )
    r = results[0]
    assert r.projected_year == float("inf")
    assert r.on_track is False


def test_no_target_leaves_gap_and_projection_none() -> None:
    df = _series("E", [1.0, 2.0, 3.0, 4.0])
    results = compute_progress(
        df, polarity="higher_is_better", target_value=None, target_year=None
    )
    r = results[0]
    assert r.gap is None
    assert r.projected_year is None
    assert r.on_track is None
    assert r.slope is not None  # still fits a trend even with no target


def test_too_few_observations_still_returns_a_result_without_a_slope() -> None:
    df = _series("F", [1.0, 2.0])  # fit_trend needs 3+
    results = compute_progress(
        df, polarity="higher_is_better", target_value=100.0, target_year=2030
    )
    r = results[0]
    assert r.slope is None
    assert r.projected_year is None
    assert r.on_track is None
    assert r.gap is not None  # gap only needs the latest value, not a slope


def test_multiple_places_each_get_their_own_result() -> None:
    df = pd.concat(
        [_series("A", [10.0, 20.0, 30.0]), _series("B", [5.0, 5.0, 5.0])],
        ignore_index=True,
    )
    results = compute_progress(
        df, polarity="higher_is_better", target_value=100.0, target_year=2030
    )
    assert {r.place_dcid for r in results} == {"A", "B"}
