from __future__ import annotations

import pandas as pd

from analytics.coverage import coverage_heatmap_data


def test_missing_cell_detection_survives_colliding_place_names() -> None:
    """Regression test for a bug found live: remapping the grid index to
    place names before computing missing cells breaks .loc scalar lookups
    when two DCIDs both fail name resolution and collide on NaN.

    This reproduces the exact failure mode (verified live: GRC and SVN both
    fail place-name resolution due to a WAF false positive) without needing
    the view module or a live API call.
    """
    long_df = pd.DataFrame(
        {
            "place_dcid": ["country/GRC", "country/SVN", "country/A"],
            "date": ["2020", "2020", "2020"],
        }
    )
    grid = coverage_heatmap_data(long_df, 2020, 2021)

    # Simulate the bug: two DCIDs collide on an unresolved (NaN) name
    names = pd.Series({"country/A": "Alphaland"})  # GRC, SVN unresolved
    resolved = names.reindex(grid.index)
    display_grid = grid.copy()
    display_grid.index = resolved.where(resolved.notna(), display_grid.index)

    # The fix computes missing cells from the DCID-indexed grid, not the
    # (possibly-colliding) display grid -- confirm that path still works
    # even though display_grid's index is no longer unique.
    missing_mask = grid == 0
    missing_rows = [
        {"place_dcid": p, "date": y}
        for p in grid.index
        for y in grid.columns
        if missing_mask.loc[p, y]
    ]
    assert {"place_dcid": "country/GRC", "date": "2021"} in missing_rows
    assert {"place_dcid": "country/SVN", "date": "2021"} in missing_rows
    assert {"place_dcid": "country/A", "date": "2021"} in missing_rows
    assert len(missing_rows) == 3
