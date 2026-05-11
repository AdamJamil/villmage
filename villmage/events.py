# pyre-strict

"""Pure scheduled-event data types owned by Simulation Engine."""

from dataclasses import dataclass, field
from typing import TypeAlias


VillagerId: TypeAlias = str


@dataclass(frozen=True)
class _ScheduledEventBase:
    """Shared heap ordering for all scheduled event variants."""

    timestamp: int
    sequence: int

    def _comparison_key(self) -> tuple[int, int]:
        """Return the timestamp-sequence pair used for heap ordering."""

        return (self.timestamp, self.sequence)

    def __lt__(self, other: object) -> bool:
        """Order scheduled events solely by timestamp and sequence."""

        if not isinstance(other, _ScheduledEventBase):
            return NotImplemented
        return self._comparison_key() < other._comparison_key()

    def __le__(self, other: object) -> bool:
        """Order scheduled events solely by timestamp and sequence."""

        if not isinstance(other, _ScheduledEventBase):
            return NotImplemented
        return self._comparison_key() <= other._comparison_key()

    def __gt__(self, other: object) -> bool:
        """Order scheduled events solely by timestamp and sequence."""

        if not isinstance(other, _ScheduledEventBase):
            return NotImplemented
        return self._comparison_key() > other._comparison_key()

    def __ge__(self, other: object) -> bool:
        """Order scheduled events solely by timestamp and sequence."""

        if not isinstance(other, _ScheduledEventBase):
            return NotImplemented
        return self._comparison_key() >= other._comparison_key()


@dataclass(frozen=True)
class ActionCompleteEvent(_ScheduledEventBase):
    """Heap event for one villager action completion."""

    villager_id: VillagerId = field(compare=False)


@dataclass(frozen=True)
class FireExtinctionEvent(_ScheduledEventBase):
    """Heap event for the next fire-extinction transition."""


@dataclass(frozen=True)
class CarcassRotEvent(_ScheduledEventBase):
    """Heap event for one tracked carcass rotting away."""

    carcass_id: int = field(compare=False)


@dataclass(frozen=True)
class MidnightEvent(_ScheduledEventBase):
    """Heap event for the daily midnight tick."""


@dataclass(frozen=True)
class CheckpointEvent(_ScheduledEventBase):
    """Heap event for writing one serialized checkpoint."""


ScheduledEvent: TypeAlias = (
    ActionCompleteEvent
    | FireExtinctionEvent
    | CarcassRotEvent
    | MidnightEvent
    | CheckpointEvent
)
