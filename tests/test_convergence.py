from __future__ import annotations

import pandas as pd

from analytics.convergence import compute_convergence


def test_returns_none_with_too_few_overlapping_places() -> None:
    df = pd.DataFrame(
        {
            "place_dcid": ["A", "B", "A", "B"],
            "date": ["2000", "2000", "2020", "2020"],
            "value": [10.0, 20.0, 15.0, 25.0],
        }
    )
    assert compute_convergence(df, "2000", "2020") is None


def test_recovers_a_clear_convergence_signal() -> None:
    # Construct places where low starters gain more (textbook convergence)
    rows = []
    for i, base in enumerate([10, 20, 30, 40, 50, 60, 70, 80]):
        gain = 100 - base  # low starters gain more, ends everyone at 100
        rows.append({"place_dcid": f"P{i}", "date": "2000", "value": float(base)})
        rows.append(
            {"place_dcid": f"P{i}", "date": "2020", "value": float(base + gain)}
        )
    df = pd.DataFrame(rows)

    result = compute_convergence(df, "2000", "2020")
    assert result is not None
    assert result.n_places == 8
    assert result.beta < 0  # negative beta = convergence signal
    assert result.r_squared > 0.9


def test_ceiling_share_flags_places_near_the_cap() -> None:
    rows = []
    for i, base in enumerate([99.6, 99.7, 99.8, 10.0, 20.0]):
        rows.append({"place_dcid": f"P{i}", "date": "2000", "value": base})
        rows.append(
            {"place_dcid": f"P{i}", "date": "2020", "value": min(base + 5, 100.0)}
        )
    df = pd.DataFrame(rows)

    result = compute_convergence(df, "2000", "2020", ceiling=100, ceiling_tolerance=0.5)
    assert result is not None
    # 3 of 5 places start within tolerance of the ceiling
    assert result.ceiling_share == 0.6


def test_no_ceiling_share_when_ceiling_not_provided() -> None:
    rows = []
    for i in range(6):
        rows.append({"place_dcid": f"P{i}", "date": "2000", "value": float(i * 10)})
        rows.append({"place_dcid": f"P{i}", "date": "2020", "value": float(i * 10 + 5)})
    df = pd.DataFrame(rows)
    result = compute_convergence(df, "2000", "2020")
    assert result.ceiling_share == 0.0
