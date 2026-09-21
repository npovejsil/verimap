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


def indicator_option_label(
    indicator: Indicator, catalog: Catalog, t=None
) -> str:  # noqa: ANN001 - Translator, avoids an import cycle through recipe.i18n
    """e.g. 'Energy delivery, losses & reliability · Transmission & distribution losses'.

    `t`, when given, translates both halves. It stays optional so this module
    keeps working from tests and scripts that have no translator in hand --
    the same fallback-to-English rule `recipe.i18n` applies everywhere else.
    """
    topics = catalog.topics_for_indicator(indicator.key)
    if topics:
        prefix = t.topic(topics[0]) if t is not None else topics[0].label
    else:
        prefix = t.t("picker.other_topic") if t is not None else "Other"
    label = t.indicator(indicator) if t is not None else indicator.label
    return f"{prefix} · {label}"
