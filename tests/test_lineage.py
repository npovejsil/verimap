from __future__ import annotations

from recipe.catalog import Indicator
from recipe.datacommons_client import ObservationPayload
from recipe.geography import JoinAudit
from recipe.i18n import load_locales
from recipe.lineage import (
    build_lineage,
    cross_source_check,
    _coverage_check,
    _facet_check,
    _geometry_check,
    _selection,
    _transformations,
    _unit_check,
)

LOCALES = load_locales()


def _indicator(**over) -> Indicator:
    base = dict(
        key="sdg_elec_access",
        dcid="undata/sdg/EG_ACS_ELEC",
        label="Electricity access",
        topics=("energy_access",),
        polarity="higher_is_better",
        source_agency="sdg",
        unit="Percent",
        provenance_id="undata/p/SDG",
        provenance_url="https://unstats.un.org/sdgs/dataportal",
        place_coverage=217,
        enriched=True,
    )
    base.update(over)
    return Indicator(**base)


def _payload(places: dict[str, tuple[str, str]], facets: dict) -> ObservationPayload:
    """places: place -> (facet_id, date)."""
    return ObservationPayload(
        data={
            "undata/sdg/EG_ACS_ELEC": {
                p: {"facet": f, "date": d, "value": 1.0} for p, (f, d) in places.items()
            }
        },
        facets=facets,
        requested_variables=("undata/sdg/EG_ACS_ELEC",),
    )


ONE_FACET = {
    "f1": {
        "unit": "Percent",
        "provenanceId": "undata/p/SDG",
        "provenanceUrl": "https://x",
        "observationPeriod": "P1Y",
    }
}


def test_geometry_check_counts_unmatched_observations() -> None:
    audit = JoinAudit(
        n_observations=100,
        n_geometries=238,
        n_matched=95,
        unmatched_observation_places=("country/GLP", "country/REU"),
        unmatched_geometry_places=(),
    )
    check = _geometry_check(audit)
    assert (check.agree, check.total) == (95, 100)
    assert not check.passed
    assert "country/GLP" in check.offenders


def test_geometry_check_passes_when_every_observation_has_a_shape() -> None:
    audit = JoinAudit(217, 238, 217, (), ("country/ATA",))
    assert _geometry_check(audit).passed


def test_coverage_check_flags_drift_from_the_enriched_catalog() -> None:
    check = _coverage_check(_indicator(place_coverage=217), n_live=210)
    assert not check.passed
    assert (check.agree, check.total) == (210, 217)
    assert check.note == "217 → 210"


def test_coverage_check_passes_when_catalog_matches_live() -> None:
    check = _coverage_check(_indicator(place_coverage=217), n_live=217)
    assert check.passed and check.note is None


def test_coverage_check_absent_when_catalog_was_never_enriched() -> None:
    assert _coverage_check(_indicator(place_coverage=None), n_live=5) is None


def test_unit_check_detects_a_served_unit_the_catalog_does_not_know() -> None:
    payload = _payload(
        {"country/KEN": ("f1", "2024"), "country/BRA": ("f2", "2024")},
        {**ONE_FACET, "f2": {"unit": "undata/UNIT_MEASURE-PT_POP"}},
    )
    check = _unit_check(_indicator(unit="Percent"), payload)
    assert not check.passed
    assert check.offenders == ("undata/UNIT_MEASURE-PT_POP",)


def test_unit_check_passes_on_a_single_matching_unit() -> None:
    payload = _payload({"country/KEN": ("f1", "2024")}, ONE_FACET)
    assert _unit_check(_indicator(unit="Percent"), payload).passed


def test_facet_check_flags_a_map_blending_two_publishers() -> None:
    payload = _payload(
        {"a": ("f1", "2024"), "b": ("f1", "2024"), "c": ("f2", "2024")},
        {**ONE_FACET, "f2": {"unit": "Percent"}},
    )
    check = _facet_check(_indicator(), payload)
    assert not check.passed
    assert (check.agree, check.total) == (2, 3)


def test_facet_check_passes_on_a_single_publisher() -> None:
    payload = _payload({"a": ("f1", "2024"), "b": ("f1", "2024")}, ONE_FACET)
    assert _facet_check(_indicator(), payload).passed


def test_cross_source_check_counts_countries_within_the_threshold() -> None:
    left = {"country/KEN": 80.0, "country/BRA": 99.0, "country/IND": 50.0}
    right = {"country/KEN": 82.0, "country/BRA": 99.5, "country/IND": 75.0}
    check = cross_source_check(left, right, threshold=10.0)
    assert (check.agree, check.total) == (2, 3)
    assert not check.passed
    assert check.offenders and "country/IND" in check.offenders[0]


def test_cross_source_check_only_compares_shared_countries() -> None:
    check = cross_source_check({"a": 1.0, "b": 2.0}, {"b": 2.0, "c": 3.0})
    assert check.total == 1 and check.passed


def test_cross_source_check_handles_no_overlap() -> None:
    check = cross_source_check({"a": 1.0}, {"b": 2.0})
    assert (check.agree, check.total) == (0, 0)
    assert check.share == 0.0


def test_selection_exposes_the_dimension_slice() -> None:
    sliced = _indicator(dcid="undata/who/COOKFUEL_PROP.COOK_FUEL--CLEAN")
    rows = dict(_selection(sliced))
    assert rows["code"] == "COOKFUEL_PROP"
    assert rows["agency"] == "who"
    assert rows["dimension: COOK_FUEL"] == "CLEAN"


def test_transformations_reflect_this_indicators_catalog_entry() -> None:
    plain = _transformations(_indicator(saturation_ceiling=None), None)
    assert "transform.saturation" not in plain
    assert "transform.merge" not in plain

    rich = _transformations(
        _indicator(saturation_ceiling=100, denominator="unicef_population"),
        _indicator(key="other"),
    )
    assert "transform.saturation" in rich
    assert "transform.denominator" in rich
    assert "transform.merge" in rich


def test_every_check_and_transform_key_has_english_copy() -> None:
    """A check that renders as a bare locale key is a bug, not a translation."""
    ui = LOCALES["en"].ui
    payload = _payload({"country/KEN": ("f1", "2024")}, ONE_FACET)
    lineage = build_lineage(
        catalog=None,
        indicator=_indicator(
            place_coverage=1, saturation_ceiling=100, denominator="unicef_population"
        ),
        payload=payload,
        audit=JoinAudit(1, 238, 1, (), ()),
        n_rows=1,
        cross_source=cross_source_check({"a": 1.0}, {"a": 1.0}),
    )
    for check in lineage.checks:
        assert f"lineage.check.{check.key}" in ui, check.key
        assert f"lineage.detail.{check.key}" in ui, check.key
    for step in lineage.transformations:
        assert step in ui, step


def test_build_lineage_reports_the_sources_that_actually_served_data() -> None:
    payload = _payload({"country/KEN": ("f1", "2024")}, ONE_FACET)
    lineage = build_lineage(
        catalog=None,
        indicator=_indicator(),
        payload=payload,
        audit=JoinAudit(1, 238, 1, (), ()),
        n_rows=1,
    )
    assert [s.id for s in lineage.sources] == ["undata/p/SDG"]
    assert lineage.sources[0].agency == "SDG"
    assert lineage.sources[0].period == "P1Y"
    assert lineage.counts["places"] == 1
