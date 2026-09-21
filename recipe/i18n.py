"""Locale loading and translation lookup for the presentation layer.

Translation sits on top of the catalog, never inside it: `Indicator.label`
stays the English canonical value, so `catalog/discovered.yml`, `make enrich`
and the key-matcher keep working untouched and every existing test keeps
passing. `Translator.indicator()` is the only thing that knows a Spanish name
for `sdg_elec_access` exists.

Fallback is deliberate and total: a locale missing a key falls back to
English, and a key no locale defines falls back to the key itself. A missing
translation must degrade to readable text on screen, never to an exception in
front of a user -- the same reason `catalog.load_catalog` treats missing
enrichment as a soft failure.

Scope is UI chrome plus indicator/topic names. The long statistical caveats
(the convergence ceiling warning, the archetype disclaimer, the cross-year and
disagreement callouts) stay English on purpose: they are nuanced claims where
a bad translation misleads rather than merely reads awkwardly, so they need a
human translator, not this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

LOCALES_DIR = Path(__file__).resolve().parent.parent / "catalog" / "locales"
DEFAULT_LOCALE = "en"


class LocaleError(Exception):
    """Raised when the default locale is missing or unreadable."""


@dataclass(frozen=True)
class Locale:
    """One language's strings, loaded from `catalog/locales/<code>.yml`."""

    code: str
    name: str
    direction: str
    ui: dict[str, str]
    indicators: dict[str, str]
    topics: dict[str, str]
    numbers: dict[str, str]

    @property
    def is_rtl(self) -> bool:
        return self.direction == "rtl"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_locales(locales_dir: Path = LOCALES_DIR) -> dict[str, Locale]:
    """Load every locale file, keyed by language code.

    Raises only if the default locale is absent -- without English there is
    nothing to fall back to, so that is the one unrecoverable case.
    """
    locales: dict[str, Locale] = {}
    for path in sorted(locales_dir.glob("*.yml")):
        raw = load_yaml(path)
        code = raw.get("locale") or path.stem
        locales[code] = Locale(
            code=code,
            name=raw.get("name", code),
            direction=raw.get("direction", "ltr"),
            ui=raw.get("ui") or {},
            indicators=raw.get("indicators") or {},
            topics=raw.get("topics") or {},
            numbers=raw.get("numbers") or {},
        )

    if DEFAULT_LOCALE not in locales:
        raise LocaleError(
            f"No '{DEFAULT_LOCALE}' locale in {locales_dir}. English is the "
            "fallback for every other language and cannot be missing."
        )
    return locales


@dataclass(frozen=True)
class Translator:
    """Looks up display strings for one locale, falling back to English."""

    locale: Locale
    fallback: Locale

    @property
    def is_rtl(self) -> bool:
        return self.locale.is_rtl

    def t(self, key: str, **params: Any) -> str:
        """Return the UI string for `key`, formatted with `params`.

        Never raises: an unknown key returns the key, and a template whose
        placeholders don't match the arguments returns the unformatted
        template rather than blowing up mid-render.
        """
        template = self.locale.ui.get(key) or self.fallback.ui.get(key) or key
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return template

    def indicator(self, indicator: Any) -> str:
        """Translated indicator name, falling back to the catalog's label."""
        return (
            self.locale.indicators.get(indicator.key)
            or self.fallback.indicators.get(indicator.key)
            or indicator.label
        )

    def topic(self, topic: Any) -> str:
        """Translated topic name, falling back to the catalog's label."""
        return (
            self.locale.topics.get(topic.key)
            or self.fallback.topics.get(topic.key)
            or topic.label
        )

    # -- number formatting -------------------------------------------------
    # Not a string swap: the decimal and thousands separators differ across
    # these six languages (1,234.5 in English, 1.234,5 in Spanish,
    # 1 234,5 in French and Russian), so every rendered figure has to go
    # through here rather than through a bare f-string.

    def _sep(self, name: str, default: str) -> str:
        return self.locale.numbers.get(name) or self.fallback.numbers.get(name, default)

    def num(self, value: float, decimals: int = 1) -> str:
        """Format a number with this locale's separators."""
        rendered = f"{value:,.{decimals}f}"
        group, decimal = self._sep("group", ","), self._sep("decimal", ".")
        # Swap via a placeholder so a locale that uses "." for grouping
        # doesn't collide with the decimal point mid-substitution.
        return (
            rendered.replace(",", "\x00").replace(".", decimal).replace("\x00", group)
        )

    def percent(self, fraction: float, decimals: int = 0) -> str:
        """Format a 0-1 fraction as a localized percentage."""
        return f"{self.num(fraction * 100, decimals)}%"

    def signed(self, value: float, decimals: int = 2) -> str:
        sign = "+" if value >= 0 else "-"
        return f"{sign}{self.num(abs(value), decimals)}"

    def millions(self, value: float, decimals: int = 1) -> str:
        return f"{self.num(value / 1e6, decimals)} {self._sep('million', 'M')}"

    def blockers(self, spec: Any) -> str:
        """Render a JoinSpec's blockers as whole localized sentences.

        Falls back to the English fragments if a spec predates `blocker_ids`,
        so this can never render an empty reason.
        """
        ids = getattr(spec, "blocker_ids", ()) or ()
        if ids:
            return " ".join(self.t(f"blocker.{i}") for i in ids)
        return "; ".join(spec.blockers)

    def join(self, items: list[str]) -> str:
        """Join a list for display with this locale's list separator."""
        return self._sep("list_separator", ", ").join(items)


def get_translator(code: str, locales: dict[str, Locale] | None = None) -> Translator:
    """Build a Translator for `code`, always with English as the fallback."""
    locales = locales if locales is not None else load_locales()
    fallback = locales[DEFAULT_LOCALE]
    return Translator(locale=locales.get(code, fallback), fallback=fallback)
