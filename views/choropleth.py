"""Render a world choropleth for one indicator using pydeck's GeoJsonLayer.

No geopandas/shapely/Mapbox token needed: pydeck consumes the raw GeoJSON
dict directly, and st.pydeck_chart renders on the default Carto basemap.
"""

from __future__ import annotations

import copy

import pandas as pd
import pydeck as pdk
import streamlit as st

from recipe.attribution import Citation, require_citations
from recipe.geography import JoinAudit
from views.palette import NO_DATA_COLOR, sequential_color


def inject_fill_colors(
    geojson: dict, long_df: pd.DataFrame, value_col: str = "value"
) -> dict:
    """Return a copy of the GeoJSON with a per-feature fill_color property.

    Features with no matching observation get an explicit grey, never a
    default/invisible color, so absence of data is a visible category.
    """
    geo = copy.deepcopy(geojson)
    values = long_df.set_index("place_dcid")[value_col]
    vmin, vmax = values.min(), values.max()

    for feature in geo["features"]:
        place_dcid = feature["id"]
        if place_dcid in values.index:
            v = values.loc[place_dcid]
            feature["properties"]["fill_color"] = sequential_color(v, vmin, vmax)
            feature["properties"]["value"] = float(v)
        else:
            feature["properties"]["fill_color"] = NO_DATA_COLOR
            feature["properties"]["value"] = None
    return geo


def render_choropleth(
    geojson: dict,
    long_df: pd.DataFrame,
    audit: JoinAudit,
    citations: list[Citation],
    value_col: str = "value",
) -> None:
    """Render the map, join-audit line, and mandatory source attribution.

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

    geo_with_colors = inject_fill_colors(geojson, long_df, value_col)

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

    st.caption(
        f"{audit.n_matched} of {audit.n_geometries} map features matched · "
        f"{len(audit.unmatched_observation_places)} observations unmatched"
    )

    for c in citations:
        st.caption(f"Source: {c.render()}")
