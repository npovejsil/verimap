"""Beta-convergence: are laggards catching up, or is this a statistical mirage.

Regresses the change from a base year to a later year on the base-year
level. A negative coefficient is the textbook convergence signal ("low
starters improved more"), but with a metric capped at a ceiling (like
percent access), the same negative coefficient is mechanically produced by
the cap itself, and pure noise produces a negative coefficient too
(regression to the mean / Galton's fallacy). The coefficient must always
ship with both caveats attached, not as a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class ConvergenceResult:
    n_places: int
    beta: float  # negative = convergence signal
    beta_ci_low: float
    beta_ci_high: float
    r_squared: float
    # share of places within tolerance of the ceiling at either year
    ceiling_share: float


def compute_convergence(
    long_df: pd.DataFrame,
    base_year: str,
    end_year: str,
    ceiling: float | None = None,
    ceiling_tolerance: float = 0.5,
    value_col: str = "value",
) -> ConvergenceResult | None:
    """Regress (end - base) on base, across places with both observations.

    Returns None if fewer than 5 places have both years -- not enough to
    fit or trust a regression.
    """
    base = long_df[long_df["date"] == base_year][["place_dcid", value_col]].rename(
        columns={value_col: "base_value"}
    )
    end = long_df[long_df["date"] == end_year][["place_dcid", value_col]].rename(
        columns={value_col: "end_value"}
    )
    merged = base.merge(end, on="place_dcid", how="inner")
    if len(merged) < 5:
        return None

    merged["change"] = merged["end_value"] - merged["base_value"]
    x = sm.add_constant(merged["base_value"])
    model = sm.OLS(merged["change"], x).fit()

    beta = float(model.params["base_value"])
    ci_low, ci_high = model.conf_int().loc["base_value"]
    # r_squared is 0/0 (nan) when `change` has zero variance -- e.g. every
    # place improved by exactly the same amount. Report 0.0 rather than nan.
    r_squared = float(model.rsquared) if merged["change"].var() > 0 else 0.0

    ceiling_share = 0.0
    if ceiling is not None:
        near_ceiling = (
            (merged["base_value"] >= ceiling - ceiling_tolerance)
            | (merged["end_value"] >= ceiling - ceiling_tolerance)
        ).sum()
        ceiling_share = near_ceiling / len(merged)

    return ConvergenceResult(
        n_places=len(merged),
        beta=beta,
        beta_ci_low=float(ci_low),
        beta_ci_high=float(ci_high),
        r_squared=r_squared,
        ceiling_share=ceiling_share,
    )
