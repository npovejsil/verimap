"""Measure how much two indicators agree in coverage, and what that allows.

Five independent checks (place overlap, date overlap, dimension alignment,
unit family) combine into a single JoinSpec. That spec doubles as both a
disagreement measurement -- how much place/date/unit coverage two sources
actually share -- and a gate on what the UI can safely do with the pair:
plot both, join them, or take their difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from recipe.catalog import Catalog, Indicator

_MIN_PLACE_JACCARD = 0.5
_MIN_SHARED_YEARS = 5


def _shared_years(left: Indicator, right: Indicator) -> int | None:
    """Count of years both indicators' catalog temporal ranges overlap.

    Returns None if either indicator has no enriched temporal range yet.
    """
    if not all(
        [
            left.temporal_start,
            left.temporal_end,
            right.temporal_start,
            right.temporal_end,
        ]
    ):
        return None
    start = max(int(left.temporal_start), int(right.temporal_start))
    end = min(int(left.temporal_end), int(right.temporal_end))
    return max(0, end - start + 1)


@dataclass(frozen=True)
class DimMatch:
    left_value: str
    right_value: str
    canonical: str | None  # None if the values didn't resolve to a shared alias


@dataclass(frozen=True)
class Overlap:
    n_left: int
    n_right: int
    n_shared: int

    @property
    def jaccard(self) -> float:
        union = self.n_left + self.n_right - self.n_shared
        return self.n_shared / union if union else 0.0


@dataclass(frozen=True)
class JoinSpec:
    left_key: str
    right_key: str
    join_keys: tuple[str, ...]
    shared_dimensions: dict[str, DimMatch]
    left_only_dimensions: dict[str, str]
    right_only_dimensions: dict[str, str]
    place_overlap: Overlap
    shared_years: int | None
    unit_relation: str  # "same" | "same_family" | "incomparable" | "unknown"
    comparability: str  # "direct" | "axes_only" | "blocked"
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # Stable identifiers for the same blockers, parallel to `blockers`.
    # `blockers` holds English sentence fragments that get glued together at
    # the call site, which no other language can reproduce grammatically;
    # these ids let a view look up a whole translated sentence instead.
    blocker_ids: tuple[str, ...] = field(default_factory=tuple)


def _resolve_dimension_value(
    dim_name: str, value: str, dimensions_catalog: dict
) -> str | None:
    """Resolve a raw dimension value (e.g. 'DOU_R') to its canonical key (e.g. 'rural')."""
    dim_spec = dimensions_catalog.get(dim_name, {})
    for canonical, spec in dim_spec.get("canonical_values", {}).items():
        if value in spec.get("aliases", []):
            return canonical
    return None


def _unit_family(unit: str | None, units_catalog: dict) -> str | None:
    if not unit:
        return None
    for family_name, spec in units_catalog.items():
        if unit in spec.get("members", []):
            return family_name
    return None


def compute_join_spec(
    left: Indicator,
    right: Indicator,
    catalog: Catalog,
    left_places: set[str],
    right_places: set[str],
) -> JoinSpec:
    """Compute the full compatibility verdict between two indicators.

    `left_places`/`right_places` are the observed place DCID sets for each
    indicator (from a point/within or series/within call) — passed in
    rather than fetched here, so this function stays a pure computation
    over already-retrieved data.
    """
    warnings: list[str] = []
    blockers: list[str] = []
    blocker_ids: list[str] = []

    # 1. Dimension intersection, resolved through the alias map.
    shared_dim_names = set(left.dimensions) & set(right.dimensions)
    shared_dimensions: dict[str, DimMatch] = {}
    for dim_name in shared_dim_names:
        lv, rv = left.dimensions[dim_name], right.dimensions[dim_name]
        left_canon = _resolve_dimension_value(dim_name, lv, catalog.dimensions)
        right_canon = _resolve_dimension_value(dim_name, rv, catalog.dimensions)
        canonical = left_canon if left_canon == right_canon and left_canon else None
        shared_dimensions[dim_name] = DimMatch(lv, rv, canonical)
        if canonical is None and lv != rv:
            warnings.append(
                f"Both sources break this category down differently ('{dim_name}'), "
                "and we couldn't match them up — treat any comparison within "
                f"'{dim_name}' with caution."
            )

    left_only_dims = {
        k: v for k, v in left.dimensions.items() if k not in shared_dim_names
    }
    right_only_dims = {
        k: v for k, v in right.dimensions.items() if k not in shared_dim_names
    }

    # 2. Place overlap.
    n_shared_places = len(left_places & right_places)
    place_overlap = Overlap(len(left_places), len(right_places), n_shared_places)
    if place_overlap.jaccard < _MIN_PLACE_JACCARD:
        max_places = max(len(left_places), len(right_places))
        warnings.append(
            f"Only {n_shared_places} of {max_places} countries are covered by "
            "both sources — comparisons will be based on a partial set."
        )
    if n_shared_places == 0:
        blockers.append("no places in common")
        blocker_ids.append("no_places")

    # 3. Date overlap.
    shared_years = _shared_years(left, right)
    if shared_years is not None:
        if shared_years == 0:
            blockers.append("no years in common")
            blocker_ids.append("no_years")
        elif shared_years < _MIN_SHARED_YEARS:
            warnings.append(
                f"These sources only overlap in {shared_years} year(s) — most "
                "of the timeline can't be compared."
            )

    # 4. Unit relation.
    left_family = _unit_family(left.unit, catalog.units)
    right_family = _unit_family(right.unit, catalog.units)
    if left.unit and left.unit == right.unit:
        unit_relation = "same"
    elif left_family and left_family == right_family:
        unit_relation = "same_family"
    elif left_family and right_family:
        unit_relation = "incomparable"
    else:
        unit_relation = "unknown"
        # Maintainer note: unit family unknown for one or both indicators
        # ('{left.unit}', '{right.unit}') — add to catalog/units.yml.
        warnings.append(
            "We don't yet know how to compare these two measurement scales."
        )

    # 5. Comparability verdict.
    if blockers:
        comparability = "blocked"
    elif unit_relation in ("same", "same_family"):
        comparability = "direct"
    else:
        comparability = "axes_only"
        if unit_relation == "incomparable":
            left_display = left.unit_display or left.unit
            right_display = right.unit_display or right.unit
            warnings.append(
                f"These are measured in different units ({left_display} vs "
                f"{right_display}), so we can show them side by side but not "
                "calculate a difference."
            )

    return JoinSpec(
        left_key=left.key,
        right_key=right.key,
        join_keys=("place_dcid", "date") + tuple(sorted(shared_dim_names)),
        shared_dimensions=shared_dimensions,
        left_only_dimensions=left_only_dims,
        right_only_dimensions=right_only_dims,
        place_overlap=place_overlap,
        shared_years=shared_years,
        unit_relation=unit_relation,
        comparability=comparability,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        blocker_ids=tuple(blocker_ids),
    )
