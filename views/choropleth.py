"""Render a world choropleth for one indicator using pydeck's GeoJsonLayer.

No geopandas/shapely/Mapbox token needed: pydeck consumes the raw GeoJSON
dict directly, and st.pydeck_chart renders on the default Carto basemap.

Colors are binned by quantile, not a plain min-max scale. Verified real case
(electricity access): 124 of 217 countries report exactly 100%, so a linear
scale renders that entire majority as one indistinguishable dark shade while
the real variation -- mostly African countries spread from 5-90% -- gets
compressed into a narrow band of similar blues. Quantile bins instead give
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
from recipe.i18n import Translator
from views.palette import (
    Tokens,
    active_tokens,
    bin_label,
    binned_sequential_color,
    quantile_breaks,
)

_N_COLOR_BINS = 5


def inject_fill_colors(
    geojson: dict,
    long_df: pd.DataFrame,
    value_col: str = "value",
    tok: Tokens | None = None,
) -> tuple[dict, list[float]]:
    """Return a copy of the GeoJSON with a per-feature fill_color property.

    Features with no matching observation get an explicit grey, never a
    default/invisible color, so absence of data is a visible category.
    Also returns the quantile breaks used, so the caller can render a
    legend that matches the colors actually on the map.
    """
    tok = tok or active_tokens()
    geo = copy.deepcopy(geojson)
    values = long_df.set_index("place_dcid")[value_col]
    breaks = quantile_breaks(values.tolist(), n_bins=_N_COLOR_BINS)

    for feature in geo["features"]:
        place_dcid = feature["id"]
        if place_dcid in values.index:
            v = values.loc[place_dcid]
            feature["properties"]["fill_color"] = binned_sequential_color(
                v, breaks, dark=tok.dark
            )
            feature["properties"]["value"] = float(v)
        else:
            feature["properties"]["fill_color"] = list(tok.no_data)
            feature["properties"]["value"] = None
    return geo, breaks


def _render_legend(
    breaks: list[float], unit_display: str | None, t: Translator, tok: Tokens
) -> None:
    """One color swatch per quantile bin, with its exact value range."""
    if len(breaks) < 2:
        return
    n_bins = len(breaks) - 1
    cols = st.columns(n_bins + 1)  # +1 for the "no data" swatch
    for i in range(n_bins):
        color = binned_sequential_color(
            (breaks[i] + breaks[i + 1]) / 2, breaks, dark=tok.dark
        )
        r, g, b, _ = color
        with cols[i]:
            st.markdown(
                f"<div style='background-color: rgb({r},{g},{b}); "
                "height: 18px; border-radius: 3px;'></div>",
                unsafe_allow_html=True,
            )
            st.caption(bin_label(breaks, i, unit_display))
    with cols[n_bins]:
        nr, ng, nb = tok.no_data[:3]
        st.markdown(
            f"<div style='background-color: rgb({nr},{ng},{nb}); "
            "height: 18px; border-radius: 3px;'></div>",
            unsafe_allow_html=True,
        )
        st.caption(t.t("map.no_data_swatch"))


def render_choropleth(
    geojson: dict,
    long_df: pd.DataFrame,
    audit: JoinAudit,
    citations: list[Citation],
    t: Translator,
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
            t.t(
                "map.excluded",
                count=len(excluded),
                places=t.join([str(e) for e in excluded]),
            )
        )

    tok = active_tokens()
    geo_with_colors, breaks = inject_fill_colors(geojson, long_df, value_col, tok)

    layer = pdk.Layer(
        "GeoJsonLayer",
        data=geo_with_colors,
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color="properties.fill_color",
        # Borders carry the country outline when a fill is pale, and separate
        # two neighbouring fills so they never bleed into one shape. The value
        # is the measured one and deliberately not theme-aware: at 24% alpha a
        # surface-coloured hairline was effectively invisible, and a mid grey
        # holds its own against both the light and dark basemaps.
        get_line_color=[110, 110, 105, 170],
        line_width_min_pixels=0.5,
    )
    # Web Mercator's basemap tiles are infinite in longitude by default --
    # zooming out far enough makes the CARTO basemap repeat side-by-side
    # (the "uncanny double-Earth" reported live). Two independent fixes,
    # verified together in a real browser across scroll-wheel zoom, the
    # +/- controls, and the default view on load: `repeat=False` on the
    # MapView stops deck.gl from drawing extra copies of the world, and
    # `min_zoom` on the same View caps how far any zoom interaction can
    # push past that point. _START_ZOOM is intentionally below _MIN_ZOOM --
    # deck.gl clamps the initial render up to the floor, which lands on a
    # clean single-world view without needing to hand-tune a start value
    # for every possible viewport width.
    _START_ZOOM = 1.2
    _MIN_ZOOM = 3.0
    view_state = pdk.ViewState(latitude=10, longitude=10, zoom=_START_ZOOM)
    view = pdk.View(type="MapView", controller=True, repeat=False, min_zoom=_MIN_ZOOM)
    tooltip = {
        "html": "<b>{name}</b><br/>{value}",
        "style": {
            "backgroundColor": tok.surface,
            "color": tok.primary,
            "border": f"1px solid {tok.border}",
            "borderRadius": "8px",
            "fontFamily": 'system-ui, -apple-system, "Segoe UI", sans-serif',
            "fontSize": "13px",
            "padding": "8px 10px",
        },
    }
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            views=[view],
            tooltip=tooltip,
            # A light basemap, because the fill ramp runs light -> dark. On the
            # default dark basemap the top of the scale sank into the background,
            # so the countries scoring highest were the hardest ones to see.
            # No-labels: place names under a choropleth compete with the fill.
            map_style=pdk.map_styles.LIGHT_NO_LABELS,
        )
    )

    _render_legend(breaks, unit_display, t, tok)

    # What the hovered number actually means -- the tooltip itself just
    # shows a bare number, which is illegible to anyone new to this
    # indicator or this dashboard.
    metric_phrase = indicator_label or t.t("map.this_indicator")
    unit_phrase = f" ({unit_display})" if unit_display else ""
    st.caption(t.t("map.hover_hint", metric=metric_phrase, unit=unit_phrase))

    st.caption(t.t("map.coverage", matched=audit.n_matched, total=audit.n_geometries))
    st.caption(t.t("map.no_data_legend"))

    for c in citations:
        st.caption(t.t("source.prefix", citation=c.render(t)))
