# pyre-strict

"""Tests for the foundational MemorySystem event log."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Coroutine
from unittest.mock import AsyncMock

import pytest
from llm_client.client import LLMClient
from llm_client.types import CallType, LLMConfig, LLMResponse, MessageRole, PromptSegment
from memory_system.memory import MemorySystem
from memory_system.types import (
    CompactionReason,
    EventLogEntry,
    EventType,
    MemoryEntry,
    RelationshipRecord,
    VillagerId,
)


_UNKNOWN_RELATIONSHIP_DESCRIPTION = "I don't know anything about them."


def _make_llm_client() -> LLMClient:
    """Construct a real LLMClient because MemorySystem only stores the dependency."""

    return LLMClient(config=LLMConfig(model="gemini-test"), api_key="test-key")


def _make_memory_system(
    villager_ids: list[VillagerId],
    event_log_path: Path,
) -> MemorySystem:
    """Construct a MemorySystem with a no-op LLM dependency for tests."""

    return MemorySystem(
        villager_ids=villager_ids,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )


def _relationship_record(
    memory_system: MemorySystem,
    speaker_id: VillagerId,
    subject_id: VillagerId,
) -> RelationshipRecord:
    """Return one directed relationship record from the memory system."""

    return memory_system._relationships[speaker_id][subject_id]


def _run_async(coroutine: Coroutine[object, object, object]) -> object:
    """Run one async test coroutine to completion."""

    return asyncio.run(coroutine)


def _six_villager_ids() -> list[VillagerId]:
    """Return the canonical six-villager fixture used by context tests."""

    return [
        VillagerId("aldric"),
        VillagerId("maren"),
        VillagerId("ivette"),
        VillagerId("tobin"),
        VillagerId("sylvi"),
        VillagerId("osric"),
    ]


def test_init_builds_empty_per_villager_structures(tmp_path: Path) -> None:
    """Each villager starts with empty active and compacted memory lists."""

    villager_ids = [VillagerId("aldric"), VillagerId("maren"), VillagerId("ivette")]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")

    for villager_id in villager_ids:
        assert memory_system._active_context_log[villager_id] == []
        assert memory_system._short_term_memories[villager_id] == []
        assert memory_system._medium_term_memories[villager_id] == []
        assert memory_system._long_term_memories[villager_id] == []


def test_init_builds_complete_relationship_map(tmp_path: Path) -> None:
    """Every ordered non-self pair starts with the default relationship record."""

    villager_ids = [VillagerId("aldric"), VillagerId("maren"), VillagerId("ivette")]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")

    total_pairs = 0
    for villager_id in villager_ids:
        assert villager_id not in memory_system._relationships[villager_id]
        for other_villager_id in villager_ids:
            if other_villager_id == villager_id:
                continue

            record = memory_system._relationships[villager_id][other_villager_id]
            assert isinstance(record, RelationshipRecord)
            assert record.description == _UNKNOWN_RELATIONSHIP_DESCRIPTION
            assert record.recent_impressions == []
            total_pairs += 1

    assert total_pairs == 6


def test_init_creates_empty_event_log_file(tmp_path: Path) -> None:
    """Construction creates the JSONL log file without writing any content."""

    event_log_path = tmp_path / "new-events.jsonl"
    assert not event_log_path.exists()

    _make_memory_system([VillagerId("aldric")], event_log_path)

    assert event_log_path.exists()
    assert event_log_path.read_bytes() == b""


def test_append_event_accumulates_entries_per_villager(tmp_path: Path) -> None:
    """Events are stored in insertion order and never bleed across villagers."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Aldric woke up.")
    second = EventLogEntry(game_time=2, type=EventType.BASE_EVENT, text="It started raining.")
    third = EventLogEntry(game_time=3, type=EventType.THOUGHT, text="Maren feels uneasy.")

    memory_system.append_event(aldric, first)
    memory_system.append_event(aldric, second)
    memory_system.append_event(maren, third)

    assert memory_system._active_context_log[aldric] == [first, second]
    assert memory_system._active_context_log[maren] == [third]


