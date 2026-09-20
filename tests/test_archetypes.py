from __future__ import annotations

import pandas as pd

from analytics.archetypes import compute_archetypes, rank_groups_by_indicator


def _two_cluster_df() -> pd.DataFrame:
    # Two well-separated groups on two features, 6 places each.
    rows = []
    for i in range(6):
        rows.append({"place_dcid": f"HIGH{i}", "x": 90 + i, "y": 90 + i})
    for i in range(6):
        rows.append({"place_dcid": f"LOW{i}", "x": 10 + i, "y": 10 + i})
    return pd.DataFrame(rows)


def test_recovers_a_clear_two_cluster_structure() -> None:
    df = _two_cluster_df()
    result = compute_archetypes(df, feature_cols=["x", "y"], k_range=range(2, 4))
    assert result is not None
    assert result.k_used == 2
    # every HIGH place should share a cluster label distinct from every LOW place
    high_labels = {result.labels[f"HIGH{i}"] for i in range(6)}
    low_labels = {result.labels[f"LOW{i}"] for i in range(6)}
    assert len(high_labels) == 1
    assert len(low_labels) == 1
    assert high_labels != low_labels


def test_silhouette_scores_reported_for_every_evaluated_k() -> None:
    df = _two_cluster_df()
    result = compute_archetypes(df, feature_cols=["x", "y"], k_range=range(2, 4))
    assert set(result.silhouette_by_k.keys()) <= {2, 3}
    assert all(0 <= v <= 1 for v in result.silhouette_by_k.values())


def test_fixed_k_skips_the_silhouette_scan_choice() -> None:
    df = _two_cluster_df()
    result = compute_archetypes(df, feature_cols=["x", "y"], k=2, k_range=range(2, 4))
    assert result.k_used == 2


def test_returns_none_with_too_few_rows() -> None:
    df = pd.DataFrame({"place_dcid": ["A"], "x": [1.0], "y": [1.0]})
    assert compute_archetypes(df, feature_cols=["x", "y"], k_range=range(2, 4)) is None


def test_drops_rows_with_missing_features() -> None:
    df = _two_cluster_df()
    df.loc[df["place_dcid"] == "HIGH0", "x"] = None
    result = compute_archetypes(df, feature_cols=["x", "y"], k_range=range(2, 4))
    assert result is not None
    assert "HIGH0" not in result.labels.index


def _centers() -> pd.DataFrame:
    # cluster 0 has the lowest "access" mean, cluster 1 the highest.
    return pd.DataFrame({"access": [20.0, 80.0], "other": [5.0, 5.0]}, index=[0, 1])


def test_rank_groups_by_indicator_picks_low_mean_for_higher_is_better() -> None:
    ranking = rank_groups_by_indicator(
        _centers(), "access", polarity="higher_is_better"
    )
    assert ranking is not None
    assert ranking.worst_cluster == 0
    assert ranking.worst_value == 20.0
    assert ranking.best_cluster == 1
    assert ranking.best_value == 80.0


def test_rank_groups_by_indicator_picks_high_mean_for_lower_is_better() -> None:
    ranking = rank_groups_by_indicator(_centers(), "access", polarity="lower_is_better")
    assert ranking is not None
    # for lower_is_better, the HIGH mean is the worst outcome
    assert ranking.worst_cluster == 1
    assert ranking.worst_value == 80.0
    assert ranking.best_cluster == 0
    assert ranking.best_value == 20.0


def test_rank_groups_by_indicator_none_for_neutral_polarity() -> None:
    assert rank_groups_by_indicator(_centers(), "access", polarity="neutral") is None


def test_rank_groups_by_indicator_none_for_unknown_column() -> None:
    assert (
        rank_groups_by_indicator(
            _centers(), "not_a_column", polarity="higher_is_better"
        )
        is None
    )
