"""Backend accuracy guards: fetch-time, combination-time, and transform-time checks.

Every check returns a Finding rather than raising or silently passing. Views
render Findings; they never swallow them. This is the mechanism behind two
hard rules: never silently drop rows, and never combine incompatible units.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from recipe.catalog import Indicator
from recipe.datacommons_client import ObservationPayload

Level = str  # "error" | "warn" | "info"


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    message: str
    evidence: dict | None = None


@dataclass(frozen=True)
class NaNReport:
    """Record of rows dropped for missing values — never silent."""

    n_before: int
    n_after: int
    n_dropped: int
    reason: str
    dropped_places: tuple[str, ...] = ()

    def message(self) -> str:
        return f"Excluded {self.n_dropped} rows: {self.reason} (n={self.n_dropped} of {self.n_before})"


# ---------------------------------------------------------------------------
# Fetch-time checks
# ---------------------------------------------------------------------------


def check_multi_facet(payload: ObservationPayload, dcid: str) -> Finding | None:
    """Flag a variable that mixes multiple provenances/facets across places.

    Verified real case: Count_Person mixes 13 provenances across dates
    spanning 1989-2026. Any indicator flagged here must be refused as a
    denominator unless the catalog pins a single facet.
    """
    var_data = payload.variable(dcid)
    facets = {o.get("facet") for o in var_data.values() if o.get("facet")}
    if len(facets) > 1:
        return Finding(
            level="warn",
            code="MULTI_FACET",
            message=(
                f"{dcid} has {len(facets)} distinct facets across "
                f"{len(var_data)} places — provenance is not uniform. "
                "Refuse as a denominator unless a single facet is pinned."
            ),
            evidence={"dcid": dcid, "n_facets": len(facets), "n_places": len(var_data)},
        )
    return None


def check_mixed_dates(payload: ObservationPayload, dcid: str) -> Finding | None:
    """Flag a point-in-time query where places report different reference dates."""
    var_data = payload.variable(dcid)
    dates = {o.get("date") for o in var_data.values() if o.get("date")}
    if len(dates) > 1:
        return Finding(
            level="warn",
            code="MIXED_DATES",
            message=(
                f"{dcid} 'latest' observations span {len(dates)} distinct dates "
                f"({min(dates)}–{max(dates)}) rather than one reference year."
            ),
            evidence={"dcid": dcid, "dates": sorted(dates)},
        )
    return None


def check_unit_drift(
    payload: ObservationPayload, indicator: Indicator
) -> Finding | None:
    """Flag when the fetched unit disagrees with the catalog's recorded unit."""
    if not indicator.unit:
        return None
    var_data = payload.variable(indicator.dcid)
    for obs in var_data.values():
        facet_id = obs.get("facet")
        if not facet_id:
            continue
        facet = payload.facet(facet_id)
        fetched_unit = facet.get("unit")
        if fetched_unit and fetched_unit != indicator.unit:
            return Finding(
                level="error",
                code="UNIT_DRIFT",
                message=(
                    f"{indicator.key}: catalog unit '{indicator.unit}' does not "
                    f"match fetched unit '{fetched_unit}'. Re-run `make enrich`."
                ),
                evidence={"catalog_unit": indicator.unit, "fetched_unit": fetched_unit},
            )
    return None


def check_range_violation(
    payload: ObservationPayload, indicator: Indicator
) -> Finding | None:
    """Flag values outside the catalog's recorded value range, if one exists."""
    if indicator.value_min is None or indicator.value_max is None:
        return None
    var_data = payload.variable(indicator.dcid)
    out_of_range = [
        (place, obs["value"])
        for place, obs in var_data.items()
        if "value" in obs
        and not (
            indicator.value_min - 1e-6 <= obs["value"] <= indicator.value_max + 1e-6
        )
    ]
    if out_of_range:
        return Finding(
            level="error",
            code="RANGE_VIOLATION",
            message=(
                f"{indicator.key}: {len(out_of_range)} values fall outside the "
                f"catalog range [{indicator.value_min}, {indicator.value_max}]."
            ),
            evidence={"examples": out_of_range[:5]},
        )
    return None


def check_empty_variable(payload: ObservationPayload, dcid: str) -> Finding | None:
    """Flag a variable with zero returned places.

    The client already raises EmptyResponseError for a fully-empty payload;
    this check exists for cases where the call succeeds but returns fewer
    places than expected (e.g. a bad region filter), which is not itself an
    exception.
    """
    var_data = payload.variable(dcid)
    if not var_data:
        return Finding(
            level="error",
            code="EMPTY_VARIABLE",
            message=f"{dcid} returned zero places.",
            evidence={"dcid": dcid},
        )
    return None


