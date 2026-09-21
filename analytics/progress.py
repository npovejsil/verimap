"""Per-place progress toward a fixed numeric SDG target.

Distinct from `analytics.trends`, which fits a slope for its own sake
(stagnation scoring, saturation detection). This module asks the sharper
question a "progress tracker" needs: at the current pace, does this place
reach its target before the target year?

Reuses `analytics.trends.fit_trend` for the slope and
`analytics.trends.years_to_target` for the pace projection rather than
re-deriving either -- the only new logic here is making both polarity-aware,
via a sign flip so a `lower_is_better` indicator (e.g. energy intensity)
reuses the same "distance closes when the number goes up" arithmetic that
`years_to_target` was written for.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analytics.trends import fit_trend, years_to_target


@dataclass(frozen=True)
class ProgressResult:
    place_dcid: str
    latest_value: float
    latest_year: int
    target_value: float | None
    target_year: int | None
    gap: float | None  # remaining distance in the favorable direction; <=0 once met
    slope: float | None  # raw units/year, sign as reported (not polarity-flipped)
    projected_year: float | None  # None if no target set; inf if never at this pace
    on_track: bool | None  # None if there's no target_year to judge against


def _favorable_sign(polarity: str) -> float:
    """+1 when a bigger number is progress, -1 when a smaller number is."""
    return -1.0 if polarity == "lower_is_better" else 1.0


def compute_progress(
    series_df: pd.DataFrame,
    polarity: str,
    target_value: float | None,
    target_year: int | None,
    value_col: str = "value",
    date_col: str = "date",
) -> list[ProgressResult]:
    """One ProgressResult per place in `series_df`.

    A place needs at least one observation to appear at all; it needs 3+
    (via `fit_trend`) to get a slope and pace projection -- otherwise those
    fields are None rather than a misleadingly confident guess.
    """
    sign = _favorable_sign(polarity)
    results: list[ProgressResult] = []

    for place_dcid, group in series_df.groupby("place_dcid"):
        clean = group.dropna(subset=[value_col, date_col]).sort_values(date_col)
        if clean.empty:
            continue
        latest_row = clean.iloc[-1]
        latest_value = float(latest_row[value_col])
        latest_year = int(latest_row[date_col])

        gap = None
        if target_value is not None:
            gap = sign * (target_value - latest_value)

        trend = fit_trend(clean, value_col=value_col, date_col=date_col)
        slope = trend.slope if trend is not None else None

        projected_year: float | None = None
        on_track: bool | None = None
        if target_value is not None:
            # Prefer the real history over a slope guess: if the target was
            # already met at some point in the observed series (even if the
            # latest point has since drifted away from it again), that's the
            # actual achievement year -- not something a linear fit should
            # re-derive. Only fall back to pace projection when it never
            # happened in the data we have.
            met = clean[sign * clean[value_col] >= sign * target_value]
            if not met.empty:
                projected_year = float(met[date_col].astype(int).min())
            elif slope is not None:
                years_needed = years_to_target(
                    latest_value=sign * latest_value,
                    latest_year=latest_year,
                    slope=sign * slope,
                    target=sign * target_value,
                )
                projected_year = (
                    float("inf")
                    if years_needed == float("inf")
                    else latest_year + years_needed
                )
            if target_year is not None and projected_year is not None:
                on_track = projected_year <= target_year

        results.append(
            ProgressResult(
                place_dcid=place_dcid,
                latest_value=latest_value,
                latest_year=latest_year,
                target_value=target_value,
                target_year=target_year,
                gap=gap,
                slope=slope,
                projected_year=projected_year,
                on_track=on_track,
            )
        )

    return results
