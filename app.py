"""Streamlit entrypoint for the cross-agency UN SDG dashboard.

Thin by design: this file wires the catalog, client, and views together.
Logic lives in recipe/, analytics/, and views/.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from recipe.attribution import citation_for_indicator
from recipe.cache import cached_data
from recipe.catalog import load_catalog
from recipe.datacommons_client import get_client
from recipe.frames import attach_place_names, point_within_to_long
from recipe.geography import audit_join, fetch_country_geojson
from recipe.keymatch import compute_join_spec
from views.choropleth import render_choropleth
from views.compatibility import render_compatibility_panel

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

    render_choropleth(geojson, long_df, audit, [citation])

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


if __name__ == "__main__":
    main()
