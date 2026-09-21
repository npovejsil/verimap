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


def quantile_breaks(values: list[float], n_bins: int = 5) -> list[float]:
    """Bin edges spanning the data's own quantiles, deduplicated.

    A plain min-max scale wastes almost all its color range whenever many
    places cluster near one end -- verified real case: 124 of 217 countries
    report exactly 100% electricity access, so a linear scale renders all of
    them (and everyone above ~90%) as the same darkest shade, while the real
    variation (mostly African countries between 5-90%) gets compressed into
    a narrow band of similar oranges. Quantile breaks instead give each bin
    roughly the same NUMBER of places, so color separates places that are
    actually different and stops trying to separate places that report the
    same number.

    Falls back to evenly-spaced breaks over [min, max] if there are fewer
    unique values than requested bins (e.g. a mostly-constant indicator).
    """
    uniq = sorted(set(values))
    if len(uniq) <= 1:
        lo = uniq[0] if uniq else 0.0
        return [lo, lo]
    if len(uniq) <= n_bins:
        return uniq

    step = 1.0 / n_bins
    breaks = []
    for i in range(n_bins + 1):
        q = i * step
        idx = q * (len(uniq) - 1)
        lo_idx = int(idx)
        hi_idx = min(lo_idx + 1, len(uniq) - 1)
        frac = idx - lo_idx
        breaks.append(uniq[lo_idx] + (uniq[hi_idx] - uniq[lo_idx]) * frac)

    deduped = [breaks[0]]
    for b in breaks[1:]:
        if b > deduped[-1]:
            deduped.append(b)
    return deduped


def binned_sequential_color(
    value: float, breaks: list[float], alpha: int = 200
) -> list[int]:
    """Map a value to one discrete step of the sequential ramp using quantile bins.

    Unlike `sequential_color`'s continuous interpolation, every value in the
    same bin gets the exact same color -- the legend can then show one swatch
    per bin with an exact range, instead of an unlabeled gradient.
    """
    if len(breaks) < 2:
        return list(_SEQUENTIAL[-1]) + [alpha]

    n_bins = len(breaks) - 1
    bin_idx = n_bins - 1
    for i in range(n_bins):
        if value <= breaks[i + 1]:
            bin_idx = i
            break

    # Sample the ramp at the bin's midpoint so bins spread across the full
    # light->dark range rather than clustering in the ramp's interior.
    t = (bin_idx + 0.5) / n_bins
    ramp_n = len(_SEQUENTIAL) - 1
    ramp_idx = min(int(t * ramp_n), ramp_n - 1)
    local_t = (t * ramp_n) - ramp_idx
    rgb = _lerp(_SEQUENTIAL[ramp_idx], _SEQUENTIAL[ramp_idx + 1], local_t)
    return rgb + [alpha]


def bin_label(
    breaks: list[float], bin_idx: int, unit_display: str | None = None
) -> str:
    """Human-readable range label for one bin, e.g. '65.1 - 88.7%'."""
    lo, hi = breaks[bin_idx], breaks[bin_idx + 1]
    suffix = f" {unit_display}" if unit_display else ""
    return f"{lo:.1f}{suffix} – {hi:.1f}{suffix}"
