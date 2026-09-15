"""Build citation strings from facet/provenance metadata.

Attribution is structural, not a footer: every panel must be able to show
where its numbers came from. `render()` raises on an empty citation list so
a panel physically cannot ship without its sources.
"""

from __future__ import annotations

from dataclasses import dataclass

from recipe.catalog import Indicator


class MissingAttributionError(Exception):
    """Raised when a view attempts to render with no citations attached."""


@dataclass(frozen=True)
class Citation:
    label: str
    provenance_id: str | None
    provenance_url: str | None
    unit_display: str | None
    as_of: str | None = None

    def render(self) -> str:
        parts = [self.label]
        if self.provenance_id:
            parts.append(f"({self.provenance_id})")
        if self.provenance_url:
            parts.append(f"· {self.provenance_url}")
        if self.unit_display:
            parts.append(f"· unit: {self.unit_display}")
        if self.as_of:
            parts.append(f"· {self.as_of}")
        return " ".join(parts)


def citation_for_indicator(indicator: Indicator, as_of: str | None = None) -> Citation:
    return Citation(
        label=indicator.label,
        provenance_id=indicator.provenance_id,
        provenance_url=indicator.provenance_url,
        unit_display=indicator.unit_display or indicator.unit,
        as_of=as_of,
    )


def require_citations(citations: list[Citation]) -> None:
    """Raise if a panel has no citations. Call this before rendering any panel."""
    if not citations:
        raise MissingAttributionError(
            "Panel attempted to render with no citations attached."
        )
