"""Render convergence and archetype analyses, each with its critique attached.

Per design: a coefficient or a cluster label ships together with the
specific reason it might be misleading, on the same screen, not as a
footnote elsewhere. This module enforces that pairing structurally --
there is no render function here that shows a result without its caveat.
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
    st.markdown(f"**Beta-convergence: {indicator_label}, {base_year} → {end_year}**")

    if result is None:
        st.info(
            "Not enough places with data in both years to fit a convergence regression."
        )
        return

    cols = st.columns(3)
    cols[0].metric("β (negative = convergence)", f"{result.beta:.3f}")
    cols[1].metric(
        "95% CI",
        f"[{result.beta_ci_low:.3f}, {result.beta_ci_high:.3f}]",
    )
    cols[2].metric("R²", f"{result.r_squared:.2f}")

    st.warning(
        f"**Read this coefficient with its ceiling effect**: {result.ceiling_share:.0%} "
        f"of places are at or near the reporting ceiling in the base or end year. "
        "A capped metric mechanically produces a negative β even without genuine "
        "catch-up, and pure noise produces a negative β too (regression to the "
        "mean / Galton's fallacy). This number is a screening signal, not "
        "evidence of convergence on its own."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")


def render_archetypes(
    result: ArchetypeResult | None,
    feature_labels: dict[str, str],
    citations: list[Citation],
) -> None:
    require_citations(citations)
    st.markdown("**Country archetypes**")

    if result is None:
        st.info("Not enough places with complete data across the selected indicators.")
        return

    st.caption(
        f"k={result.k_used} clusters chosen by silhouette score "
        f"({', '.join(f'k={k}: {v:.2f}' for k, v in sorted(result.silhouette_by_k.items()))})."
    )

    display_centers = result.cluster_centers.rename(columns=feature_labels)
    st.dataframe(display_centers.round(1), use_container_width=True)

    counts = result.labels.value_counts().sort_index()
    fig = px.bar(
        x=[f"Cluster {i}" for i in counts.index],
        y=counts.values,
        labels={"x": "Cluster", "y": "Countries"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.warning(
        "**These clusters are descriptive, not causal.** KMeans groups countries "
        "by statistical similarity on the selected indicators alone -- it knows "
        "nothing about history, geography, or policy. Treat cluster membership as "
        "a starting point for investigation, not an explanation, and re-run with "
        "different features before trusting a narrative label."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")
