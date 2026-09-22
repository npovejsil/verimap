"""Render a time-series trend panel for a set of countries.

Plotly, faceted by indicator when units differ, so two incompatible units
never share one y-axis. Overlays the OLS fit line for countries where a
trend was computed (saturated countries are shown as raw series only, with
no fit line, since their "trend" measures a ceiling, not progress), unless
`show_trend_lines` is off -- the caller wires that to a toggle so the raw
series can be read on its own.

When `target_value`/`target_year` are given (from the indicator's SDG
target, when it has a single fixed number), a target line and target-year
marker are drawn on the same axes -- this is the Trends tab absorbing what
used to be the separate Progress tab's headline chart element.

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
from recipe.i18n import Translator
from views.palette import active_tokens, apply_chart_chrome

_KIND_LABELS = {
    "spike": "Sudden jump/drop",
    "peer_outlier": "Breaking from the pack",
    "reversal": "Moving the wrong direction",
}


def render_trend_panel(
    long_df: pd.DataFrame,
    place_dcids: list[str],
    citations: list[Citation],
    t: Translator,
    trends: dict[str, TrendResult] | None = None,
    saturated_places: set[str] | None = None,
    value_col: str = "value",
    unit_display: str | None = None,
    indicator_label: str | None = None,
    total_places: int | None = None,
    anomalies: list[Anomaly] | None = None,
    place_names: dict[str, str] | None = None,
    show_trend_lines: bool = True,
    target_value: float | None = None,
    target_year: int | None = None,
) -> None:
    """Plot value-over-time lines for the given places, with optional fit lines.

    `total_places`, when given, renders a "showing N of M countries" caption
    so a limited selection is never silently mistaken for the full picture.
    `anomalies`, when given, overlays markers for anomalies in currently
    plotted countries and lists every detected anomaly (plotted or not) in
    a summary table below the chart. `indicator_label`, when given, is
    combined with `unit_display` into the y-axis title (e.g. "Electricity
    access (%)") -- a bare unit like "%" tells a first-time viewer nothing
    about what's actually being measured. `show_trend_lines` gates the
    dotted OLS fit-line overlay; the raw series are always shown regardless.
    `target_value`/`target_year` draw the SDG target as a horizontal/vertical
    reference line when the indicator has one.
    """
    require_citations(citations)
    trends = trends or {}
    saturated_places = saturated_places or set()
    anomalies = anomalies or []
    place_names = place_names or {}

    st.subheader(t.t("trends.title"))

    if target_value is None:
        st.caption(t.t("trends.no_fixed_target"))

    if total_places is not None:
        st.caption(f"Showing {len(place_dcids)} of {total_places} countries.")

    df = long_df[long_df["place_dcid"].isin(place_dcids)].sort_values("date")
    if df.empty:
        st.info(t.t("trends.empty"))
        return

    plotted = set(place_dcids)
    anomalies_by_place: dict[str, list[Anomaly]] = {}
    for a in anomalies:
        anomalies_by_place.setdefault(a.place_dcid, []).append(a)

    tok = active_tokens()
    fig = go.Figure()
    # Hues assigned in fixed slot order, never cycled: the same country keeps
    # its colour whatever else is on screen, and the order is what makes the
    # set separable under colour-vision deficiency.
    for slot, place_dcid in enumerate(place_dcids):
        color = tok.categorical[slot % len(tok.categorical)]
        place_df = df[df["place_dcid"] == place_dcid]
        if place_df.empty:
            continue
        name = (
            place_df["place_name"].iloc[0]
            if "place_name" in place_df.columns
            else place_dcid
        )
        label = (
            t.t("trends.saturated_legend", place=name)
            if place_dcid in saturated_places
            else name
        )

        fig.add_trace(
            go.Scatter(
                x=place_df["date"],
                y=place_df[value_col],
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=8, color=color, line=dict(width=2, color=tok.surface)),
                hovertemplate="%{y}<extra>" + label + "</extra>",
            )
        )

        trend = trends.get(place_dcid) if show_trend_lines else None
        if trend is not None:
            years = place_df["date"].astype(int)
            fit_y = trend.intercept + trend.slope * years
            fig.add_trace(
                go.Scatter(
                    x=place_df["date"],
                    y=fit_y,
                    mode="lines",
                    # Same hue as its series, dotted: the fit is an annotation
                    # on that country, not a second entity.
                    line=dict(dash="dot", color=color, width=2),
                    hoverinfo="skip",
                    name=t.t(
                        "trends.fit_legend", place=name, slope=t.signed(trend.slope)
                    ),
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

    if target_value is not None:
        target_label = (
            t.t(
                "trends.target_label_dated",
                value=f"{target_value:g}",
                year=target_year,
            )
            if target_year is not None
            else t.t("trends.target_label", value=f"{target_value:g}")
        )
        fig.add_hline(
            y=target_value,
            line_dash="dash",
            line_color=tok.muted,
            annotation_text=target_label,
            annotation_position="top left",
        )
    if target_year is not None:
        fig.add_vline(x=target_year, line_dash="dot", line_color=tok.muted)

    if indicator_label and unit_display:
        yaxis_title = t.t(
            "trends.axis_value_with_unit", indicator=indicator_label, unit=unit_display
        )
    else:
        yaxis_title = indicator_label or unit_display or t.t("trends.axis_value")

    fig.update_layout(
        yaxis_title=yaxis_title,
        xaxis_title=t.t("trends.axis_year"),
        hovermode="x unified",
    )
    apply_chart_chrome(fig, tok)
    st.plotly_chart(fig, use_container_width=True)

    _render_anomaly_summary(anomalies, plotted, place_names)

    for c in citations:
        st.caption(t.t("source.prefix", citation=c.render(t)))


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
