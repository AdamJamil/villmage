# pyre-strict

"""Tests for pure character canon data types."""

from dataclasses import FrozenInstanceError

import pytest

from character_canon.types import Profession, VillagerCanon, VillagerId, WorldBackstory


def test_profession_values_match_spec() -> None:
    """Profession contains exactly the authored members and values."""

    assert len(Profession) == 6
    assert Profession.CRAFTER.value == 1
    assert Profession.WOODCUTTER.value == 2
    assert Profession.HUNTER.value == 3
    assert Profession.COOK.value == 4
    assert Profession.GATHERER.value == 5
    assert Profession.BUILDER.value == 6


def test_villager_canon_is_frozen() -> None:
    """VillagerCanon rejects field reassignment."""

    canon = VillagerCanon(
        id=VillagerId("aldric"),
        name="Aldric",
        bio="Village merchant.",
        personality="Measured and observant.",
        desires="Keep the village stable.",
        profession=Profession.CRAFTER,
    )

    with pytest.raises(FrozenInstanceError):
        canon.name = "Other"


def test_world_backstory_is_frozen() -> None:
    """WorldBackstory rejects field reassignment."""

    backstory = WorldBackstory(text="A quiet settlement endures a strange season.")

    with pytest.raises(FrozenInstanceError):
        backstory.text = "Mutated"
