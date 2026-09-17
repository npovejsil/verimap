"""Unserved-population gaps and an explainable, weighted-rank priority score.

The priority score is deliberately a transparent weighted sum of percentile
ranks, not a learned model: every component is its own visible, sortable
column, and the weights are exposed so a viewer can watch the ranking move.
For a resource-allocation decision, that auditability is the product
requirement -- a ranking anyone can recompute in a spreadsheet beats a score
nobody can interrogate.
"""

from __future__ import annotations

import pandas as pd

from recipe.validation import Finding, NaNReport, drop_missing


def unserved_population(
    access_df: pd.DataFrame, pop_df: pd.DataFrame, access_col: str = "value"
) -> tuple[pd.DataFrame, NaNReport]:
    """Compute (100 - access%)/100 * population per place, for one shared year.

    Both inputs must already be filtered to a single date before calling
    this -- joining across different reference years silently mixes
    vintages, which is exactly the denominator-provenance pitfall the
    validation layer exists to catch elsewhere.
    """
    access_cols = ["place_dcid", access_col]
    if "place_name" in access_df.columns:
        access_cols.insert(1, "place_name")
    merged = access_df[access_cols].merge(
        pop_df[["place_dcid", "value"]].rename(columns={"value": "population"}),
        on="place_dcid",
        how="inner",
    )
    merged, report = drop_missing(
        merged,
        [access_col, "population"],
        reason="no matching access or population observation for this year",
    )
    merged["unserved_population"] = (
        (100 - merged[access_col]) / 100 * merged["population"]
    )
    return merged, report


def percentile_rank(series: pd.Series, higher_is_worse: bool = True) -> pd.Series:
    """Rank a series 0-1, where 1 is always 'most in need of attention'.

    `higher_is_worse=True` for things like unserved population (more people
    unserved = higher priority). Set False for things like access rate
    (lower access = higher priority, so the rank is inverted).
    """
    ranks = series.rank(pct=True)
    return ranks if higher_is_worse else 1 - ranks


def priority_score(
    df: pd.DataFrame,
    components: dict[str, tuple[str, bool]],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Compute a transparent weighted-percentile-rank priority score.

    `components` maps a display name to (column_name, higher_is_worse).
    Every component's percentile rank is added as its own column
    (`rank_<name>`) alongside the final `priority_score` -- nothing is
    hidden inside the composite.
    """
    if weights is None:
        weights = {name: 1.0 for name in components}
    total_weight = sum(weights.get(name, 1.0) for name in components)

    out = df.copy()
    score = pd.Series(0.0, index=out.index)
    for name, (col, higher_is_worse) in components.items():
        rank_col = f"rank_{name}"
        out[rank_col] = percentile_rank(out[col], higher_is_worse=higher_is_worse)
        score += out[rank_col] * weights.get(name, 1.0)
    out["priority_score"] = score / total_weight
    return out.sort_values("priority_score", ascending=False)


def coverage_asymmetry(left_places: set[str], right_places: set[str]) -> Finding:
    """Report which places have one indicator but not the other."""
    left_only = left_places - right_places
    right_only = right_places - left_places
    return Finding(
        level="info",
        code="COVERAGE_ASYMMETRY",
        message=(
            f"{len(left_only)} places have the first indicator but not the "
            f"second; {len(right_only)} have the second but not the first."
        ),
        evidence={
            "left_only": sorted(left_only),
            "right_only": sorted(right_only),
        },
    )
