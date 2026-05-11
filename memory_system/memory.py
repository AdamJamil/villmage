# pyre-strict

"""Stateful event-log storage for the memory system subsystem."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import TextIO

from llm_client.client import LLMClient
from memory_system.types import (
    EventLogEntry,
    EventType,
    MemoryEntry,
    RelationshipRecord,
    VillagerId,
)


_UNKNOWN_RELATIONSHIP_DESCRIPTION = "I don't know anything about them."


class MemorySystem:
    """Own per-villager event-log state and the persistent JSONL log file."""

    _active_context_log: dict[VillagerId, list[EventLogEntry]]
    _short_term_memories: dict[VillagerId, list[MemoryEntry]]
    _medium_term_memories: dict[VillagerId, list[MemoryEntry]]
    _long_term_memories: dict[VillagerId, list[MemoryEntry]]
    _relationships: dict[VillagerId, dict[VillagerId, RelationshipRecord]]
    _last_long_term_compaction_day: int
    _llm_client: LLMClient
    _event_log_file: TextIO

    def __init__(
        self,
        villager_ids: list[VillagerId],
        llm_client: LLMClient,
        event_log_path: Path,
    ) -> None:
        """Initialize empty per-villager structures and open the persistent event log."""

        self._llm_client = llm_client
        self._active_context_log = {villager_id: [] for villager_id in villager_ids}
        self._short_term_memories = {villager_id: [] for villager_id in villager_ids}
        self._medium_term_memories = {villager_id: [] for villager_id in villager_ids}
        self._long_term_memories = {villager_id: [] for villager_id in villager_ids}
        self._relationships = {
            villager_id: {
                other_villager_id: RelationshipRecord(
                    description=_UNKNOWN_RELATIONSHIP_DESCRIPTION,
                    recent_impressions=[],
                )
                for other_villager_id in villager_ids
                if other_villager_id != villager_id
            }
            for villager_id in villager_ids
        }
        self._last_long_term_compaction_day = 0

        event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._event_log_file = event_log_path.open("a", encoding="utf-8")

    def append_event(self, villager_id: VillagerId, entry: EventLogEntry) -> None:
        """Append one event in memory and durably write it as a JSONL line."""

        self._active_context_log[villager_id].append(entry)
        self._event_log_file.write(json.dumps(asdict(entry)) + "\n")
        self._event_log_file.flush()
        os.fsync(self._event_log_file.fileno())

    def append_thought(self, villager_id: VillagerId, game_time: int, text: str) -> None:
        """Append one THOUGHT event through the main append_event code path."""

        self.append_event(
            villager_id,
            EventLogEntry(game_time=game_time, type=EventType.THOUGHT, text=text),
        )
