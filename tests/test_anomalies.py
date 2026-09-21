from __future__ import annotations

import pandas as pd

from analytics.anomalies import (
    AnomalyScales,
    compute_scales,
    detect_anomalies,
    detect_interpolated,
    detect_peer_outliers,
    detect_reversals,
    detect_spikes,
    robust_scale,
    year_over_year,
)
from analytics.trends import TrendResult


def _series(place: str, values: list[float], start_year: int = 2000) -> pd.DataFrame:
    years = [str(start_year + i) for i in range(len(values))]
    return pd.DataFrame(
        {"place_dcid": [place] * len(values), "date": years, "value": values}
    )


def _trend(place: str, slope: float, ci_low: float, ci_high: float) -> TrendResult:
    return TrendResult(
        place_dcid=place,
        n_obs=25,
        slope=slope,
        slope_ci_low=ci_low,
        slope_ci_high=ci_high,
        intercept=0.0,
        is_saturated=False,
    )


def test_robust_scale_is_zero_for_flat_series() -> None:
    assert robust_scale(pd.Series([5.0, 5.0, 5.0, 5.0])) == 0.0


def test_robust_scale_empty_is_zero() -> None:
    assert robust_scale(pd.Series([], dtype=float)) == 0.0


def test_year_over_year_uses_prior_observed_year_not_calendar_year() -> None:
    # A country with a gap year: 2000, 2001, 2003 -- the 2003 row's "prior"
    # must be 2001, and gap_years must say 2, not fabricate a 2002 value.
    df = pd.DataFrame(
        {
            "place_dcid": ["A", "A", "A"],
            "date": ["2000", "2001", "2003"],
            "value": [10.0, 12.0, 20.0],
        }
    )
    yoy = year_over_year(df)
    assert len(yoy) == 2
    last = yoy[yoy["date"] == "2003"].iloc[0]
    assert last["prior_date"] == "2001"
    assert last["gap_years"] == 2
    assert last["change"] == 8.0


def test_year_over_year_empty_input() -> None:
    df = pd.DataFrame({"place_dcid": [], "date": [], "value": []})
    yoy = year_over_year(df)
    assert yoy.empty
    assert list(yoy.columns) == [
        "place_dcid",
        "date",
        "value",
        "prior_date",
        "prior_value",
        "change",
        "gap_years",
    ]


def test_compute_scales_none_with_too_few_rows() -> None:
    df = _series("A", [10.0, 12.0])  # exactly one year-over-year row
    yoy = year_over_year(df)
    assert len(yoy) == 1
    assert compute_scales(yoy) is None


def test_compute_scales_reflects_indicator_own_distribution() -> None:
    # Mirrors the verified real spread: renewable capacity's p90 |change| is
    # ~37x water access's. The gate must come from THIS panel, not a constant.
    small_changes = pd.concat(
        [_series(f"P{i}", [1.0, 1.1, 1.2, 1.05]) for i in range(15)]
    )
    big_changes = pd.concat(
        [_series(f"P{i}", [10.0, 60.0, 40.0, 90.0]) for i in range(15)]
    )

    small_scales = compute_scales(year_over_year(small_changes))
    big_scales = compute_scales(year_over_year(big_changes))
    assert small_scales.magnitude_gate < big_scales.magnitude_gate


# ---------------------------------------------------------------------------
# spike
# ---------------------------------------------------------------------------


def test_spike_fires_on_one_injected_jump() -> None:
    # 15 flat-ish countries as peers/pool, one with an obvious single-year
    # jump. 7 values -> 6 year-over-year rows each, clearing min_obs=6.
    frames = [
        _series(f"FLAT{i}", [50.0, 50.5, 49.8, 50.2, 50.1, 49.9, 50.3])
        for i in range(15)
    ]
    jumpy = _series("JUMPY", [50.0, 50.5, 90.0, 50.2, 50.1, 49.9, 50.3])
    long_df = pd.concat(frames + [jumpy], ignore_index=True)

    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    spikes = detect_spikes(yoy, scales)

    assert any(a.place_dcid == "JUMPY" for a in spikes)


def test_spike_does_not_fire_on_pure_linear_series() -> None:
    # A perfectly smooth line has zero interesting year-over-year variation
    # once pooled against itself -- no spike should ever fire here.
    frames = [_series(f"LIN{i}", [10 + j for j in range(10)]) for i in range(15)]
    long_df = pd.concat(frames, ignore_index=True)
    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    assert detect_spikes(yoy, scales) == []


