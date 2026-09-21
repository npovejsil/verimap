from __future__ import annotations

import re

import pytest

from recipe.catalog import load_catalog
from recipe.i18n import (
    DEFAULT_LOCALE,
    Locale,
    Translator,
    get_translator,
    load_locales,
)

LOCALES = load_locales()
REFERENCE = LOCALES[DEFAULT_LOCALE]
OTHERS = [c for c in sorted(LOCALES) if c != DEFAULT_LOCALE]

_PLACEHOLDER = re.compile(r"{(\w+)}")


def _stub(key: str, label: str) -> object:
    """Minimal stand-in for an Indicator/Topic: i18n only reads .key/.label."""

    class _Stub:
        pass

    s = _Stub()
    s.key, s.label = key, label
    return s


def test_all_six_un_languages_present() -> None:
    assert set(LOCALES) == {"ar", "en", "es", "fr", "ru", "zh"}


@pytest.mark.parametrize("code", OTHERS)
def test_ui_keys_match_english_exactly(code: str) -> None:
    """The check that keeps this honest as strings are added later.

    A new key in en.yml fails every other locale until it is translated,
    which is the point -- a half-translated release should not be silently
    possible.
    """
    locale = LOCALES[code]
    assert set(locale.ui) == set(REFERENCE.ui), (
        f"{code}: missing={sorted(set(REFERENCE.ui) - set(locale.ui))} "
        f"extra={sorted(set(locale.ui) - set(REFERENCE.ui))}"
    )


@pytest.mark.parametrize("code", OTHERS)
def test_indicator_and_topic_keys_match_english(code: str) -> None:
    locale = LOCALES[code]
    assert set(locale.indicators) == set(REFERENCE.indicators)
    assert set(locale.topics) == set(REFERENCE.topics)


@pytest.mark.parametrize("code", OTHERS)
def test_placeholders_match_english_per_key(code: str) -> None:
    """A template must interpolate exactly the names English passes it.

    Translating `{matched} of {total}` into a string that says `{total}`
    twice and drops `{matched}` would render a sentence missing a number
    rather than raising, so it has to be caught here.
    """
    locale = LOCALES[code]
    for key, english in REFERENCE.ui.items():
        assert set(_PLACEHOLDER.findall(locale.ui[key])) == set(
            _PLACEHOLDER.findall(english)
        ), f"{code}: placeholder mismatch on '{key}'"


def test_every_catalog_indicator_has_an_english_name() -> None:
    """A new indicator in the catalog must not appear untranslated."""
    catalog = load_catalog()
    for key in catalog.indicators:
        assert key in REFERENCE.indicators, f"'{key}' has no en.yml entry"
    for key in catalog.topics:
        assert key in REFERENCE.topics, f"topic '{key}' has no en.yml entry"


def test_unknown_key_returns_the_key_and_does_not_raise() -> None:
    t = get_translator("fr", LOCALES)
    assert t.t("nope.not.a.key") == "nope.not.a.key"


def test_missing_translation_falls_back_to_english() -> None:
    sparse = Locale(
        code="xx",
        name="Test",
        direction="ltr",
        ui={},
        indicators={},
        topics={},
        numbers={},
    )
    t = Translator(locale=sparse, fallback=REFERENCE)
    assert t.t("tab.map") == REFERENCE.ui["tab.map"]


def test_unknown_locale_falls_back_to_english() -> None:
    assert get_translator("xx", LOCALES).locale.code == DEFAULT_LOCALE


def test_bad_params_return_the_template_rather_than_raising() -> None:
    t = get_translator("en", LOCALES)
    assert t.t("map.coverage", wrong="x") == REFERENCE.ui["map.coverage"]


def test_indicator_falls_back_to_catalog_label() -> None:
    t = get_translator("es", LOCALES)
    unknown = _stub("not_in_any_locale", "Catalog Label")
    assert t.indicator(unknown) == "Catalog Label"
    assert t.indicator(_stub("sdg_elec_access", "Electricity access")) == (
        "Acceso a la electricidad"
    )


def test_topic_falls_back_to_catalog_label() -> None:
    t = get_translator("fr", LOCALES)
    assert t.topic(_stub("nope", "Catalog Topic")) == "Catalog Topic"


def test_number_separators_are_locale_specific() -> None:
    assert get_translator("en", LOCALES).num(1234567.89, 2) == "1,234,567.89"
    assert get_translator("es", LOCALES).num(1234567.89, 2) == "1.234.567,89"
    assert get_translator("fr", LOCALES).num(1234567.89, 2) == "1 234 567,89"


def test_percent_and_signed_use_locale_separators() -> None:
    assert get_translator("es", LOCALES).percent(0.634, 1) == "63,4%"
    assert get_translator("en", LOCALES).signed(-0.5) == "-0.50"
    assert get_translator("en", LOCALES).signed(0.5) == "+0.50"


def test_rtl_flag_only_set_for_arabic() -> None:
    assert get_translator("ar", LOCALES).is_rtl
    for code in ("en", "es", "fr", "ru", "zh"):
        assert not get_translator(code, LOCALES).is_rtl


def test_blockers_render_as_whole_sentences() -> None:
    class _Spec:
        blocker_ids = ("no_places", "no_years")
        blockers = ("no places in common", "no years in common")

    rendered = get_translator("fr", LOCALES).blockers(_Spec())
    assert "en commun" in rendered
    assert "no places in common" not in rendered


def test_blockers_fall_back_to_english_fragments_without_ids() -> None:
    class _OldSpec:
        blocker_ids = ()
        blockers = ("no places in common",)

    assert get_translator("fr", LOCALES).blockers(_OldSpec()) == ("no places in common")
