"""Streamlit entrypoint for the cross-agency UN SDG dashboard.

Thin by design: this file wires the catalog, client, and views together.
Logic lives in recipe/, analytics/, and views/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from analytics.anomalies import detect_anomalies
from analytics.archetypes import compute_archetypes, rank_groups_by_indicator
from analytics.convergence import compute_convergence, rank_convergence_movers
from analytics.coverage import compute_coverage
from analytics.gap_scoring import priority_score, unserved_population
from analytics.progress import compute_progress
from analytics.trends import fit_trends_excluding_saturated
from recipe.attribution import citation_for_indicator
from recipe.cache import cached_data
from recipe.catalog import load_catalog, selectable_indicators
from recipe.datacommons_client import get_client
from recipe.source_checks import check_all_pulls
from recipe.sources import client_for_indicator, load_sources
from recipe.frames import (
    attach_place_names,
    point_within_to_long,
    series_within_to_long,
)
from recipe.geography import audit_join, country_to_continent, fetch_country_geojson
from recipe.i18n import DEFAULT_LOCALE, get_translator, load_locales
from recipe.keymatch import compute_join_spec
from recipe.lineage import build_lineage, cross_source_check
from recipe.validation import check_mixed_dates
from views.bivariate import render_bivariate
from views.choropleth import render_choropleth
from views.compatibility import render_compatibility_panel
from views.coverage_panel import render_coverage_panel
from views.insights_panel import render_archetypes, render_convergence
from views.lineage_panel import render_lineage_panel
from views.picker import indicator_option_label
from views.priority_table import render_priority_table
from views.progress_panel import render_progress_panel
from views.sources_panel import render_sources_panel
from views.trend_panel import render_trend_panel

# Runs at import, before any widget exists, so this one string cannot follow
# the language switcher -- it stays English rather than lagging a rerun behind.
st.set_page_config(page_title="UN SDG Cross-Agency Dashboard", layout="wide")


@cached_data(ttl=3600)
def _load_geojson() -> dict:
    # Geometry is Data Commons only -- the World Bank API serves no shapes.
    client = get_client()
    return fetch_country_geojson(client)


@cached_data(ttl=3600)
def _load_indicator_point_payload(dcid_key: str):
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = client_for_indicator(indicator)
    return client.point_within("Earth", "Country", [indicator.dcid])


@cached_data(ttl=3600)
def _load_indicator_latest(dcid_key: str) -> pd.DataFrame:
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = client_for_indicator(indicator)
    payload = _load_indicator_point_payload(dcid_key)
    long_df = point_within_to_long(payload, indicator)
    if long_df.empty:
        return long_df
    names = client.place_names(list(long_df["place_dcid"]))
    return attach_place_names(long_df, {k: v for k, v in names.items() if v})


@cached_data(ttl=3600)
def _load_indicator_series(dcid_key: str) -> pd.DataFrame:
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = client_for_indicator(indicator)
    try:
        payload = client.series_within("Earth", "Country", [indicator.dcid])
    except Exception:  # noqa: BLE001 - offline client has no series_within snapshot
        return pd.DataFrame()
    return series_within_to_long(payload, indicator)


@cached_data(ttl=3600)
def _load_continent_map() -> dict[str, str]:
    # Place hierarchy is Data Commons only, same as the geometry above.
    client = get_client()
    try:
        return country_to_continent(client)
    except Exception:  # noqa: BLE001 - offline client has no place/descendent snapshot
        return {}


@cached_data(ttl=3600)
def _load_source_checks() -> list:
    return check_all_pulls()


def _drop_stale_selection(key: str, valid: list[str]) -> None:
    """Clear a remembered selection that the current options no longer contain.

    These are the app's only widgets with a `key`, and they need one so a
    choice survives changing the topic filter. The cost is that Streamlit
    raises if a remembered value is missing from the options, which happens
    the moment a filter narrows past the current selection. Dropping the key
    falls the widget back to its first option instead.
    """
    if key in st.session_state and st.session_state[key] not in valid:
        del st.session_state[key]


_LANGUAGE_ORDER = ["en", "ar", "es", "fr", "ru", "zh"]


@cached_data(ttl=3600)
def _load_locales():
    return load_locales()


def main() -> None:
    catalog = load_catalog()

    locales = _load_locales()
    codes = [c for c in _LANGUAGE_ORDER if c in locales] + [
        c for c in sorted(locales) if c not in _LANGUAGE_ORDER
    ]
    # Read the stored choice before building the widget so the widget's own
    # label is already in the selected language.
    t = get_translator(st.session_state.get("lang", DEFAULT_LOCALE), locales)
    lang = st.sidebar.selectbox(
        t.t("sidebar.language"),
        codes,
        format_func=lambda c: locales[c].name,
        key="lang",
    )
    t = get_translator(lang, locales)

    if t.is_rtl:
        # Streamlit has no RTL mode. This flips text and layout blocks; the
        # pydeck map and plotly charts are not mirrored, which rtl.notice says.
        st.markdown(
            "<style>.stApp { direction: rtl; text-align: right; }</style>",
            unsafe_allow_html=True,
        )
        st.caption(t.t("rtl.notice"))

    st.title(t.t("app.title"))
    st.caption(t.t("app.caption"))

    # Topic is a filter, not a gate: it narrows the list below but never
    # restricts what can be compared against what. Leaving it empty shows
    # everything, which is the default.
    topic_filter = st.sidebar.multiselect(
        t.t("sidebar.topic_filter"),
        list(catalog.topics),
        format_func=lambda k: t.topic(catalog.topics[k]),
        key="topic_filter",
    )
    options = selectable_indicators(catalog, set(topic_filter))
    if not options:
        st.warning(t.t("warn.no_indicators"))
        return

    _drop_stale_selection("indicator_key", [i.key for i in options])
    indicator_key = st.sidebar.selectbox(
        t.t("sidebar.indicator"),
        [i.key for i in options],
        format_func=lambda k: indicator_option_label(catalog.indicators[k], catalog, t),
        key="indicator_key",
    )
    indicator = catalog.indicators[indicator_key]
    indicator_label = t.indicator(indicator)

    # Deliberately NOT narrowed by the topic filter: comparing across topics is
    # the point, and having to clear a filter to reach the other half of the
    # catalog is the exact friction this replaced.
    #
    # None, not a display string, is the "no comparison" sentinel: the old
    # "(none)" literal was the option value, the label and the branch
    # condition at once, so translating it broke the branch.
    compare_options = [
        i.key for i in selectable_indicators(catalog) if i.key != indicator_key
    ]
    _drop_stale_selection("compare_key", [None] + compare_options)
    compare_key = st.sidebar.selectbox(
        t.t("sidebar.compare"),
        [None] + compare_options,
        format_func=lambda k: (
            t.t("sidebar.compare_none")
            if k is None
            else indicator_option_label(catalog.indicators[k], catalog, t)
        ),
        key="compare_key",
    )

    geojson = _load_geojson()
    long_df = _load_indicator_latest(indicator_key)

    if long_df.empty:
        st.warning(t.t("warn.no_observations", indicator=indicator_label))
        return

    audit = audit_join(geojson, set(long_df["place_dcid"]))
    latest_date = long_df["date"].mode().iloc[0]
    citation = citation_for_indicator(
        indicator, as_of=latest_date, label=indicator_label
    )

    compare_indicator = None
    compare_df = pd.DataFrame()
    spec = None
    if compare_key is not None:
        compare_indicator = catalog.indicators[compare_key]
        compare_df = _load_indicator_latest(compare_key)
        spec = compute_join_spec(
            indicator,
            compare_indicator,
            catalog,
            set(long_df["place_dcid"]),
            set(compare_df["place_dcid"]) if not compare_df.empty else set(),
        )
        render_compatibility_panel(
            indicator,
            compare_indicator,
            spec,
            t,
            left_label=indicator_label,
            right_label=t.indicator(compare_indicator),
            dimensions=catalog.dimensions,
        )

    # Tab *ids* are the dict keys and stay English; only what st.tabs displays
    # is translated. Keying the dict by the label would break every lookup
    # below the moment the language changes.
    tab_keys = ["map", "trends", "progress"]
    if compare_indicator is not None:
        tab_keys.append("gap")
    has_priority_tab = (
        indicator.denominator and indicator.denominator in catalog.indicators
    )
    if has_priority_tab:
        tab_keys.append("priority")
    tab_keys += ["coverage", "insights", "sources"]

    # Computed above st.tabs() rather than inside the "Priority" tab's `with`
    # block, so the Insights tab's cross-link to priority rank is an
    # explicit dependency (a local variable) rather than relying on
    # Priority's tab body happening to execute first in script order.
    priority = (
        _compute_priority_scores(catalog, indicator, t) if has_priority_tab else None
    )

    tabs = st.tabs([t.t(f"tab.{k}") for k in tab_keys])
    tab_map = dict(zip(tab_keys, tabs))

    with tab_map["map"]:
        render_choropleth(
            geojson,
            long_df,
            audit,
            [citation],
            t,
            indicator_label=t.indicator(indicator),
            unit_display=indicator.unit_display or indicator.unit,
        )

    with tab_map["trends"]:
        _render_trends_tab(indicator, long_df, citation, t)

    with tab_map["progress"]:
        _render_progress_tab(indicator, long_df, citation, t)

    if compare_indicator is not None:
        with tab_map["gap"]:
            _render_gap_analysis_tab(
                catalog,
                indicator,
                compare_indicator,
                long_df,
                compare_df,
                spec,
                citation,
                t,
            )

    if "priority" in tab_map:
        with tab_map["priority"]:
            _render_priority_section(indicator, priority, t)

    with tab_map["coverage"]:
        _render_coverage_tab(indicator, long_df, citation, t)

    with tab_map["insights"]:
        _render_insights_tab(catalog, indicator, long_df, citation, t, priority)

    # Both halves of "where did this come from" live in one tab: the catalog-
    # wide pull checks (does each source still check out at all) followed by
    # the lineage of the readout actually on screen. Splitting them would
    # make a reader hunt in two places for one question.
    with tab_map["sources"]:
        render_sources_panel(_load_source_checks(), load_sources())

        st.divider()

        citations = [citation]
        cross_check = None
        if compare_indicator is not None and not compare_df.empty:
            citations.append(
                citation_for_indicator(
                    compare_indicator, label=t.indicator(compare_indicator)
                )
            )
            # Only meaningful when the two are on the same scale -- comparing
            # watts per capita against a percentage would manufacture a
            # disagreement out of a unit mismatch.
            if spec is not None and spec.unit_relation in ("same", "same_family"):
                cross_check = cross_source_check(
                    dict(zip(long_df["place_dcid"], long_df["value"])),
                    dict(zip(compare_df["place_dcid"], compare_df["value"])),
                )

        render_lineage_panel(
            build_lineage(
                catalog,
                indicator,
                _load_indicator_point_payload(indicator_key),
                audit,
                n_rows=len(long_df),
                compare=compare_indicator,
                compare_payload=(
                    _load_indicator_point_payload(compare_key)
                    if compare_indicator is not None
                    else None
                ),
                cross_source=cross_check,
            ),
            citations,
            t,
        )


def _render_insights_tab(
    catalog,
    indicator,
    long_df: pd.DataFrame,
    citation,
    t,
    priority: PriorityBundle | None,
) -> None:  # noqa: ANN001 - avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty or not indicator.temporal_start:
        st.info(t.t("info.need_history"))
        return

    names = (
        long_df.set_index("place_dcid")["place_name"].dropna().to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    priority_ranks, priority_total = _priority_lookup(priority)

    years_available = sorted(series_df["date"].unique())
    base_year, end_year = years_available[0], years_available[-1]
    convergence = compute_convergence(
        series_df, base_year, end_year, ceiling=indicator.saturation_ceiling
    )
    movers = (
        rank_convergence_movers(convergence, polarity=indicator.polarity)
        if convergence is not None
        else None
    )
    render_convergence(
        convergence,
        t.indicator(indicator),
        base_year,
        end_year,
        [citation],
        t,
        movers=movers,
        place_names=names,
        priority_ranks=priority_ranks,
        priority_total=priority_total,
        total_places=series_df["place_dcid"].nunique(),
    )

    st.divider()

    # Siblings now follow the selected indicator rather than a separate
    # sidebar topic: any indicator sharing a topic with it. The sidebar no
    # longer tracks one "current" topic, and this is the better question
    # anyway -- what else describes the same subject as the thing on screen.
    sibling_topics = {tp.key for tp in catalog.topics_for_indicator(indicator.key)}
    topic_indicators = [
        i
        for i in selectable_indicators(catalog, sibling_topics)
        if i.enriched and i.key != indicator.key
    ]
    feature_keys = [indicator.key] + [i.key for i in topic_indicators][:2]
    # place_name travels alongside value so archetype membership can be
    # named later -- previously this frame carried dcids only, which made
    # naming cluster membership impossible without a second lookup.
    feature_frames = [
        (
            long_df[["place_dcid", "place_name", "value"]].rename(
                columns={"value": indicator.key}
            )
            if "place_name" in long_df.columns
            else long_df[["place_dcid", "value"]].rename(
                columns={"value": indicator.key}
            )
        )
    ]
    feature_labels = {indicator.key: t.indicator(indicator)}
    for other in topic_indicators[:2]:
        other_df = _load_indicator_latest(other.key)
        if other_df.empty:
            continue
        feature_frames.append(
            other_df[["place_dcid", "value"]].rename(columns={"value": other.key})
        )
        feature_labels[other.key] = t.indicator(other)

    if len(feature_frames) < 2:
        st.info(t.t("info.need_two_indicators"))
        return

    merged = feature_frames[0]
    for f in feature_frames[1:]:
        merged = merged.merge(f, on="place_dcid", how="inner")
    used_keys = [k for k in feature_keys if k in merged.columns]

    archetypes = compute_archetypes(merged, feature_cols=used_keys)
    group_ranking = (
        rank_groups_by_indicator(
            archetypes.cluster_centers, indicator.key, polarity=indicator.polarity
        )
        if archetypes is not None
        else None
    )
    render_archetypes(
        archetypes,
        feature_labels,
        [citation],
        t,
        group_ranking=group_ranking,
        place_names=names,
        priority_ranks=priority_ranks,
        priority_total=priority_total,
    )


def _default_focus_places(
    indicator, long_df: pd.DataFrame, n: int = 5
) -> list[str]:  # noqa: ANN001 - Indicator, avoids import cycle noise
    """Countries furthest behind on this indicator -- where a trend or a
    target actually matters. For a higher_is_better metric like electricity
    access, that's the smallest values; the already-saturated places all
    look identical near the ceiling and add nothing to a chart. For a
    lower_is_better metric it's the largest values.
    """
    ascending = indicator.polarity == "higher_is_better"
    return (
        long_df.nsmallest(n, "value")["place_dcid"].tolist()
        if ascending
        else long_df.nlargest(n, "value")["place_dcid"].tolist()
    )


def _render_trends_tab(
    indicator, long_df: pd.DataFrame, citation, t
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    # _default_focus_places picks the countries furthest behind. That is
    # only the *default* selection here -- the multiselect below can widen
    # it to any subset, up to every country, so data is never permanently
    # hidden.
    default_places = _default_focus_places(indicator, long_df)
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info(t.t("info.need_history"))
        return
    names = (
        long_df.set_index("place_dcid")["place_name"].dropna().to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    series_df = series_df.copy()
    series_df["place_name"] = series_df["place_dcid"].map(names)

    all_places = sorted(series_df["place_dcid"].unique(), key=lambda d: names.get(d, d))
    # Keyed per-indicator so switching the sidebar indicator resets the
    # selection instead of carrying stale place dcids into a new series.
    selected_places = st.multiselect(
        "Countries to chart",
        options=all_places,
        default=[p for p in default_places if p in all_places],
        format_func=lambda d: names.get(d, d),
        key=f"trend_places_{indicator.key}",
    )

    if not selected_places:
        st.info(
            f"Pick at least one country above to see its trend "
            f"(showing 0 of {len(all_places)} countries)."
        )
        return

    trend_results, saturated_places = fit_trends_excluding_saturated(
        series_df, ceiling=indicator.saturation_ceiling
    )
    trends = {r.place_dcid: r for r in trend_results}

    # Anomaly detection runs over the FULL panel, not just the countries
    # currently selected -- an unusual movement in an unplotted country
    # must still surface (see analytics/anomalies.py and the summary table
    # in render_trend_panel).
    anomalies = detect_anomalies(
        series_df, polarity=indicator.polarity, trend_results=trend_results
    )

    render_trend_panel(
        series_df,
        selected_places,
        [citation],
        t,
        trends=trends,
        saturated_places=set(saturated_places),
        unit_display=indicator.unit_display or indicator.unit,
        indicator_label=t.indicator(indicator),
        total_places=len(all_places),
        anomalies=anomalies,
        place_names=names,
    )


def _render_progress_tab(
    indicator, long_df: pd.DataFrame, citation, t
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info(t.t("info.need_history"))
        return

    names = (
        long_df.set_index("place_dcid")["place_name"].dropna().to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    series_df = series_df.copy()
    series_df["place_name"] = series_df["place_dcid"].map(names)

    default_places = _default_focus_places(indicator, long_df)
    # Restrict the toggle to places we can actually name -- an unnamed dcid
    # in the picker is just noise for a "pick a country" control.
    available = sorted(
        (d for d in series_df["place_dcid"].unique() if d in names),
        key=lambda d: names[d],
    )
    selected = st.multiselect(
        "Countries to compare",
        options=available,
        default=[d for d in default_places if d in available],
        format_func=lambda d: names.get(d, d),
        key=f"progress_places_{indicator.key}",
    )
    if not selected:
        st.info("Pick at least one country to see its progress toward the target.")
        return

    results = compute_progress(
        series_df,
        polarity=indicator.polarity,
        target_value=indicator.target_value,
        target_year=indicator.target_year,
    )
    progress = {r.place_dcid: r for r in results}

    render_progress_panel(
        series_df,
        selected,
        [citation],
        progress,
        target_value=indicator.target_value,
        target_year=indicator.target_year,
        unit_display=indicator.unit_display or indicator.unit,
        indicator_label=t.indicator(indicator),
    )


def _render_coverage_tab(
    indicator, long_df: pd.DataFrame, citation, t
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info(t.t("info.need_history"))
        return
    if not indicator.temporal_start or not indicator.temporal_end:
        st.info(t.t("info.need_date_range"))
        return

    names = (
        long_df.set_index("place_dcid")["place_name"].to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    series_df = series_df.copy()
    series_df["place_name"] = series_df["place_dcid"].map(names)

    start, end = int(indicator.temporal_start), int(indicator.temporal_end)
    report = compute_coverage(series_df, start, end)
    render_coverage_panel(series_df, report, [citation], start, end, t)


def _render_gap_analysis_tab(
    catalog, indicator, compare_indicator, long_df, compare_df, spec, citation, t
) -> None:  # noqa: ANN001 - avoids import cycle noise
    if spec.comparability == "blocked":
        st.error(t.t("gap.cannot_crossplot", reasons=t.blockers(spec)))
        return

    left_label = t.indicator(indicator)
    right_label = t.indicator(compare_indicator)
    pop_indicator = catalog.indicators.get("unicef_population")
    left_dates_finding = check_mixed_dates(
        _load_indicator_point_payload(indicator.key), indicator.dcid
    )
    right_dates_finding = check_mixed_dates(
        _load_indicator_point_payload(compare_indicator.key), compare_indicator.dcid
    )

    # Merge on place + date so a country is only compared against itself in
    # the same reference year; the "date" columns are renamed per-source
    # rather than dropped, so a mismatch is visible instead of silently
    # plotting e.g. 2023-World-Bank against 2024-SDG per country.
    merged = (
        long_df[["place_dcid", "place_name", "date", "value"]]
        .rename(columns={"value": indicator.key, "date": f"{indicator.key}_date"})
        .merge(
            compare_df[["place_dcid", "date", "value"]].rename(
                columns={
                    "value": compare_indicator.key,
                    "date": f"{compare_indicator.key}_date",
                }
            ),
            on="place_dcid",
            how="inner",
        )
    )
    merged["same_year"] = (
        merged[f"{indicator.key}_date"] == merged[f"{compare_indicator.key}_date"]
    )
    # Units already agree (checked via spec.unit_relation), so the arithmetic
    # itself is safe regardless of year match -- but a cross-year row is
    # comparing two different points in time, not two measurements of the
    # same moment, so `same_year` stays attached as a per-row caveat rather
    # than gating whether we compute the number at all.
    if spec.unit_relation in ("same", "same_family"):
        merged["difference"] = merged[compare_indicator.key] - merged[indicator.key]

    n_cross_year = int((~merged["same_year"]).sum())
    # Intentionally English in every locale: a nuanced statistical caveat
    # where a poor translation misleads. Needs a human translator.
    if left_dates_finding or right_dates_finding or n_cross_year:
        st.warning(
            f"⚠️ Comparing across different years: {n_cross_year} of "
            f"{len(merged)} countries are matched on different reference "
            f"years between {indicator.label} and {compare_indicator.label} "
            "(each source reports its own most recent year). Rows below are "
            "flagged rather than silently treated as the same point in time."
        )

    _render_disagreement_callout(indicator, compare_indicator, merged)

    with st.expander(t.t("gap.table_expander")):
        table_cols = [
            "place_name",
            f"{indicator.key}_date",
            indicator.key,
            f"{compare_indicator.key}_date",
            compare_indicator.key,
        ]
        if "difference" in merged.columns:
            table_cols.append("difference")
        st.dataframe(
            merged[table_cols].sort_values("place_name"),
            use_container_width=True,
            # Keys are dataframe column ids; only the values are display
            # text, so translating these cannot break the lookup.
            column_config={
                "place_name": t.t("gap.col_country"),
                f"{indicator.key}_date": t.t(
                    "gap.col_indicator_year", indicator=left_label
                ),
                indicator.key: left_label,
                f"{compare_indicator.key}_date": t.t(
                    "gap.col_indicator_year", indicator=right_label
                ),
                compare_indicator.key: right_label,
                "difference": t.t("gap.col_difference"),
            },
        )

    size_col = None
    if pop_indicator is not None:
        pop_df = _load_indicator_latest(pop_indicator.key)
        if not pop_df.empty:
            merged = merged.merge(
                pop_df[["place_dcid", "value"]].rename(columns={"value": "population"}),
                on="place_dcid",
                how="left",
            )
            size_col = "population"

    # Region is a filter, not a colour channel. Seven continents cannot be
    # told apart reliably on a scatter -- see views/palette.py -- so the
    # dimension moves into a control above the chart, per the one-row-of-
    # filters convention.
    continent_map = _load_continent_map()
    if continent_map:
        merged["continent"] = merged["place_dcid"].map(continent_map)
        regions = sorted({r for r in merged["continent"].dropna().unique()})
        if regions:
            choice = st.selectbox(
                t.t("gap.region_filter"),
                [None] + regions,
                format_func=lambda r: t.t("gap.region_all") if r is None else r.title(),
            )
            if choice is not None:
                merged = merged[merged["continent"] == choice]
            if merged.empty:
                st.info(t.t("gap.empty"))
                return

    compare_citation = citation_for_indicator(compare_indicator, label=right_label)
    render_bivariate(
        merged,
        x_col=indicator.key,
        y_col=compare_indicator.key,
        x_label=left_label,
        y_label=right_label,
        spec=spec,
        citations=[citation, compare_citation],
        t=t,
        size_col=size_col,
    )


_DISAGREEMENT_THRESHOLD_PP = 10.0


def _render_disagreement_callout(
    indicator, compare_indicator, merged: pd.DataFrame
) -> None:  # noqa: ANN001 - Indicator, avoids import cycle noise
    """Surface concrete cross-source disagreement, not just a compatibility verdict.

    This is the demo's centerpiece moment for "triage across disagreeing
    sources": named countries and numbers, written into the view rather than
    left for a presenter to remember to say out loud.

    Intentionally English in every locale, like the other statistical
    caveats: this is a claim about survey methodology, not UI chrome.
    """
    if "difference" not in merged.columns:
        return
    valid = merged.dropna(subset=["difference"])
    if valid.empty:
        return

    disagreeing = valid[valid["difference"].abs() > _DISAGREEMENT_THRESHOLD_PP]
    if disagreeing.empty:
        return

    worst = disagreeing.reindex(
        disagreeing["difference"].abs().sort_values(ascending=False).index
    )
    top = worst.iloc[0]
    top_name = top.get("place_name") or top["place_dcid"]
    year_note = (
        ""
        if top["same_year"]
        else f" ({top[f'{indicator.key}_date']} vs. "
        f"{top[f'{compare_indicator.key}_date']})"
    )
    st.info(
        f"📊 **{indicator.label} and {compare_indicator.label} disagree by more "
        f"than {_DISAGREEMENT_THRESHOLD_PP:.0f} percentage points for "
        f"{len(disagreeing)} countries**, including {top_name}: "
        f"{top[indicator.key]:.1f}% vs. {top[compare_indicator.key]:.1f}%{year_note} — "
        "different survey methods and reference years produce different "
        "answers to the same question."
    )


@dataclass(frozen=True)
class PriorityBundle:
    scored: pd.DataFrame
    year: str
    total_unserved: float
    notes: tuple[str, ...] = field(default_factory=tuple)


def _compute_priority_scores(
    catalog, indicator, t
) -> PriorityBundle | None:  # noqa: ANN001 - Catalog/Indicator, avoids import cycle
    """All of the old _render_priority_section, minus the st.* rendering.

    Split out so this computation can run above st.tabs() and be shared
    with the Insights tab's priority-rank cross-link, instead of the two
    tabs depending on an implicit "Priority's `with` block runs first"
    ordering. The two st.sidebar.slider calls stay here: sidebar placement
    is independent of where in the script a call runs, so hoisting this
    doesn't move the sliders.

    Returns None when the indicator has no denominator, no shared years
    between access/population series, or no series data at all -- the
    common case for 8 of 9 catalog indicators today.

    Takes `t` because the sidebar sliders it owns are labelled, and because
    the notes it returns are user-facing strings: translating them here
    keeps the renderer a pure pass-through.
    """
    denom = catalog.indicators[indicator.denominator]

    access_series = _load_indicator_series(indicator.key)
    pop_series = _load_indicator_series(denom.key)
    if access_series.empty or pop_series.empty:
        return None

    shared_years = sorted(
        set(access_series["date"]) & set(pop_series["date"]), reverse=True
    )
    if not shared_years:
        return None
    year = shared_years[0]

    access_year = access_series[access_series["date"] == year]
    pop_year = pop_series[pop_series["date"] == year]
    client = client_for_indicator(indicator)
    names = client.place_names(list(access_year["place_dcid"]))
    access_year = attach_place_names(access_year, {k: v for k, v in names.items() if v})
    merged, nan_report = unserved_population(access_year, pop_year, access_col="value")

    notes = []
    if nan_report.n_dropped:
        notes.append(nan_report.message())

    results, saturated_places = fit_trends_excluding_saturated(
        access_series, ceiling=indicator.saturation_ceiling
    )
    slopes = pd.DataFrame(
        [{"place_dcid": r.place_dcid, "slope": r.slope} for r in results]
    )
    merged = merged.merge(slopes, on="place_dcid", how="left")
    merged["slope"] = merged["slope"].fillna(0.0)
    if saturated_places:
        notes.append(
            t.t(
                "priority.saturation_excluded",
                count=len(saturated_places),
                ceiling=indicator.saturation_ceiling,
            )
        )

    st.sidebar.markdown(t.t("sidebar.weights_header"))
    w_gap = st.sidebar.slider(t.t("sidebar.weight_people"), 0.0, 3.0, 1.0, 0.5)
    w_stag = st.sidebar.slider(t.t("sidebar.weight_stagnation"), 0.0, 3.0, 1.0, 0.5)

    scored = priority_score(
        merged,
        components={
            "unserved_pop": ("unserved_population", True),
            "stagnation": ("slope", False),
        },
        weights={"unserved_pop": w_gap, "stagnation": w_stag},
    )

    return PriorityBundle(
        scored=scored,
        year=year,
        total_unserved=float(merged["unserved_population"].sum()),
        notes=tuple(notes),
    )


def _priority_lookup(priority: PriorityBundle | None) -> tuple[dict[str, int], int]:
    """place_dcid -> 1-based priority rank, plus the total ranked, for the
    Insights-tab cross-link. Empty dict when there's no priority bundle.
    """
    if priority is None or priority.scored.empty:
        return {}, 0
    ranks = {
        place_dcid: rank
        for rank, place_dcid in enumerate(priority.scored["place_dcid"], start=1)
    }
    return ranks, len(ranks)


def _render_priority_section(
    indicator, priority: PriorityBundle | None, t
) -> None:  # noqa: ANN001 - Indicator, avoids import cycle noise
    if priority is None:
        st.info(t.t("priority.needs_history", indicator=t.indicator(indicator)))
        return

    for note in priority.notes:
        st.caption(note)

    citation = citation_for_indicator(
        indicator, as_of=priority.year, label=t.indicator(indicator)
    )
    render_priority_table(
        priority.scored,
        [citation],
        t,
        headline_total_unserved=priority.total_unserved,
    )


if __name__ == "__main__":
    main()
