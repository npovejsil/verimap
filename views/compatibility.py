"""Render the JoinSpec as a visible compatibility panel.

This panel is the pitch's centerpiece and renders above every tab, so it's
the first thing anyone reads. The audience is not just analysts -- it's
non-technical stakeholders too -- so every label here is plain language,
never a raw stat term, enum value, or DCID column name.
"""

from __future__ import annotations

import streamlit as st

from recipe.catalog import Indicator
from recipe.i18n import Translator
from recipe.keymatch import JoinSpec

# Maps the JoinSpec.comparability ENUM to a locale key. The dict keys are
# program values compared at app.py and views/bivariate.py -- never translate
# them. Only what they resolve to is language-dependent.
_COMPARABILITY_KEYS = {
    "direct": "compare.verdict_direct",
    "axes_only": "compare.verdict_axes_only",
    "blocked": "compare.verdict_blocked",
}


def _dimension_label(dim: str, canonical: str, dimensions: dict) -> str:
    """Human label for a canonical dimension value.

    Prefers the `label:` in catalog/dimensions.yml over deriving English from
    the identifier (`rural` -> "Rural"), which is what this used to do and
    which cannot work in any other language. These labels are still English;
    they are a small closed set and out of scope for the locale files.
    """
    values = (dimensions.get(dim) or {}).get("canonical_values") or {}
    label = (values.get(canonical) or {}).get("label")
    return label or canonical.replace("_", " ").title()


def render_compatibility_panel(
    left: Indicator,
    right: Indicator,
    spec: JoinSpec,
    t: Translator,
    left_label: str | None = None,
    right_label: str | None = None,
    dimensions: dict | None = None,
) -> None:
    """Render the compatibility panel. Always visible, never in an expander."""
    dimensions = dimensions or {}
    st.subheader(t.t("compare.title"))

    external = t.t("compare.external_source")
    st.markdown(
        t.t(
            "compare.pair",
            left=left_label or left.label,
            left_source=left.source_agency or external,
            right=right_label or right.label,
            right_source=right.source_agency or external,
        )
    )

    if not left.dcid.startswith("undata/") or not right.dcid.startswith("undata/"):
        st.caption(t.t("compare.outside_un"))

    cols = st.columns(2)
    max_places = max(spec.place_overlap.n_left, spec.place_overlap.n_right)
    cols[0].metric(
        t.t("compare.countries_both"),
        t.t(
            "compare.countries_both_value",
            shared=spec.place_overlap.n_shared,
            total=max_places,
        ),
        t.t(
            "compare.countries_only_one",
            count=max_places - spec.place_overlap.n_shared,
        ),
        delta_color="off",
    )
    cols[1].metric(
        t.t("compare.years_both"),
        (
            spec.shared_years
            if spec.shared_years is not None
            else t.t("compare.none_marker")
        ),
    )

    verdict_key = _COMPARABILITY_KEYS.get(spec.comparability)
    st.markdown(t.t(verdict_key) if verdict_key else spec.comparability)

    if spec.shared_dimensions:
        rows = [
            (
                t.t(
                    "compare.dimension_shared",
                    dimension=_dimension_label(dim, m.canonical, dimensions),
                )
                if m.canonical
                else t.t("compare.dimension_unmatched", dimension=dim)
            )
            for dim, m in spec.shared_dimensions.items()
        ]
        st.markdown("\n".join(rows))

    for w in spec.warnings:
        st.warning(w)
    for b in spec.blockers:
        st.error(b)