def test_spike_regression_zero_mad_does_not_divide_by_zero() -> None:
    """Verified real bug: 79 of 217 countries have a year-over-year MAD of
    exactly 0 (flat/step-function reporting). Without a pooled floor, this
    produces a divide-by-zero and flags every one of them. A step-function
    country with a single big jump should not explode into a spurious spike
    on every other flat row, and must not raise.
    """
    frames = [_series(f"FLAT{i}", [50.0] * 6) for i in range(15)]  # MAD == 0 for all
    step = _series("STEP", [50.0, 50.0, 50.0, 90.0, 90.0, 90.0])  # MAD == 0 too
    long_df = pd.concat(frames + [step], ignore_index=True)

    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    # must not raise, and the flat countries (real MAD 0, no actual movement
    # once pooled) must not all be flagged
    spikes = detect_spikes(yoy, scales)
    flat_flagged = [a for a in spikes if a.place_dcid.startswith("FLAT")]
    assert flat_flagged == []


def test_spike_regression_magnitude_gate_suppresses_tiny_wobble() -> None:
    """Verified real case: a near-perfectly linear series (Jordan, water
    access, ~+1.8pp/yr) has such a tiny per-country MAD that a -0.07pp
    wobble scores as a 9-sigma spike without a magnitude floor. The
    magnitude gate (must also clear the panel's own p90 |change|) must
    suppress a wobble this small when every other country moves by a lot
    more in a typical year.
    """
    # 15 peers with big, noisy typical swings (sets a large p90 gate)...
    noisy_peers = [
        _series(f"NOISY{i}", [10.0, 40.0, 15.0, 55.0, 20.0, 60.0]) for i in range(15)
    ]
    # ...and one near-perfect line with a microscopic wobble.
    smooth = _series("JORDANLIKE", [55.586, 55.516, 57.113, 58.9, 60.7, 62.5])
    long_df = pd.concat(noisy_peers + [smooth], ignore_index=True)

    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    spikes = detect_spikes(yoy, scales)
    assert all(a.place_dcid != "JORDANLIKE" for a in spikes)


def test_spike_respects_min_obs() -> None:
    # A country with fewer than min_obs year-over-year rows never qualifies,
    # even with an enormous jump.
    frames = [
        _series(f"FLAT{i}", [50.0, 50.5, 49.8, 50.2, 50.1, 49.9]) for i in range(15)
    ]
    short = pd.DataFrame(
        {
            "place_dcid": ["SHORT", "SHORT"],
            "date": ["2000", "2001"],
            "value": [10.0, 90.0],
        }
    )
    long_df = pd.concat(frames + [short], ignore_index=True)
    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    spikes = detect_spikes(yoy, scales, min_obs=6)
    assert all(a.place_dcid != "SHORT" for a in spikes)


def test_spike_top_n_caps_and_dedupes_one_row_per_place() -> None:
    frames = [
        _series(f"FLAT{i}", [50.0, 50.5, 49.8, 50.2, 50.1, 49.9]) for i in range(10)
    ]
    jumpy = [
        _series(f"JUMPY{i}", [50.0, 50.0 + 40 + i, 50.0, 50.2, 50.1, 49.9])
        for i in range(5)
    ]
    long_df = pd.concat(frames + jumpy, ignore_index=True)
    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    spikes = detect_spikes(yoy, scales, top_n=3)
    assert len(spikes) <= 3
    assert len({a.place_dcid for a in spikes}) == len(spikes)


# ---------------------------------------------------------------------------
# peer_outlier
# ---------------------------------------------------------------------------


def test_peer_outlier_fires_when_one_country_diverges_from_the_pack() -> None:
    # Small natural variance across peers (2.0 +/- a fractional jitter) so
    # the pooled/year scale isn't literally zero -- a real "diverges from
    # the pack" case, not a fully-degenerate one.
    frames = [
        _series(f"PEER{i}", [10.0, 12.0 + 0.1 * (i % 5), 14.0, 16.0]) for i in range(20)
    ]
    odd = _series("ODD", [10.0, 60.0, 14.0, 16.0])
    long_df = pd.concat(frames + [odd], ignore_index=True)
    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    outliers = detect_peer_outliers(yoy, scales, min_peers=10)
    assert any(a.place_dcid == "ODD" for a in outliers)


def test_peer_outlier_suppressed_below_min_peers() -> None:
    # Only 5 countries report this year -- below min_peers=10, so even a
    # wild divergence must not fire.
    frames = [_series(f"PEER{i}", [10.0, 12.0, 14.0, 16.0]) for i in range(4)]
    odd = _series("ODD", [10.0, 60.0, 14.0, 16.0])
    long_df = pd.concat(frames + [odd], ignore_index=True)
    yoy = year_over_year(long_df)
    scales = compute_scales(yoy)
    outliers = detect_peer_outliers(yoy, scales, min_peers=10)
    assert outliers == []


