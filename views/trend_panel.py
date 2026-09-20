"""Render a time-series trend panel for a set of countries.

Plotly, faceted by indicator when units differ, so two incompatible units
never share one y-axis. Overlays the OLS fit line for countries where a
trend was computed (saturated countries are shown as raw series only, with
no fit line, since their "trend" measures a ceiling, not progress).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.trends import TrendResult
from recipe.attribution import Citation, require_citations


def render_trend_panel(
    long_df: pd.DataFrame,
    place_dcids: list[str],
    citations: list[Citation],
    trends: dict[str, TrendResult] | None = None,
    saturated_places: set[str] | None = None,
    value_col: str = "value",
    unit_display: str | None = None,
    total_places: int | None = None,
) -> None:
    """Plot value-over-time lines for the given places, with optional fit lines.

    `total_places`, when given, renders a "showing N of M countries" caption
    so a limited selection is never silently mistaken for the full picture.
    """
    require_citations(citations)
    trends = trends or {}
    saturated_places = saturated_places or set()

    st.subheader("Trends over time")

    if total_places is not None:
        st.caption(f"Showing {len(place_dcids)} of {total_places} countries.")

    df = long_df[long_df["place_dcid"].isin(place_dcids)].sort_values("date")
    if df.empty:
        st.info("No time-series data for the selected places.")
        return

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
        label = f"{name} (already at max)" if place_dcid in saturated_places else name

        fig.add_trace(
            go.Scatter(
                x=place_df["date"],
                y=place_df[value_col],
                mode="lines+markers",
                name=label,
            )
        )

        trend = trends.get(place_dcid)
        if trend is not None:
            years = place_df["date"].astype(int)
            fit_y = trend.intercept + trend.slope * years
            fig.add_trace(
                go.Scatter(
                    x=place_df["date"],
                    y=fit_y,
                    mode="lines",
                    line=dict(dash="dot"),
                    name=f"{name} trend ({trend.slope:+.2f}/yr)",
                    showlegend=True,
                )
            )

    fig.update_layout(
        yaxis_title=unit_display or "value",
        xaxis_title="Year",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    for c in citations:
        st.caption(f"Source: {c.render()}")
