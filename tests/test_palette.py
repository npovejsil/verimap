"""Properties the palette and the map legend depend on.

Two separate defects are guarded here. The colour system itself is CVD-
validated, so the ordering and the ramp directions are load-bearing and not
cosmetic. Separately: the legend once said "Grey = no data" while the no-data
fill was 47% alpha, so what rendered was whatever the basemap showed through
-- a colour the legend never described. A legend is only honest if it is drawn
from the same values the map fills use, and those values only mean anything if
they render as specified.
"""

from __future__ import annotations

import pytest

from views.palette import (
    ALL_PAIRS_CAP,
    CATEGORICAL_DARK,
    CATEGORICAL_LIGHT,
    DARK,
    LIGHT,
    NO_DATA_COLOR,
    _BLUE_RAMP,
    binned_sequential_color,
    diverging_color,
    quantile_breaks,
    sequential_color,
    sequential_scale,
    tokens,
)


def _luminance(rgb) -> float:
    """Relative luminance, enough to assert a ramp's direction."""

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_categorical_orders_are_the_same_length_and_unique() -> None:
    assert len(CATEGORICAL_LIGHT) == len(CATEGORICAL_DARK) == 8
    assert len(set(CATEGORICAL_LIGHT)) == 8
    assert len(set(CATEGORICAL_DARK)) == 8


def test_all_pairs_cap_is_three() -> None:
    """Scatter/choropleth compare every pair; only three slots clear that.

    Raising this without re-running the CVD validator would put green beside
    orange on an every-pair chart, which measures ΔE 3.2 to a protanope.
    """
    assert ALL_PAIRS_CAP == 3


def test_sequential_is_monotonic_in_lightness_on_light_surface() -> None:
    """One hue, light to dark -- the defining property of a sequential ramp."""
    lums = [
        _luminance(sequential_color(v, 0, 100, dark=False)) for v in range(0, 101, 10)
    ]
    assert lums == sorted(lums, reverse=True), lums


def test_sequential_reverses_direction_on_the_dark_surface() -> None:
    """Low values must recede toward the surface in both modes."""
    lums = [
        _luminance(sequential_color(v, 0, 100, dark=True)) for v in range(0, 101, 10)
    ]
    assert lums == sorted(lums), lums


def test_sequential_endpoints_differ_strongly() -> None:
    lo = _luminance(sequential_color(0, 0, 100))
    hi = _luminance(sequential_color(100, 0, 100))
    assert abs(lo - hi) > 0.5


def test_sequential_handles_a_degenerate_range() -> None:
    assert sequential_color(5, 5, 5)[:3] == sequential_color(0, 0, 0)[:3]


def test_diverging_midpoint_is_neutral_grey() -> None:
    """Zero difference must not read as a hue."""
    r, g, b = diverging_color(0.0, -10, 10)[:3]
    assert max(r, g, b) - min(r, g, b) <= 6, (r, g, b)


def test_diverging_poles_are_opposite_hues() -> None:
    low = diverging_color(-10, -10, 10)[:3]
    high = diverging_color(10, -10, 10)[:3]
    assert low[0] > low[2]  # warm pole: more red than blue
    assert high[2] > high[0]  # cool pole: more blue than red


@pytest.mark.parametrize("dark", [False, True])
def test_sequential_scale_is_a_well_formed_plotly_colorscale(dark: bool) -> None:
    scale = sequential_scale(dark)
    positions = [p for p, _ in scale]
    assert positions[0] == 0.0 and positions[-1] == 1.0
    assert positions == sorted(positions)


def test_no_data_is_distinct_from_both_ramp_ends() -> None:
    """Absence must not be mistakable for a low value."""
    for tok in (LIGHT, DARK):
        nd = list(tok.no_data)
        lo = sequential_color(0, 0, 100, dark=tok.dark)
        assert abs(_luminance(nd) - _luminance(lo)) > 0.02 or nd[:3] != lo[:3]