# ---------------------------------------------------------------------------
# reversal
# ---------------------------------------------------------------------------


def test_reversal_fires_on_wrong_way_slope_with_ci_excluding_zero() -> None:
    trends = [_trend("BAD", slope=-1.25, ci_low=-1.6, ci_high=-0.9)]
    reversals = detect_reversals(trends, polarity="higher_is_better")
    assert len(reversals) == 1
    assert reversals[0].place_dcid == "BAD"
    assert reversals[0].kind == "reversal"


def test_reversal_does_not_fire_when_ci_straddles_zero() -> None:
    # Slope is negative, but the confidence interval includes zero -- not
    # statistically real, must not be flagged as a reversal.
    trends = [_trend("NOISY", slope=-0.1, ci_low=-0.5, ci_high=0.3)]
    assert detect_reversals(trends, polarity="higher_is_better") == []


def test_reversal_direction_flips_for_lower_is_better() -> None:
    # For a lower_is_better indicator (e.g. energy intensity), "wrong way"
    # means rising, not falling.
    trends = [_trend("RISING", slope=0.8, ci_low=0.3, ci_high=1.3)]
    reversals = detect_reversals(trends, polarity="lower_is_better")
    assert len(reversals) == 1
    assert reversals[0].place_dcid == "RISING"

    # the same slope is fine (not a reversal) for higher_is_better
    assert detect_reversals(trends, polarity="higher_is_better") == []


def test_reversal_neutral_polarity_always_empty() -> None:
    trends = [_trend("X", slope=-5.0, ci_low=-6.0, ci_high=-4.0)]
    assert detect_reversals(trends, polarity="neutral") == []


def test_reversal_top_n_caps_by_magnitude() -> None:
    trends = [
        _trend("SMALL", slope=-0.1, ci_low=-0.2, ci_high=-0.05),
        _trend("MEDIUM", slope=-1.0, ci_low=-1.5, ci_high=-0.5),
        _trend("BIG", slope=-5.0, ci_low=-6.0, ci_high=-4.0),
    ]
    reversals = detect_reversals(trends, polarity="higher_is_better", top_n=2)
    assert [a.place_dcid for a in reversals] == ["BIG", "MEDIUM"]


# ---------------------------------------------------------------------------
# detect_anomalies (end-to-end, degenerate inputs)
# ---------------------------------------------------------------------------


def test_detect_anomalies_empty_dataframe() -> None:
    df = pd.DataFrame({"place_dcid": [], "date": [], "value": []})
    assert detect_anomalies(df, polarity="higher_is_better") == []


def test_detect_anomalies_single_row() -> None:
    df = pd.DataFrame({"place_dcid": ["A"], "date": ["2020"], "value": [10.0]})
    assert detect_anomalies(df, polarity="higher_is_better") == []


def test_detect_anomalies_two_years_only() -> None:
    df = _series("A", [10.0, 90.0])
    # Not enough year-over-year rows for a meaningful pooled scale (only 1),
    # and not enough observations for a trend fit -- should not raise.
    assert detect_anomalies(df, polarity="higher_is_better") == []


def test_detect_anomalies_all_nan_values() -> None:
    df = pd.DataFrame(
        {
            "place_dcid": ["A", "A", "A"],
            "date": ["2020", "2021", "2022"],
            "value": [None, None, None],
        }
    )
    assert detect_anomalies(df, polarity="higher_is_better") == []


def test_detect_anomalies_neutral_polarity_skips_reversal_but_keeps_others() -> None:
    frames = [
        _series(f"FLAT{i}", [50.0, 50.5, 49.8, 50.2, 50.1, 49.9, 50.3])
        for i in range(15)
    ]
    jumpy = _series("JUMPY", [50.0, 50.5, 90.0, 50.2, 50.1, 49.9, 50.3])
    long_df = pd.concat(frames + [jumpy], ignore_index=True)

    anomalies = detect_anomalies(long_df, polarity="neutral")
    assert all(a.kind != "reversal" for a in anomalies)
    assert any(a.kind == "spike" for a in anomalies)


def test_spike_does_not_imply_reversal() -> None:
    # A country with one big single-year jump but an otherwise flat/zero
    # long-run slope must not also register as a reversal -- the two
    # detectors answer different questions (one year vs. the whole trend)
    # even though a spike can independently double as a peer_outlier (both
    # look at the same single-year change from different angles).
    frames = [
        _series(f"FLAT{i}", [50.0, 50.5, 49.8, 50.2, 50.1, 49.9, 50.3])
        for i in range(15)
    ]
    jumpy = _series("JUMPY", [50.0, 50.5, 90.0, 50.2, 50.1, 49.9, 50.3])
    long_df = pd.concat(frames + [jumpy], ignore_index=True)

    anomalies = detect_anomalies(long_df, polarity="higher_is_better")
    jumpy_kinds = {a.kind for a in anomalies if a.place_dcid == "JUMPY"}
    assert "spike" in jumpy_kinds
    assert "reversal" not in jumpy_kinds


