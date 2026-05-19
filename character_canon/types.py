# pyre-strict

"""Pure data types for the character canon subsystem."""

from dataclasses import dataclass
from enum import Enum
from typing import NewType


VillagerId = NewType("VillagerId", str)


class Profession(Enum):
    """Static profession tag authored for a villager."""

    CRAFTER = 1
    WOODCUTTER = 2
    HUNTER = 3
    COOK = 4
    GATHERER = 5
    BUILDER = 6


@dataclass(frozen=True)
class VillagerCanon:
    """Immutable authored canon for one villager."""

    id: VillagerId
    name: str
    bio: str
    personality: str
    desires: str
    profession: Profession


@dataclass(frozen=True)
class WorldBackstory:
    """Immutable shared world-context prose."""

    text: str
