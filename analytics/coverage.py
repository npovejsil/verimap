"""Coverage/gap finder: where does an indicator have holes, and how stale is it.

This is the "help researchers find data" deliverable -- cheap to build,
directly answers "is this indicator usable for what I want to do" before
anyone writes a query against it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CoverageReport:
    indicator_key: str
    n_places_total: int
    n_place_years_expected: int
    n_place_years_observed: int
    n_missing_cells: int
    missing_share: float
    latest_year_by_place: dict[str, str]
    stalest_places: tuple[
        tuple[str, str], ...
    ]  # (place_dcid, latest_year), oldest first


def compute_coverage(
    long_df: pd.DataFrame, expected_start: int, expected_end: int
) -> CoverageReport:
    """Compute completeness of a long-format indicator frame over an expected year range.

    `n_place_years_expected` assumes every observed place should have one
    observation per year in [expected_start, expected_end] -- a place with
    a genuinely shorter reporting history will show as "missing" years it
    was never expected to report, which is a limitation worth stating
    rather than hiding: this module reports gaps against a uniform grid,
    not against each place's own known reporting start.
    """
    places = sorted(long_df["place_dcid"].unique())
    years = [str(y) for y in range(expected_start, expected_end + 1)]
    expected = len(places) * len(years)

    observed_pairs = set(zip(long_df["place_dcid"], long_df["date"]))
    observed = len(observed_pairs)
    missing = expected - observed

    latest_by_place: dict[str, str] = (
        long_df.groupby("place_dcid")["date"].max().to_dict()
    )
    stalest = tuple(sorted(latest_by_place.items(), key=lambda kv: kv[1])[:10])

    return CoverageReport(
        indicator_key="",
        n_places_total=len(places),
        n_place_years_expected=expected,
        n_place_years_observed=observed,
        n_missing_cells=missing,
        missing_share=missing / expected if expected else 0.0,
        latest_year_by_place=latest_by_place,
        stalest_places=stalest,
    )


def coverage_heatmap_data(
    long_df: pd.DataFrame, expected_start: int, expected_end: int
) -> pd.DataFrame:
    """Build a place x year grid of 1 (observed) / 0 (missing) for a heatmap."""
    places = sorted(long_df["place_dcid"].unique())
    years = [str(y) for y in range(expected_start, expected_end + 1)]
    observed_pairs = set(zip(long_df["place_dcid"], long_df["date"]))

    grid = pd.DataFrame(
        [[1 if (p, y) in observed_pairs else 0 for y in years] for p in places],
        index=places,
        columns=years,
    )
    return grid
