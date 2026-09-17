"""Render the JoinSpec as a visible compatibility panel.

This panel is the pitch's centerpiece: it makes the key-matching engine's
verdict visible before any join or plot happens, so the "recipe"
automatically discovering overlapping keys is something the user sees, not
something they have to trust blindly.
"""

from __future__ import annotations

import streamlit as st

from recipe.catalog import Indicator
from recipe.keymatch import JoinSpec

_COMPARABILITY_LABELS = {
    "direct": "✅ Direct — can be joined, plotted, and differenced",
    "axes_only": "⚠️ Axes only — can be plotted on two axes, arithmetic disabled",
    "blocked": "🚫 Blocked — cannot be combined",
}


def render_compatibility_panel(
    left: Indicator, right: Indicator, spec: JoinSpec
) -> None:
    """Render the compatibility panel. Always visible, never in an expander."""
    st.subheader("Compatibility")
    st.markdown(
        f"**{left.label}** ({left.source_agency}) × **{right.label}** "
        f"({right.source_agency})"
    )

    cols = st.columns(4)
    cols[0].metric(
        "Place overlap",
        f"{spec.place_overlap.n_shared} / {spec.place_overlap.n_left}",
        f"Jaccard {spec.place_overlap.jaccard:.2f}",
    )
    cols[1].metric(
        "Shared years", spec.shared_years if spec.shared_years is not None else "—"
    )
    cols[2].metric("Unit relation", spec.unit_relation)
    cols[3].metric("Join keys", ", ".join(spec.join_keys))

    st.markdown(_COMPARABILITY_LABELS.get(spec.comparability, spec.comparability))

    if spec.shared_dimensions:
        rows = [
            f"- **{dim}**: `{m.left_value}` ↔ `{m.right_value}` "
            + (f"→ canonical `{m.canonical}`" if m.canonical else "→ **unresolved**")
            for dim, m in spec.shared_dimensions.items()
        ]
        st.markdown("Shared dimensions:\n" + "\n".join(rows))

    for w in spec.warnings:
        st.warning(w)
    for b in spec.blockers:
        st.error(b)
