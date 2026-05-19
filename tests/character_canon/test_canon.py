# pyre-strict

"""Tests for static character canon data and accessors."""

import pytest

from character_canon.canon import CharacterCanon, _BACKSTORY, _VILLAGERS
from character_canon.types import Profession, VillagerCanon, VillagerId, WorldBackstory


def test_villagers_contains_exactly_six_records() -> None:
    """The authored villager table contains exactly six records."""

    assert len(_VILLAGERS) == 6


def test_villager_ids_are_unique() -> None:
    """Each authored villager id appears exactly once."""

    assert len({villager.id for villager in _VILLAGERS}) == 6


def test_villager_identity_fields_match_spec_table() -> None:
    """Each villager's id, name, and profession match the authored spec."""

    expected: dict[VillagerId, tuple[str, Profession]] = {
        VillagerId("aldric"): ("Aldric the Woodsman", Profession.WOODCUTTER),
        VillagerId("sewalt"): ("Sewalt the Hunter", Profession.HUNTER),
        VillagerId("harren"): ("Harren the Builder", Profession.BUILDER),
        VillagerId("maren"): ("Maren the Gatherer", Profession.GATHERER),
        VillagerId("ivette"): ("Ivette the Crafter", Profession.CRAFTER),
        VillagerId("thessia"): ("Thessia the Cook", Profession.COOK),
    }

    actual = {
        villager.id: (villager.name, villager.profession) for villager in _VILLAGERS
    }

    assert actual == expected


def test_villager_authored_prompt_fields_are_non_empty() -> None:
    """Each villager has authored bio, personality, and desires text."""

    for villager in _VILLAGERS:
        assert villager.bio
        assert villager.personality
        assert villager.desires


def test_get_villager_returns_expected_record_for_each_valid_id() -> None:
    """Lookup returns the authored villager record for every known id."""

    canon = CharacterCanon()

    for villager in _VILLAGERS:
        assert canon.get_villager(villager.id) == villager


def test_get_villager_raises_key_error_for_unknown_id() -> None:
    """Lookup raises KeyError when the id is not present."""

    canon = CharacterCanon()

    with pytest.raises(KeyError):
        canon.get_villager(VillagerId("nobody"))


def test_get_all_villagers_returns_authoring_order() -> None:
    """Bulk access returns the authored villager tuple unchanged."""

    canon = CharacterCanon()

    assert canon.get_all_villagers() == _VILLAGERS


def test_get_backstory_returns_authored_world_backstory() -> None:
    """Backstory access returns the shared authored prose record."""

    canon = CharacterCanon()

    backstory = canon.get_backstory()

    assert isinstance(backstory, WorldBackstory)
    assert backstory == _BACKSTORY
    assert "Grey Rot" in backstory.text
