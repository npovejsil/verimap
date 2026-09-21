"""Pure tests for the per-pull verification harness -- no network.

The harness is a driver over recipe/validation.py, so these tests assert the
status roll-up and the exception path rather than re-testing each validator.
"""

from __future__ import annotations

from recipe.catalog import Indicator
from recipe.datacommons_client import EmptyResponseError, ObservationPayload
from recipe.source_checks import PullCheck, check_pull, run_checks, summarize

FACET = "f1"
IND = Indicator(
    key="wb_transmission_losses",
    dcid="worldbank/EG.ELC.LOSS.ZS",
    label="Transmission & distribution losses",
    topics=("energy_delivery",),
    polarity="lower_is_better",
    source="world_bank",
    unit="worldbank/PCT_OUTPUT",
    unit_display="% of output",
    value_min=0.0,
    value_max=100.0,
    place_coverage=150,
    upstream_source="IEA Energy Statistics Data Browser",
)


def _payload(places: dict[str, float], unit: str = "worldbank/PCT_OUTPUT", date="2023"):
    return ObservationPayload(
        data={
            IND.dcid: {
                p: {"date": date, "facet": FACET, "value": v} for p, v in places.items()
            }
        },
        facets={FACET: {"unit": unit, "unitDisplayName": "% of output"}},
        requested_variables=(IND.dcid,),
    )


def _clean_places(n: int = 150) -> dict[str, float]:
    # country/AAA .. spread across a valid range.
    return {
        f"country/{chr(65 + i // 26)}{chr(65 + i % 26)}Z": 10.0 + (i % 40)
        for i in range(n)
    }


class _Client:
    def __init__(self, payload=None, exc=None):
        self._payload, self._exc = payload, exc

    def point_within(self, parent, child_type, variables):
        if self._exc:
            raise self._exc
        return self._payload


def test_a_clean_pull_passes() -> None:
    check = check_pull(IND, _Client(_payload(_clean_places())))
    assert check.status == "pass"
    assert check.ok
    assert check.findings == ()
    assert check.n_places == 150
    assert check.latest_date == "2023"


def test_lineage_is_carried_onto_the_result() -> None:
    # The whole reason the field exists: a "World Bank" pull that is IEA data.
    check = check_pull(IND, _Client(_payload(_clean_places())))
    assert check.upstream_source == "IEA Energy Statistics Data Browser"


def test_unit_drift_fails_the_pull() -> None:
    check = check_pull(IND, _Client(_payload(_clean_places(), unit="Percent")))
    assert check.status == "fail"
    assert not check.ok
    assert any(f.code == "UNIT_DRIFT" for f in check.findings)


def test_coverage_drop_warns_but_does_not_fail() -> None:
    check = check_pull(IND, _Client(_payload(_clean_places(100))))
    assert check.status == "warn"
    assert check.ok  # a warning is still usable data
    assert any(f.code == "PLACE_COVERAGE_DROP" for f in check.findings)


def test_malformed_place_ids_fail_the_pull() -> None:
    # These would vanish off the choropleth rather than raise, so the check
    # has to be an error and not a warning.
    check = check_pull(IND, _Client(_payload({"RWA": 18.3, "country/KEN": 20.0})))
    assert check.status == "fail"
    assert any(f.code == "MALFORMED_PLACE_ID" for f in check.findings)


def test_a_dead_endpoint_is_reported_not_raised() -> None:
    check = check_pull(IND, _Client(exc=EmptyResponseError(IND.dcid, "/point/within")))
    assert check.status == "fail"
    assert check.error is not None
    assert "EmptyResponseError" in check.error
    assert check.n_places == 0


def test_out_of_range_values_fail_the_pull() -> None:
    places = _clean_places(150)
    places["country/ZZZ"] = 4200.0
    check = check_pull(IND, _Client(_payload(places)))
    assert check.status == "fail"
    assert any(f.code == "RANGE_VIOLATION" for f in check.findings)


def test_run_checks_is_pure_and_returns_only_real_findings() -> None:
    assert run_checks(_payload(_clean_places()), IND) == []


def test_summarize_counts_each_status() -> None:
    def c(status_findings, error=None):
        return PullCheck(
            indicator_key="k",
            indicator_label="l",
            source_id="world_bank",
            upstream_source=None,
            endpoint="e",
            findings=tuple(status_findings),
            error=error,
        )

    from recipe.validation import Finding

    warn = Finding(level="warn", code="W", message="m")
    err = Finding(level="error", code="E", message="m")
    assert summarize([c([]), c([warn]), c([err]), c([], error="boom")]) == {
        "pass": 1,
        "warn": 1,
        "fail": 2,
    }
