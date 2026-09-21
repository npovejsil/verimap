"""Pure tests for the un-gated indicator picker.

Topic used to gate which indicators could be selected at all. It is now a
filter on the list, so these tests pin the two properties that matter: nothing
is unreachable, and population never shows up as something to map.
"""

from __future__ import annotations

from recipe.catalog import Catalog, Indicator, Topic, selectable_indicators
from views.picker import indicator_option_label


def _catalog() -> Catalog:
    topics = {
        "energy_access": Topic("energy_access", "Energy access (SDG7.1)", ()),
        "energy_delivery": Topic("energy_delivery", "Energy delivery", ()),
        "water": Topic("water", "Water & sanitation", ()),
    }
    indicators = {
        "access": Indicator(
            key="access",
            dcid="undata/sdg/A",
            label="Electricity access",
            topics=("energy_access",),
            polarity="higher_is_better",
        ),
        "losses": Indicator(
            key="losses",
            dcid="worldbank/EG.ELC.LOSS.ZS",
            label="T&D losses",
            topics=("energy_delivery",),
            polarity="lower_is_better",
            source="world_bank",
        ),
        "water": Indicator(
            key="water",
            dcid="undata/sdg/W",
            label="Safe water",
            topics=("water",),
            polarity="higher_is_better",
        ),
        # Deliberately in two topics -- the dataclass has always allowed it.
        "both": Indicator(
            key="both",
            dcid="undata/sdg/B",
            label="Straddles two topics",
            topics=("energy_access", "energy_delivery"),
            polarity="neutral",
        ),
        "population": Indicator(
            key="population",
            dcid="undata/unicef/POP",
            label="Total population",
            topics=("_denominators",),
            polarity="neutral",
            role="denominator",
        ),
    }
    return Catalog(indicators=indicators, topics=topics, dimensions={}, units={})


def test_denominators_are_never_selectable() -> None:
    # Population is a divisor for other indicators, not a map in its own right.
    for filt in (None, set(), {"energy_access"}, {"water"}):
        assert "population" not in [
            i.key for i in selectable_indicators(_catalog(), filt)
        ]


def test_an_empty_filter_means_everything_not_nothing() -> None:
    c = _catalog()
    assert {i.key for i in selectable_indicators(c)} == {
        "access",
        "losses",
        "water",
        "both",
    }
    assert selectable_indicators(c, set()) == selectable_indicators(c, None)


def test_a_filter_narrows_to_matching_indicators() -> None:
    keys = {i.key for i in selectable_indicators(_catalog(), {"energy_delivery"})}
    assert keys == {"losses", "both"}


def test_a_multi_topic_indicator_is_reachable_from_either_topic() -> None:
    c = _catalog()
    assert "both" in {i.key for i in selectable_indicators(c, {"energy_access"})}
    assert "both" in {i.key for i in selectable_indicators(c, {"energy_delivery"})}


def test_filtering_several_topics_unions_them() -> None:
    keys = {
        i.key for i in selectable_indicators(_catalog(), {"water", "energy_delivery"})
    }
    assert keys == {"water", "losses", "both"}


def test_results_are_ordered_by_topic_then_label() -> None:
    # A flat list still has to read as grouped.
    c = _catalog()
    assert [i.key for i in selectable_indicators(c)] == [
        "access",  # energy_access, "Electricity access"
        "both",  # energy_access, "Straddles two topics"
        "losses",  # energy_delivery
        "water",  # water
    ]


def test_topics_for_indicator_inverts_indicators_for_topic() -> None:
    c = _catalog()
    for topic_key in c.topics:
        for indicator in c.indicators_for_topic(topic_key):
            assert topic_key in [t.key for t in c.topics_for_indicator(indicator.key)]


def test_option_label_carries_topic_context() -> None:
    c = _catalog()
    assert indicator_option_label(c.indicators["losses"], c) == (
        "Energy delivery · T&D losses"
    )


def test_option_label_falls_back_when_an_indicator_has_no_known_topic() -> None:
    c = _catalog()
    orphan = Indicator(
        key="orphan",
        dcid="undata/sdg/O",
        label="Orphan",
        topics=("_denominators",),
        polarity="neutral",
    )
    c.indicators["orphan"] = orphan
    assert indicator_option_label(orphan, c) == "Other · Orphan"
