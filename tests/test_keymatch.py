from __future__ import annotations

from recipe.catalog import Catalog, Indicator, Topic
from recipe.keymatch import compute_join_spec

DIMENSIONS = {
    "URBANIZATION": {
        "canonical_values": {
            "rural": {"aliases": ["R", "DOU_R"]},
            "urban": {"aliases": ["U", "DOU_U"]},
        }
    },
    "COOK_FUEL": {
        "canonical_values": {
            "clean": {"aliases": ["CLEAN"]},
            "polluting": {"aliases": ["POLLUTING"]},
        }
    },
}

UNITS = {
    "percent": {"members": ["Percent", "undata/UNIT_MEASURE-PT_POP"]},
    "power_per_capita": {"members": ["undata/UNIT_MEASURE-RATIO_POWER_W_PER_POP"]},
}


def _catalog() -> Catalog:
    return Catalog(indicators={}, topics={}, dimensions=DIMENSIONS, units=UNITS)


def _indicator(**overrides) -> Indicator:
    base = dict(
        key="ind",
        dcid="undata/sdg/X",
        label="X",
        topics=(),
        polarity="higher_is_better",
        dimensions={},
        unit=None,
        temporal_start=None,
        temporal_end=None,
    )
    base.update(overrides)
    return Indicator(**base)


def test_direct_join_same_unit_family_verified_real_case() -> None:
    """Mirrors the verified real join: SDG electricity access x WHO clean cooking.

    Real numbers: 217 vs 194 places, 194 shared, Jaccard 0.894; both 2000-2024
    (25 shared years); SDG unit 'Percent', WHO unit 'undata/UNIT_MEASURE-PT_POP'.
    """
    elec = _indicator(
        key="sdg_elec_access",
        unit="Percent",
        temporal_start="2000",
        temporal_end="2024",
    )
    cook = _indicator(
        key="who_clean_cooking",
        unit="undata/UNIT_MEASURE-PT_POP",
        dimensions={"COOK_FUEL": "CLEAN"},
        temporal_start="2000",
        temporal_end="2024",
    )
    left_places = {f"country/{i}" for i in range(217)}
    right_places = {f"country/{i}" for i in range(23, 217)}  # 194 shared, 23 elec-only

    spec = compute_join_spec(elec, cook, _catalog(), left_places, right_places)

    assert spec.place_overlap.n_shared == 194
    assert round(spec.place_overlap.jaccard, 3) == 0.894
    assert spec.shared_years == 25
    assert spec.unit_relation == "same_family"
    assert spec.comparability == "direct"
    assert not spec.blockers


def test_urbanization_alias_resolves_dou_r_to_r() -> None:
    """The sharpest case from the plan: SDG writes 'DOU_R', WHO writes 'R', both rural."""
    left = _indicator(key="l", dimensions={"URBANIZATION": "DOU_R"}, unit="Percent")
    right = _indicator(key="r", dimensions={"URBANIZATION": "R"}, unit="Percent")

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/A"})

    match = spec.shared_dimensions["URBANIZATION"]
    assert match.canonical == "rural"
    assert not spec.warnings


def test_unresolved_dimension_value_warns() -> None:
    left = _indicator(key="l", dimensions={"URBANIZATION": "DOU_R"})
    right = _indicator(key="r", dimensions={"URBANIZATION": "TOTALLY_UNKNOWN"})

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/A"})

    assert spec.shared_dimensions["URBANIZATION"].canonical is None
    assert any("couldn't match them up" in w for w in spec.warnings)


def test_incomparable_units_blocks_arithmetic_not_plotting() -> None:
    percent_ind = _indicator(key="l", unit="Percent")
    watts_ind = _indicator(key="r", unit="undata/UNIT_MEASURE-RATIO_POWER_W_PER_POP")

    spec = compute_join_spec(
        percent_ind, watts_ind, _catalog(), {"country/A"}, {"country/A"}
    )

    assert spec.unit_relation == "incomparable"
    assert spec.comparability == "axes_only"
    assert not spec.blockers  # legal on two scatter axes


def test_zero_place_overlap_blocks() -> None:
    left = _indicator(key="l")
    right = _indicator(key="r")

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/B"})

    assert spec.comparability == "blocked"
    assert "no places in common" in spec.blockers


def test_zero_date_overlap_blocks() -> None:
    left = _indicator(key="l", temporal_start="1990", temporal_end="1999")
    right = _indicator(key="r", temporal_start="2010", temporal_end="2020")

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/A"})

    assert spec.shared_years == 0
    assert "no years in common" in spec.blockers
    assert spec.comparability == "blocked"


def test_thin_place_overlap_warns_below_jaccard_threshold() -> None:
    """ECLAC's Latin-America-only indicators should correctly trip this."""
    left = _indicator(key="l")
    right = _indicator(key="r")
    left_places = {f"country/{i}" for i in range(200)}
    right_places = {f"country/{i}" for i in range(20)}  # small overlap, low jaccard

    spec = compute_join_spec(left, right, _catalog(), left_places, right_places)

    assert spec.place_overlap.jaccard < 0.5
    assert any("covered by both sources" in w for w in spec.warnings)


def test_thin_date_overlap_warns_below_minimum_years() -> None:
    left = _indicator(
        key="l", temporal_start="2020", temporal_end="2024", unit="Percent"
    )
    right = _indicator(
        key="r", temporal_start="2023", temporal_end="2030", unit="Percent"
    )

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/A"})

    assert spec.shared_years == 2
    assert any("can't be compared" in w for w in spec.warnings)
    assert spec.comparability == "direct"  # thin overlap warns, does not block


def test_join_keys_include_shared_dimensions() -> None:
    left = _indicator(key="l", dimensions={"URBANIZATION": "R", "SEX": "F"})
    right = _indicator(key="r", dimensions={"URBANIZATION": "R"})

    spec = compute_join_spec(left, right, _catalog(), {"country/A"}, {"country/A"})

    assert spec.join_keys == ("place_dcid", "date", "URBANIZATION")
    assert spec.left_only_dimensions == {"SEX": "F"}
    assert spec.right_only_dimensions == {}
