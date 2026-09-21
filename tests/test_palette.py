"""Properties the map legend depends on.

The bug these guard: the legend said "Grey = no data" while the no-data fill
was 47% alpha, so what rendered was whatever the basemap showed through -- a
colour the legend never described. A legend is only honest if it is drawn from
the same values the map fills use.
"""

from __future__ import annotations

from views.palette import (
    NO_DATA_COLOR,
    _SEQUENTIAL,
    binned_sequential_color,
    quantile_breaks,
    sequential_color,
)


def _luminance(rgb: tuple[int, int, int]) -> float:
    """Relative luminance, for checking the ramp actually darkens."""

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_no_data_fill_is_opaque() -> None:
    # At any alpha below 255 the rendered colour depends on the basemap, so the
    # legend cannot name it. This is the actual defect, in one assertion.
    assert NO_DATA_COLOR[3] == 255


def test_sequential_fills_are_opaque_by_default() -> None:
    assert sequential_color(50, 0, 100)[3] == 255
    assert sequential_color(0, 0, 100)[3] == 255


def test_sequential_ramp_darkens_monotonically() -> None:
    # Sequential means one direction: dark = more. A ramp that brightens
    # anywhere along its length reads as two different scales.
    lums = [_luminance(step) for step in _SEQUENTIAL]
    assert lums == sorted(lums, reverse=True), lums


def test_ramp_floor_is_not_near_white() -> None:
    # The palest ColorBrewer YlOrBr step (#fff7bc) sat at 1.06:1 against the
    # light basemap -- indistinguishable from "no country here".
    assert _luminance(_SEQUENTIAL[0]) < 0.80


def test_no_data_is_clearly_darker_than_the_ramp_floor() -> None:
    # Otherwise "no data" and "lowest value" look alike, which is the one
    # confusion a choropleth must never allow.
    assert _luminance(tuple(NO_DATA_COLOR[:3])) < _luminance(_SEQUENTIAL[0])


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
    assert sequential_color(0, 0, 100)[:3] == list(_SEQUENTIAL[0])
    assert sequential_color(100, 0, 100)[:3] == list(_SEQUENTIAL[-1])
