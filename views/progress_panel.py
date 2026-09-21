"""Render progress-toward-target: trend lines plus the target itself as a
first-class mark on the chart, not just a number in a caption.

Companion to `views/trend_panel.py`, which optimizes for stagnation/pace
analysis across many places. This view optimizes for a sharper, more public
question: "is this specific place going to make it, and by when?" -- so a
target line, a target-year marker, and a per-place on-track table are the
point, where trend_panel's OLS fit-line overlay is not.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.progress import ProgressResult
from recipe.attribution import Citation, require_citations


def render_progress_panel(
    series_df: pd.DataFrame,
    place_dcids: list[str],
    citations: list[Citation],
    progress: dict[str, ProgressResult],
    target_value: float | None,
    target_year: int | None,
    unit_display: str | None = None,
) -> None:
    require_citations(citations)
    st.subheader("Progress toward the target")

    df = series_df[series_df["place_dcid"].isin(place_dcids)].sort_values("date")
    if df.empty:
        st.info("No time-series data for the selected places.")
        return

    if target_value is None:
        st.caption(
            "This indicator's SDG target isn't a single fixed number (e.g. "
            '"substantially increase" or "double the rate"), so there\'s no '
            "target line to plot against -- the trend is still shown below."
        )

    fig = go.Figure()
    for place_dcid in place_dcids:
        place_df = df[df["place_dcid"] == place_dcid]
        if place_df.empty:
            continue
        name = (
            place_df["place_name"].iloc[0]
            if "place_name" in place_df.columns
            else place_dcid
        )
        fig.add_trace(
            go.Scatter(
                x=place_df["date"].astype(int),
                y=place_df["value"],
                mode="lines+markers",
                name=name,
            )
        )

    if target_value is not None:
        target_label = (
            f"Target: {target_value:g} by {target_year}"
            if target_year is not None
            else f"Target: {target_value:g}"
        )
        fig.add_hline(
            y=target_value,
            line_dash="dash",
            line_color="gray",
            annotation_text=target_label,
            annotation_position="top left",
        )
    if target_year is not None:
        fig.add_vline(x=target_year, line_dash="dot", line_color="gray")

    fig.update_layout(
        yaxis_title=unit_display or "value",
        xaxis_title="Year",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    _render_summary_table(df, place_dcids, progress, target_value, target_year)

    for c in citations:
        st.caption(f"Source: {c.render()}")


def _render_summary_table(
    df: pd.DataFrame,
    place_dcids: list[str],
    progress: dict[str, ProgressResult],
    target_value: float | None,
    target_year: int | None,
) -> None:
    names = (
        df.set_index("place_dcid")["place_name"].to_dict()
        if "place_name" in df.columns
        else {}
    )

    rows = []
    for place_dcid in place_dcids:
        r = progress.get(place_dcid)
        if r is None:
            continue
        rows.append(
            {
                "Country": names.get(place_dcid, place_dcid),
                f"Latest ({r.latest_year})": round(r.latest_value, 1),
                "Gap to target": _format_gap(r) if target_value is not None else None,
                "Reaches target": (
                    _format_projected_year(r) if target_value is not None else None
                ),
                "On track?": _format_on_track(r) if target_year is not None else None,
            }
        )

    if not rows:
        return
    table = pd.DataFrame(rows)
    table = table.dropna(axis="columns", how="all")
    st.dataframe(table, use_container_width=True, hide_index=True)


def _format_gap(r: ProgressResult) -> str:
    if r.gap is None:
        return "—"
    if r.gap <= 0:
        return "Met"
    return f"{r.gap:.1f} remaining"


def _format_projected_year(r: ProgressResult) -> str:
    if r.projected_year is None:
        return "—"
    if r.projected_year == float("inf"):
        return "Not at current pace"
    return str(int(round(r.projected_year)))


def _format_on_track(r: ProgressResult) -> str:
    if r.on_track is None:
        return "—"
    return "✅ Yes" if r.on_track else "❌ No"
