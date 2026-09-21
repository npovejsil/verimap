"""Labels for the indicator picker.

The picker is a flat list spanning every topic, so each option has to carry
enough context to be recognised on its own: what it measures, which subject
area it belongs to, and who publishes it. Two indicators can otherwise look
identical in a dropdown -- "Electricity access" appears three times in this
catalog, from different sources and at different geographic breakdowns.
"""

from __future__ import annotations

from recipe.catalog import Catalog, Indicator
from recipe.sources import load_sources


def source_label(indicator: Indicator) -> str:
    """Readable publisher name for an indicator's source."""
    sources = load_sources()
    source = sources.get(indicator.source)
    return source.label if source else indicator.source


def indicator_option_label(indicator: Indicator, catalog: Catalog) -> str:
    """e.g. 'Energy delivery, losses & reliability · Transmission & distribution losses'."""
    topics = catalog.topics_for_indicator(indicator.key)
    prefix = topics[0].label if topics else "Other"
    return f"{prefix} · {indicator.label}"
