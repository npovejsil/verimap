"""Render convergence and archetype analyses, each with its critique attached.

Per design: a coefficient or a cluster label ships together with the
specific reason it might be misleading, on the same screen, not as a
footnote elsewhere. This module enforces that pairing structurally --
there is no render function here that shows a result without its caveat.
Copy throughout is written for a non-technical reader: no unexplained
statistics vocabulary in the main flow.

Both render functions optionally take a `priority_ranks` lookup so a named
country can show its existing Priority-tab rank inline ("priority rank #3
of 194") -- this is a pointer to a score that tab already computes, never a
new metric invented here.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.archetypes import ArchetypeResult, GroupRanking
from analytics.convergence import ConvergenceMovers, ConvergenceResult
from recipe.attribution import Citation, require_citations

# Below this share of countries having both years, the "fastest/slowest"
# lists get an explicit coverage caveat -- naming winners and losers out of
# a small, silently-unstated slice of the data is the exact failure this
# codebase's other caveats (ceiling effect, cluster causality) already guard
# against.
_LOW_COVERAGE_THRESHOLD = 0.8


def _priority_suffix(
    place_dcid: str,
    priority_ranks: dict[str, int] | None,
    priority_total: int | None,
) -> str:
    if not priority_ranks or priority_total is None:
        return ""
    rank = priority_ranks.get(place_dcid)
    if rank is None:
        return ""
    return f" (priority rank #{rank} of {priority_total})"


def render_convergence(
    result: ConvergenceResult | None,
    indicator_label: str,
    base_year: str,
    end_year: str,
    citations: list[Citation],
    movers: ConvergenceMovers | None = None,
    place_names: dict[str, str] | None = None,
    priority_ranks: dict[str, int] | None = None,
    priority_total: int | None = None,
    total_places: int | None = None,
) -> None:
    require_citations(citations)
    place_names = place_names or {}
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

    if total_places and result.n_places / total_places < _LOW_COVERAGE_THRESHOLD:
        st.caption(
            f"⚠️ Only {result.n_places} of {total_places} countries "
            f"({result.n_places / total_places:.0%}) have data for both "
            f"{base_year} and {end_year} -- the lists below are drawn from "
            "that smaller set, not the full picture."
        )

    if movers is not None:
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Catching up fastest**")
            _render_mover_list(
                movers.catching_up,
                base_year,
                end_year,
                place_names,
                priority_ranks,
                priority_total,
            )
        with cols[1]:
            st.markdown("**Falling further behind**")
            _render_mover_list(
                movers.falling_behind,
                base_year,
                end_year,
                place_names,
                priority_ranks,
                priority_total,
            )
        st.caption(
            f"Both lists are drawn from the {movers.n_behind} countries that "
            f"started at or below the typical (median) level in {base_year} "
            "-- countries already ahead at the start aren't 'catching up' by "
            "definition, so they're excluded from both lists."
        )

    st.warning(
        f"**Be careful with this**: {result.ceiling_share:.0%} of countries were "
        "already near the maximum possible score at the start or end of this "
        "period. When a measurement has a ceiling, it can look like catch-up is "
        "happening even when it isn't really — so treat this as a hint to look "
        "closer, not a proven trend."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")


def _render_mover_list(
    df: pd.DataFrame,
    base_year: str,
    end_year: str,
    place_names: dict[str, str],
    priority_ranks: dict[str, int] | None,
    priority_total: int | None,
) -> None:
    if df.empty:
        st.caption("Not enough countries to list.")
        return
    for _, row in df.iterrows():
        name = place_names.get(row["place_dcid"], row["place_dcid"])
        suffix = _priority_suffix(row["place_dcid"], priority_ranks, priority_total)
        st.markdown(
            f"- **{name}**: {row['base_value']:.1f} → {row['end_value']:.1f}"
            f"{suffix}"
        )


def render_archetypes(
    result: ArchetypeResult | None,
    feature_labels: dict[str, str],
    citations: list[Citation],
    group_ranking: GroupRanking | None = None,
    place_names: dict[str, str] | None = None,
    priority_ranks: dict[str, int] | None = None,
    priority_total: int | None = None,
) -> None:
    require_citations(citations)
    place_names = place_names or {}
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

    if group_ranking is not None:
        worst_members = result.labels[
            result.labels == group_ranking.worst_cluster
        ].index
        st.markdown(
            f"**Group {group_ranking.worst_cluster + 1} needs the most attention** "
            f"-- it has the worst average on "
            f"{feature_labels.get(group_ranking.indicator_key, group_ranking.indicator_key)} "
            f"({group_ranking.worst_value:.1f})."
        )
        names_with_rank = [
            f"{place_names.get(p, p)}{_priority_suffix(p, priority_ranks, priority_total)}"
            for p in sorted(worst_members, key=lambda p: place_names.get(p, p))
        ]
        st.caption(f"Countries in this group: {', '.join(names_with_rank)}")

    st.warning(
        "**These groups are a starting point, not an answer.** They're based "
        "only on the numbers we gave it — the computer doesn't know anything "
        "about each country's history, geography, or politics. Use this to "
        "prompt questions, not to explain them, and re-run with different "
        "indicators before trusting a label you put on a group."
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")
