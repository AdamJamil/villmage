# pyre-strict

"""Tests for the foundational MemorySystem event log."""

from __future__ import annotations

import json
from pathlib import Path

from llm_client.client import LLMClient
from llm_client.types import LLMConfig
from memory_system.memory import MemorySystem
from memory_system.types import EventLogEntry, EventType, RelationshipRecord, VillagerId


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
