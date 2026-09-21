"""Load and merge the YAML catalog into typed indicator/dimension/unit records.

Three-tier catalog: curated `indicators.yml` entries (hand-authored) are
merged with `discovered.yml` enrichment (machine-populated by
scripts/discover_indicators.py --enrich). Curated fields always win over
discovered ones. An indicator with no enrichment yet is loaded but flagged
`enriched=False` so the UI can hide it with a visible reason instead of
crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


class CatalogError(Exception):
    """Raised on unrecoverable catalog problems (unknown topic, missing dcid)."""


_VALID_POLARITIES = {"higher_is_better", "lower_is_better", "neutral"}


@dataclass(frozen=True)
class Indicator:
    key: str
    dcid: str
    label: str
    topics: tuple[str, ...]
    polarity: str
    sdg_target: str | None = None
    saturation_ceiling: float | None = None
    denominator: str | None = None
    role: str | None = None
    # Which API this indicator is pulled from; see catalog/sources.yml.
    source: str = "un_datacommons"

    # Enriched fields (blank until `make enrich` has run)
    source_agency: str | None = None
    code: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    provenance_id: str | None = None
    provenance_url: str | None = None
    unit: str | None = None
    unit_display: str | None = None
    temporal_start: str | None = None
    temporal_end: str | None = None
    value_min: float | None = None
    value_max: float | None = None
    place_coverage: int | None = None
    facet_count: int | None = None
    # Who actually produced the numbers, which is often not the publisher:
    # three of the four direct World Bank energy pulls are republished IEA data.
    upstream_source: str | None = None
    enriched: bool = False


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    default_indicators: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    indicators: dict[str, Indicator]
    topics: dict[str, Topic]
    dimensions: dict[str, Any]
    units: dict[str, Any]

    def indicators_for_topic(self, topic_key: str) -> list[Indicator]:
        return [ind for ind in self.indicators.values() if topic_key in ind.topics]


def _valid_sources() -> set[str]:
    """Source ids declared in catalog/sources.yml.

    Read directly rather than via recipe.sources, which imports this module.
    """
    return set(load_yaml(CATALOG_DIR / "sources.yml").get("sources", {}))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_catalog(catalog_dir: Path = CATALOG_DIR) -> Catalog:
    """Load, merge, and validate the full catalog.

    Raises CatalogError on hard failures (missing dcid, unknown topic
    reference, invalid polarity). Missing enrichment is a soft failure: the
    indicator loads with `enriched=False` rather than raising.
    """
    curated_raw = load_yaml(catalog_dir / "indicators.yml").get("indicators", {})
    discovered_raw = load_yaml(catalog_dir / "discovered.yml").get("indicators", {})
    topics_raw = load_yaml(catalog_dir / "topics.yml").get("topics", {})
    dimensions = load_yaml(catalog_dir / "dimensions.yml").get("dimensions", {})
    units = load_yaml(catalog_dir / "units.yml").get("families", {})

    topics: dict[str, Topic] = {}
    for key, raw in topics_raw.items():
        topics[key] = Topic(
            key=key,
            label=raw.get("label", key),
            default_indicators=tuple(raw.get("default_indicators", [])),
        )

    indicators: dict[str, Indicator] = {}
    for key, curated in curated_raw.items():
        if "dcid" not in curated:
            raise CatalogError(f"indicator '{key}' is missing required field 'dcid'")
        if "label" not in curated:
            raise CatalogError(f"indicator '{key}' is missing required field 'label'")

        polarity = curated.get("polarity", "neutral")
        if polarity not in _VALID_POLARITIES:
            raise CatalogError(
                f"indicator '{key}' has invalid polarity '{polarity}', "
                f"must be one of {_VALID_POLARITIES}"
            )

        source = curated.get("source", "un_datacommons")
        if source not in _valid_sources():
            raise CatalogError(
                f"indicator '{key}' declares unknown source '{source}', "
                f"must be one of {sorted(_valid_sources())} (see catalog/sources.yml)"
            )

        topic_keys = tuple(curated.get("topics", []))
        for t in topic_keys:
            if t != "_denominators" and t not in topics:
                raise CatalogError(f"indicator '{key}' references unknown topic '{t}'")

        enrichment = discovered_raw.get(key, {})
        merged = {**enrichment, **curated}

        indicators[key] = Indicator(
            key=key,
            dcid=merged["dcid"],
            label=merged["label"],
            topics=topic_keys,
            polarity=polarity,
            sdg_target=merged.get("sdg_target"),
            saturation_ceiling=merged.get("saturation_ceiling"),
            denominator=merged.get("denominator"),
            role=merged.get("role"),
            source=source,
            source_agency=enrichment.get("source_agency"),
            code=enrichment.get("code"),
            dimensions=enrichment.get("dimensions", {}),
            provenance_id=enrichment.get("provenance_id"),
            provenance_url=enrichment.get("provenance_url"),
            unit=enrichment.get("unit"),
            unit_display=enrichment.get("unit_display"),
            temporal_start=enrichment.get("temporal_start"),
            temporal_end=enrichment.get("temporal_end"),
            value_min=enrichment.get("value_min"),
            value_max=enrichment.get("value_max"),
            place_coverage=enrichment.get("place_coverage"),
            facet_count=enrichment.get("facet_count"),
            upstream_source=enrichment.get("upstream_source"),
            enriched=bool(enrichment),
        )

    return Catalog(
        indicators=indicators, topics=topics, dimensions=dimensions, units=units
    )
