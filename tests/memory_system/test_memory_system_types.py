# pyre-strict

"""Tests for pure memory system data types."""

from dataclasses import FrozenInstanceError

import pytest

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


def test_event_type_values_match_spec() -> None:
    """EventType contains the exact routing values from the spec."""

    assert len(EventType) == 5
    assert EventType.ACTION.value == 1
    assert EventType.THOUGHT.value == 2
    assert EventType.CONVO_TURN.value == 3
    assert EventType.TRADE.value == 4
    assert EventType.BASE_EVENT.value == 5


def test_compaction_reason_values_match_spec() -> None:
    """CompactionReason contains the exact routing values from the spec."""

    assert len(CompactionReason) == 2
    assert CompactionReason.SLEEP.value == 1
    assert CompactionReason.AWAKE_THRESHOLD.value == 2


def test_event_log_entry_construction() -> None:
    """EventLogEntry stores all supplied fields."""

    entry = EventLogEntry(
        game_time=123,
        type=EventType.CONVO_TURN,
        text="Aldric traded for berries.",
    )

    assert entry.game_time == 123
    assert entry.type is EventType.CONVO_TURN
    assert entry.text == "Aldric traded for berries."


def test_event_log_entry_is_frozen() -> None:
    """EventLogEntry rejects field reassignment."""

    entry = EventLogEntry(game_time=5, type=EventType.ACTION, text="Started hauling.")

    with pytest.raises(FrozenInstanceError):
        entry.text = "Mutated"


def test_memory_entry_construction() -> None:
    """MemoryEntry stores all supplied fields."""

    entry = MemoryEntry(game_time=1440, text="Yesterday involved a trade and a hunt.")

    assert entry.game_time == 1440
    assert entry.text == "Yesterday involved a trade and a hunt."


def test_memory_entry_is_frozen() -> None:
    """MemoryEntry rejects field reassignment."""

    entry = MemoryEntry(game_time=10, text="A summary.")

    with pytest.raises(FrozenInstanceError):
        entry.game_time = 11


def test_relationship_record_is_mutable() -> None:
    """RelationshipRecord exposes mutable fields for in-place updates."""

    record = RelationshipRecord(
        description="I do not know them well.",
        recent_impressions=[],
    )

    assert record.description == "I do not know them well."
    assert record.recent_impressions == []

    record.recent_impressions.append("They shared their food.")
    assert record.recent_impressions == ["They shared their food."]

    removed_impression = record.recent_impressions.pop()
    assert removed_impression == "They shared their food."
    assert record.recent_impressions == []


def test_villager_memory_context_construction() -> None:
    """VillagerMemoryContext stores all supplied fields."""

    context = VillagerMemoryContext(
        long_term_memories=[],
        medium_term_memories=[],
        short_term_memories=[],
        active_context_log=[],
        relationships={},
    )

    assert context.long_term_memories == []
    assert context.medium_term_memories == []
    assert context.short_term_memories == []
    assert context.active_context_log == []
    assert context.relationships == {}


def test_villager_memory_context_is_frozen() -> None:
    """VillagerMemoryContext rejects field reassignment."""

    context = VillagerMemoryContext(
        long_term_memories=[],
        medium_term_memories=[],
        short_term_memories=[],
        active_context_log=[],
        relationships={},
    )

    with pytest.raises(FrozenInstanceError):
        context.relationships = {}


def test_memory_snapshot_construction() -> None:
    """MemorySnapshot stores all supplied fields."""

    snapshot = MemorySnapshot(
        active_context_log={},
        short_term_memories={},
        medium_term_memories={},
        long_term_memories={},
        relationships={},
        last_long_term_compaction_day=6,
    )

    assert snapshot.active_context_log == {}
    assert snapshot.short_term_memories == {}
    assert snapshot.medium_term_memories == {}
    assert snapshot.long_term_memories == {}
    assert snapshot.relationships == {}
    assert snapshot.last_long_term_compaction_day == 6


def test_memory_snapshot_is_frozen() -> None:
    """MemorySnapshot rejects field reassignment."""

    snapshot = MemorySnapshot(
        active_context_log={},
        short_term_memories={},
        medium_term_memories={},
        long_term_memories={},
        relationships={},
        last_long_term_compaction_day=0,
    )

    with pytest.raises(FrozenInstanceError):
        snapshot.last_long_term_compaction_day = 1


def test_villager_id_behaves_like_str_at_runtime() -> None:
    """VillagerId remains string-compatible at runtime."""

    villager_id = VillagerId("aldric")
    records = {villager_id: "present"}

    assert villager_id == "aldric"
    assert records["aldric"] == "present"
