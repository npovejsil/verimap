"""Render the priority table: one row per country, one column per score component.

No black box: the composite priority_score is a weighted sum of the
rank_* columns shown alongside it, and the weights are exposed as sliders
so the ranking's sensitivity is visible, not hidden.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from recipe.attribution import Citation, require_citations


def render_priority_table(
    scored_df: pd.DataFrame,
    citations: list[Citation],
    headline_total_unserved: float | None = None,
) -> None:
    require_citations(citations)

    st.subheader("Priority: where does more electrification reach the most people?")

    if headline_total_unserved is not None:
        st.metric(
            "Total population without electricity access",
            f"{headline_total_unserved / 1e6:,.1f} M",
        )

    st.caption(
        "priority_score is a weighted average of the rank_* columns below — "
        "sort by any single component to see what's driving the ranking."
    )

    display_cols = ["place_name", "priority_score"] + [
        c for c in scored_df.columns if c.startswith("rank_")
    ]
    display_cols = [c for c in display_cols if c in scored_df.columns]

    st.dataframe(
        scored_df[display_cols].reset_index(drop=True),
        use_container_width=True,
        column_config={
            "priority_score": st.column_config.ProgressColumn(
                "Priority score", min_value=0, max_value=1
            ),
        },
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")
