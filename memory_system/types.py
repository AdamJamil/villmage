# pyre-strict

"""Pure data types for the memory system subsystem."""

from dataclasses import dataclass
from enum import IntEnum
from typing import NewType


VillagerId = NewType("VillagerId", str)


class EventType(IntEnum):
    """Category tag for one event-log entry."""

    ACTION = 1
    THOUGHT = 2
    CONVO_TURN = 3
    TRADE = 4
    BASE_EVENT = 5


class CompactionReason(IntEnum):
    """Cause of a per-villager short-term compaction."""

    SLEEP = 1
    AWAKE_THRESHOLD = 2


@dataclass(frozen=True)
class EventLogEntry:
    """Immutable timestamped event stored in a villager log."""

    game_time: int
    type: EventType
    text: str


@dataclass(frozen=True)
class MemoryEntry:
    """Immutable compacted memory summary with its compaction time."""

    game_time: int
    text: str


@dataclass
class RelationshipRecord:
    """Mutable directional relationship state for one speaker-subject pair."""

    description: str
    recent_impressions: list[str]


@dataclass(frozen=True)
class VillagerMemoryContext:
    """Read-only assembled memory view consumed by AI Coordinator."""

    long_term_memories: list[MemoryEntry]
    medium_term_memories: list[MemoryEntry]
    short_term_memories: list[MemoryEntry]
    active_context_log: list[EventLogEntry]
    relationships: dict[VillagerId, RelationshipRecord]


@dataclass(frozen=True)
class MemorySnapshot:
    """Read-only typed checkpoint of the memory system state."""

    active_context_log: dict[VillagerId, list[EventLogEntry]]
    short_term_memories: dict[VillagerId, list[MemoryEntry]]
    medium_term_memories: dict[VillagerId, list[MemoryEntry]]
    long_term_memories: dict[VillagerId, list[MemoryEntry]]
    relationships: dict[VillagerId, dict[VillagerId, RelationshipRecord]]
    last_long_term_compaction_day: int
