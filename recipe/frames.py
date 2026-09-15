"""Convert raw Data Commons observation JSON into tidy long-format frames.

The long schema is agency-agnostic: every observation, from any agency, ends
up in one dataframe with the same columns, which is what lets the rest of the
engine (joins, validation, plots) treat all sources identically.
"""

from __future__ import annotations

import pandas as pd

from recipe.catalog import Catalog, Indicator
from recipe.dcid_grammar import parse_dcid
from recipe.datacommons_client import ObservationPayload

LONG_COLUMNS = [
    "place_dcid",
    "date",
    "indicator_key",
    "variable_dcid",
    "value",
    "unit",
    "unit_display",
    "source_agency",
    "provenance_id",
    "provenance_url",
    "facet_id",
]


def series_within_to_long(
    payload: ObservationPayload, indicator: Indicator
) -> pd.DataFrame:
    """Turn one variable's series/within payload into a long dataframe.

    Adds the indicator's parsed dimension columns (e.g. `cook_fuel`) so a
    downstream filter can select "rural" regardless of which agency's
    dimension-value spelling produced the row.
    """
    var_data = payload.variable(indicator.dcid)
    rows: list[dict] = []
    for place_dcid, place_obs in var_data.items():
        facet_id = place_obs.get("facet")
        facet_meta = payload.facet(facet_id) if facet_id else {}
        for point in place_obs.get("series", []):
            rows.append(
                {
                    "place_dcid": place_dcid,
                    "date": point["date"],
                    "indicator_key": indicator.key,
                    "variable_dcid": indicator.dcid,
                    "value": point["value"],
                    "unit": facet_meta.get("unit"),
                    "unit_display": facet_meta.get("unitDisplayName"),
                    "source_agency": indicator.source_agency,
                    "provenance_id": facet_meta.get("provenanceId"),
                    "provenance_url": facet_meta.get("provenanceUrl"),
                    "facet_id": facet_id,
                }
            )

    df = pd.DataFrame(rows, columns=LONG_COLUMNS)
    if df.empty:
        return df

    df["date"] = df["date"].astype(str)
    for dim_name, dim_value in indicator.dimensions.items():
        df[dim_name.lower()] = dim_value
    return df


def point_within_to_long(
    payload: ObservationPayload, indicator: Indicator
) -> pd.DataFrame:
    """Turn one variable's point/within (latest-only) payload into a long df."""
    var_data = payload.variable(indicator.dcid)
    rows: list[dict] = []
    for place_dcid, obs in var_data.items():
        facet_id = obs.get("facet")
        facet_meta = payload.facet(facet_id) if facet_id else {}
        rows.append(
            {
                "place_dcid": place_dcid,
                "date": str(obs["date"]),
                "indicator_key": indicator.key,
                "variable_dcid": indicator.dcid,
                "value": obs["value"],
                "unit": facet_meta.get("unit"),
                "unit_display": facet_meta.get("unitDisplayName"),
                "source_agency": indicator.source_agency,
                "provenance_id": facet_meta.get("provenanceId"),
                "provenance_url": facet_meta.get("provenanceUrl"),
                "facet_id": facet_id,
            }
        )
    df = pd.DataFrame(rows, columns=LONG_COLUMNS)
    for dim_name, dim_value in indicator.dimensions.items():
        if not df.empty:
            df[dim_name.lower()] = dim_value
    return df


def attach_place_names(df: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """Add a `place_name` column from a place_dcid -> name mapping."""
    out = df.copy()
    out["place_name"] = out["place_dcid"].map(names)
    return out


def to_wide(
    long_df: pd.DataFrame, index: list[str], value: str = "value"
) -> pd.DataFrame:
    """Pivot a long frame to wide, one column per indicator_key."""
    return long_df.pivot_table(
        index=index, columns="indicator_key", values=value, aggfunc="first"
    ).reset_index()
