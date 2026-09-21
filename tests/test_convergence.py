from __future__ import annotations

import pandas as pd

from analytics.convergence import compute_convergence, rank_convergence_movers


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


def test_per_place_has_one_row_per_overlapping_place() -> None:
    rows = []
    for i, base in enumerate([10, 20, 30, 40, 50, 60, 70, 80]):
        gain = 100 - base
        rows.append({"place_dcid": f"P{i}", "date": "2000", "value": float(base)})
        rows.append(
            {"place_dcid": f"P{i}", "date": "2020", "value": float(base + gain)}
        )
    df = pd.DataFrame(rows)
    result = compute_convergence(df, "2000", "2020")
    assert result is not None
    assert len(result.per_place) == result.n_places
    assert set(result.per_place.columns) == {
        "place_dcid",
        "base_value",
        "end_value",
        "change",
    }


def test_rank_convergence_movers_names_the_right_countries_higher_is_better() -> None:
    # P0..P3 start behind (base <= median); P0/P1 catch up a lot, P2/P3 barely move.
    # P4..P7 start ahead and are excluded from the "behind" pool entirely.
    rows = []
    behind_gains = {"P0": 60.0, "P1": 50.0, "P2": 1.0, "P3": 0.0}
    for i, base in enumerate([10.0, 15.0, 20.0, 25.0]):
        place = f"P{i}"
        rows.append({"place_dcid": place, "date": "2000", "value": base})
        rows.append(
            {
                "place_dcid": place,
                "date": "2020",
                "value": base + behind_gains[place],
            }
        )
    for i, base in enumerate([80.0, 85.0, 90.0, 95.0]):
        place = f"P{i + 4}"
        rows.append({"place_dcid": place, "date": "2000", "value": base})
        rows.append({"place_dcid": place, "date": "2020", "value": base + 2.0})
    df = pd.DataFrame(rows)

    result = compute_convergence(df, "2000", "2020")
    assert result is not None
    movers = rank_convergence_movers(result, polarity="higher_is_better", top_n=2)
    assert movers is not None
    assert list(movers.catching_up["place_dcid"]) == ["P0", "P1"]
    assert list(movers.falling_behind["place_dcid"]) == ["P3", "P2"]
    # the ahead-at-base-year places must never appear in either list
    assert "P4" not in set(movers.catching_up["place_dcid"]) | set(
        movers.falling_behind["place_dcid"]
    )


def test_rank_convergence_movers_inverts_for_lower_is_better() -> None:
    # For lower_is_better (e.g. energy intensity), "behind" means a HIGH
    # base value, and "improving" means the value going DOWN.
    rows = []
    behind_deltas = {"P0": -60.0, "P1": -50.0, "P2": -1.0, "P3": 0.0}
    for i, base in enumerate([95.0, 90.0, 85.0, 80.0]):
        place = f"P{i}"
        rows.append({"place_dcid": place, "date": "2000", "value": base})
        rows.append(
            {
                "place_dcid": place,
                "date": "2020",
                "value": base + behind_deltas[place],
            }
        )
    for i, base in enumerate([10.0, 15.0, 20.0, 25.0]):
        place = f"P{i + 4}"
        rows.append({"place_dcid": place, "date": "2000", "value": base})
        rows.append({"place_dcid": place, "date": "2020", "value": base + 2.0})
    df = pd.DataFrame(rows)

    result = compute_convergence(df, "2000", "2020")
    assert result is not None
    movers = rank_convergence_movers(result, polarity="lower_is_better", top_n=2)
    assert movers is not None
    # P0 dropped the most (biggest improvement for lower_is_better)
    assert list(movers.catching_up["place_dcid"]) == ["P0", "P1"]
    assert list(movers.falling_behind["place_dcid"]) == ["P3", "P2"]


def test_rank_convergence_movers_none_for_neutral_polarity() -> None:
    rows = []
    for i, base in enumerate([10.0, 20.0, 30.0, 40.0, 50.0, 60.0]):
        rows.append({"place_dcid": f"P{i}", "date": "2000", "value": base})
        rows.append({"place_dcid": f"P{i}", "date": "2020", "value": base + 5.0})
    df = pd.DataFrame(rows)
    result = compute_convergence(df, "2000", "2020")
    assert result is not None
    assert rank_convergence_movers(result, polarity="neutral") is None


def test_rank_convergence_movers_none_when_per_place_empty() -> None:
    empty_result = compute_convergence(
        pd.DataFrame({"place_dcid": [], "date": [], "value": []}), "2000", "2020"
    )
    assert empty_result is None  # compute_convergence itself returns None here

    # Construct a ConvergenceResult with an explicitly empty per_place to
    # cover the case of a result built without this field populated.
    from analytics.convergence import ConvergenceResult

    bare_result = ConvergenceResult(
        n_places=0,
        beta=0.0,
        beta_ci_low=0.0,
        beta_ci_high=0.0,
        r_squared=0.0,
        ceiling_share=0.0,
    )
    assert rank_convergence_movers(bare_result, polarity="higher_is_better") is None