# ---------------------------------------------------------------------------
# Combination-time checks (used by keymatch.py's JoinSpec construction)
# ---------------------------------------------------------------------------


def check_ceiling_effect(
    values: pd.Series, ceiling: float, threshold: float = 0.4
) -> Finding | None:
    """Flag when a large share of places sit at or near a saturation ceiling.

    Verified real case: 140 of 217 countries (65%) are at >=99.5% electricity
    access. Trend/slope/convergence analysis over that population measures a
    ceiling, not progress.
    """
    if values.empty:
        return None
    saturated = (values >= ceiling - 0.5).sum()
    share = saturated / len(values)
    if share > threshold:
        return Finding(
            level="warn",
            code="CEILING_EFFECT",
            message=(
                f"{saturated} of {len(values)} places ({share:.0%}) are at or "
                f"near the saturation ceiling ({ceiling}). Trend and convergence "
                "analysis should exclude them and report them separately."
            ),
            evidence={
                "n_saturated": int(saturated),
                "n_total": len(values),
                "share": share,
            },
        )
    return None


def check_unweighted_aggregate(weighted: bool) -> Finding | None:
    """Flag an aggregate computed without population weights.

    Verified real case: unweighted country mean of electricity access is
    88.3%, population-weighted is 91.6%, and the UN's own published Earth
    aggregate is 91.7% -- a 3.4pp error from skipping weights.
    """
    if weighted:
        return None
    return Finding(
        level="warn",
        code="UNWEIGHTED_AGGREGATE",
        message=(
            "Aggregate computed as an unweighted country mean. Verified this "
            "differs from the population-weighted mean by 3.4pp on electricity "
            "access -- label this aggregate or switch to weighting."
        ),
    )


# ---------------------------------------------------------------------------
# Transform-time: row-count and NaN discipline
# ---------------------------------------------------------------------------


def log_filter_result(
    n_before: int, df_after: pd.DataFrame, description: str
) -> Finding:
    """Report a row-count delta for a filter. Call after every filter operation."""
    n_after = len(df_after)
    return Finding(
        level="info",
        code="FILTER_APPLIED",
        message=f"{description}: {n_before} → {n_after} rows ({n_before - n_after} dropped)",
        evidence={"n_before": n_before, "n_after": n_after, "description": description},
    )


def drop_missing(
    df: pd.DataFrame, cols: list[str], reason: str, place_col: str = "place_dcid"
) -> tuple[pd.DataFrame, NaNReport]:
    """Drop rows with missing values in `cols`, reporting count, reason, and places.

    Never call `.dropna()` bare — this is the one path that removes rows for
    missingness, and it always returns a report the caller must surface.
    """
    n_before = len(df)
    mask = df[cols].isna().any(axis=1)
    dropped_places = (
        tuple(sorted(df.loc[mask, place_col].dropna().unique()))
        if place_col in df.columns
        else ()
    )
    result = df.loc[~mask].copy()
    report = NaNReport(
        n_before=n_before,
        n_after=len(result),
        n_dropped=int(mask.sum()),
        reason=reason,
        dropped_places=dropped_places,
    )
    return result, report


# ---------------------------------------------------------------------------
# Headline cross-check
# ---------------------------------------------------------------------------


def cross_check_weighted_mean(
    long_df: pd.DataFrame,
    pop_df: pd.DataFrame,
    published_value: float,
    tolerance_pp: float = 0.5,
) -> Finding:
    """Assert a population-weighted mean reproduces a published aggregate.

    Verified: population-weighted 2023 electricity access (91.6%) reproduces
    the UN's own published Earth aggregate (91.7%) to 0.07pp, while the
    unweighted country mean is off by 3.4pp. This assertion is the strongest
    evidence the pipeline is wired correctly and should run at startup.
    """
    merged = long_df.merge(
        pop_df[["place_dcid", "value"]].rename(columns={"value": "population"}),
        on="place_dcid",
        how="inner",
    )
    if merged.empty or merged["population"].sum() == 0:
        return Finding(
            level="error",
            code="CROSS_CHECK_FAILED",
            message="Cross-check could not run: no overlapping places with population.",
        )
    weighted_mean = (merged["value"] * merged["population"]).sum() / merged[
        "population"
    ].sum()
    delta = abs(weighted_mean - published_value)
    level = "info" if delta <= tolerance_pp else "error"
    return Finding(
        level=level,
        code="HEADLINE_CROSS_CHECK",
        message=(
            f"Population-weighted mean {weighted_mean:.2f} vs published "
            f"{published_value:.2f} (delta {delta:.2f}pp, tolerance {tolerance_pp}pp)"
        ),
        evidence={
            "weighted_mean": weighted_mean,
            "published": published_value,
            "delta": delta,
        },
    )
