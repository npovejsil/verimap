"""Small local color helpers for pydeck fill colors.

pydeck's GeoJsonLayer wants `[r, g, b, a]` integer arrays per feature. This
is a minimal standalone replacement for the internal `vizwhiz` package
(not installable outside the NYT network) covering just what the choropleth
needs.
"""

from __future__ import annotations

NO_DATA_COLOR = [229, 229, 229, 120]

# Sequential ramp (low -> high), used when the metric is a level (e.g. % access).
_SEQUENTIAL = [
    (255, 247, 188),
    (254, 196, 79),
    (217, 95, 14),
    (153, 52, 4),
]

# Diverging ramp (negative -> positive), used when the metric is a gap/difference.
_DIVERGING = [
    (178, 24, 43),
    (244, 165, 130),
    (247, 247, 247),
    (146, 197, 222),
    (33, 102, 172),
]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> list[int]:
    return [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]


def sequential_color(
    value: float, vmin: float, vmax: float, alpha: int = 200
) -> list[int]:
    """Map a value in [vmin, vmax] to a color on the sequential ramp."""
    if vmax <= vmin:
        t = 0.0
    else:
        t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    n = len(_SEQUENTIAL) - 1
    idx = min(int(t * n), n - 1)
    local_t = (t * n) - idx
    rgb = _lerp(_SEQUENTIAL[idx], _SEQUENTIAL[idx + 1], local_t)
    return rgb + [alpha]


def diverging_color(
    value: float, vmin: float, vmax: float, alpha: int = 200
) -> list[int]:
    """Map a value in [vmin, vmax] to a color on the diverging ramp, centered at 0."""
    bound = max(abs(vmin), abs(vmax), 1e-9)
    t = max(-1.0, min(1.0, value / bound))
    t01 = (t + 1) / 2
    n = len(_DIVERGING) - 1
    idx = min(int(t01 * n), n - 1)
    local_t = (t01 * n) - idx
    rgb = _lerp(_DIVERGING[idx], _DIVERGING[idx + 1], local_t)
    return rgb + [alpha]
