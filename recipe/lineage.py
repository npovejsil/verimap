"""Where every figure on screen came from, and where the sources disagree.

The app attributes each panel with a one-line citation, which says *who*
published a number but not how it reached the screen. This assembles the rest
of the trail: which sources are in play, which records were selected, which
raw field backs each readout, what was done to the values, and the
cross-checks.

The cross-checks are the point. Several figures here have two independent
derivations, so they can be compared rather than trusted:

    observation places      vs  the country geometry the map can draw
    coverage recorded by    vs  the rows the API returns right now
      `make enrich`
    the unit in the catalog vs  the unit on the facet that was served
    one source's country    vs  another source's, for the same concept

Everything is computed from the catalog, the live response facets and the
artifacts on disk -- nothing is typed by hand, so this panel cannot claim
something the shipped data does not support. Where the API publishes no
field at all (licensing, most obviously), that absence is reported rather
than filled in.

Check *labels* are locale keys, not sentences: this module stays language-free
so it can be unit-tested on the numbers alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from recipe.catalog import Catalog, Indicator
from recipe.dcid_grammar import parse_dcid
from recipe.datacommons_client import BASE_URL, ObservationPayload
from recipe.geography import JoinAudit

DISCOVERED_PATH = Path(__file__).resolve().parent.parent / "catalog" / "discovered.yml"

# A country-level percentage-point gap wider than this counts as the two
# sources disagreeing. Same threshold the disagreement callout uses.
DISAGREEMENT_THRESHOLD_PP = 10.0


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def built_at(path: Path = DISCOVERED_PATH) -> str | None:
    """When an artifact was written -- evidence, rather than a guess."""
    return _utc(path.stat().st_mtime) if path.exists() else None


@dataclass(frozen=True)
class SourceRow:
    """One publisher behind the figures currently on screen."""

    id: str
    agency: str
    provides: str
    access: str
    period: str
    retrieved: str
    url: str | None


@dataclass(frozen=True)
class FieldTrace:
    """A readout label and the variable it is actually read from."""

    shown: str
    field: str


@dataclass(frozen=True)
class CrossCheck:
    """One figure with two independent derivations, compared.

    `key` is a locale key, not a sentence -- the numbers are computed here,
    the wording lives in catalog/locales/.
    """

    key: str
    agree: int
    total: int
    passed: bool
    offenders: tuple[str, ...] = field(default_factory=tuple)
    note: str | None = None

    @property
    def share(self) -> float:
        return (self.agree / self.total) if self.total else 0.0


@dataclass(frozen=True)
class Lineage:
    generated: str
    catalog_built: str | None
    sources: tuple[SourceRow, ...]
    selection: tuple[tuple[str, str], ...]
    fields: tuple[FieldTrace, ...]
    transformations: tuple[str, ...]
    counts: dict[str, Any]
    checks: tuple[CrossCheck, ...]


def _source_rows(
    indicators: Sequence[Indicator], payloads: Sequence[ObservationPayload]
) -> tuple[SourceRow, ...]:
    """One row per provenance actually serving the indicators on screen.

    Built from the facets that came back with the data, so a source cannot
    appear here unless it served a value that is being displayed.
    """
    rows: dict[str, SourceRow] = {}
    for ind, payload in zip(indicators, payloads):
        obs = payload.variable(ind.dcid)
        facet_ids = {o["facet"] for o in obs.values() if "facet" in o}
        for fid in facet_ids:
            meta = payload.facet(fid)
            prov = meta.get("provenanceId") or ind.provenance_id or "unknown"
            existing = rows.get(prov)
            provides = (
                ind.label if existing is None else f"{existing.provides}, {ind.label}"
            )
            rows[prov] = SourceRow(
                id=prov,
                agency=(ind.source_agency or "—").upper(),
                provides=provides,
                access=f"{BASE_URL}/api/observations/point/within",
                period=meta.get("observationPeriod") or "—",
                retrieved=_utc(datetime.now(timezone.utc).timestamp()),
                url=meta.get("provenanceUrl") or ind.provenance_url,
            )
    return tuple(rows.values())


def _selection(indicator: Indicator) -> tuple[tuple[str, str], ...]:
    """Decompose the DCID into the query that selected these records.

    `recipe.dcid_grammar` already parses agency / code / dimensions; this
    just presents what it found, which is why a dimension-sliced indicator
    like `COOKFUEL_PROP.COOK_FUEL--CLEAN` explains itself here for free.
    """
    parsed = parse_dcid(indicator.dcid)
    rows: list[tuple[str, str]] = [
        ("variable", indicator.dcid),
        ("agency", parsed.agency or "—"),
        ("code", parsed.code),
        ("parentEntity", "Earth"),
        ("childType", "Country"),
    ]
    for dim, value in sorted(parsed.dimensions.items()):
        rows.append((f"dimension: {dim}", value))
    return tuple(rows)


def _fields(indicators: Sequence[Indicator]) -> tuple[FieldTrace, ...]:
    return tuple(FieldTrace(shown=i.label, field=i.dcid) for i in indicators)


def _transformations(
    indicator: Indicator, compare: Indicator | None
) -> tuple[str, ...]:
    """The operations between the API response and the pixels.

    Derived from the indicator's own catalog entry, so it states what was
    actually applied to *this* indicator rather than a generic list.
    """
    steps = [
        "transform.fetch",
        "transform.latest",
        "transform.long",
        "transform.names",
        "transform.join",
    ]
    if indicator.saturation_ceiling is not None:
        steps.append("transform.saturation")
    if indicator.denominator:
        steps.append("transform.denominator")
    if compare is not None:
        steps.append("transform.merge")
    return tuple(steps)


def _coverage_check(indicator: Indicator, n_live: int) -> CrossCheck | None:
    """Coverage recorded by `make enrich` vs the rows the API returns now.

    Two independent derivations of "how many countries report this": one
    frozen into catalog/discovered.yml at enrich time, one from the response
    in hand. Drift means the catalog is stale, which is worth seeing before
    trusting a figure derived from it.
    """
    recorded = indicator.place_coverage
    if not recorded:
        return None
    return CrossCheck(
        key="catalog_coverage",
        agree=min(recorded, n_live),
        total=max(recorded, n_live),
        passed=recorded == n_live,
        note=None if recorded == n_live else f"{recorded} → {n_live}",
    )


def _unit_check(indicator: Indicator, payload: ObservationPayload) -> CrossCheck | None:
    """The unit in the catalog vs the unit on every facet actually served."""
    if not indicator.unit:
        return None
    obs = payload.variable(indicator.dcid)
    facet_ids = {o["facet"] for o in obs.values() if "facet" in o}
    served = {payload.facet(f).get("unit") for f in facet_ids}
    served.discard(None)
    agree = sum(1 for u in served if u == indicator.unit)
    offenders = tuple(sorted(str(u) for u in served if u != indicator.unit))
    return CrossCheck(
        key="unit_drift",
        agree=agree,
        total=len(served) or 1,
        passed=not offenders,
        offenders=offenders,
    )


def _facet_check(indicator: Indicator, payload: ObservationPayload) -> CrossCheck:
    """How many of the displayed values come from a single provenance.

    More than one facet means the map is blending publishers within one
    choropleth, which is legitimate but must not be invisible.
    """
    obs = payload.variable(indicator.dcid)
    counts: dict[str, int] = {}
    for o in obs.values():
        counts[o.get("facet", "?")] = counts.get(o.get("facet", "?"), 0) + 1
    dominant = max(counts.values()) if counts else 0
    total = sum(counts.values())
    return CrossCheck(
        key="single_facet",
        agree=dominant,
        total=total,
        passed=len(counts) <= 1,
        offenders=tuple(sorted(counts)[1:]) if len(counts) > 1 else (),
    )


def _year_check(payload: ObservationPayload, dcid: str) -> CrossCheck:
    """How many places report the modal year, vs all reporting places."""
    obs = payload.variable(dcid)
    years: dict[str, int] = {}
    for o in obs.values():
        years[o.get("date", "?")] = years.get(o.get("date", "?"), 0) + 1
    modal = max(years.values()) if years else 0
    total = sum(years.values())
    others = tuple(sorted(y for y in years if years[y] != modal))
    return CrossCheck(
        key="same_year",
        agree=modal,
        total=total,
        passed=len(years) <= 1,
        offenders=others[:8],
    )


def _geometry_check(audit: JoinAudit) -> CrossCheck:
    """Observations vs the geometry the map can actually draw them on."""
    return CrossCheck(
        key="map_join",
        agree=audit.n_matched,
        total=audit.n_observations,
        passed=audit.is_clean,
        offenders=audit.unmatched_observation_places[:8],
    )


def cross_source_check(
    left_values: dict[str, float],
    right_values: dict[str, float],
    threshold: float = DISAGREEMENT_THRESHOLD_PP,
) -> CrossCheck:
    """Two publishers' figures for the same concept, country by country.

    The strongest check available: neither source is a transformation of the
    other, so a disagreement is a real discrepancy between publishers rather
    than an arithmetic slip.
    """
    shared = sorted(set(left_values) & set(right_values))
    gaps = {p: abs(left_values[p] - right_values[p]) for p in shared}
    agree = sum(1 for g in gaps.values() if g <= threshold)
    worst = sorted(gaps, key=lambda p: gaps[p], reverse=True)
    offenders = tuple(f"{p} ({gaps[p]:.1f} pp)" for p in worst if gaps[p] > threshold)
    return CrossCheck(
        key="cross_source",
        agree=agree,
        total=len(shared),
        passed=agree == len(shared),
        offenders=offenders[:8],
    )


def build_lineage(
    catalog: Catalog,
    indicator: Indicator,
    payload: ObservationPayload,
    audit: JoinAudit,
    n_rows: int,
    compare: Indicator | None = None,
    compare_payload: ObservationPayload | None = None,
    cross_source: CrossCheck | None = None,
) -> Lineage:
    """Assemble the full trail for what is currently on screen."""
    indicators = [indicator] + ([compare] if compare is not None else [])
    payloads = [payload] + ([compare_payload] if compare_payload is not None else [])
    payloads = [p for p in payloads if p is not None]

    checks: list[CrossCheck] = [_geometry_check(audit)]
    for c in (
        _coverage_check(indicator, n_rows),
        _unit_check(indicator, payload),
    ):
        if c is not None:
            checks.append(c)
    checks.append(_facet_check(indicator, payload))
    checks.append(_year_check(payload, indicator.dcid))
    if cross_source is not None:
        checks.append(cross_source)

    return Lineage(
        generated=_utc(datetime.now(timezone.utc).timestamp()),
        catalog_built=built_at(),
        sources=_source_rows(indicators[: len(payloads)], payloads),
        selection=_selection(indicator),
        fields=_fields(indicators),
        transformations=_transformations(indicator, compare),
        counts={
            "places": n_rows,
            "geometries": audit.n_geometries,
            "indicators": len(indicators),
            "sources": len({i.provenance_id for i in indicators if i.provenance_id}),
        },
        checks=tuple(checks),
    )
