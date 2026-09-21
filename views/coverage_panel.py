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
from recipe.i18n import Translator
from views.palette import active_tokens, apply_chart_chrome


def render_coverage_panel(
    long_df: pd.DataFrame,
    report: CoverageReport,
    citations: list[Citation],
    expected_start: int,
    expected_end: int,
    t: Translator,
) -> None:
    require_citations(citations)

    st.subheader(t.t("coverage.title"))

    cols = st.columns(2)
    cols[0].metric(t.t("coverage.places_reporting"), report.n_places_total)
    cols[1].metric(
        t.t("coverage.completeness"),
        t.percent(1 - report.missing_share, 1),
        t.t("coverage.missing_cells", count=report.n_missing_cells),
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

    tok = active_tokens()
    fig = px.imshow(
        display_grid,
        # Binary presence: the "missing" end sits at the surface colour so a
        # hole reads as absence rather than as a low value.
        color_continuous_scale=[
            [0, f"rgb{tok.no_data[:3]}"],
            [1, tok.categorical[0]],
        ],
        aspect="auto",
        labels=dict(
            x=t.t("coverage.axis_year"),
            y=t.t("coverage.axis_place"),
            color=t.t("coverage.axis_observed"),
        ),
    )
    fig.update_layout(
        height=max(300, min(1200, 12 * len(display_grid))),
        coloraxis_showscale=False,
    )
    apply_chart_chrome(fig, tok, legend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(t.t("coverage.stalest_header"))
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
            "place_dcid": t.t("gap.col_country"),
            "latest_year": t.t("coverage.col_latest_year"),
        },
    )

    if missing_rows:
        csv = pd.DataFrame(missing_rows).to_csv(index=False)
        st.download_button(
            t.t("coverage.download"),
            data=csv,
            file_name="coverage_gaps.csv",
            mime="text/csv",
        )

    for c in citations:
        st.caption(t.t("source.prefix", citation=c.render(t)))