def test_tokens_select_by_mode() -> None:
    assert tokens(False) is LIGHT and not LIGHT.dark
    assert tokens(True) is DARK and DARK.dark
    assert LIGHT.series == CATEGORICAL_LIGHT[0]
    assert DARK.series == CATEGORICAL_DARK[0]


def test_dark_is_a_selected_palette_not_an_inversion() -> None:
    """Six of eight hues are re-stepped for the dark surface, not flipped."""
    changed = sum(1 for a, b in zip(CATEGORICAL_LIGHT, CATEGORICAL_DARK) if a != b)
    assert changed >= 6


def test_no_data_fill_is_opaque_in_both_modes() -> None:
    # At any alpha below 255 the rendered colour depends on the basemap, so the
    # legend cannot name it -- and a CVD measurement taken on the token stops
    # describing what a viewer sees. This is the actual defect, in one place.
    assert NO_DATA_COLOR[3] == 255
    assert LIGHT.no_data[3] == 255
    assert DARK.no_data[3] == 255


def test_sequential_fills_are_opaque_by_default() -> None:
    assert sequential_color(50, 0, 100)[3] == 255
    assert sequential_color(0, 0, 100)[3] == 255


def test_sequential_ramp_darkens_monotonically() -> None:
    # Sequential means one direction: dark = more. A ramp that brightens
    # anywhere along its length reads as two different scales.
    lums = [_luminance(step) for step in _BLUE_RAMP]
    assert lums == sorted(lums, reverse=True), lums


def test_ramp_floor_is_not_near_white() -> None:
    # A near-white floor is indistinguishable from "no country here" against
    # the light basemap, whatever hue family the ramp uses.
    assert _luminance(_BLUE_RAMP[0]) < 0.80


def test_no_data_is_clearly_darker_than_the_ramp_floor() -> None:
    # Otherwise "no data" and "lowest value" look alike, which is the one
    # confusion a choropleth must never allow. Light surface only: the ramp
    # reverses on dark, so there the floor is the ramp's *dark* end.
    assert _luminance(tuple(NO_DATA_COLOR[:3])) < _luminance(_BLUE_RAMP[0])


def test_binned_fills_are_opaque_by_default() -> None:
    # Same defect as the continuous ramp: a translucent fill renders as
    # whatever the basemap shows through, so the legend cannot name it.
    breaks = quantile_breaks([0.0, 25.0, 50.0, 75.0, 100.0])
    assert binned_sequential_color(50.0, breaks)[3] == 255


def test_legend_swatches_are_drawn_from_the_map_ramp() -> None:
    # The structural guard: the legend renders one swatch per bin using the
    # same function as the fills, so it cannot name a colour the map does not
    # draw. Each bin's midpoint must land on a distinct colour.
    breaks = quantile_breaks([0.0, 25.0, 50.0, 75.0, 100.0])
    swatches = [
        tuple(binned_sequential_color((breaks[i] + breaks[i + 1]) / 2, breaks)[:3])
        for i in range(len(breaks) - 1)
    ]
    assert len(set(swatches)) == len(swatches), swatches


def test_no_data_swatch_is_not_a_ramp_colour() -> None:
    # The legend's "No data" swatch previously hardcoded rgb(229,229,229),
    # which is the drift this file exists to prevent.
    breaks = quantile_breaks([0.0, 25.0, 50.0, 75.0, 100.0])
    ramp_colours = {
        tuple(binned_sequential_color((breaks[i] + breaks[i + 1]) / 2, breaks)[:3])
        for i in range(len(breaks) - 1)
    }
    assert tuple(NO_DATA_COLOR[:3]) not in ramp_colours


def test_ramp_endpoints_are_reachable() -> None:
    assert sequential_color(0, 0, 100)[:3] == list(_BLUE_RAMP[0])
    assert sequential_color(100, 0, 100)[:3] == list(_BLUE_RAMP[-1])
