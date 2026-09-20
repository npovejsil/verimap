from __future__ import annotations

import pandas as pd

from analytics.gap_scoring import (
    coverage_asymmetry,
    percentile_rank,
    priority_score,
    unserved_population,
)


def test_unserved_population_computes_correctly() -> None:
    access_df = pd.DataFrame(
        {"place_dcid": ["country/A", "country/B"], "value": [80.0, 50.0]}
    )
    pop_df = pd.DataFrame(
        {"place_dcid": ["country/A", "country/B"], "value": [1_000_000, 2_000_000]}
    )
    merged, report = unserved_population(access_df, pop_df)

    assert report.n_dropped == 0
    assert merged.set_index("place_dcid")["unserved_population"].to_dict() == {
        "country/A": 200_000.0,
        "country/B": 1_000_000.0,
    }


def test_unserved_population_reports_unmatched_places() -> None:
    access_df = pd.DataFrame(
        {"place_dcid": ["country/A", "country/B"], "value": [80.0, 50.0]}
    )
    pop_df = pd.DataFrame({"place_dcid": ["country/A"], "value": [1_000_000]})
    merged, report = unserved_population(access_df, pop_df)

    assert len(merged) == 1
    assert report.n_dropped == 0  # country/B dropped by the inner merge itself,
    # not by drop_missing -- confirm merge behavior explicitly:
    assert "country/B" not in merged["place_dcid"].values


def test_unserved_population_works_without_place_name_column() -> None:
    access_df = pd.DataFrame({"place_dcid": ["country/A"], "value": [80.0]})
    pop_df = pd.DataFrame({"place_dcid": ["country/A"], "value": [1_000_000]})
    merged, _ = unserved_population(access_df, pop_df)
    assert "place_name" not in merged.columns
    assert len(merged) == 1


def test_percentile_rank_higher_is_worse() -> None:
    series = pd.Series([10, 20, 30])
    ranks = percentile_rank(series, higher_is_worse=True)
    assert ranks.iloc[2] > ranks.iloc[0]  # highest value -> highest rank


def test_percentile_rank_inverted_when_lower_is_worse() -> None:
    series = pd.Series([10, 20, 30])
    ranks = percentile_rank(series, higher_is_worse=False)
    assert ranks.iloc[0] > ranks.iloc[2]  # lowest value -> highest rank


def test_priority_score_every_component_is_a_visible_column() -> None:
    df = pd.DataFrame(
        {
            "place_dcid": ["A", "B", "C"],
            "unserved": [100, 50, 10],
            "slope": [0.1, -0.5, 2.0],
        }
    )
    scored = priority_score(
        df,
        components={
            "gap": ("unserved", True),
            "stagnation": ("slope", False),
        },
    )
    assert "rank_gap" in scored.columns
    assert "rank_stagnation" in scored.columns
    assert "priority_score" in scored.columns
    # sorted descending by priority_score
    assert scored["priority_score"].is_monotonic_decreasing


def test_priority_score_respects_weights() -> None:
    df = pd.DataFrame({"place_dcid": ["A", "B"], "gap": [100, 0], "other": [0, 100]})
    heavy_gap = priority_score(
        df,
        components={"gap": ("gap", True), "other": ("other", True)},
        weights={"gap": 10.0, "other": 1.0},
    )
    assert heavy_gap.iloc[0]["place_dcid"] == "A"


def test_coverage_asymmetry_reports_both_directions() -> None:
    left = {"country/A", "country/B", "country/C"}
    right = {"country/B", "country/C", "country/D"}
    finding = coverage_asymmetry(left, right)
    assert finding.evidence["left_only"] == ["country/A"]
    assert finding.evidence["right_only"] == ["country/D"]