def _prepared(frames: list[pd.DataFrame]):
    long_df = pd.concat(frames, ignore_index=True)
    yoy = year_over_year(long_df)
    return yoy, compute_scales(yoy)


def test_flags_a_straight_line_between_two_anchors() -> None:
    # A measured 2000 and a measured 2006, with the five intervening years
    # drawn as a straight line: every step is exactly 2.0.
    straight = _series("A", [40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0])
    # Peers that actually wobble, so the pooled scale is not degenerate.
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6, 44.1])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0, 76.3])

    yoy, scales = _prepared([straight, noisy_b, noisy_c])
    found = detect_interpolated(yoy, scales)

    assert [a.place_dcid for a in found] == ["A"]
    a = found[0]
    assert a.kind == "interpolated"
    assert a.prior_date == "2000"
    assert a.date == "2006"
    assert a.score == 6.0  # six identical steps
    assert "identical steps" in a.detail


def test_does_not_flag_a_saturated_series() -> None:
    # A country pinned at 100% produces a long run of identical ZERO steps.
    # That is the opposite of this finding and must not fire — the min_step
    # floor is what keeps it out.
    saturated = _series("A", [100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0])

    yoy, scales = _prepared([saturated, noisy_b, noisy_c])
    assert detect_interpolated(yoy, scales) == []


def test_does_not_flag_a_series_that_wobbles() -> None:
    wobbly = _series("A", [40.0, 43.2, 44.1, 47.9, 49.0, 53.4])
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0])

    yoy, scales = _prepared([wobbly, noisy_b, noisy_c])
    assert [a.place_dcid for a in detect_interpolated(yoy, scales)] == []


def test_run_shorter_than_min_run_does_not_fire() -> None:
    # Only two identical steps (2000->2002), then the series breaks pattern.
    short = _series("A", [40.0, 42.0, 44.0, 51.3, 52.1, 58.9])
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0])

    yoy, scales = _prepared([short, noisy_b, noisy_c])
    assert [a.place_dcid for a in detect_interpolated(yoy, scales)] == []


def test_a_reporting_gap_breaks_the_run() -> None:
    # Steps of 2.0 either side of a missing 2003. The 2004 change spans two
    # years, so it is not comparable to a single-year step and must not
    # extend the run.
    df = pd.DataFrame(
        {
            "place_dcid": ["A"] * 5,
            "date": ["2000", "2001", "2002", "2004", "2005"],
            "value": [40.0, 42.0, 44.0, 48.0, 50.0],
        }
    )
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0])

    yoy, scales = _prepared([df, noisy_b, noisy_c])
    assert [a.place_dcid for a in detect_interpolated(yoy, scales)] == []


def test_degenerate_pooled_scale_returns_empty_not_everything() -> None:
    # Every country perfectly flat: pooled_scale is 0, so there is nothing to
    # calibrate a tolerance against. Must return [], not flag all of them.
    flat_a = _series("A", [10.0, 10.0, 10.0, 10.0, 10.0])
    flat_b = _series("B", [20.0, 20.0, 20.0, 20.0, 20.0])

    yoy, scales = _prepared([flat_a, flat_b])
    assert scales is not None
    assert detect_interpolated(yoy, scales) == []


def test_empty_input_returns_empty() -> None:
    empty = year_over_year(pd.DataFrame(columns=["place_dcid", "date", "value"]))
    scales = AnomalyScales(pooled_scale=1.0, magnitude_gate=1.0, n_yoy_rows=0)
    assert detect_interpolated(empty, scales) == []


def test_detect_anomalies_includes_the_new_kind() -> None:
    straight = _series("A", [40.0, 42.0, 44.0, 46.0, 48.0, 50.0, 52.0])
    noisy_b = _series("B", [30.0, 33.1, 34.4, 38.0, 39.2, 43.6, 44.1])
    noisy_c = _series("C", [61.0, 62.8, 66.9, 67.4, 71.2, 72.0, 76.3])
    long_df = pd.concat([straight, noisy_b, noisy_c], ignore_index=True)

    kinds = {a.kind for a in detect_anomalies(long_df, polarity="higher_is_better")}
    assert "interpolated" in kinds
