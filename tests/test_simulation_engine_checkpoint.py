# pyre-strict

"""Tests for SimulationEngine checkpoint persistence and reload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import Mock

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from llm_client.client import LLMClient
from llm_client.types import LLMConfig
from memory_system.memory import MemorySystem
from memory_system.types import VillagerId as MemoryVillagerId
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import (
    ActionCompleteEvent,
    CarcassRotEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
    ScheduledEvent,
)
from villmage.simulation_engine import SimulationEngine


def _make_memory_system(event_log_path: Path) -> MemorySystem:
    """Construct one real memory system for checkpoint round-trip coverage."""

    villager_ids = [
        MemoryVillagerId("aldric"),
        MemoryVillagerId("sewalt"),
        MemoryVillagerId("harren"),
        MemoryVillagerId("maren"),
        MemoryVillagerId("ivette"),
        MemoryVillagerId("thessia"),
    ]
    return MemorySystem(
        villager_ids=villager_ids,
        llm_client=LLMClient(config=LLMConfig(model="gemini-test"), api_key="test-key"),
        event_log_path=event_log_path,
    )


def _build_engine(tmp_path: Path) -> SimulationEngine:
    """Construct one engine with a real memory system and mocked peers."""

    engine = SimulationEngine(
        character_canon=CharacterCanon(),
        action_system=cast(object, Mock()),
        ai_coordinator=cast(AICoordinator, Mock(spec=AICoordinator)),
        conversation_system=cast(ConversationSystem, Mock(spec=ConversationSystem)),
        memory_system=_make_memory_system(tmp_path / "events.jsonl"),
    )
    engine.checkpoint_dir = tmp_path
    return engine


def _event_key(event: ScheduledEvent) -> tuple[object, ...]:
    """Return one stable comparable tuple for a scheduled event."""

    if isinstance(event, ActionCompleteEvent):
        return (type(event).__name__, event.timestamp, event.sequence, event.villager_id)
    if isinstance(event, CarcassRotEvent):
        return (type(event).__name__, event.timestamp, event.sequence, event.carcass_id)
    return (type(event).__name__, event.timestamp, event.sequence)


def test_handle_checkpoint_writes_expected_filename(tmp_path: Path) -> None:
    """Checkpoint writes to `{current_game_time}.json` in the configured directory."""

    engine = _build_engine(tmp_path)
    engine.current_game_time = 540
    engine.event_heap = []
    engine.next_sequence = 0

    engine._handle_checkpoint()

    assert (tmp_path / "540.json").exists()


def test_handle_checkpoint_writes_valid_json_with_required_top_level_keys(
    tmp_path: Path,
) -> None:
    """Checkpoint output parses and exposes the full required root schema."""

    engine = _build_engine(tmp_path)
    engine.current_game_time = 540
    engine.event_heap = []
    engine.next_sequence = 0

    engine._handle_checkpoint()

    with (tmp_path / "540.json").open("r", encoding="utf-8") as checkpoint_file:
        data = json.load(checkpoint_file)

    assert set(data.keys()) == {
        "villager_states",
        "world_state",
        "memory_state",
        "autobalance",
        "event_heap",
        "current_game_time",
    }


def test_handle_checkpoint_serializes_all_event_types(tmp_path: Path) -> None:
    """Checkpoint event-heap JSON preserves each event's tag, timing, and payload."""

    engine = _build_engine(tmp_path)
    engine.current_game_time = 540
    engine.event_heap = []
    engine.next_sequence = 0
    engine._push(ActionCompleteEvent(timestamp=600, sequence=-1, villager_id="aldric"))
    engine._push(FireExtinctionEvent(timestamp=610, sequence=-1))
    engine._push(CarcassRotEvent(timestamp=620, sequence=-1, carcass_id=3))
    engine._push(MidnightEvent(timestamp=1440, sequence=-1))
    engine._push(CheckpointEvent(timestamp=900, sequence=-1))

    engine._handle_checkpoint()

    with (tmp_path / "540.json").open("r", encoding="utf-8") as checkpoint_file:
        data = json.load(checkpoint_file)

    event_heap = data["event_heap"]
    assert isinstance(event_heap, list)
    assert len(event_heap) == 5
    events_by_type = {
        cast(str, event["type"]): event
        for event in cast(list[dict[str, object]], event_heap)
    }

    assert events_by_type["ActionCompleteEvent"] == {
        "type": "ActionCompleteEvent",
        "timestamp": 600,
        "sequence": 0,
        "villager_id": "aldric",
    }
    assert events_by_type["FireExtinctionEvent"] == {
        "type": "FireExtinctionEvent",
        "timestamp": 610,
        "sequence": 1,
    }
    assert events_by_type["CarcassRotEvent"] == {
        "type": "CarcassRotEvent",
        "timestamp": 620,
        "sequence": 2,
        "carcass_id": 3,
    }
    assert events_by_type["MidnightEvent"] == {
        "type": "MidnightEvent",
        "timestamp": 1440,
        "sequence": 3,
    }
    assert events_by_type["CheckpointEvent"] == {
        "type": "CheckpointEvent",
        "timestamp": 900,
        "sequence": 4,
    }


def test_handle_checkpoint_schedules_next_checkpoint_once(tmp_path: Path) -> None:
    """Checkpoint handling leaves exactly one future checkpoint on the live heap."""

    engine = _build_engine(tmp_path)
    engine.current_game_time = 540

    engine._handle_checkpoint()

    checkpoint_events = [
        event for event in engine.event_heap if isinstance(event, CheckpointEvent)
    ]
    assert len(checkpoint_events) == 1
    assert checkpoint_events[0].timestamp == 720


def test_load_checkpoint_round_trips_engine_state(tmp_path: Path) -> None:
    """Reload preserves the saved clock, multipliers, and effective heap contents."""

    engine = _build_engine(tmp_path)
    engine.current_game_time = 540
    engine.event_heap = []
    engine.next_sequence = 0
    engine.autobalance.exploration_yield = 1.25
    engine.autobalance.satiation_restore = 0.8
    engine.autobalance.hydration_restore = 1.1
    engine._push(ActionCompleteEvent(timestamp=600, sequence=-1, villager_id="aldric"))
    engine._push(FireExtinctionEvent(timestamp=610, sequence=-1))
    engine._push(CarcassRotEvent(timestamp=620, sequence=-1, carcass_id=3))
    engine._push(MidnightEvent(timestamp=1440, sequence=-1))

    engine._handle_checkpoint()

    restored = SimulationEngine.load_checkpoint(tmp_path / "540.json")

    assert restored.current_game_time == engine.current_game_time
    assert restored.autobalance == engine.autobalance
    assert sorted(_event_key(event) for event in restored.event_heap) == sorted(
        _event_key(event) for event in engine.event_heap
    )
