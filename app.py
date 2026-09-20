"""Streamlit entrypoint for the cross-agency UN SDG dashboard.

Thin by design: this file wires the catalog, client, and views together.
Logic lives in recipe/, analytics/, and views/.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.archetypes import compute_archetypes
from analytics.convergence import compute_convergence
from analytics.coverage import compute_coverage
from analytics.gap_scoring import priority_score, unserved_population
from analytics.trends import fit_trends_excluding_saturated
from recipe.attribution import citation_for_indicator
from recipe.cache import cached_data
from recipe.catalog import load_catalog
from recipe.datacommons_client import get_client
from recipe.frames import (
    attach_place_names,
    point_within_to_long,
    series_within_to_long,
)
from recipe.geography import audit_join, country_to_continent, fetch_country_geojson
from recipe.keymatch import compute_join_spec
from recipe.validation import check_mixed_dates
from views.bivariate import render_bivariate
from views.choropleth import render_choropleth
from views.compatibility import render_compatibility_panel
from views.coverage_panel import render_coverage_panel
from views.insights_panel import render_archetypes, render_convergence
from views.priority_table import render_priority_table
from views.trend_panel import render_trend_panel

st.set_page_config(page_title="UN SDG Cross-Agency Dashboard", layout="wide")


@cached_data(ttl=3600)
def _load_geojson() -> dict:
    client = get_client()
    return fetch_country_geojson(client)


@cached_data(ttl=3600)
def _load_indicator_point_payload(dcid_key: str):
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = get_client()
    return client.point_within("Earth", "Country", [indicator.dcid])


@cached_data(ttl=3600)
def _load_indicator_latest(dcid_key: str) -> pd.DataFrame:
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = get_client()
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
    client = get_client()
    try:
        payload = client.series_within("Earth", "Country", [indicator.dcid])
    except Exception:  # noqa: BLE001 - offline client has no series_within snapshot
        return pd.DataFrame()
    return series_within_to_long(payload, indicator)


@cached_data(ttl=3600)
def _load_continent_map() -> dict[str, str]:
    client = get_client()
    try:
        return country_to_continent(client)
    except Exception:  # noqa: BLE001 - offline client has no place/descendent snapshot
        return {}


def main() -> None:
    catalog = load_catalog()

    st.title("UN SDG Cross-Agency Dashboard")
    st.caption(
        "A reusable recipe for retrieving, validating, and joining indicators "
        "across UN agencies — no new code per indicator."
    )

    topic_keys = list(catalog.topics.keys())
    topic_key = st.sidebar.selectbox(
        "Topic",
        topic_keys,
        format_func=lambda k: catalog.topics[k].label,
    )
    topic_indicators = catalog.indicators_for_topic(topic_key)
    if not topic_indicators:
        st.warning("No indicators are set up yet for this topic.")
        return

    indicator_key = st.sidebar.selectbox(
        "Indicator",
        [i.key for i in topic_indicators],
        format_func=lambda k: catalog.indicators[k].label,
    )
    indicator = catalog.indicators[indicator_key]

    all_indicators = [i for i in catalog.indicators.values() if i.role != "denominator"]
    compare_key = st.sidebar.selectbox(
        "Compare against",
        ["(none)"] + [i.key for i in all_indicators if i.key != indicator_key],
        format_func=lambda k: (
            "(none)" if k == "(none)" else catalog.indicators[k].label
        ),
    )

    geojson = _load_geojson()
    long_df = _load_indicator_latest(indicator_key)

    if long_df.empty:
        st.warning(f"No observations returned for {indicator.label}.")
        return

    audit = audit_join(geojson, set(long_df["place_dcid"]))
    latest_date = long_df["date"].mode().iloc[0]
    citation = citation_for_indicator(indicator, as_of=latest_date)

    compare_indicator = None
    compare_df = pd.DataFrame()
    spec = None
    if compare_key != "(none)":
        compare_indicator = catalog.indicators[compare_key]
        compare_df = _load_indicator_latest(compare_key)
        spec = compute_join_spec(
            indicator,
            compare_indicator,
            catalog,
            set(long_df["place_dcid"]),
            set(compare_df["place_dcid"]) if not compare_df.empty else set(),
        )
        render_compatibility_panel(indicator, compare_indicator, spec)

    tab_labels = ["Map", "Trends"]
    if compare_indicator is not None:
        tab_labels.append("Gap analysis")
    if indicator.denominator and indicator.denominator in catalog.indicators:
        tab_labels.append("Priority")
    tab_labels.append("Coverage")
    tab_labels.append("Insights")
    tabs = st.tabs(tab_labels)
    tab_map = dict(zip(tab_labels, tabs))

    with tab_map["Map"]:
        render_choropleth(geojson, long_df, audit, [citation])

    with tab_map["Trends"]:
        _render_trends_tab(indicator, long_df, citation)

    if compare_indicator is not None:
        with tab_map["Gap analysis"]:
            _render_gap_analysis_tab(
                catalog,
                indicator,
                compare_indicator,
                long_df,
                compare_df,
                spec,
                citation,
            )

    if "Priority" in tab_map:
        with tab_map["Priority"]:
            _render_priority_section(catalog, indicator)

    with tab_map["Coverage"]:
        _render_coverage_tab(indicator, long_df, citation)

    with tab_map["Insights"]:
        _render_insights_tab(catalog, topic_key, indicator, long_df, citation)


def _render_insights_tab(
    catalog, topic_key: str, indicator, long_df: pd.DataFrame, citation
) -> None:  # noqa: ANN001 - avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty or not indicator.temporal_start:
        st.info("This view needs more historical data than we have loaded right now.")
        return

    years_available = sorted(series_df["date"].unique())
    base_year, end_year = years_available[0], years_available[-1]
    convergence = compute_convergence(
        series_df, base_year, end_year, ceiling=indicator.saturation_ceiling
    )
    render_convergence(convergence, indicator.label, base_year, end_year, [citation])

    st.divider()

    topic_indicators = [
        i
        for i in catalog.indicators_for_topic(topic_key)
        if i.enriched and i.key != indicator.key
    ]
    feature_keys = [indicator.key] + [i.key for i in topic_indicators][:2]
    feature_frames = [
        long_df[["place_dcid", "value"]].rename(columns={"value": indicator.key})
    ]
    feature_labels = {indicator.key: indicator.label}
    for other in topic_indicators[:2]:
        other_df = _load_indicator_latest(other.key)
        if other_df.empty:
            continue
        feature_frames.append(
            other_df[["place_dcid", "value"]].rename(columns={"value": other.key})
        )
        feature_labels[other.key] = other.label

    if len(feature_frames) < 2:
        st.info(
            "This view needs at least two indicators set up for this topic — "
            "there's only one available right now."
        )
        return

    merged = feature_frames[0]
    for f in feature_frames[1:]:
        merged = merged.merge(f, on="place_dcid", how="inner")
    used_keys = [k for k in feature_keys if k in merged.columns]

    archetypes = compute_archetypes(merged, feature_cols=used_keys)
    render_archetypes(archetypes, feature_labels, [citation])


def _render_trends_tab(
    indicator, long_df: pd.DataFrame, citation
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    default_n = 5
    # Default to the lowest values, not the highest: for a higher_is_better
    # metric like electricity access, the countries furthest behind are the
    # ones where a trend actually matters. The already-saturated places all
    # look identical near the ceiling and add nothing to the chart.
    ascending = indicator.polarity == "higher_is_better"
    top_places = (
        long_df.nsmallest(default_n, "value")["place_dcid"].tolist()
        if ascending
        else long_df.nlargest(default_n, "value")["place_dcid"].tolist()
    )
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info("This view needs more historical data than we have loaded right now.")
        return
    names = (
        long_df.set_index("place_dcid")["place_name"].to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    series_df = series_df.copy()
    series_df["place_name"] = series_df["place_dcid"].map(names)

    trend_results, saturated_places = fit_trends_excluding_saturated(
        series_df, ceiling=indicator.saturation_ceiling
    )
    trends = {r.place_dcid: r for r in trend_results}

    render_trend_panel(
        series_df,
        top_places,
        [citation],
        trends=trends,
        saturated_places=set(saturated_places),
        unit_display=indicator.unit_display or indicator.unit,
    )


def _render_coverage_tab(
    indicator, long_df: pd.DataFrame, citation
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info("This view needs more historical data than we have loaded right now.")
        return
    if not indicator.temporal_start or not indicator.temporal_end:
        st.info(
            "This view needs a known date range for this indicator, which isn't set up yet."
        )
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
    render_coverage_panel(series_df, report, [citation], start, end)


def _render_gap_analysis_tab(
    catalog, indicator, compare_indicator, long_df, compare_df, spec, citation
) -> None:  # noqa: ANN001 - avoids import cycle noise
    if spec.comparability == "blocked":
        st.error("Cannot cross-plot: " + "; ".join(spec.blockers))
        return

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
    if left_dates_finding or right_dates_finding or n_cross_year:
        st.warning(
            f"⚠️ Comparing across different years: {n_cross_year} of "
            f"{len(merged)} countries are matched on different reference "
            f"years between {indicator.label} and {compare_indicator.label} "
            "(each source reports its own most recent year). Rows below are "
            "flagged rather than silently treated as the same point in time."
        )

    _render_disagreement_callout(indicator, compare_indicator, merged)

    with st.expander("See the year-by-year comparison table"):
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
            column_config={
                "place_name": "Country",
                f"{indicator.key}_date": f"{indicator.label} year",
                indicator.key: indicator.label,
                f"{compare_indicator.key}_date": f"{compare_indicator.label} year",
                compare_indicator.key: compare_indicator.label,
                "difference": "Difference",
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

    continent_map = _load_continent_map()
    color_col = None
    if continent_map:
        merged["continent"] = merged["place_dcid"].map(continent_map)
        color_col = "continent"

    compare_citation = citation_for_indicator(compare_indicator)
    render_bivariate(
        merged,
        x_col=indicator.key,
        y_col=compare_indicator.key,
        x_label=indicator.label,
        y_label=compare_indicator.label,
        spec=spec,
        citations=[citation, compare_citation],
        size_col=size_col,
        color_col=color_col,
    )


_DISAGREEMENT_THRESHOLD_PP = 10.0


def _render_disagreement_callout(
    indicator, compare_indicator, merged: pd.DataFrame
) -> None:  # noqa: ANN001 - Indicator, avoids import cycle noise
    """Surface concrete cross-source disagreement, not just a compatibility verdict.

    This is the demo's centerpiece moment for "triage across disagreeing
    sources": named countries and numbers, written into the view rather than
    left for a presenter to remember to say out loud.
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


