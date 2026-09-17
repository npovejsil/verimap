"""Per-place trend slopes with honest confidence intervals.

Annual country series are serially correlated, so naive OLS standard errors
are too narrow — this uses HAC (Newey-West) errors instead. Saturated places
(at or near a ceiling like 100%) are excluded from slope fitting: their
"trend" measures a ceiling, not progress, and are reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm

_MAX_PROJECTION_YEAR = 2100


@dataclass(frozen=True)
class TrendResult:
    place_dcid: str
    n_obs: int
    slope: float  # units per year
    slope_ci_low: float
    slope_ci_high: float
    intercept: float
    is_saturated: bool


def is_saturated(latest_value: float, ceiling: float, tolerance: float = 0.5) -> bool:
    return latest_value >= ceiling - tolerance


def fit_trend(
    place_df: pd.DataFrame, value_col: str = "value", date_col: str = "date"
) -> TrendResult | None:
    """Fit value ~ year with HAC (Newey-West) standard errors for one place.

    Returns None if fewer than 3 observations — not enough to fit a
    meaningful line, let alone trust a confidence interval.
    """
    df = place_df.dropna(subset=[value_col, date_col]).sort_values(date_col)
    if len(df) < 3:
        return None

    years = df[date_col].astype(int)
    x = sm.add_constant(years)
    y = df[value_col].astype(float)

    model = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    slope = model.params[date_col]
    ci_low, ci_high = model.conf_int().loc[date_col]

    place_dcid = df["place_dcid"].iloc[0] if "place_dcid" in df.columns else ""
    return TrendResult(
        place_dcid=place_dcid,
        n_obs=len(df),
        slope=float(slope),
        slope_ci_low=float(ci_low),
        slope_ci_high=float(ci_high),
        intercept=float(model.params["const"]),
        is_saturated=False,
    )


def fit_trends_excluding_saturated(
    long_df: pd.DataFrame, ceiling: float | None, value_col: str = "value"
) -> tuple[list[TrendResult], list[str]]:
    """Fit trends per place, excluding places saturated at the ceiling.

    Returns (trend_results, saturated_place_dcids) — saturated places are
    never silently dropped, their dcids are always returned alongside.
    """
    saturated_places: list[str] = []
    results: list[TrendResult] = []

    for place_dcid, group in long_df.groupby("place_dcid"):
        latest = group.sort_values("date")[value_col].iloc[-1]
        if ceiling is not None and is_saturated(latest, ceiling):
            saturated_places.append(place_dcid)
            continue
        trend = fit_trend(group, value_col=value_col)
        if trend is not None:
            results.append(trend)

    return results, saturated_places


def years_to_target(
    latest_value: float, latest_year: int, slope: float, target: float = 100.0
) -> float:
    """Linear pace extrapolation to a target value. Not a forecast.

    Returns float('inf') for non-positive slope (never reaches target at
    current pace) and caps the projected year at 2100.
    """
    if slope <= 0:
        return float("inf")
    years_needed = (target - latest_value) / slope
    if years_needed <= 0:
        return 0.0
    projected_year = latest_year + years_needed
    if projected_year > _MAX_PROJECTION_YEAR:
        return float("inf")
    return years_needed
