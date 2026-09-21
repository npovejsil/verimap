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
from recipe.i18n import Translator
from recipe.keymatch import JoinSpec
from recipe.validation import drop_missing
from views.palette import active_tokens, apply_chart_chrome


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
    t: Translator,
    size_col: str | None = None,
) -> None:
    """Render the gap-analysis scatter. Requires spec.comparability != 'blocked'.

    Deliberately a single series. This used to colour points by continent,
    which put seven hues on a chart where every pair is compared at once --
    a test the eight-slot palette fails badly (green vs orange reads as
    ΔE 3.2 to a protanope). Region is a filter above the chart instead, so
    the same question is answerable without an unreadable legend.
    """
    require_citations(citations)

    if spec.comparability == "blocked":
        st.error(
            t.t(
                "gap.cannot_plot",
                x=x_label,
                y=y_label,
                reasons=t.blockers(spec),
            )
        )
        return

    st.subheader(t.t("gap.title"))

    plot_df = df.dropna(subset=[x_col, y_col]).copy()
    if plot_df.empty:
        st.info(t.t("gap.empty"))
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

    tok = active_tokens()
    fig = px.scatter(
        plot_df,
        x=x_col,
        y=y_col,
        size=size_col,
        hover_name="place_name" if "place_name" in plot_df.columns else None,
        labels={x_col: x_label, y_col: y_label},
    )
    # A surface-coloured ring keeps overlapping points readable where the
    # cloud is dense, which is exactly where the interesting countries are.
    fig.update_traces(
        marker=dict(
            color=tok.series,
            opacity=0.85,
            line=dict(width=2, color=tok.surface),
            sizemin=5,
        )
    )

    if size_col and size_col in plot_df.columns and plot_df[size_col].sum() > 0:
        x_ref = weighted_median(plot_df[x_col], plot_df[size_col])
        y_ref = weighted_median(plot_df[y_col], plot_df[size_col])
    else:
        x_ref = plot_df[x_col].median()
        y_ref = plot_df[y_col].median()

    fig.add_vline(x=x_ref, line_dash="dash", line_width=1, line_color=tok.baseline)
    fig.add_hline(y=y_ref, line_dash="dash", line_width=1, line_color=tok.baseline)
    fig.add_annotation(
        x=plot_df[x_col].min(),
        y=plot_df[y_col].min(),
        text=t.t("gap.headroom_annotation"),
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(color=tok.muted, size=11),
    )

    apply_chart_chrome(fig, tok, legend=False)
    st.plotly_chart(fig, use_container_width=True)

    if size_report is not None and size_report.n_dropped:
        st.caption(size_report.message())

    if spec.comparability == "axes_only":
        st.caption(t.t("gap.axes_only_note"))
    for w in spec.warnings:
        st.caption(f"⚠️ {w}")

    for c in citations:
        st.caption(t.t("source.prefix", citation=c.render(t)))
