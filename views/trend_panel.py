"""Render a time-series trend panel for a set of countries.

Plotly, faceted by indicator when units differ, so two incompatible units
never share one y-axis. Overlays the OLS fit line for countries where a
trend was computed (saturated countries are shown as raw series only, with
no fit line, since their "trend" measures a ceiling, not progress).

Anomalies (see analytics/anomalies.py) get two treatments depending on
whether their country is currently charted: a marker on the line itself,
or a row in a summary table with a nudge to add that country to the chart
-- an anomaly in an unselected country must never be silently invisible.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.anomalies import Anomaly
from analytics.trends import TrendResult
from recipe.attribution import Citation, require_citations

_KIND_LABELS = {
    "spike": "Sudden jump/drop",
    "peer_outlier": "Breaking from the pack",
    "reversal": "Moving the wrong direction",
}


def render_trend_panel(
    long_df: pd.DataFrame,
    place_dcids: list[str],
    citations: list[Citation],
    trends: dict[str, TrendResult] | None = None,
    saturated_places: set[str] | None = None,
    value_col: str = "value",
    unit_display: str | None = None,
    total_places: int | None = None,
    anomalies: list[Anomaly] | None = None,
    place_names: dict[str, str] | None = None,
) -> None:
    """Plot value-over-time lines for the given places, with optional fit lines.

    `total_places`, when given, renders a "showing N of M countries" caption
    so a limited selection is never silently mistaken for the full picture.
    `anomalies`, when given, overlays markers for anomalies in currently
    plotted countries and lists every detected anomaly (plotted or not) in
    a summary table below the chart.
    """
    require_citations(citations)
    trends = trends or {}
    saturated_places = saturated_places or set()
    anomalies = anomalies or []
    place_names = place_names or {}

    st.subheader("Trends over time")

    if total_places is not None:
        st.caption(f"Showing {len(place_dcids)} of {total_places} countries.")

    df = long_df[long_df["place_dcid"].isin(place_dcids)].sort_values("date")
    if df.empty:
        st.info("No time-series data for the selected places.")
        return

    plotted = set(place_dcids)
    anomalies_by_place: dict[str, list[Anomaly]] = {}
    for a in anomalies:
        anomalies_by_place.setdefault(a.place_dcid, []).append(a)

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

        # Anomaly markers: only spike/peer_outlier have a (date, value) point
        # to sit on. Reversal is a whole-series signal with nothing to mark.
        place_anomalies = [
            a for a in anomalies_by_place.get(place_dcid, []) if a.kind != "reversal"
        ]
        if place_anomalies:
            fig.add_trace(
                go.Scatter(
                    x=[a.date for a in place_anomalies],
                    y=[a.value for a in place_anomalies],
                    mode="markers",
                    marker=dict(size=13, symbol="circle-open", line=dict(width=2)),
                    name=f"{name}: {_KIND_LABELS.get(place_anomalies[0].kind, 'unusual')}",
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

    _render_anomaly_summary(anomalies, plotted, place_names)

    for c in citations:
        st.caption(f"Source: {c.render()}")


def _render_anomaly_summary(
    anomalies: list[Anomaly],
    plotted: set[str],
    place_names: dict[str, str],
) -> None:
    if not anomalies:
        return

    rows = []
    for a in anomalies:
        rows.append(
            {
                "place_dcid": a.place_dcid,
                "Country": place_names.get(a.place_dcid, a.place_dcid),
                "Type": _KIND_LABELS.get(a.kind, a.kind),
                "Year": a.date or "—",
                "Change": f"{a.change:+.1f}" if a.change is not None else "—",
                "Why it's flagged": a.detail,
                "On chart?": "Yes" if a.place_dcid in plotted else "Add it above ↑",
            }
        )
    summary = pd.DataFrame(rows).sort_values("On chart?")

    st.markdown(
        "**Unusual movements found across all countries, not just the ones charted**"
    )
    st.dataframe(
        summary.drop(columns="place_dcid"),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Why it's flagged": st.column_config.TextColumn(width="large"),
            "On chart?": st.column_config.TextColumn(width="small"),
        },
    )
    st.caption(
        "These are unusual *movements* in the data, not confirmed real-world "
        "events -- a flagged row can just as easily be a reporting correction "
        "or a change in survey method as an actual event. Treat this as a "
        "starting point for questions, not a verified fact."
    )
