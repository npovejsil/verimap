"""Render convergence and archetype analyses, each with its critique attached.

Per design: a coefficient or a cluster label ships together with the
specific reason it might be misleading, on the same screen, not as a
footnote elsewhere. This module enforces that pairing structurally --
there is no render function here that shows a result without its caveat.
Copy throughout is written for a non-technical reader: no unexplained
statistics vocabulary in the main flow.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.archetypes import ArchetypeResult
from analytics.convergence import ConvergenceResult
from recipe.attribution import Citation, require_citations


def render_convergence(
    result: ConvergenceResult | None,
    indicator_label: str,
    base_year: str,
    end_year: str,
    citations: list[Citation],
) -> None:
    require_citations(citations)
    st.markdown(
        f"**Are lagging countries catching up?** ({indicator_label}, "
        f"{base_year}–{end_year})"
    )

    if result is None:
        st.info("Not enough places with data in both years to check for catch-up.")
        return

    catch_up = "Yes, some catch-up" if result.beta < 0 else "No catch-up detected"
    st.metric("Catch-up signal", f"{catch_up} ({result.beta:+.2f})")

    with st.expander("Show the statistics behind this"):
        cols = st.columns(3)
        cols[0].metric("β (negative = convergence)", f"{result.beta:.3f}")
        cols[1].metric(
            "95% CI", f"[{result.beta_ci_low:.3f}, {result.beta_ci_high:.3f}]"
        )
        cols[2].metric("R²", f"{result.r_squared:.2f}")

    st.warning(
        f"**Be careful with this**: {result.ceiling_share:.0%} of countries were "
        "already near the maximum possible score at the start or end of this "
        "period. When a measurement has a ceiling, it can look like catch-up is "
        "happening even when it isn't really — so treat this as a hint to look "
        "closer, not a proven trend."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")


def render_archetypes(
    result: ArchetypeResult | None,
    feature_labels: dict[str, str],
    citations: list[Citation],
) -> None:
    require_citations(citations)
    st.markdown("**Groups of similar countries**")

    if result is None:
        st.info("Not enough places with complete data across the selected indicators.")
        return

    with st.expander("How we chose the number of groups"):
        st.caption(
            f"{result.k_used} groups chosen by silhouette score "
            f"({', '.join(f'k={k}: {v:.2f}' for k, v in sorted(result.silhouette_by_k.items()))})."
        )

    display_centers = result.cluster_centers.rename(columns=feature_labels)
    display_centers.index = [f"Group {i + 1}" for i in display_centers.index]
    display_centers.index.name = "Group"
    st.dataframe(display_centers.round(1), use_container_width=True)

    counts = result.labels.value_counts().sort_index()
    fig = px.bar(
        x=[f"Group {i + 1}" for i in counts.index],
        y=counts.values,
        labels={"x": "Group", "y": "Countries"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.warning(
        "**These groups are a starting point, not an answer.** They're based "
        "only on the numbers we gave it — the computer doesn't know anything "
        "about each country's history, geography, or politics. Use this to "
        "prompt questions, not to explain them, and re-run with different "
        "indicators before trusting a label you put on a group."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")
