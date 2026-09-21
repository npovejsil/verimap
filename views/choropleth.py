"""Render a world choropleth for one indicator using pydeck's GeoJsonLayer.

No geopandas/shapely/Mapbox token needed: pydeck consumes the raw GeoJSON
dict directly, and st.pydeck_chart renders on the default Carto basemap.

Colors are binned by quantile, not a plain min-max scale. Verified real case
(electricity access): 124 of 217 countries report exactly 100%, so a linear
scale renders that entire majority as one indistinguishable dark shade while
the real variation -- mostly African countries spread from 5-90% -- gets
compressed into a narrow band of similar oranges. Quantile bins instead give
each color step roughly the same number of countries, so shade differences
on the map track real differences between places rather than an accident of
where a handful of raw values happen to fall on a fixed 0-100 ruler.
"""

from __future__ import annotations

import copy

import pandas as pd
import pydeck as pdk
import streamlit as st

from recipe.attribution import Citation, require_citations
from recipe.geography import JoinAudit
from views.palette import (
    NO_DATA_COLOR,
    bin_label,
    binned_sequential_color,
    quantile_breaks,
)

_N_COLOR_BINS = 5


def inject_fill_colors(
    geojson: dict, long_df: pd.DataFrame, value_col: str = "value"
) -> tuple[dict, list[float]]:
    """Return a copy of the GeoJSON with a per-feature fill_color property.

    Features with no matching observation get an explicit grey, never a
    default/invisible color, so absence of data is a visible category.
    Also returns the quantile breaks used, so the caller can render a
    legend that matches the colors actually on the map.
    """
    geo = copy.deepcopy(geojson)
    values = long_df.set_index("place_dcid")[value_col]
    breaks = quantile_breaks(values.tolist(), n_bins=_N_COLOR_BINS)

    for feature in geo["features"]:
        place_dcid = feature["id"]
        if place_dcid in values.index:
            v = values.loc[place_dcid]
            feature["properties"]["fill_color"] = binned_sequential_color(v, breaks)
            feature["properties"]["value"] = float(v)
        else:
            feature["properties"]["fill_color"] = NO_DATA_COLOR
            feature["properties"]["value"] = None
    return geo, breaks


def _render_legend(breaks: list[float], unit_display: str | None) -> None:
    """One color swatch per quantile bin, with its exact value range."""
    if len(breaks) < 2:
        return
    n_bins = len(breaks) - 1
    cols = st.columns(n_bins + 1)  # +1 for the "no data" swatch
    for i in range(n_bins):
        color = binned_sequential_color((breaks[i] + breaks[i + 1]) / 2, breaks)
        r, g, b, _ = color
        with cols[i]:
            st.markdown(
                f"<div style='background-color: rgb({r},{g},{b}); "
                "height: 18px; border-radius: 3px;'></div>",
                unsafe_allow_html=True,
            )
            st.caption(bin_label(breaks, i, unit_display))
    with cols[n_bins]:
        st.markdown(
            "<div style='background-color: rgb(229,229,229); "
            "height: 18px; border-radius: 3px;'></div>",
            unsafe_allow_html=True,
        )
        st.caption("No data")


def render_choropleth(
    geojson: dict,
    long_df: pd.DataFrame,
    audit: JoinAudit,
    citations: list[Citation],
    indicator_label: str | None = None,
    unit_display: str | None = None,
    value_col: str = "value",
) -> None:
    """Render the map, its legend, a plain-language caption, and attribution.

    If any observations have no matching map geometry, they are named
    explicitly rather than only counted — those rows are excluded from the
    map but must never disappear silently.
    """
    require_citations(citations)

    if audit.unmatched_observation_places:
        place_names = (
            long_df.set_index("place_dcid")["place_name"].to_dict()
            if "place_name" in long_df.columns
            else {}
        )
        excluded = [
            name if isinstance(name := place_names.get(p), str) else p
            for p in audit.unmatched_observation_places
        ]
        st.warning(
            f"Excluded {len(excluded)} places with data but no map geometry: "
            f"{', '.join(map(str, excluded))}. Not rendered on the map below."
        )

    geo_with_colors, breaks = inject_fill_colors(geojson, long_df, value_col)

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geo_with_colors,
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        get_line_color=[80, 80, 80, 60],
        line_width_min_pixels=0.5,
    )
    view_state = pdk.ViewState(latitude=10, longitude=10, zoom=1.2)
    tooltip = {
        "html": "<b>{name}</b><br/>{value}",
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }
    st.pydeck_chart(
        pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
    )

    _render_legend(breaks, unit_display)

    # What the hovered number actually means -- the tooltip itself just
    # shows a bare number, which is illegible to anyone new to this
    # indicator or this dashboard.
    metric_phrase = indicator_label or "this indicator"
    unit_phrase = f" ({unit_display})" if unit_display else ""
    st.caption(
        f"ℹ️ Hovering over a country shows its value for **{metric_phrase}**"
        f"{unit_phrase} — the same number the color shading is based on."
    )

    st.caption(
        f"{audit.n_matched} of {audit.n_geometries} places on the map have "
        "data for this indicator."
    )
    st.caption("⬜ Grey = no data available for this country.")

    for c in citations:
        st.caption(f"Source: {c.render()}")