def test_append_event_writes_jsonl_and_flushes_each_line(tmp_path: Path) -> None:
    """Each appended event appears as one valid JSON line on disk."""

    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([VillagerId("aldric")], event_log_path)
    first = EventLogEntry(game_time=7, type=EventType.ACTION, text="Aldric chopped wood.")
    second = EventLogEntry(game_time=8, type=EventType.BASE_EVENT, text="The fire burned low.")

    memory_system.append_event(VillagerId("aldric"), first)

    lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["game_time"] == first.game_time
    assert parsed["type"] == first.type.value
    assert parsed["text"] == first.text

    memory_system.append_event(VillagerId("aldric"), second)

    assert len(event_log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_append_event_is_immediately_readable_from_disk(tmp_path: Path) -> None:
    """append_event flushes enough that the new line can be read immediately."""

    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([VillagerId("aldric")], event_log_path)
    entry = EventLogEntry(game_time=9, type=EventType.CONVO_TURN, text="Aldric greeted Maren.")

    memory_system.append_event(VillagerId("aldric"), entry)

    lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == entry.text


def test_append_thought_creates_thought_entry(tmp_path: Path) -> None:
    """append_thought wraps the supplied text in a THOUGHT event."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")

    memory_system.append_thought(aldric, game_time=44, text="I should gather more wood.")

    entry = memory_system._active_context_log[aldric][0]
    assert entry.type is EventType.THOUGHT
    assert entry.game_time == 44
    assert entry.text == "I should gather more wood."


def test_append_thought_delegates_to_append_event_jsonl_path(tmp_path: Path) -> None:
    """Thought entries go through append_event and therefore reach the JSONL log."""

    event_log_path = tmp_path / "events.jsonl"
    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], event_log_path)

    memory_system.append_thought(aldric, game_time=81, text="I trust Maren a little more now.")

    lines = event_log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["game_time"] == 81
    assert parsed["type"] == EventType.THOUGHT.value
    assert parsed["text"] == "I trust Maren a little more now."


def test_write_impressions_first_impression_preserves_default_description(
    tmp_path: Path,
) -> None:
    """The first impression is stored while the default description remains intact."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(aldric, maren, "Shared watch duty.", None)

    record = _relationship_record(memory_system, aldric, maren)
    assert record.recent_impressions == ["Shared watch duty."]
    assert record.description == _UNKNOWN_RELATIONSHIP_DESCRIPTION


def test_write_impressions_keeps_up_to_three_in_insertion_order(tmp_path: Path) -> None:
    """The queue preserves oldest-to-newest order while still below the cap."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(aldric, maren, "A", None)
    memory_system.write_impressions(aldric, maren, "B", None)
    memory_system.write_impressions(aldric, maren, "C", None)

    assert _relationship_record(memory_system, aldric, maren).recent_impressions == [
        "A",
        "B",
        "C",
    ]


def test_write_impressions_fourth_impression_drops_oldest_fifo(tmp_path: Path) -> None:
    """Adding a fourth impression discards index zero rather than the newest entry."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    for impression in ["A", "B", "C", "D"]:
        memory_system.write_impressions(aldric, maren, impression, None)

    assert _relationship_record(memory_system, aldric, maren).recent_impressions == [
        "B",
        "C",
        "D",
    ]


def test_write_impressions_continues_fifo_on_successive_rollovers(tmp_path: Path) -> None:
    """Repeated writes keep evicting the oldest entry while preserving chronology."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    for impression in ["A", "B", "C", "D", "E"]:
        memory_system.write_impressions(aldric, maren, impression, None)

    assert _relationship_record(memory_system, aldric, maren).recent_impressions == [
        "C",
        "D",
        "E",
    ]

    memory_system.write_impressions(aldric, maren, "F", None)

    assert _relationship_record(memory_system, aldric, maren).recent_impressions == [
        "D",
        "E",
        "F",
    ]


def test_write_impressions_none_desc_update_leaves_description_unchanged(
    tmp_path: Path,
) -> None:
    """A missing description update never blocks the impression append."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    for impression in ["A", "B", "C", "D"]:
        memory_system.write_impressions(aldric, maren, impression, None)

    record = _relationship_record(memory_system, aldric, maren)
    assert record.recent_impressions == ["B", "C", "D"]
    assert record.description == _UNKNOWN_RELATIONSHIP_DESCRIPTION


def test_write_impressions_replaces_description_wholesale_when_provided(
    tmp_path: Path,
) -> None:
    """A provided description update overwrites the previous description text."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(
        aldric,
        maren,
        "Offered bread after the hunt.",
        "Shared food with party.",
    )

    record = _relationship_record(memory_system, aldric, maren)
    assert record.recent_impressions == ["Offered bread after the hunt."]
    assert record.description == "Shared food with party."


def test_write_impressions_updates_queue_and_description_independently(
    tmp_path: Path,
) -> None:
    """One call can append a new impression and replace the description together."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    for impression in ["A", "B", "C"]:
        memory_system.write_impressions(aldric, maren, impression, None)

    memory_system.write_impressions(
        aldric,
        maren,
        "D",
        "Stayed calm under pressure.",
    )

    record = _relationship_record(memory_system, aldric, maren)
    assert record.recent_impressions == ["B", "C", "D"]
    assert record.description == "Stayed calm under pressure."


def test_write_impressions_isolated_by_ordered_pair(tmp_path: Path) -> None:
    """Directed speaker-subject pairs maintain separate relationship records."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(aldric, maren, "imp1", None)
    memory_system.write_impressions(maren, aldric, "imp2", None)

    assert _relationship_record(memory_system, aldric, maren).recent_impressions == [
        "imp1"
    ]
    assert _relationship_record(memory_system, maren, aldric).recent_impressions == [
        "imp2"
    ]


def test_trigger_snapshot_captures_active_context_log(tmp_path: Path) -> None:
    """Snapshots preserve each villager's current event log entries."""

    villager_ids = _six_villager_ids()
    aldric = villager_ids[0]
    maren = villager_ids[1]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Aldric woke up.")
    second = EventLogEntry(game_time=2, type=EventType.THOUGHT, text="Need more wood.")
    third = EventLogEntry(game_time=3, type=EventType.BASE_EVENT, text="Rain started.")

    memory_system.append_event(aldric, first)
    memory_system.append_event(aldric, second)
    memory_system.append_event(maren, third)

    snapshot = memory_system.trigger_snapshot()

    assert snapshot.active_context_log[aldric] == [first, second]
    assert snapshot.active_context_log[maren] == [third]
    for villager_id in villager_ids[2:]:
        assert snapshot.active_context_log[villager_id] == []


def test_trigger_snapshot_captures_empty_memory_tiers(tmp_path: Path) -> None:
    """Snapshots include every villager key even when all memory tiers are empty."""

    villager_ids = _six_villager_ids()
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")

    snapshot = memory_system.trigger_snapshot()

    for memory_map in [
        snapshot.short_term_memories,
        snapshot.medium_term_memories,
        snapshot.long_term_memories,
    ]:
        assert set(memory_map.keys()) == set(villager_ids)
        for villager_id in villager_ids:
            assert memory_map[villager_id] == []


def test_trigger_snapshot_captures_relationships_with_defaults(tmp_path: Path) -> None:
    """Snapshots include every directed relationship with the default description."""

    villager_ids = _six_villager_ids()
    aldric = villager_ids[0]
    maren = villager_ids[1]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")

    snapshot = memory_system.trigger_snapshot()

    assert (
        snapshot.relationships[aldric][maren].description
        == _UNKNOWN_RELATIONSHIP_DESCRIPTION
    )
    total_pairs = 0
    for villager_id in villager_ids:
        assert villager_id not in snapshot.relationships[villager_id]
        for other_villager_id in villager_ids:
            if other_villager_id == villager_id:
                continue
            total_pairs += 1
            assert other_villager_id in snapshot.relationships[villager_id]
    assert total_pairs == len(villager_ids) * (len(villager_ids) - 1)


def test_trigger_snapshot_captures_populated_relationships(tmp_path: Path) -> None:
    """Snapshots reflect relationship mutations already present in live state."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(
        aldric,
        maren,
        "Shared watch duty.",
        "Dependable at night.",
    )

    snapshot = memory_system.trigger_snapshot()

    assert snapshot.relationships[aldric][maren] == RelationshipRecord(
        description="Dependable at night.",
        recent_impressions=["Shared watch duty."],
    )


def test_trigger_snapshot_is_deep_copy(tmp_path: Path) -> None:
    """Snapshots remain frozen when the live system mutates afterward."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Aldric woke up.")
    second = EventLogEntry(game_time=2, type=EventType.ACTION, text="Aldric ate.")

    memory_system.append_event(aldric, first)
    snapshot = memory_system.trigger_snapshot()
    memory_system.append_event(aldric, second)

    assert snapshot.active_context_log[aldric] == [first]


