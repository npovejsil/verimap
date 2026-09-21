"""Colour tokens and chart chrome, chosen for colour-vision deficiency.

Every categorical set here was run through a CVD validator rather than picked
by eye, and the ordering is the safety mechanism: hues are assigned in this
fixed order and never cycled. Measured on the adjacent pairlist (lines, bars,
stacks), the first five slots clear the gates in both modes -- worst adjacent
CVD ΔE 9.1 light / 8.4 dark against an 8.0 target, worst normal-vision ΔE 19.6
light / 19.3 dark against a 15.0 floor.

`ALL_PAIRS_CAP` is the constraint that shapes the views. Scatter, bubble and
choropleth compare *every* pair on screen, not just neighbours, and under that
harder test only the first three slots pass: at eight slots, green against
orange measures ΔE 3.2 for a protanope and red against orange measures 7.1 even
with full colour vision. So a scatter never colours by a seven-value dimension
like continent -- that becomes a filter instead.

Sequential is one hue light-to-dark, never a rainbow. Diverging is two hues
with a neutral grey midpoint, so "no difference" reads as nothing.

Dark mode is *selected*, not an automatic inversion: the dark column is the
same hues re-stepped for the dark surface and validated against it.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- categorical -------------------------------------------------------------
# Fixed assignment order. Never cycle; a 9th series folds into "Other".
CATEGORICAL_LIGHT = (
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
)
CATEGORICAL_DARK = (
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
)

#: Max series for charts that compare every pair at once (scatter, choropleth).
ALL_PAIRS_CAP = 3

# -- sequential: one hue, light -> dark --------------------------------------
_BLUE_RAMP = (
    (205, 226, 251),  # 100
    (158, 197, 244),  # 200
    (109, 167, 236),  # 300
    (57, 135, 229),  # 400
    (37, 106, 191),  # 500
    (24, 79, 149),  # 600
    (13, 54, 107),  # 700
)

# -- diverging: two poles, neutral grey midpoint -----------------------------
_DIVERGING_LIGHT = (
    (158, 47, 47),
    (227, 73, 72),
    (240, 239, 236),  # neutral -- "no difference" must not read as a hue
    (42, 120, 214),
    (24, 79, 149),
)
_DIVERGING_DARK = (
    (201, 75, 75),
    (230, 103, 103),
    (56, 56, 53),
    (57, 135, 229),
    (28, 92, 171),
)


# Map fills are opaque on purpose. At partial alpha a fill picks up whatever
# basemap sits beneath it, so the swatch in the legend describes a colour that
# never actually renders -- and a CVD measurement taken on the token stops
# describing what a viewer sees. What validates here is what renders.
@dataclass(frozen=True)
class Tokens:
    """Chart chrome for one mode. Roles, not raw hex, at the call sites."""

    dark: bool
    surface: str
    primary: str
    secondary: str
    muted: str
    grid: str
    baseline: str
    border: str
    categorical: tuple[str, ...]
    no_data: tuple[int, int, int, int]
    good: str = "#0ca30c"
    warning: str = "#fab219"
    critical: str = "#d03b3b"

    @property
    def series(self) -> str:
        """Slot 1 -- the default for a single-series chart."""
        return self.categorical[0]


LIGHT = Tokens(
    dark=False,
    surface="#fcfcfb",
    primary="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    baseline="#c3c2b7",
    border="rgba(11,11,11,0.10)",
    categorical=CATEGORICAL_LIGHT,
    no_data=(176, 176, 170, 255),
)
DARK = Tokens(
    dark=True,
    surface="#1a1a19",
    primary="#ffffff",
    secondary="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    baseline="#383835",
    border="rgba(255,255,255,0.10)",
    categorical=CATEGORICAL_DARK,
    no_data=(90, 90, 85, 255),
)

#: Kept for callers that predate theme awareness; light is the default surface.
NO_DATA_COLOR = list(LIGHT.no_data)


def tokens(dark: bool = False) -> Tokens:
    return DARK if dark else LIGHT


def active_tokens() -> Tokens:
    """Tokens for the viewer's current theme.

    Read per render rather than threaded through every signature, and falling
    back to light outside a script run so the module stays importable from
    tests and scripts.
    """
    try:
        import streamlit as st

        return tokens(getattr(st.context.theme, "type", None) == "dark")
    except Exception:  # noqa: BLE001 - theme is cosmetic, never fatal
        return LIGHT


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> list[int]:
    return [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]


def _ramp_at(ramp: tuple, t: float) -> list[int]:
    t = max(0.0, min(1.0, t))
    n = len(ramp) - 1
    idx = min(int(t * n), n - 1)
    return _lerp(ramp[idx], ramp[idx + 1], (t * n) - idx)


def sequential_color(
    value: float, vmin: float, vmax: float, alpha: int = 255, dark: bool = False
) -> list[int]:
    """Map a value to the single-hue blue ramp.

    Direction flips with the surface so the low end always recedes *toward*
    the background: pale blue on light, deep blue on dark. Magnitude still
    reads as "more ink", which is what a sequential ramp has to mean.
    """
    t = 0.0 if vmax <= vmin else (value - vmin) / (vmax - vmin)
    ramp = tuple(reversed(_BLUE_RAMP)) if dark else _BLUE_RAMP
    return _ramp_at(ramp, t) + [alpha]


def diverging_color(
    value: float, vmin: float, vmax: float, alpha: int = 255, dark: bool = False
) -> list[int]:
    """Map a signed value to the blue↔red ramp, centred on zero at the grey."""
    bound = max(abs(vmin), abs(vmax), 1e-9)
    t = max(-1.0, min(1.0, value / bound))
    return _ramp_at(_DIVERGING_DARK if dark else _DIVERGING_LIGHT, (t + 1) / 2) + [
        alpha
    ]


def sequential_scale(dark: bool = False) -> list[list]:
    """The same ramp as a plotly colorscale."""
    ramp = tuple(reversed(_BLUE_RAMP)) if dark else _BLUE_RAMP
    n = len(ramp) - 1
    return [[i / n, f"rgb{c}"] for i, c in enumerate(ramp)]


def apply_chart_chrome(fig, tok: Tokens, *, legend: bool = True) -> None:
    """Recede the chrome so the data is the only thing with weight.

    Hairline grid, muted axis ink, no plot border, transparent surface so the
    chart sits on the page rather than in a box, and a hover label that
    matches the surface instead of plotly's default black.
    """
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", sans-serif',
            size=13,
            color=tok.secondary,
        ),
        margin=dict(t=56 if legend else 24, l=8, r=8, b=8),
        hoverlabel=dict(
            bgcolor=tok.surface,
            bordercolor=tok.border,
            font=dict(
                family='system-ui, -apple-system, "Segoe UI", sans-serif',
                color=tok.primary,
            ),
        ),
        showlegend=legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=tok.secondary),
        ),
        colorway=list(tok.categorical),
    )
    axis = dict(
        gridcolor=tok.grid,
        griddash="solid",
        zerolinecolor=tok.baseline,
        linecolor=tok.baseline,
        tickfont=dict(color=tok.muted, size=12),
        title_font=dict(color=tok.secondary, size=13),
        showline=False,
        ticks="",
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)


def quantile_breaks(values: list[float], n_bins: int = 5) -> list[float]:
    """Bin edges spanning the data's own quantiles, deduplicated.

    A plain min-max scale wastes almost all its color range whenever many
    places cluster near one end -- verified real case: 124 of 217 countries
    report exactly 100% electricity access, so a linear scale renders all of
    them (and everyone above ~90%) as the same darkest shade, while the real
    variation (mostly African countries between 5-90%) gets compressed into
    a narrow band of similar blues. Quantile breaks instead give each bin
    roughly the same NUMBER of places, so color separates places that are
    actually different and stops trying to separate places that report the
    same number.

    Falls back to the unique values themselves if there are fewer of them
    than requested bins (e.g. a mostly-constant indicator).
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
    value: float, breaks: list[float], alpha: int = 255, dark: bool = False
) -> list[int]:
    """Map a value to one discrete step of the sequential ramp using quantile bins.

    Unlike `sequential_color`'s continuous interpolation, every value in the
    same bin gets the exact same color -- the legend can then show one swatch
    per bin with an exact range, instead of an unlabeled gradient. Ramp
    direction flips with the surface for the same reason it does there.
    """
    ramp = tuple(reversed(_BLUE_RAMP)) if dark else _BLUE_RAMP
    if len(breaks) < 2:
        return list(ramp[-1]) + [alpha]

    n_bins = len(breaks) - 1
    bin_idx = n_bins - 1
    for i in range(n_bins):
        if value <= breaks[i + 1]:
            bin_idx = i
            break

    # Sample the ramp at the bin's midpoint so bins spread across the full
    # light->dark range rather than clustering in the ramp's interior.
    return _ramp_at(ramp, (bin_idx + 0.5) / n_bins) + [alpha]


def bin_label(
    breaks: list[float], bin_idx: int, unit_display: str | None = None
) -> str:
    """Human-readable range label for one bin, e.g. '65.1 - 88.7%'."""
    lo, hi = breaks[bin_idx], breaks[bin_idx + 1]
    suffix = f" {unit_display}" if unit_display else ""
    return f"{lo:.1f}{suffix} – {hi:.1f}{suffix}"
