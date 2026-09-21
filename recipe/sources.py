"""Which API each indicator comes from, and how to get a client for it.

Indicators declare a `source` in catalog/indicators.yml (defaulting to Data
Commons). This module is the single place that turns that string into a live
client, so app.py never hardcodes one.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from recipe.catalog import CATALOG_DIR, CatalogError, load_yaml

DEFAULT_SOURCE = "un_datacommons"
SOURCES_PATH = CATALOG_DIR / "sources.yml"


@dataclass(frozen=True)
class Source:
    id: str
    label: str
    base_url: str
    status: str
    verified_on: str | None = None
    notes: str | None = None


@lru_cache(maxsize=None)
def load_sources(path: Path = SOURCES_PATH) -> dict[str, Source]:
    raw: dict[str, Any] = load_yaml(path).get("sources", {})
    if DEFAULT_SOURCE not in raw:
        raise CatalogError(
            f"sources.yml must declare the default source {DEFAULT_SOURCE!r}"
        )
    return {
        key: Source(
            id=key,
            label=spec["label"],
            base_url=spec["base_url"],
            status=spec.get("status", "unverified"),
            verified_on=str(spec["verified_on"]) if spec.get("verified_on") else None,
            notes=(spec.get("notes") or "").strip() or None,
        )
        for key, spec in raw.items()
    }


@lru_cache(maxsize=None)
def client_for(source_id: str):
    """Return a cached client for a source id, honouring DATA_BEARS_OFFLINE.

    Offline mode serves every source from cache/snapshot/, because the snapshot
    format records observations by dcid and is already source-neutral.
    """
    if source_id not in load_sources():
        raise CatalogError(f"Unknown source {source_id!r}")

    import os

    if os.getenv("DATA_BEARS_OFFLINE"):
        from recipe.datacommons_client import OfflineDataCommonsClient

        return OfflineDataCommonsClient()

    if source_id == "world_bank":
        from recipe.worldbank_client import WorldBankClient

        return WorldBankClient()

    from recipe.datacommons_client import DataCommonsClient

    return DataCommonsClient()


def client_for_indicator(indicator):  # noqa: ANN001 - Indicator, avoids import cycle
    return client_for(indicator.source)
