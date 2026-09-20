from __future__ import annotations

import pandas as pd

from analytics.coverage import compute_coverage, coverage_heatmap_data


def test_compute_coverage_full_grid_has_zero_missing() -> None:
    rows = [
        {"place_dcid": p, "date": str(y)} for p in ["A", "B"] for y in range(2000, 2003)
    ]
    df = pd.DataFrame(rows)
    report = compute_coverage(df, 2000, 2002)

    assert report.n_places_total == 2
    assert report.n_place_years_expected == 6
    assert report.n_place_years_observed == 6
    assert report.n_missing_cells == 0
    assert report.missing_share == 0.0


def test_compute_coverage_reports_real_gap() -> None:
    rows = [
        {"place_dcid": "A", "date": "2000"},
        {"place_dcid": "A", "date": "2001"},
        {"place_dcid": "B", "date": "2000"},
        # B is missing 2001
    ]
    df = pd.DataFrame(rows)
    report = compute_coverage(df, 2000, 2001)

    assert report.n_place_years_expected == 4
    assert report.n_place_years_observed == 3
    assert report.n_missing_cells == 1
    assert report.missing_share == 0.25


def test_compute_coverage_verified_real_numbers() -> None:
    # Mirrors the verified real case: EG_ACS_ELEC has 217 places x 25 years
    # (2000-2024) = 5425 expected, 5400 observed, 25 missing (0.5%). Drop one
    # scattered cell per country/0..24 (not a whole place) so all 217 places
    # remain present in place_dcid.unique() -- expected stays 217x25.
    places = [f"country/{i}" for i in range(217)]
    years = [str(y) for y in range(2000, 2025)]
    # Drop exactly one (place, year) cell for each of the first 25 places,
    # each place keeping its other 24 years -- so all 217 places remain
    # present and "expected" is unaffected.
    missing_cells = {(f"country/{i}", years[i]) for i in range(25)}
    rows = [
        {"place_dcid": p, "date": y}
        for p in places
        for y in years
        if (p, y) not in missing_cells
    ]
    df = pd.DataFrame(rows)

    report = compute_coverage(df, 2000, 2024)
    assert report.n_place_years_expected == 5425
    assert report.n_missing_cells == 25
    assert abs(report.missing_share - 0.0046) < 0.001


def test_stalest_places_sorted_oldest_first() -> None:
    rows = [
        {"place_dcid": "OLD", "date": "2010"},
        {"place_dcid": "NEW", "date": "2024"},
        {"place_dcid": "MID", "date": "2018"},
    ]
    df = pd.DataFrame(rows)
    report = compute_coverage(df, 2000, 2024)
    ordered = [p for p, _ in report.stalest_places]
    assert ordered[0] == "OLD"
    assert ordered[-1] == "NEW"


def test_coverage_heatmap_data_shape_and_values() -> None:
    rows = [
        {"place_dcid": "A", "date": "2000"},
        {"place_dcid": "A", "date": "2001"},
        {"place_dcid": "B", "date": "2000"},
    ]
    df = pd.DataFrame(rows)
    grid = coverage_heatmap_data(df, 2000, 2001)

    assert list(grid.index) == ["A", "B"]
    assert list(grid.columns) == ["2000", "2001"]
    assert grid.loc["A", "2001"] == 1
    assert grid.loc["B", "2001"] == 0