def test_from_snapshot_round_trips_active_context_log(tmp_path: Path) -> None:
    """Reconstruction restores the active context log exactly as snapshotted."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([aldric, maren], event_log_path)
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Aldric woke up.")
    second = EventLogEntry(game_time=2, type=EventType.THOUGHT, text="Need more wood.")

    memory_system.append_event(aldric, first)
    memory_system.append_event(maren, second)
    snapshot = memory_system.trigger_snapshot()

    restored = MemorySystem.from_snapshot(
        snapshot,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )

    assert restored._active_context_log == snapshot.active_context_log


def test_from_snapshot_round_trips_relationships(tmp_path: Path) -> None:
    """Reconstruction restores all updated relationship records."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    ivette = VillagerId("ivette")
    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([aldric, maren, ivette], event_log_path)

    memory_system.write_impressions(aldric, maren, "Shared bread.", "Generous.")
    memory_system.write_impressions(maren, aldric, "Kept watch.", None)
    memory_system.write_impressions(ivette, aldric, "Worked silently.", "Reserved.")
    snapshot = memory_system.trigger_snapshot()

    restored = MemorySystem.from_snapshot(
        snapshot,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )

    assert restored._relationships == snapshot.relationships


def test_from_snapshot_round_trips_memory_tiers(tmp_path: Path) -> None:
    """Reconstruction restores all memory tiers, including directly injected entries."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([aldric, maren], event_log_path)
    short_term_entry = MemoryEntry(game_time=10, text="Aldric gathered wood.")
    medium_term_entry = MemoryEntry(game_time=20, text="Aldric had a steady morning.")
    long_term_entry = MemoryEntry(game_time=30, text="Maren is consistently cautious.")

    memory_system._short_term_memories[aldric].append(short_term_entry)
    memory_system._medium_term_memories[aldric].append(medium_term_entry)
    memory_system._long_term_memories[maren].append(long_term_entry)
    snapshot = memory_system.trigger_snapshot()

    restored = MemorySystem.from_snapshot(
        snapshot,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )

    assert restored._short_term_memories == snapshot.short_term_memories
    assert restored._medium_term_memories == snapshot.medium_term_memories
    assert restored._long_term_memories == snapshot.long_term_memories


def test_from_snapshot_restores_last_long_term_compaction_day(tmp_path: Path) -> None:
    """Reconstruction restores the last long-term compaction day counter."""

    aldric = VillagerId("aldric")
    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([aldric], event_log_path)
    memory_system._last_long_term_compaction_day = 6
    snapshot = memory_system.trigger_snapshot()

    restored = MemorySystem.from_snapshot(
        snapshot,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )

    assert restored._last_long_term_compaction_day == 6


def test_snapshot_round_trip_after_long_term_compaction(tmp_path: Path) -> None:
    """Snapshot reconstruction preserves post-compaction long-term state."""

    aldric = VillagerId("aldric")
    event_log_path = tmp_path / "events.jsonl"
    memory_system = _make_memory_system([aldric], event_log_path)
    remaining_entry = MemoryEntry(game_time=4420, text="Day 3 summary.")
    compacted_entry = MemoryEntry(game_time=5860, text="Day 4 summary.")
    memory_system._medium_term_memories[aldric].extend([remaining_entry, compacted_entry])
    memory_system._last_long_term_compaction_day = 3

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed long-term summary."""

        del segments, call_type
        return LLMResponse(text="Long-term summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=8640))
    finally:
        monkeypatch.undo()

    snapshot = memory_system.trigger_snapshot()
    restored = MemorySystem.from_snapshot(
        snapshot,
        llm_client=_make_llm_client(),
        event_log_path=event_log_path,
    )

    assert restored._long_term_memories == snapshot.long_term_memories
    assert restored._medium_term_memories == snapshot.medium_term_memories
    assert restored._last_long_term_compaction_day == 6


def test_get_memory_context_relationships_has_exactly_five_entries(
    tmp_path: Path,
) -> None:
    """Context excludes self and includes one relationship per other villager."""

    villager_ids = _six_villager_ids()
    aldric = villager_ids[0]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")

    context = memory_system.get_memory_context(aldric)

    assert len(context.relationships) == 5
    assert aldric not in context.relationships


def test_get_memory_context_relationship_values_match_live_state(tmp_path: Path) -> None:
    """Context relationships mirror the current live relationship state."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")

    memory_system.write_impressions(
        aldric,
        maren,
        "Shared watch duty.",
        "Dependable at night.",
    )

    context = memory_system.get_memory_context(aldric)

    assert context.relationships[maren] == RelationshipRecord(
        description="Dependable at night.",
        recent_impressions=["Shared watch duty."],
    )


def test_get_memory_context_active_context_log_matches_live_state(
    tmp_path: Path,
) -> None:
    """Context exposes the live active-context entries in chronological order."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Aldric woke up.")
    second = EventLogEntry(game_time=2, type=EventType.THOUGHT, text="Need more wood.")

    memory_system.append_event(aldric, first)
    memory_system.append_event(aldric, second)
    context = memory_system.get_memory_context(aldric)

    assert context.active_context_log == [first, second]


