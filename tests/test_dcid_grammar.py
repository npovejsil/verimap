from __future__ import annotations

from recipe.dcid_grammar import format_dcid, parse_dcid


def test_base_indicator_no_dimensions() -> None:
    p = parse_dcid("undata/sdg/EG_ACS_ELEC")
    assert p.agency == "sdg"
    assert p.code == "EG_ACS_ELEC"
    assert p.dimensions == {}
    assert p.is_undata


def test_single_dimension() -> None:
    p = parse_dcid("undata/sdg/EG_ACS_ELEC.URBANIZATION--DOU_R")
    assert p.dimensions == {"URBANIZATION": "DOU_R"}


def test_multiple_dimensions() -> None:
    p = parse_dcid(
        "undata/eclac/NO_ELECTRICITY.AVERAGING_METHOD--_Z"
        "__INCOME_QUANTILE--Q1__URBANIZATION--R"
    )
    assert p.agency == "eclac"
    assert p.code == "NO_ELECTRICITY"
    # _Z ("not applicable") normalizes to absent
    assert "AVERAGING_METHOD" not in p.dimensions
    assert p.dimensions == {"INCOME_QUANTILE": "Q1", "URBANIZATION": "R"}


def test_non_undata_dcid() -> None:
    p = parse_dcid("Count_Person")
    assert p.agency is None
    assert p.code == "Count_Person"
    assert p.dimensions == {}
    assert not p.is_undata


def test_who_dimension_shape() -> None:
    p = parse_dcid("undata/who/COOKFUEL_PROP.COOK_FUEL--CLEAN__URBANIZATION--U")
    assert p.dimensions == {"COOK_FUEL": "CLEAN", "URBANIZATION": "U"}


def test_format_roundtrip() -> None:
    dcid = "undata/sdg/EG_ACS_ELEC.URBANIZATION--DOU_R"
    p = parse_dcid(dcid)
    assert format_dcid(p.agency, p.code, p.dimensions) == dcid


def test_format_sorts_dimensions_for_canonical_comparison() -> None:
    a = format_dcid("who", "COOKFUEL_PROP", {"URBANIZATION": "U", "COOK_FUEL": "CLEAN"})
    b = format_dcid("who", "COOKFUEL_PROP", {"COOK_FUEL": "CLEAN", "URBANIZATION": "U"})
    assert a == b


def test_format_no_dimensions() -> None:
    assert format_dcid("sdg", "EG_ACS_ELEC") == "undata/sdg/EG_ACS_ELEC"
