"""Render the JoinSpec as a visible compatibility panel.

This panel is the pitch's centerpiece and renders above every tab, so it's
the first thing anyone reads. The audience is not just analysts -- it's
non-technical stakeholders too -- so every label here is plain language,
never a raw stat term, enum value, or DCID column name.
"""

from __future__ import annotations

import streamlit as st

from recipe.catalog import Indicator
from recipe.keymatch import JoinSpec

_COMPARABILITY_LABELS = {
    "direct": "✅ These can be compared directly — same measurement, comparable scale.",
    "axes_only": (
        "⚠️ These can be shown side by side, but not subtracted or divided — "
        "they're measured in different units."
    ),
    "blocked": "🚫 These can't be compared — no overlapping countries or years.",
}


def render_compatibility_panel(
    left: Indicator, right: Indicator, spec: JoinSpec
) -> None:
    """Render the compatibility panel. Always visible, never in an expander."""
    st.subheader("Can we compare these two?")

    left_source = left.source_agency or "external source"
    right_source = right.source_agency or "external source"
    st.markdown(
        f"**{left.label}** ({left_source}) × **{right.label}** ({right_source})"
    )

    if not left.dcid.startswith("undata/") or not right.dcid.startswith("undata/"):
        st.caption("🌐 One of these sources is outside the UN statistical system.")

    cols = st.columns(2)
    max_places = max(spec.place_overlap.n_left, spec.place_overlap.n_right)
    cols[0].metric(
        "Countries covered by both",
        f"{spec.place_overlap.n_shared} of {max_places}",
        f"{max_places - spec.place_overlap.n_shared} countries only in one source",
        delta_color="off",
    )
    cols[1].metric(
        "Years both sources report",
        spec.shared_years if spec.shared_years is not None else "—",
    )

    st.markdown(_COMPARABILITY_LABELS.get(spec.comparability, spec.comparability))

    if spec.shared_dimensions:
        rows = [
            (
                f"- Both sources break this down the same way: "
                f"**{m.canonical.replace('_', ' ').title()}**"
                if m.canonical
                else f"- **{dim}**: the two sources categorize this differently and "
                "we couldn't line them up"
            )
            for dim, m in spec.shared_dimensions.items()
        ]
        st.markdown("\n".join(rows))

    for w in spec.warnings:
        st.warning(w)
    for b in spec.blockers:
        st.error(b)