def test_get_memory_context_all_memory_tiers_initially_empty(tmp_path: Path) -> None:
    """Fresh context starts with empty long-, medium-, and short-term memory lists."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")

    context = memory_system.get_memory_context(aldric)

    assert context.long_term_memories == []
    assert context.medium_term_memories == []
    assert context.short_term_memories == []


def test_trigger_short_term_compaction_skips_empty_log(tmp_path: Path) -> None:
    """An empty active log short-circuits without calling the LLM or adding memory."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    complete_mock = AsyncMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", complete_mock)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    complete_mock.assert_not_called()
    assert memory_system._short_term_memories[aldric] == []


def test_trigger_short_term_compaction_calls_llm_for_non_empty_log(
    tmp_path: Path,
) -> None:
    """A non-empty active log triggers exactly one memory-compaction LLM call."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=1, type=EventType.ACTION, text="Gathered wood."),
    )
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=2, type=EventType.CONVO_TURN, text="Spoke to Sewalt."),
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed compaction response while asserting the call type."""

        del segments
        assert call_type is CallType.MEMORY_COMPACTION
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    complete_mock = AsyncMock(side_effect=fake_complete)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", complete_mock)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    complete_mock.assert_awaited_once()
    assert complete_mock.await_args.args[1] is CallType.MEMORY_COMPACTION


