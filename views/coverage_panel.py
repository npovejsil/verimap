"""Render the data coverage / gap-finder tab.

This is the "help researchers find data they need" deliverable: a place x
year completeness heatmap, staleness ranking, and a downloadable CSV of the
holes, so a researcher can tell in seconds whether an indicator has the
grain and recency they need before writing a query against it.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.coverage import CoverageReport, coverage_heatmap_data
from recipe.attribution import Citation, require_citations


def render_coverage_panel(
    long_df: pd.DataFrame,
    report: CoverageReport,
    citations: list[Citation],
    expected_start: int,
    expected_end: int,
) -> None:
    require_citations(citations)

    st.subheader("Data coverage")

    cols = st.columns(2)
    cols[0].metric("Places reporting", report.n_places_total)
    cols[1].metric(
        "Completeness",
        f"{1 - report.missing_share:.1%}",
        f"{report.n_missing_cells} missing cells",
    )

    st.caption(
        f"Grid assumes every place should report annually from "
        f"{expected_start}-{expected_end}. A place with a genuinely shorter "
        "reporting history shows as 'missing' years it was never expected "
        "to report — this is a completeness check against a uniform grid, "
        "not against each place's own known start date."
    )

    grid = coverage_heatmap_data(long_df, expected_start, expected_end)

    # Compute missing cells from the DCID-indexed grid first -- the display
    # grid below may remap to place names, and names can collide (e.g. two
    # DCIDs with no resolved name both fall back to NaN), which breaks
    # scalar .loc lookups on a non-unique index.
    missing_mask = grid == 0
    missing_rows = [
        {"place_dcid": p, "date": y}
        for p in grid.index
        for y in grid.columns
        if missing_mask.loc[p, y]
    ]

    display_grid = grid.copy()
    if "place_name" in long_df.columns:
        names = long_df.drop_duplicates("place_dcid").set_index("place_dcid")[
            "place_name"
        ]
        resolved = names.reindex(display_grid.index)
        display_grid.index = resolved.where(resolved.notna(), display_grid.index)

    fig = px.imshow(
        display_grid,
        color_continuous_scale=[[0, "#e5e5e5"], [1, "#2166ac"]],
        aspect="auto",
        labels=dict(x="Year", y="Place", color="Observed"),
    )
    fig.update_layout(height=max(300, min(1200, 12 * len(display_grid))))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Least up-to-date countries** (oldest latest-reported year)")
    stale_df = pd.DataFrame(
        report.stalest_places, columns=["place_dcid", "latest_year"]
    )
    if "place_name" in long_df.columns:
        names = long_df.drop_duplicates("place_dcid").set_index("place_dcid")[
            "place_name"
        ]
        resolved = names.reindex(stale_df["place_dcid"])
        stale_df["place_dcid"] = resolved.where(
            resolved.notna(), stale_df["place_dcid"]
        ).values
    st.dataframe(
        stale_df,
        use_container_width=True,
        column_config={
            "place_dcid": "Country",
            "latest_year": "Most recent year reported",
        },
    )

    if missing_rows:
        csv = pd.DataFrame(missing_rows).to_csv(index=False)
        st.download_button(
            "Download missing (place, year) cells as CSV",
            data=csv,
            file_name="coverage_gaps.csv",
            mime="text/csv",
        )

    for c in citations:
        st.caption(f"Source: {c.render()}")
