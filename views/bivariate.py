"""Cross-plot two indicators to find where resources maximize impact.

Point size encodes population, color encodes continent. Quadrant lines sit
at population-weighted medians. The bottom-left quadrant (low on both axes)
is the headroom quadrant -- where a resource has the most room to move both
indicators meaningfully.

Legality of the plot itself follows the JoinSpec's comparability verdict:
`axes_only` pairs may be plotted here (two separate axes, no arithmetic)
even when a difference/ratio between them would be blocked.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from recipe.attribution import Citation, require_citations
from recipe.keymatch import JoinSpec
from recipe.validation import drop_missing


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    """Population-weighted median, used for quadrant boundaries."""
    order = values.sort_values().index
    v = values.loc[order]
    w = weights.loc[order]
    cum = w.cumsum()
    half = w.sum() / 2
    return float(v[cum >= half].iloc[0])


def render_bivariate(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
    spec: JoinSpec,
    citations: list[Citation],
    size_col: str | None = None,
    color_col: str | None = None,
) -> None:
    """Render the gap-analysis scatter. Requires spec.comparability != 'blocked'."""
    require_citations(citations)

    if spec.comparability == "blocked":
        st.error(
            f"Cannot plot {x_label} against {y_label}: " + "; ".join(spec.blockers)
        )
        return

    st.subheader("Gap analysis: where does a resource move the most people?")

    plot_df = df.dropna(subset=[x_col, y_col]).copy()
    if plot_df.empty:
        st.info("No overlapping observations to plot.")
        return

    # Point size comes from a left join on population, so a country the
    # denominator does not cover arrives here as NaN -- which plotly rejects
    # outright rather than skipping. Drop those rows from the sized plot and
    # say so, rather than letting them disappear without explanation.
    size_report = None
    if size_col and size_col in plot_df.columns:
        plot_df, size_report = drop_missing(
            plot_df, [size_col], f"no {size_col} figure available to size the point"
        )
        if plot_df.empty:
            st.info("No overlapping observations to plot.")
            return

    fig = px.scatter(
        plot_df,
        x=x_col,
        y=y_col,
        size=size_col,
        color=color_col,
        hover_name="place_name" if "place_name" in plot_df.columns else None,
        labels={x_col: x_label, y_col: y_label},
    )

    if size_col and size_col in plot_df.columns and plot_df[size_col].sum() > 0:
        x_ref = weighted_median(plot_df[x_col], plot_df[size_col])
        y_ref = weighted_median(plot_df[y_col], plot_df[size_col])
    else:
        x_ref = plot_df[x_col].median()
        y_ref = plot_df[y_col].median()

    fig.add_vline(x=x_ref, line_dash="dash", line_color="gray")
    fig.add_hline(y=y_ref, line_dash="dash", line_color="gray")
    fig.add_annotation(
        x=plot_df[x_col].min(),
        y=plot_df[y_col].min(),
        text="low / low — highest headroom",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(color="gray", size=11),
    )

    st.plotly_chart(fig, use_container_width=True)

    if size_report is not None and size_report.n_dropped:
        st.caption(size_report.message())

    if spec.comparability == "axes_only":
        st.caption(
            "Units differ between these indicators — plotted on separate "
            "axes only. Differences/ratios between them are disabled."
        )
    for w in spec.warnings:
        st.caption(f"⚠️ {w}")

    for c in citations:
        st.caption(f"Source: {c.render()}")