def test_trigger_short_term_compaction_prompt_contains_log_content(
    tmp_path: Path,
) -> None:
    """The compaction prompt embeds the active log entries verbatim."""

    aldric = VillagerId("aldric")
    first_text = "Gathered wood."
    second_text = "Spoke to Sewalt."
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=1, type=EventType.ACTION, text=first_text),
    )
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=2, type=EventType.CONVO_TURN, text=second_text),
    )
    captured_segments: list[PromptSegment] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture prompt segments and return a fixed response."""

        del call_type
        captured_segments.extend(segments)
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    assert captured_segments == [
        PromptSegment(
            role=MessageRole.USER,
            text=(
                "Here is a log of everything you experienced recently: "
                '{"game_time": 1, "type": 1, "text": "Gathered wood."}\n'
                '{"game_time": 2, "type": 3, "text": "Spoke to Sewalt."}. '
                "In 128 tokens (~90 words), form an EXTREMELY CONCISE summary "
                "of the salient memories you experienced. This will be recorded "
                "in the future and the rest will be thrown out. Prioritize "
                "information you will use to inform later actions or opinions on "
                "others. Prioritize information density and accuracy."
            ),
        )
    ]
    assert first_text in captured_segments[0].text
    assert second_text in captured_segments[0].text


def test_trigger_short_term_compaction_stores_memory_entry_with_supplied_game_time(
    tmp_path: Path,
) -> None:
    """The produced memory entry uses the compaction call's game_time."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=9, type=EventType.ACTION, text="Gathered wood."),
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed memory summary."""

        del segments, call_type
        return LLMResponse(
            text="Gathered wood, spoke to Sewalt.",
            input_tokens=10,
            output_tokens=4,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=720,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    assert memory_system._short_term_memories[aldric][-1].game_time == 720


def test_trigger_short_term_compaction_stores_raw_llm_response_text(
    tmp_path: Path,
) -> None:
    """The produced memory entry preserves the LLM response text verbatim."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=9, type=EventType.ACTION, text="Gathered wood."),
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return the expected raw summary text."""

        del segments, call_type
        return LLMResponse(
            text="Gathered wood, spoke to Sewalt.",
            input_tokens=10,
            output_tokens=4,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=720,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    assert (
        memory_system._short_term_memories[aldric][-1].text
        == "Gathered wood, spoke to Sewalt."
    )


def test_trigger_short_term_compaction_clears_active_context_log(
    tmp_path: Path,
) -> None:
    """Successful compaction empties the villager's active context log."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=1, type=EventType.ACTION, text="Gathered wood."),
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed compaction response."""

        del segments, call_type
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    assert memory_system._active_context_log[aldric] == []


def test_trigger_short_term_compaction_subsequent_events_accumulate_in_cleared_log(
    tmp_path: Path,
) -> None:
    """New events still append normally after compaction clears the active log."""

    aldric = VillagerId("aldric")
    first = EventLogEntry(game_time=1, type=EventType.ACTION, text="Gathered wood.")
    second = EventLogEntry(game_time=2, type=EventType.THOUGHT, text="Need more wood.")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system.append_event(aldric, first)

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed compaction response."""

        del segments, call_type
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    memory_system.append_event(aldric, second)

    assert memory_system._active_context_log[aldric] == [second]


def test_trigger_short_term_compaction_multiple_sequential_runs_append_in_order(
    tmp_path: Path,
) -> None:
    """Each successful compaction appends one short-term memory in insertion order."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    responses = ["summary one", "summary two", "summary three"]
    response_index = 0

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return the next canned summary in sequence."""

        nonlocal response_index
        del segments, call_type
        text = responses[response_index]
        response_index += 1
        return LLMResponse(text=text, input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        for game_time, event_text in enumerate(
            ["first event", "second event", "third event"],
            start=10,
        ):
            memory_system.append_event(
                aldric,
                EventLogEntry(
                    game_time=game_time,
                    type=EventType.ACTION,
                    text=event_text,
                ),
            )
            _run_async(
                memory_system.trigger_short_term_compaction(
                    aldric,
                    game_time=game_time + 100,
                    reason=CompactionReason.SLEEP,
                )
            )
    finally:
        monkeypatch.undo()

    assert [entry.text for entry in memory_system._short_term_memories[aldric]] == responses


def test_trigger_short_term_compaction_preserves_other_villagers_state(
    tmp_path: Path,
) -> None:
    """Compacting one villager does not touch another villager's logs or memories."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    aldric_entry = EventLogEntry(game_time=1, type=EventType.ACTION, text="Gathered wood.")
    maren_entry = EventLogEntry(game_time=2, type=EventType.THOUGHT, text="Need more bread.")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")
    memory_system.append_event(aldric, aldric_entry)
    memory_system.append_event(maren, maren_entry)

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed compaction response."""

        del segments, call_type
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(
            memory_system.trigger_short_term_compaction(
                aldric,
                game_time=100,
                reason=CompactionReason.SLEEP,
            )
        )
    finally:
        monkeypatch.undo()

    assert memory_system._active_context_log[maren] == [maren_entry]
    assert memory_system._short_term_memories[maren] == []


def test_trigger_short_term_compaction_reason_has_no_behavioral_effect(
    tmp_path: Path,
) -> None:
    """Changing CompactionReason does not alter the produced LLM call shape."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    captured_calls: list[tuple[list[PromptSegment], CallType]] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture each call and return a fixed response."""

        captured_calls.append((list(segments), call_type))
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        for reason in [CompactionReason.SLEEP, CompactionReason.AWAKE_THRESHOLD]:
            memory_system.append_event(
                aldric,
                EventLogEntry(game_time=1, type=EventType.ACTION, text="Gathered wood."),
            )
            _run_async(
                memory_system.trigger_short_term_compaction(
                    aldric,
                    game_time=100,
                    reason=reason,
                )
            )
    finally:
        monkeypatch.undo()

    assert len(memory_system._short_term_memories[aldric]) == 2
    assert len(captured_calls) == 2
    assert captured_calls[0] == captured_calls[1]


def test_compact_medium_term_filters_only_previous_day_entries(
    tmp_path: Path,
) -> None:
    """Medium-term compaction includes only the previous day's short-term entries."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].extend(
        [
            MemoryEntry(game_time=1000, text="Day 0: Found tracks."),
            MemoryEntry(game_time=1440, text="Day 1: Hunted boar."),
            MemoryEntry(game_time=2900, text="Day 2: Sharpened spear."),
        ]
    )
    captured_segments: list[PromptSegment] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the medium-term prompt and return a fixed summary."""

        del call_type
        captured_segments.extend(segments)
        return LLMResponse(text="Day 1 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert captured_segments == [
        PromptSegment(
            role=MessageRole.USER,
            text=(
                "Here are your memories from yesterday: "
                '{"game_time": 1440, "text": "Day 1: Hunted boar."}. '
                "In 256 tokens (~180 words), form an EXTREMELY CONCISE summary "
                "of the salient memories you experienced. This will be recorded "
                "in the future and the rest will be thrown out. Prioritize "
                "information you will use to inform later actions or opinions on "
                "others. Prioritize information density and accuracy."
            ),
        )
    ]
    assert MemoryEntry(game_time=1000, text="Day 0: Found tracks.") in (
        memory_system._short_term_memories[aldric]
    )
    assert MemoryEntry(game_time=2900, text="Day 2: Sharpened spear.") in (
        memory_system._short_term_memories[aldric]
    )


def test_compact_medium_term_removes_previous_day_entries_after_compaction(
    tmp_path: Path,
) -> None:
    """Successful medium-term compaction removes the compacted short-term entries."""

    aldric = VillagerId("aldric")
    day_zero_entry = MemoryEntry(game_time=1000, text="Day 0: Found tracks.")
    day_one_entry = MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    day_two_entry = MemoryEntry(game_time=2900, text="Day 2: Sharpened spear.")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].extend(
        [day_zero_entry, day_one_entry, day_two_entry]
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed medium-term summary."""

        del segments, call_type
        return LLMResponse(text="Day 1 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert memory_system._short_term_memories[aldric] == [day_zero_entry, day_two_entry]


def test_compact_medium_term_skips_llm_when_previous_day_is_empty(
    tmp_path: Path,
) -> None:
    """No previous-day short-term entries means medium-term compaction is a no-op."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(
        MemoryEntry(game_time=2880, text="Day 2: Checked traps.")
    )
    complete_mock = AsyncMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", complete_mock)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    complete_mock.assert_not_called()
    assert memory_system._medium_term_memories[aldric] == []


