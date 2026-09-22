"""Render the progress-toward-target summary table.

Companion to `views/trend_panel.py`, which now draws the target line and
target-year marker directly on the Trends chart (the two used to live on
separate tabs; the chart-with-target-overlay is trend_panel's job now).
This module keeps the sharper, tabular question a chart can't answer at a
glance: is this specific place on track, and by when.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.progress import ProgressResult


def render_progress_summary(
    df: pd.DataFrame,
    place_dcids: list[str],
    progress: dict[str, ProgressResult],
    target_value: float | None,
    target_year: int | None,
) -> None:
    st.subheader("Progress toward the target")
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
