# pyre-strict

"""Pure scheduled-event data types owned by Simulation Engine."""

from dataclasses import dataclass, field
from typing import TypeAlias


VillagerId: TypeAlias = str


@dataclass(order=True, frozen=True)
class ActionCompleteEvent:
    """Heap event for one villager action completion."""

    timestamp: int
    sequence: int
    villager_id: VillagerId = field(compare=False)


@dataclass(order=True, frozen=True)
class FireExtinctionEvent:
    """Heap event for the next fire-extinction transition."""

    timestamp: int
    sequence: int


@dataclass(order=True, frozen=True)
class CarcassRotEvent:
    """Heap event for one tracked carcass rotting away."""

    timestamp: int
    sequence: int
    carcass_id: int = field(compare=False)


@dataclass(order=True, frozen=True)
class MidnightEvent:
    """Heap event for the daily midnight tick."""

    timestamp: int
    sequence: int


@dataclass(order=True, frozen=True)
class CheckpointEvent:
    """Heap event for writing one serialized checkpoint."""

    timestamp: int
    sequence: int


ScheduledEvent: TypeAlias = (
    ActionCompleteEvent
    | FireExtinctionEvent
    | CarcassRotEvent
    | MidnightEvent
    | CheckpointEvent
)
