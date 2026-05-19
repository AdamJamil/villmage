# pyre-strict

"""Stateful event-log storage for the memory system subsystem."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import TextIO

from llm_client.client import LLMClient
from llm_client.types import CallType, MessageRole, PromptSegment
from memory_system.types import (
    CompactionReason,
    EventLogEntry,
    EventType,
    MemoryEntry,
    MemorySnapshot,
    RelationshipRecord,
    VillagerId,
    VillagerMemoryContext,
)


_UNKNOWN_RELATIONSHIP_DESCRIPTION = "I don't know anything about them."
_SHORT_TERM_COMPACTION_PROMPT = (
    "Here is a log of everything you experienced recently: {log}. "
    "In 128 tokens (~90 words), form an EXTREMELY CONCISE summary of the salient "
    "memories you experienced. This will be recorded in the future and the rest "
    "will be thrown out. Prioritize information you will use to inform later "
    "actions or opinions on others. Prioritize information density and accuracy."
)
_MEDIUM_TERM_COMPACTION_PROMPT = (
    "Here are your memories from yesterday: {memories}. "
    "In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient "
    "memories you experienced. This will be recorded in the future and the rest "
    "will be thrown out. Prioritize information you will use to inform later "
    "actions or opinions on others. Prioritize information density and accuracy."
)
_LONG_TERM_COMPACTION_PROMPT = (
    "Here are your accumulated memories from prior days: {memories}. "
    "In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient "
    "memories you experienced. This will be recorded in the future and the rest "
    "will be thrown out. Prioritize information you will use to inform later "
    "actions or opinions on others. Prioritize information density and accuracy."
)


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
        self._last_long_term_compaction_day = -1

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

    @staticmethod
    def _serialize_event_log_entries(entries: list[EventLogEntry]) -> str:
        """Return one stable string serialization of a chronological event log slice."""

        return "\n".join(json.dumps(asdict(entry)) for entry in entries)

    @staticmethod
    def _serialize_memory_entries(entries: list[MemoryEntry]) -> str:
        """Return one stable string serialization of a chronological memory slice."""

        return "\n".join(json.dumps(asdict(entry)) for entry in entries)

    @staticmethod
    def _is_from_day(entry: MemoryEntry, day: int) -> bool:
        """Return whether one memory entry was compacted during the supplied day."""

        return entry.game_time // 1440 == day

    def _is_after_long_term_boundary(self, entry: MemoryEntry) -> bool:
        """Return whether one medium-term entry is newer than the last long-term cut."""

        return entry.game_time // 1440 > self._last_long_term_compaction_day

    def write_impressions(
        self,
        speaker_id: VillagerId,
        subject_id: VillagerId,
        impression: str,
        desc_update: str | None,
    ) -> None:
        """Append one impression and optionally replace the relationship description."""

        relationship = self._relationships[speaker_id][subject_id]
        relationship.recent_impressions.append(impression)
        if len(relationship.recent_impressions) > 3:
            relationship.recent_impressions.pop(0)
        if desc_update is not None:
            relationship.description = desc_update

    async def trigger_short_term_compaction(
        self,
        villager_id: VillagerId,
        game_time: int,
        reason: CompactionReason,
    ) -> None:
        """Compact one villager's active context log into one short-term memory entry."""

        del reason
        active_context_log = self._active_context_log[villager_id]
        if len(active_context_log) == 0:
            return

        prompt = _SHORT_TERM_COMPACTION_PROMPT.format(
            log=self._serialize_event_log_entries(active_context_log)
        )
        response = await self._llm_client.complete(
            [PromptSegment(role=MessageRole.USER, text=prompt)],
            CallType.MEMORY_COMPACTION,
        )
        self._short_term_memories[villager_id].append(
            MemoryEntry(game_time=game_time, text=response.text)
        )
        active_context_log.clear()

    async def _compact_medium_term(
        self,
        villager_id: VillagerId,
        current_game_time: int,
    ) -> None:
        """Compact one villager's previous-day short-term memories into medium-term."""

        if len(self._active_context_log[villager_id]) > 0:
            await self.trigger_short_term_compaction(
                villager_id,
                current_game_time,
                CompactionReason.AWAKE_THRESHOLD,
            )

        previous_day = (current_game_time // 1440) - 1
        short_term_memories = self._short_term_memories[villager_id]
        previous_day_entries = [
            entry
            for entry in short_term_memories
            if self._is_from_day(entry, previous_day)
        ]
        if len(previous_day_entries) == 0:
            return

        prompt = _MEDIUM_TERM_COMPACTION_PROMPT.format(
            memories=self._serialize_memory_entries(previous_day_entries)
        )
        response = await self._llm_client.complete(
            [PromptSegment(role=MessageRole.USER, text=prompt)],
            CallType.MEMORY_COMPACTION,
        )
        self._medium_term_memories[villager_id].append(
            MemoryEntry(game_time=current_game_time, text=response.text)
        )
        self._short_term_memories[villager_id] = [
            entry
            for entry in short_term_memories
            if not self._is_from_day(entry, previous_day)
        ]

    async def trigger_midnight_compaction(self, current_game_time: int) -> None:
        """Run midnight compaction for every villager across all eligible tiers."""

        for villager_id in self._active_context_log:
            await self._compact_medium_term(villager_id, current_game_time)

        current_day = current_game_time // 1440
        if current_day % 3 == 0:
            await self._compact_long_term(current_game_time)

    async def _compact_long_term(self, current_game_time: int) -> None:
        """Compact newly accumulated medium-term memories into long-term summaries."""

        for villager_id, medium_term_memories in self._medium_term_memories.items():
            new_entries = [
                entry
                for entry in medium_term_memories
                if self._is_after_long_term_boundary(entry)
            ]
            if len(new_entries) == 0:
                continue

            prompt = _LONG_TERM_COMPACTION_PROMPT.format(
                memories=self._serialize_memory_entries(new_entries)
            )
            response = await self._llm_client.complete(
                [PromptSegment(role=MessageRole.USER, text=prompt)],
                CallType.MEMORY_COMPACTION,
            )
            self._long_term_memories[villager_id].append(
                MemoryEntry(game_time=current_game_time, text=response.text)
            )
            self._medium_term_memories[villager_id] = [
                entry
                for entry in medium_term_memories
                if not self._is_after_long_term_boundary(entry)
            ]

        self._last_long_term_compaction_day = current_game_time // 1440

    @staticmethod
    def _copy_memory_map(
        memory_map: dict[VillagerId, list[MemoryEntry]],
    ) -> dict[VillagerId, list[MemoryEntry]]:
        """Return a per-villager copy of one memory-tier map."""

        return {
            villager_id: list(entries) for villager_id, entries in memory_map.items()
        }

    @staticmethod
    def _copy_event_log_map(
        event_log_map: dict[VillagerId, list[EventLogEntry]],
    ) -> dict[VillagerId, list[EventLogEntry]]:
        """Return a per-villager copy of one event-log map."""

        return {
            villager_id: list(entries) for villager_id, entries in event_log_map.items()
        }

    @staticmethod
    def _copy_relationship_record(record: RelationshipRecord) -> RelationshipRecord:
        """Return a deep copy of one relationship record."""

        return RelationshipRecord(
            description=record.description,
            recent_impressions=list(record.recent_impressions),
        )

    @classmethod
    def _copy_relationship_map(
        cls,
        relationship_map: dict[VillagerId, dict[VillagerId, RelationshipRecord]],
    ) -> dict[VillagerId, dict[VillagerId, RelationshipRecord]]:
        """Return a deep copy of the full directed relationship map."""

        return {
            speaker_id: {
                subject_id: cls._copy_relationship_record(record)
                for subject_id, record in subject_records.items()
            }
            for speaker_id, subject_records in relationship_map.items()
        }

    def trigger_snapshot(self) -> MemorySnapshot:
        """Serialize all in-memory state into a stable point-in-time snapshot."""

        return MemorySnapshot(
            active_context_log=self._copy_event_log_map(self._active_context_log),
            short_term_memories=self._copy_memory_map(self._short_term_memories),
            medium_term_memories=self._copy_memory_map(self._medium_term_memories),
            long_term_memories=self._copy_memory_map(self._long_term_memories),
            relationships=self._copy_relationship_map(self._relationships),
            last_long_term_compaction_day=self._last_long_term_compaction_day,
        )

    def get_full_state(self) -> MemorySnapshot:
        """Return the full checkpointable memory snapshot."""

        return self.trigger_snapshot()

    @classmethod
    def from_snapshot(
        cls,
        snapshot: MemorySnapshot,
        llm_client: LLMClient,
        event_log_path: Path,
    ) -> MemorySystem:
        """Reconstruct a MemorySystem from a previously captured snapshot."""

        if not event_log_path.exists():
            raise FileNotFoundError(event_log_path)

        villager_ids = list(snapshot.active_context_log.keys())
        memory_system = cls.__new__(cls)
        memory_system._llm_client = llm_client
        memory_system._active_context_log = cls._copy_event_log_map(
            snapshot.active_context_log
        )
        memory_system._short_term_memories = cls._copy_memory_map(
            snapshot.short_term_memories
        )
        memory_system._medium_term_memories = cls._copy_memory_map(
            snapshot.medium_term_memories
        )
        memory_system._long_term_memories = cls._copy_memory_map(
            snapshot.long_term_memories
        )
        memory_system._relationships = cls._copy_relationship_map(
            snapshot.relationships
        )
        memory_system._last_long_term_compaction_day = (
            snapshot.last_long_term_compaction_day
        )
        memory_system._event_log_file = event_log_path.open("a", encoding="utf-8")
        for villager_id in villager_ids:
            memory_system._active_context_log.setdefault(villager_id, [])
            memory_system._short_term_memories.setdefault(villager_id, [])
            memory_system._medium_term_memories.setdefault(villager_id, [])
            memory_system._long_term_memories.setdefault(villager_id, [])
            memory_system._relationships.setdefault(villager_id, {})
        return memory_system

    def get_memory_context(self, villager_id: VillagerId) -> VillagerMemoryContext:
        """Assemble the current read-only memory context for one villager."""

        return VillagerMemoryContext(
            long_term_memories=list(self._long_term_memories[villager_id]),
            medium_term_memories=list(self._medium_term_memories[villager_id]),
            short_term_memories=list(self._short_term_memories[villager_id]),
            active_context_log=list(self._active_context_log[villager_id]),
            relationships={
                other_villager_id: self._copy_relationship_record(record)
                for other_villager_id, record in self._relationships[villager_id].items()
            },
        )

    def get_relationship_record(
        self,
        speaker_id: VillagerId,
        subject_id: VillagerId,
    ) -> RelationshipRecord:
        """Return a copied directional relationship record for one ordered pair."""

        return self._copy_relationship_record(
            self._relationships[speaker_id][subject_id]
        )
