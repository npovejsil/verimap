"""Streamlit entrypoint for the cross-agency UN SDG dashboard.

Thin by design: this file wires the catalog, client, and views together.
Logic lives in recipe/, analytics/, and views/.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

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
from views.bivariate import render_bivariate
from views.choropleth import render_choropleth
from views.compatibility import render_compatibility_panel
from views.coverage_panel import render_coverage_panel
from views.priority_table import render_priority_table
from views.trend_panel import render_trend_panel

st.set_page_config(page_title="UN SDG Cross-Agency Dashboard", layout="wide")


@cached_data(ttl=3600)
def _load_geojson() -> dict:
    client = get_client()
    return fetch_country_geojson(client)


@cached_data(ttl=3600)
def _load_indicator_latest(dcid_key: str) -> pd.DataFrame:
    catalog = load_catalog()
    indicator = catalog.indicators[dcid_key]
    client = get_client()
    payload = client.point_within("Earth", "Country", [indicator.dcid])
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
        st.warning(f"No indicators enriched yet for topic '{topic_key}'.")
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
        st.info("Trend view needs the full time series, unavailable in offline mode.")
        return
    names = (
        long_df.set_index("place_dcid")["place_name"].to_dict()
        if "place_name" in long_df.columns
        else {}
    )
    series_df = series_df.copy()
    series_df["place_name"] = series_df["place_dcid"].map(names)
    render_trend_panel(
        series_df,
        top_places,
        [citation],
        unit_display=indicator.unit_display or indicator.unit,
    )


def _render_coverage_tab(
    indicator, long_df: pd.DataFrame, citation
) -> None:  # noqa: ANN001 - Indicator/Citation, avoids import cycle noise
    series_df = _load_indicator_series(indicator.key)
    if series_df.empty:
        st.info(
            "Coverage view needs the full time series, unavailable in offline mode."
        )
        return
    if not indicator.temporal_start or not indicator.temporal_end:
        st.info("Coverage view needs an enriched temporal range for this indicator.")
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
    merged = (
        long_df[["place_dcid", "place_name", "value"]]
        .rename(columns={"value": indicator.key})
        .merge(
            compare_df[["place_dcid", "value"]].rename(
                columns={"value": compare_indicator.key}
            ),
            on="place_dcid",
            how="inner",
        )
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


def _render_priority_section(
    catalog, indicator
) -> None:  # noqa: ANN001 - Catalog/Indicator, avoids import cycle noise
    denom = catalog.indicators[indicator.denominator]

    access_series = _load_indicator_series(indicator.key)
    pop_series = _load_indicator_series(denom.key)
    if access_series.empty or pop_series.empty:
        st.info(
            f"Priority scoring for {indicator.label} needs the full time series, "
            "which isn't available in offline mode."
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
    w_gap = st.sidebar.slider("Weight: unserved population", 0.0, 3.0, 1.0, 0.5)
    w_stag = st.sidebar.slider("Weight: stagnation", 0.0, 3.0, 1.0, 0.5)

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
