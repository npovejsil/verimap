"""Render where the numbers come from, and whether each pull still checks out.

Written for the same non-technical audience as the rest of the app, so the
column headings are plain language and every warning is shown as readable
text rather than hidden behind an icon.

The "Actually produced by" column is the point of this panel. The World Bank
republishes a great deal of data it did not collect, so a chart labelled
"World Bank" can be IEA numbers, and two sources that look independent can
turn out to be one dataset seen twice.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from recipe.source_checks import PullCheck, summarize
from recipe.sources import Source

_STATUS_LABEL = {
    "pass": "✅ Checks out",
    "warn": "⚠️ Check the note",
    "fail": "🚫 Not usable",
}


def render_sources_panel(checks: list[PullCheck], sources: dict[str, Source]) -> None:
    """Render one section per source, each listing its indicator pulls."""
    st.subheader("Where these numbers come from")
    st.caption(
        "Every indicator is re-fetched and re-checked against what the catalog "
        "expects — the right units, a sensible value range, the expected number "
        "of countries, and country codes that will actually land on the map."
    )

    counts = summarize(checks)
    a, b, c = st.columns(3)
    a.metric("Pulls checking out", counts["pass"])
    b.metric("With a caveat", counts["warn"])
    c.metric("Not usable", counts["fail"])

    for source_id, source in sources.items():
        source_checks = [c for c in checks if c.source_id == source_id]
        st.markdown(f"### {source.label}")
        st.caption(f"`{source.base_url}` — last reviewed by hand {source.verified_on}")
        if source.notes:
            st.caption(source.notes)

        if not source_checks:
            st.info("No indicators are set up for this source yet.")
            continue

        rows = [
            {
                "Indicator": c.indicator_label,
                "Status": _STATUS_LABEL[c.status],
                "Actually produced by": c.upstream_source or source.label,
                "Countries": c.n_places,
                "Most recent year": c.latest_date or "—",
                "Response time": f"{c.elapsed_ms} ms",
            }
            for c in source_checks
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Findings are spelled out rather than summarised into the table: a
        # warning nobody can read is the same as no warning at all.
        for check in source_checks:
            if check.error:
                st.error(f"**{check.indicator_label}** — {check.error}")
            for finding in check.findings:
                text = f"**{check.indicator_label}** — {finding.message}"
                if finding.level == "error":
                    st.error(text)
                else:
                    st.warning(text)
