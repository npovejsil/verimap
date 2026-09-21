"""Standing validation of every API pull the catalog declares.

This is a driver, not new validation logic: it fetches each indicator from the
source it claims and runs the checks that already exist in recipe/validation.py
over the result. The point is to have a live answer to "is this pull still
returning what the catalog says it returns?" rather than discovering drift in
a chart.

scripts/verify_sources.py runs it at the command line; the app's Sources tab
renders the same results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from recipe.catalog import Catalog, Indicator, load_catalog
from recipe.datacommons_client import ObservationPayload
from recipe.sources import client_for_indicator, load_sources
from recipe.validation import (
    Finding,
    check_empty_variable,
    check_mixed_dates,
    check_multi_facet,
    check_place_coverage,
    check_place_id_format,
    check_range_violation,
    check_unit_drift,
)


@dataclass(frozen=True)
class PullCheck:
    """The verdict on one indicator's pull from one source."""

    indicator_key: str
    indicator_label: str
    source_id: str
    upstream_source: str | None
    endpoint: str
    findings: tuple[Finding, ...] = ()
    n_places: int = 0
    latest_date: str | None = None
    elapsed_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status != "fail"

    @property
    def status(self) -> str:
        if self.error is not None:
            return "fail"
        if any(f.level == "error" for f in self.findings):
            return "fail"
        if any(f.level == "warn" for f in self.findings):
            return "warn"
        return "pass"


def run_checks(payload: ObservationPayload, indicator: Indicator) -> list[Finding]:
    """Run every fetch-time check that applies to a payload. Pure."""
    candidates = [
        check_empty_variable(payload, indicator.dcid),
        check_place_id_format(payload, indicator.dcid),
        check_unit_drift(payload, indicator),
        check_range_violation(payload, indicator),
        check_place_coverage(payload, indicator),
        check_multi_facet(payload, indicator.dcid),
        check_mixed_dates(payload, indicator.dcid),
    ]
    return [f for f in candidates if f is not None]


def _latest_date(payload: ObservationPayload, dcid: str) -> str | None:
    dates = [o["date"] for o in payload.variable(dcid).values() if o.get("date")]
    return max(dates) if dates else None


def check_pull(indicator: Indicator, client=None) -> PullCheck:  # noqa: ANN001
    """Fetch one indicator and validate what came back."""
    client = client or client_for_indicator(indicator)
    endpoint = f"point/within Earth/Country [{indicator.dcid}]"
    started = time.perf_counter()

    try:
        payload = client.point_within("Earth", "Country", [indicator.dcid])
    except Exception as exc:  # noqa: BLE001 - a dead endpoint is a result, not a crash
        return PullCheck(
            indicator_key=indicator.key,
            indicator_label=indicator.label,
            source_id=indicator.source,
            upstream_source=indicator.upstream_source,
            endpoint=endpoint,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return PullCheck(
        indicator_key=indicator.key,
        indicator_label=indicator.label,
        source_id=indicator.source,
        upstream_source=indicator.upstream_source,
        endpoint=endpoint,
        findings=tuple(run_checks(payload, indicator)),
        n_places=len(payload.variable(indicator.dcid)),
        latest_date=_latest_date(payload, indicator.dcid),
        elapsed_ms=elapsed_ms,
    )


def check_all_pulls(catalog: Catalog | None = None) -> list[PullCheck]:
    """Check every catalog indicator, grouped by source for readable output."""
    catalog = catalog or load_catalog()
    sources = list(load_sources())
    indicators = sorted(
        catalog.indicators.values(),
        key=lambda i: (sources.index(i.source) if i.source in sources else 99, i.key),
    )
    return [check_pull(i) for i in indicators]


def summarize(checks: list[PullCheck]) -> dict[str, int]:
    out = {"pass": 0, "warn": 0, "fail": 0}
    for c in checks:
        out[c.status] += 1
    return out