def _render_priority_section(
    catalog, indicator
) -> None:  # noqa: ANN001 - Catalog/Indicator, avoids import cycle noise
    denom = catalog.indicators[indicator.denominator]

    access_series = _load_indicator_series(indicator.key)
    pop_series = _load_indicator_series(denom.key)
    if access_series.empty or pop_series.empty:
        st.info(
            f"Priority scoring for {indicator.label} needs more historical "
            "data than we have loaded right now."
        )
        return

    shared_years = sorted(
        set(access_series["date"]) & set(pop_series["date"]), reverse=True
    )
    if not shared_years:
        return
    year = shared_years[0]

    access_year = access_series[access_series["date"] == year]
    pop_year = pop_series[pop_series["date"] == year]
    client = get_client()
    names = client.place_names(list(access_year["place_dcid"]))
    access_year = attach_place_names(access_year, {k: v for k, v in names.items() if v})
    merged, nan_report = unserved_population(access_year, pop_year, access_col="value")
    if nan_report.n_dropped:
        st.caption(nan_report.message())

    results, saturated_places = fit_trends_excluding_saturated(
        access_series, ceiling=indicator.saturation_ceiling
    )
    slopes = pd.DataFrame(
        [{"place_dcid": r.place_dcid, "slope": r.slope} for r in results]
    )
    merged = merged.merge(slopes, on="place_dcid", how="left")
    merged["slope"] = merged["slope"].fillna(0.0)
    if saturated_places:
        st.caption(
            f"{len(saturated_places)} places already at/near the saturation "
            f"ceiling ({indicator.saturation_ceiling}) are excluded from the "
            "stagnation component and treated as zero-slope."
        )

    st.sidebar.markdown("**Priority score weights**")
    w_gap = st.sidebar.slider(
        "How much to prioritize: people affected", 0.0, 3.0, 1.0, 0.5
    )
    w_stag = st.sidebar.slider(
        "How much to prioritize: not improving", 0.0, 3.0, 1.0, 0.5
    )

    scored = priority_score(
        merged,
        components={
            "unserved_pop": ("unserved_population", True),
            "stagnation": ("slope", False),
        },
        weights={"unserved_pop": w_gap, "stagnation": w_stag},
    )

    citation = citation_for_indicator(indicator, as_of=year)
    render_priority_table(
        scored,
        [citation],
        headline_total_unserved=merged["unserved_population"].sum(),
    )


if __name__ == "__main__":
    main()
