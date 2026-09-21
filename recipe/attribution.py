"""Build citation strings from facet/provenance metadata.

Attribution is structural, not a footer: every panel must be able to show
where its numbers came from. `render()` raises on an empty citation list so
a panel physically cannot ship without its sources.
"""

from __future__ import annotations

from dataclasses import dataclass

from recipe.catalog import Indicator
from recipe.i18n import Translator


class MissingAttributionError(Exception):
    """Raised when a view attempts to render with no citations attached."""


@dataclass(frozen=True)
class Citation:
    label: str
    provenance_id: str | None
    provenance_url: str | None
    unit_display: str | None
    as_of: str | None = None

    def render(self, t: Translator | None = None) -> str:
        """Render the citation line, localizing the "unit:" label if given."""
        parts = [self.label]
        if self.provenance_url:
            parts.append(f"· {self.provenance_url}")
        if self.unit_display:
            unit = (
                t.t("source.unit", unit=self.unit_display)
                if t is not None
                else f"unit: {self.unit_display}"
            )
            parts.append(f"· {unit}")
        if self.as_of:
            parts.append(f"· {self.as_of}")
        return " ".join(parts)


def citation_for_indicator(
    indicator: Indicator, as_of: str | None = None, label: str | None = None
) -> Citation:
    """Build a Citation. `label` overrides the catalog's English name.

    The override is how a translated indicator name reaches the citation
    line without the catalog itself ever holding a non-English label.
    """
    return Citation(
        label=label or indicator.label,
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
