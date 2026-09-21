"""Render the sources & lineage trail beneath the tabs.

Collapsed by default: this is for the reader who wants to check a figure,
not a permanent fixture. The summary line above the fold is always visible,
so the section announces what it covers without being opened.

Everything rendered here comes from `recipe.lineage`, which computes it from
the catalog, the live response facets and the artifacts on disk. This module
only formats -- if a field is absent upstream it is reported as absent rather
than filled in, which is why there is no licence column: the Data Commons
facet publishes `provenanceUrl`, `unit` and `observationPeriod`, and no
licensing field at all.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from recipe.attribution import Citation, require_citations
from recipe.i18n import Translator
from recipe.lineage import CrossCheck, Lineage


def _check_row(check: CrossCheck, t: Translator) -> None:
    """One cross-check: verdict tag, what was compared, and the exceptions."""
    verdict = t.t("lineage.agrees" if check.passed else "lineage.differs")
    icon = "✅" if check.passed else "⚠️"
    st.markdown(f"{icon} **{t.t(f'lineage.check.{check.key}')}** — {verdict}")
    st.caption(t.t(f"lineage.detail.{check.key}"))

    figure = t.t(
        "lineage.of_total",
        agree=t.num(check.agree, 0),
        total=t.num(check.total, 0),
    )
    if check.total:
        figure += f" ({t.percent(check.share, 1)})"
    if check.note:
        figure += f" · {check.note}"
    st.caption(figure)

    if check.offenders:
        st.caption("· " + t.join([str(o) for o in check.offenders]))


def render_lineage_panel(
    lineage: Lineage,
    citations: list[Citation],
    t: Translator,
) -> None:
    """Render the panel. `citations` are the same ones the tabs above used."""
    require_citations(citations)

    st.divider()
    st.subheader(t.t("lineage.title"))

    st.caption(
        t.t(
            "lineage.summary",
            places=t.num(lineage.counts["places"], 0),
            geometries=t.num(lineage.counts["geometries"], 0),
            indicators=lineage.counts["indicators"],
            sources=lineage.counts["sources"],
        )
    )

    failing = [c for c in lineage.checks if not c.passed]
    if failing:
        st.caption(
            t.t(
                "lineage.checks_summary_failing",
                failed=len(failing),
                total=len(lineage.checks),
            )
        )
    else:
        st.caption(t.t("lineage.checks_summary_clean", total=len(lineage.checks)))

    with st.expander(t.t("lineage.show")):
        st.markdown(f"##### {t.t('lineage.sources_heading')}")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "agency": s.agency,
                        "provides": s.provides,
                        "id": s.id,
                        "url": s.url or "—",
                        "period": s.period,
                        "access": s.access,
                    }
                    for s in lineage.sources
                ]
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "agency": t.t("lineage.col_source"),
                "provides": t.t("lineage.col_provides"),
                "id": t.t("lineage.col_provenance"),
                "url": st.column_config.LinkColumn(t.t("lineage.col_url")),
                "period": t.t("lineage.col_period"),
                "access": t.t("lineage.col_access"),
            },
        )
        # Stated rather than left as an empty column: the absence of a
        # licence field upstream is itself a fact about this data.
        st.caption(t.t("lineage.no_licence"))

        st.markdown(f"##### {t.t('lineage.selected_heading')}")
        st.dataframe(
            pd.DataFrame([{"parameter": k, "value": v} for k, v in lineage.selection]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "parameter": t.t("lineage.col_parameter"),
                "value": t.t("lineage.col_value"),
            },
        )

        st.markdown(f"##### {t.t('lineage.fields_heading')}")
        st.dataframe(
            pd.DataFrame(
                [{"shown": f.shown, "field": f.field} for f in lineage.fields]
            ),
            use_container_width=True,
            hide_index=True,
            column_config={
                "shown": t.t("lineage.col_shown"),
                "field": t.t("lineage.col_field"),
            },
        )

        st.markdown(f"##### {t.t('lineage.applied_heading')}")
        st.markdown("\n".join(f"- {t.t(step)}" for step in lineage.transformations))

        st.markdown(f"##### {t.t('lineage.checks_heading')}")
        st.caption(t.t("lineage.checks_note"))
        for check in lineage.checks:
            _check_row(check, t)

        st.markdown(f"##### {t.t('lineage.cite_heading')}")
        cite = "\n".join(c.render(t) for c in citations)
        st.code(
            t.t(
                "lineage.citation",
                citations=cite,
                generated=lineage.generated,
                catalog=lineage.catalog_built or "—",
            ),
            language=None,
        )
        st.caption(t.t("lineage.untranslated"))