def test_compact_medium_term_forces_short_term_compaction_first(
    tmp_path: Path,
) -> None:
    """Uncompacted active events are compacted before medium-term selection runs."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(
        MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    )
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=2875, type=EventType.ACTION, text="Banked the fire."),
    )
    call_texts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture prompt order for both compaction passes."""

        assert call_type is CallType.MEMORY_COMPACTION
        call_texts.append(segments[0].text)
        if "Here is a log of everything you experienced recently:" in segments[0].text:
            return LLMResponse(text="Day 2 short-term", input_tokens=10, output_tokens=4)
        return LLMResponse(text="Day 1 medium-term", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert len(call_texts) == 2
    assert "Here is a log of everything you experienced recently:" in call_texts[0]
    assert "Here are your memories from yesterday:" in call_texts[1]
    assert memory_system._active_context_log[aldric] == []


def test_compact_medium_term_excludes_same_day_entry_created_by_forced_short_term(
    tmp_path: Path,
) -> None:
    """The forced same-day short-term entry remains for the next midnight."""

    aldric = VillagerId("aldric")
    previous_day_entry = MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(previous_day_entry)
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=2875, type=EventType.ACTION, text="Banked the fire."),
    )
    captured_medium_prompt = ""

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return one short-term and one medium-term summary while capturing the latter."""

        nonlocal captured_medium_prompt
        assert call_type is CallType.MEMORY_COMPACTION
        if "Here is a log of everything you experienced recently:" in segments[0].text:
            return LLMResponse(
                text="Day 2: Banked the fire.",
                input_tokens=10,
                output_tokens=4,
            )
        captured_medium_prompt = segments[0].text
        return LLMResponse(
            text="Day 1: Hunted boar, argued with Harren.",
            input_tokens=10,
            output_tokens=4,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert "Day 1: Hunted boar." in captured_medium_prompt
    assert "Day 2: Banked the fire." not in captured_medium_prompt
    assert memory_system._short_term_memories[aldric] == [
        MemoryEntry(game_time=2880, text="Day 2: Banked the fire.")
    ]


def test_compact_medium_term_stores_entry_with_current_game_time(
    tmp_path: Path,
) -> None:
    """The medium-term MemoryEntry timestamp is the compaction time."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(
        MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed medium-term summary."""

        del segments, call_type
        return LLMResponse(text="Day 1 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert memory_system._medium_term_memories[aldric][-1].game_time == 2880


def test_compact_medium_term_stores_raw_llm_response_text(
    tmp_path: Path,
) -> None:
    """The stored medium-term text matches the LLM response exactly."""

    aldric = VillagerId("aldric")
    expected_text = "Day 1: Hunted boar, argued with Harren."
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(
        MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return the expected medium-term summary."""

        del segments, call_type
        return LLMResponse(text=expected_text, input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_medium_term(aldric, current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert memory_system._medium_term_memories[aldric][-1].text == expected_text


def test_trigger_midnight_compaction_runs_for_all_villagers(tmp_path: Path) -> None:
    """Midnight compaction runs one medium-term pass per villager."""

    villager_ids = [VillagerId("aldric"), VillagerId("maren"), VillagerId("ivette")]
    memory_system = _make_memory_system(villager_ids, tmp_path / "events.jsonl")
    for villager_id in villager_ids:
        memory_system._short_term_memories[villager_id].append(
            MemoryEntry(game_time=1440, text=f"Day 1: {villager_id} acted.")
        )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Echo each villager-specific prompt into a generic summary."""

        del call_type
        return LLMResponse(text=segments[0].text, input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=2880))
    finally:
        monkeypatch.undo()

    for villager_id in villager_ids:
        assert len(memory_system._medium_term_memories[villager_id]) == 1
        assert memory_system._short_term_memories[villager_id] == []


def test_trigger_midnight_compaction_leaves_empty_villager_unchanged(
    tmp_path: Path,
) -> None:
    """A villager with no previous-day entries remains a no-op at midnight."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")
    memory_system._short_term_memories[aldric].append(
        MemoryEntry(game_time=1440, text="Day 1: Hunted boar.")
    )
    captured_prompts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the villagers that actually trigger a medium-term LLM call."""

        assert call_type is CallType.MEMORY_COMPACTION
        captured_prompts.append(segments[0].text)
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=2880))
    finally:
        monkeypatch.undo()

    assert len(captured_prompts) == 1
    assert memory_system._short_term_memories[maren] == []
    assert memory_system._medium_term_memories[maren] == []


def test_trigger_midnight_compaction_fires_long_term_on_day_three(
    tmp_path: Path,
) -> None:
    """Day three midnight triggers long-term compaction for accumulated entries."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._medium_term_memories[aldric].append(
        MemoryEntry(game_time=1000, text="Day 0 summary.")
    )
    captured_prompts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the long-term prompt and return a fixed summary."""

        assert call_type is CallType.MEMORY_COMPACTION
        captured_prompts.append(segments[0].text)
        return LLMResponse(text="Long-term summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=4320))
    finally:
        monkeypatch.undo()

    assert len(captured_prompts) == 1
    assert "Here are your accumulated memories from prior days:" in captured_prompts[0]
    assert len(memory_system._long_term_memories[aldric]) == 1


def test_trigger_midnight_compaction_skips_long_term_on_days_one_and_two(
    tmp_path: Path,
) -> None:
    """Long-term compaction does not run on non-multiples of three."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._medium_term_memories[aldric].append(
        MemoryEntry(game_time=1000, text="Day 0 summary.")
    )
    complete_mock = AsyncMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", complete_mock)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=1440))
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=2880))
    finally:
        monkeypatch.undo()

    complete_mock.assert_not_called()
    assert memory_system._long_term_memories[aldric] == []


