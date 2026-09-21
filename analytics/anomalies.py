"""Detect unusual year-to-year movements, independent of what's plotted.

Four detector types, each answering a different question about the same
year-over-year panel:

- spike: is this year's change unusual for THIS country, relative to its own
  typical year-to-year change?
- peer_outlier: is this year's change unusual relative to what every OTHER
  country did that same year?
- reversal: does this country's multi-year trend point the wrong way for the
  indicator's polarity, with the direction statistically real (not noise)?
- interpolated: does this country move in identical steps, the signature of a
  straight line drawn between two real measurements?

All four run over the full panel regardless of what a UI has selected to
plot -- an anomaly in an unselected country must still surface, never be
hidden by a picker (see views/trend_panel.py).

Two corrections came from live-data testing before this was trusted:

1. Every threshold is derived from the indicator's OWN data, never a literal
   constant. The 90th percentile of |year-over-year change| is 42.7 for
   renewable capacity (watts/capita) and 1.16 for water access (percentage
   points) -- a ~37x spread across indicators already in the catalog. A
   fixed absolute threshold would be meaningless for one or the other.
2. A per-country noise floor computed only from that country's own history
   divides by zero for any country with a perfectly flat or step-function
   series. Verified: 79 of 217 countries have a year-over-year MAD of
   exactly 0 for electricity access. Every per-country scale is floored at
   a pooled, indicator-wide scale before it's ever used as a divisor.

`reversal` deliberately does NOT use the single-year diff sign -- a raw
"did this move opposite to polarity this year" check fires on 7.7% of all
rows (119 of 217 countries, on electricity access alone), which is just the
shape of noisy annual data, not a headline. Reversal instead reuses the
HAC-robust confidence interval `analytics/trends.py::fit_trend` already
computes: flag a country only when its fitted slope opposes polarity AND
the 95% CI excludes zero. Verified this yields exactly 2 countries for
electricity access (Libya, Syria) -- a small, real list.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.trends import TrendResult

ANOMALY_KINDS = ("spike", "peer_outlier", "reversal", "interpolated")

_ROBUST_SCALE_FACTOR = 1.4826  # scales MAD to be comparable to a standard deviation


@dataclass(frozen=True)
class Anomaly:
    place_dcid: str
    kind: str  # one of ANOMALY_KINDS
    date: str  # year of the change; "" for reversal (a whole-series signal)
    value: float | None
    prior_value: float | None
    prior_date: str | None
    change: float | None  # value - prior_value; None for reversal
    score: float  # robust z (spike/peer_outlier) or |slope| (reversal)
    detail: str  # one plain-language sentence, no statistics vocabulary


@dataclass(frozen=True)
class AnomalyScales:
    pooled_scale: float  # robust (MAD-based) scale over all year-over-year changes
    magnitude_gate: float  # max(pooled_scale, 90th percentile of |change|)
    n_yoy_rows: int


def robust_scale(values: pd.Series) -> float:
    """1.4826 * median absolute deviation. Returns 0.0 for empty/degenerate input."""
    values = values.dropna()
    if values.empty:
        return 0.0
    median = values.median()
    mad = (values - median).abs().median()
    return float(_ROBUST_SCALE_FACTOR * mad)


def year_over_year(
    long_df: pd.DataFrame,
    value_col: str = "value",
    date_col: str = "date",
    place_col: str = "place_dcid",
) -> pd.DataFrame:
    """One row per (place, year) that has a prior observed year for that place.

    Uses each place's own previous *observed* year, not necessarily the
    prior calendar year -- a gap in reporting produces a multi-year change
    rather than a fabricated one. Columns: place_dcid, date, value,
    prior_date, prior_value, change, gap_years.
    """
    df = long_df.dropna(subset=[value_col, date_col]).copy()
    if df.empty:
        return pd.DataFrame(
            columns=[
                place_col,
                date_col,
                value_col,
                "prior_date",
                "prior_value",
                "change",
                "gap_years",
            ]
        )
    df[date_col] = df[date_col].astype(str)
    df = df.sort_values([place_col, date_col])
    df["prior_value"] = df.groupby(place_col)[value_col].shift(1)
    df["prior_date"] = df.groupby(place_col)[date_col].shift(1)
    df = df.dropna(subset=["prior_value", "prior_date"]).copy()
    df["change"] = df[value_col] - df["prior_value"]
    df["gap_years"] = df[date_col].astype(int) - df["prior_date"].astype(int)
    return df[
        [
            place_col,
            date_col,
            value_col,
            "prior_date",
            "prior_value",
            "change",
            "gap_years",
        ]
    ].reset_index(drop=True)


def compute_scales(yoy: pd.DataFrame) -> AnomalyScales | None:
    """Derive the indicator-wide thresholds every detector scales against.

    Returns None when there's not enough data to compute a meaningful
    scale at all (fewer than 2 year-over-year rows).
    """
    if len(yoy) < 2:
        return None
    pooled_scale = robust_scale(yoy["change"])
    p90 = float(yoy["change"].abs().quantile(0.9))
    return AnomalyScales(
        pooled_scale=pooled_scale,
        magnitude_gate=max(pooled_scale, p90),
        n_yoy_rows=len(yoy),
    )


def detect_spikes(
    yoy: pd.DataFrame,
    scales: AnomalyScales,
    k: float = 3.5,
    min_obs: int = 6,
    top_n: int = 8,
) -> list[Anomaly]:
    """Flag countries whose single-year change is unusual for THAT country.

    Deliberately does not exclude saturated (at-ceiling) countries: a
    country's value can spike or drop sharply even while near a cap (e.g. a
    reporting correction), and that's exactly the kind of row worth
    surfacing, not hiding.
    """
    if yoy.empty:
        return []

    counts = yoy.groupby("place_dcid")["change"].transform("count")
    eligible = yoy[counts >= min_obs].copy()
    if eligible.empty:
        return []

    place_median = eligible.groupby("place_dcid")["change"].transform("median")
    place_scale = eligible.groupby("place_dcid")["change"].transform(robust_scale)
    floored_scale = place_scale.clip(lower=scales.pooled_scale)
    floored_scale = floored_scale.replace(0.0, np.nan)  # avoid /0 if pooled is also 0

    z = (eligible["change"] - place_median).abs() / floored_scale
    eligible["_z"] = z.fillna(0.0)

    candidates = eligible[
        (eligible["_z"] > k) & (eligible["change"].abs() >= scales.magnitude_gate)
    ]
    if candidates.empty:
        return []

    # one row per place: keep its single worst-scoring year
    best = candidates.sort_values("_z", ascending=False).drop_duplicates(
        "place_dcid", keep="first"
    )
    best = best.sort_values("_z", ascending=False).head(top_n)

    anomalies = []
    for _, row in best.iterrows():
        direction = "jumped up" if row["change"] > 0 else "dropped"
        anomalies.append(
            Anomaly(
                place_dcid=row["place_dcid"],
                kind="spike",
                date=row["date"],
                value=float(row["value"]),
                prior_value=float(row["prior_value"]),
                prior_date=row["prior_date"],
                change=float(row["change"]),
                score=float(row["_z"]),
                detail=(
                    f"{direction} by {abs(row['change']):.1f} between "
                    f"{row['prior_date']} and {row['date']}, much more than this "
                    "country's usual year-to-year change."
                ),
            )
        )
    return anomalies


def detect_peer_outliers(
    yoy: pd.DataFrame,
    scales: AnomalyScales,
    k: float = 3.5,
    min_peers: int = 10,
    top_n: int = 8,
) -> list[Anomaly]:
    """Flag countries whose single-year change is unusual relative to peers
    reporting THAT SAME year.
    """
    if yoy.empty:
        return []

    year_counts = yoy.groupby("date")["change"].transform("count")
    eligible = yoy[year_counts >= min_peers].copy()
    if eligible.empty:
        return []

    year_median = eligible.groupby("date")["change"].transform("median")
    year_scale = eligible.groupby("date")["change"].transform(robust_scale)
    floored_scale = year_scale.clip(lower=scales.pooled_scale)
    floored_scale = floored_scale.replace(0.0, np.nan)

    z = (eligible["change"] - year_median).abs() / floored_scale
    eligible["_z"] = z.fillna(0.0)

    candidates = eligible[
        (eligible["_z"] > k) & (eligible["change"].abs() >= scales.magnitude_gate)
    ]
    if candidates.empty:
        return []

    best = candidates.sort_values("_z", ascending=False).drop_duplicates(
        "place_dcid", keep="first"
    )
    best = best.sort_values("_z", ascending=False).head(top_n)

    anomalies = []
    for _, row in best.iterrows():
        direction = "gained" if row["change"] > 0 else "lost"
        anomalies.append(
            Anomaly(
                place_dcid=row["place_dcid"],
                kind="peer_outlier",
                date=row["date"],
                value=float(row["value"]),
                prior_value=float(row["prior_value"]),
                prior_date=row["prior_date"],
                change=float(row["change"]),
                score=float(row["_z"]),
                detail=(
                    f"{direction} {abs(row['change']):.1f} in {row['date']}, far more "
                    "than other countries typically moved that same year."
                ),
            )
        )
    return anomalies


def detect_reversals(
    trend_results: list[TrendResult],
    polarity: str,
    top_n: int = 8,
) -> list[Anomaly]:
    """Flag countries whose fitted multi-year trend points the wrong way.

    "Wrong way" means opposing the indicator's polarity, and the direction
    must be statistically real: the 95% confidence interval on the slope
    must exclude zero. `polarity="neutral"` has no "wrong way" and always
    returns an empty list.
    """
    if polarity not in ("higher_is_better", "lower_is_better"):
        return []

    flagged = []
    for r in trend_results:
        wrong_way = (
            polarity == "higher_is_better" and r.slope < 0 and r.slope_ci_high < 0
        ) or (polarity == "lower_is_better" and r.slope > 0 and r.slope_ci_low > 0)
        if wrong_way:
            flagged.append(r)

    flagged.sort(key=lambda r: abs(r.slope), reverse=True)
    flagged = flagged[:top_n]

    direction_word = "down" if polarity == "higher_is_better" else "up"
    anomalies = []
    for r in flagged:
        anomalies.append(
            Anomaly(
                place_dcid=r.place_dcid,
                kind="reversal",
                date="",
                value=None,
                prior_value=None,
                prior_date=None,
                change=None,
                score=abs(r.slope),
                detail=(
                    f"Moving {direction_word} over its full reporting history "
                    f"({r.slope:+.2f} per year), not just noise in a single year."
                ),
            )
        )
    return anomalies


def detect_interpolated(
    yoy: pd.DataFrame,
    scales: AnomalyScales,
    min_run: int = 3,
    tol_frac: float = 0.33,
    min_step_frac: float = 1.0,
    top_n: int = 8,
) -> list[Anomaly]:
    """Flag runs of near-identical year-over-year changes.

    A straight line drawn between two real measurements produces consecutive
    changes that are all but equal. Genuine annual measurement does not: it
    wobbles, because the instrument, the sample and the rounding all wobble.
    So a long run of identical steps is evidence the intervening years were
    filled in rather than observed.

    Three conditions, all of which must hold across at least `min_run`
    consecutive changes:

    - each change is between consecutively *observed* years (`gap_years == 1`),
      since a multi-year gap is not comparable to a single-year step;
    - each change is at least `min_step` in size, which is what keeps a
      saturated or rounding-noise series out (a country sitting at 100%
      produces a long run of identical zero-changes that means the opposite
      of this finding);
    - adjacent changes differ by no more than `tol`.

    Both thresholds are derived from the indicator's own pooled scale rather
    than set as literal constants, for the reason recorded at the top of this
    module: the 90th percentile of absolute year-over-year change spans ~37x
    across the catalog, so any fixed value is meaningless for one indicator
    or the other. `tol_frac` and `min_step_frac` are fractions of
    `scales.pooled_scale`.

    CALIBRATION, verified against live data (undata/sdg/EG_ACS_ELEC, 217
    countries x 2000-2024, 5,183 year-over-year rows, UNSD SDG data portal):
    pooled_scale is 0.2965 percentage points. The defaults above are the
    fractions that reproduce the hand-tuned thresholds validated on that
    indicator -- 0.33 * 0.2965 = 0.098 ~ 0.1 pp tolerance, and
    1.0 * 0.2965 = 0.297 ~ 0.3 pp minimum step. min_step_frac = 1.0 reads
    directly: a step must be at least one pooled scale to count.

    At that setting 42 of 217 countries carry a run of 3+ identical steps.
    That rate is high but it is not over-firing: SDG 7.1.1 is modelled
    between survey years for much of its coverage. Belarus is the clearest
    case -- 89.0 in 2000 to 100.0 in 2019 in steps of +0.5/+0.6/+0.7, a
    19-year straight line, then flat at 100. Eritrea runs +1.1/+1.2 for 18
    consecutive years (2003-2021) and only then starts to wobble (+2.9,
    -1.0, +0.9), which is what real measurement resuming looks like.

    Not yet verified on the other catalog indicators. pooled_scale varies by
    ~37x across them (see the note at the top of this module), so the
    fractions should hold where the absolute thresholds would not -- but
    confirm before relying on the output for a new indicator.

    Uses `pooled_scale` rather than `magnitude_gate` on purpose. The gate is
    `max(pooled_scale, p90)`, which asks whether a change is unusually large.
    An interpolated run is made of entirely ordinary-sized steps -- that is
    precisely why it goes unnoticed -- so requiring p90-sized steps would
    filter out every genuine case.

    `score` is the length of the run in years: a longer fabricated stretch is
    a worse problem than a shorter one, and it sorts meaningfully.
    """
    if yoy.empty or scales.pooled_scale <= 0:
        # With no pooled scale there is nothing to calibrate against, and a
        # tolerance of zero would flag every perfectly flat series.
        return []

    tol = tol_frac * scales.pooled_scale
    min_step = min_step_frac * scales.pooled_scale

    runs: list[dict] = []
    for place, group in yoy.groupby("place_dcid"):
        g = group.sort_values("date").reset_index(drop=True)
        if len(g) < min_run:
            continue

        changes = g["change"].tolist()
        gaps = g["gap_years"].tolist()

        # links[i] is True when change i continues an identical-step run
        # started at change i-1.
        links = [False] * len(changes)
        for i in range(1, len(changes)):
            links[i] = (
                gaps[i] == 1
                and gaps[i - 1] == 1
                and abs(changes[i]) >= min_step
                and abs(changes[i - 1]) >= min_step
                and abs(changes[i] - changes[i - 1]) <= tol
            )

        # Walk maximal runs of consecutive links. A run of m links covers
        # m + 1 changes.
        i = 1
        while i < len(links):
            if not links[i]:
                i += 1
                continue
            start = i - 1
            while i < len(links) and links[i]:
                i += 1
            end = i - 1  # last change index in the run
            n_changes = end - start + 1
            if n_changes >= min_run:
                first, last = g.iloc[start], g.iloc[end]
                runs.append(
                    {
                        "place_dcid": place,
                        "date": last["date"],
                        "value": float(last["value"]),
                        "prior_date": first["prior_date"],
                        "prior_value": float(first["prior_value"]),
                        "change": float(last["value"] - first["prior_value"]),
                        "n_changes": n_changes,
                        "step": float(
                            sum(changes[start : end + 1]) / n_changes
                        ),
                    }
                )

    if not runs:
        return []

    # One row per place: keep its longest run.
    best: dict[str, dict] = {}
    for r in runs:
        current = best.get(r["place_dcid"])
        if current is None or r["n_changes"] > current["n_changes"]:
            best[r["place_dcid"]] = r

    ordered = sorted(best.values(), key=lambda r: r["n_changes"], reverse=True)
    ordered = ordered[:top_n]

    anomalies = []
    for r in ordered:
        direction = "rose" if r["step"] > 0 else "fell"
        anomalies.append(
            Anomaly(
                place_dcid=r["place_dcid"],
                kind="interpolated",
                date=r["date"],
                value=r["value"],
                prior_value=r["prior_value"],
                prior_date=r["prior_date"],
                change=r["change"],
                score=float(r["n_changes"]),
                detail=(
                    f"{direction} by almost exactly {abs(r['step']):.2f} every "
                    f"year from {r['prior_date']} to {r['date']}. A series that "
                    "moves in identical steps is usually filled in between two "
                    "real measurements rather than measured each year."
                ),
            )
        )
    return anomalies


def detect_anomalies(
    long_df: pd.DataFrame,
    polarity: str,
    trend_results: list[TrendResult] | None = None,
    value_col: str = "value",
    k: float = 3.5,
    min_obs: int = 6,
    min_peers: int = 10,
    top_n: int = 8,
) -> list[Anomaly]:
    """Run all four detectors over the full panel. Never raises on degenerate input."""
    yoy = year_over_year(long_df, value_col=value_col)
    scales = compute_scales(yoy)

    anomalies: list[Anomaly] = []
    if scales is not None:
        anomalies += detect_spikes(yoy, scales, k=k, min_obs=min_obs, top_n=top_n)
        anomalies += detect_peer_outliers(
            yoy, scales, k=k, min_peers=min_peers, top_n=top_n
        )
        anomalies += detect_interpolated(yoy, scales, top_n=top_n)
    anomalies += detect_reversals(trend_results or [], polarity, top_n=top_n)
    return anomalies