def test_trigger_midnight_compaction_fires_long_term_again_on_day_six(
    tmp_path: Path,
) -> None:
    """Day six compaction includes only medium-term entries past the day-three cut."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._last_long_term_compaction_day = 3
    day_three_entry = MemoryEntry(game_time=4420, text="Day 3 summary.")
    day_four_entry = MemoryEntry(game_time=5860, text="Day 4 summary.")
    memory_system._medium_term_memories[aldric].extend([day_three_entry, day_four_entry])
    captured_prompts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the long-term prompt for boundary assertions."""

        assert call_type is CallType.MEMORY_COMPACTION
        captured_prompts.append(segments[0].text)
        return LLMResponse(text="Days 4-5 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=8640))
    finally:
        monkeypatch.undo()

    assert len(captured_prompts) == 1
    assert day_three_entry.text not in captured_prompts[0]
    assert day_four_entry.text in captured_prompts[0]
    assert len(memory_system._long_term_memories[aldric]) == 1


def test_compact_long_term_filters_only_entries_after_last_compaction_day(
    tmp_path: Path,
) -> None:
    """The last long-term day is an exclusive lower bound for medium-term selection."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._last_long_term_compaction_day = 3
    day_three_entry = MemoryEntry(game_time=3 * 1440 + 100, text="Day 3 summary.")
    day_four_entry = MemoryEntry(game_time=4 * 1440 + 100, text="Day 4 summary.")
    memory_system._medium_term_memories[aldric].extend([day_three_entry, day_four_entry])
    captured_prompt = ""

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the long-term prompt and return a fixed summary."""

        nonlocal captured_prompt
        assert call_type is CallType.MEMORY_COMPACTION
        captured_prompt = segments[0].text
        return LLMResponse(text="Day 4 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=8640))
    finally:
        monkeypatch.undo()

    assert day_three_entry.text not in captured_prompt
    assert day_four_entry.text in captured_prompt


def test_compact_long_term_removes_compacted_medium_term_entries(tmp_path: Path) -> None:
    """Successful long-term compaction removes the selected medium-term entries."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    day_three_entry = MemoryEntry(game_time=4420, text="Day 3 summary.")
    day_four_entry = MemoryEntry(game_time=5860, text="Day 4 summary.")
    day_five_entry = MemoryEntry(game_time=7300, text="Day 5 summary.")
    memory_system._last_long_term_compaction_day = 3
    memory_system._medium_term_memories[aldric].extend(
        [day_three_entry, day_four_entry, day_five_entry]
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed long-term summary."""

        del segments, call_type
        return LLMResponse(text="Days 4-5 summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=8640))
    finally:
        monkeypatch.undo()

    assert memory_system._medium_term_memories[aldric] == [day_three_entry]


def test_compact_long_term_updates_last_compaction_day(tmp_path: Path) -> None:
    """Long-term compaction records the day on which it ran."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return a fixed long-term summary."""

        del segments, call_type
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=4320))
    finally:
        monkeypatch.undo()

    assert memory_system._last_long_term_compaction_day == 3


def test_compact_long_term_stores_entry_with_current_game_time_and_response_text(
    tmp_path: Path,
) -> None:
    """The stored long-term entry preserves compaction time and raw response text."""

    aldric = VillagerId("aldric")
    expected_text = "Aldric distrusts Maren but values her skill."
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    memory_system._medium_term_memories[aldric].append(
        MemoryEntry(game_time=1000, text="Day 0 summary.")
    )

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Return the expected long-term summary."""

        del segments, call_type
        return LLMResponse(text=expected_text, input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=4320))
    finally:
        monkeypatch.undo()

    assert memory_system._long_term_memories[aldric][-1].game_time == 4320
    assert memory_system._long_term_memories[aldric][-1].text == expected_text


def test_compact_long_term_skips_llm_when_no_medium_term_entries_exist(
    tmp_path: Path,
) -> None:
    """Without qualifying medium-term entries, long-term compaction is a no-op."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    complete_mock = AsyncMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", complete_mock)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=4320))
    finally:
        monkeypatch.undo()

    complete_mock.assert_not_called()
    assert memory_system._long_term_memories[aldric] == []


def test_compact_long_term_skips_villagers_without_new_medium_term_entries(
    tmp_path: Path,
) -> None:
    """Only villagers with qualifying medium-term entries trigger long-term LLM calls."""

    aldric = VillagerId("aldric")
    maren = VillagerId("maren")
    memory_system = _make_memory_system([aldric, maren], tmp_path / "events.jsonl")
    memory_system._last_long_term_compaction_day = 3
    memory_system._medium_term_memories[aldric].append(
        MemoryEntry(game_time=5860, text="Day 4 summary.")
    )
    memory_system._medium_term_memories[maren].append(
        MemoryEntry(game_time=4420, text="Day 3 summary.")
    )
    captured_prompts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture which villager actually reaches long-term compaction."""

        assert call_type is CallType.MEMORY_COMPACTION
        captured_prompts.append(segments[0].text)
        return LLMResponse(text="summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system._compact_long_term(current_game_time=8640))
    finally:
        monkeypatch.undo()

    assert len(captured_prompts) == 1
    assert memory_system._long_term_memories[maren] == []


def test_trigger_midnight_compaction_runs_full_chain_on_day_three(
    tmp_path: Path,
) -> None:
    """Day-three midnight runs forced short-term, medium-term, then long-term in order."""

    aldric = VillagerId("aldric")
    memory_system = _make_memory_system([aldric], tmp_path / "events.jsonl")
    previous_day_entry = MemoryEntry(game_time=2880, text="Day 2: Hunted boar.")
    qualifying_medium_entry = MemoryEntry(game_time=1000, text="Day 0 summary.")
    memory_system._short_term_memories[aldric].append(previous_day_entry)
    memory_system._medium_term_memories[aldric].append(qualifying_medium_entry)
    memory_system.append_event(
        aldric,
        EventLogEntry(game_time=4310, type=EventType.ACTION, text="Banked the fire."),
    )
    call_texts: list[str] = []

    async def fake_complete(
        segments: list[PromptSegment],
        call_type: CallType,
    ) -> LLMResponse:
        """Capture the exact compaction sequence across all three tiers."""

        assert call_type is CallType.MEMORY_COMPACTION
        prompt_text = segments[0].text
        call_texts.append(prompt_text)
        if "Here is a log of everything you experienced recently:" in prompt_text:
            return LLMResponse(text="Day 3 short-term", input_tokens=10, output_tokens=4)
        if "Here are your memories from yesterday:" in prompt_text:
            return LLMResponse(text="Day 2 medium-term", input_tokens=10, output_tokens=4)
        return LLMResponse(text="Long-term summary", input_tokens=10, output_tokens=4)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(memory_system._llm_client, "complete", fake_complete)
    try:
        _run_async(memory_system.trigger_midnight_compaction(current_game_time=4320))
    finally:
        monkeypatch.undo()

    assert len(call_texts) == 3
    assert "Here is a log of everything you experienced recently:" in call_texts[0]
    assert "Here are your memories from yesterday:" in call_texts[1]
    assert "Here are your accumulated memories from prior days:" in call_texts[2]
    assert memory_system._active_context_log[aldric] == []
    assert "Day 0 summary." in call_texts[2]
    assert "Day 2 medium-term" in call_texts[2]
    assert memory_system._medium_term_memories[aldric] == []
    assert memory_system._long_term_memories[aldric] == [
        MemoryEntry(game_time=4320, text="Long-term summary")
    ]
