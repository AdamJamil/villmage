# pyre-strict

"""Tests for simulation-engine conversation-action rescheduling."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import ActionCompleteEvent
from villmage.simulation_engine import SimulationEngine


def _build_engine() -> SimulationEngine:
    """Construct one engine with mocked subsystem dependencies."""

    return SimulationEngine(
        character_canon=CharacterCanon(),
        action_system=cast(object, Mock()),
        ai_coordinator=cast(AICoordinator, Mock(spec=AICoordinator)),
        conversation_system=cast(
            ConversationSystem,
            Mock(spec=ConversationSystem),
        ),
        memory_system=cast(MemorySystem, Mock(spec=MemorySystem)),
    )


def _action_events(engine: SimulationEngine) -> list[ActionCompleteEvent]:
    """Return only action-complete events from the engine heap."""

    return [
        event for event in engine.event_heap if isinstance(event, ActionCompleteEvent)
    ]


def _action_timestamps_for(
    engine: SimulationEngine,
    villager_id: str,
) -> list[int]:
    """Return all pending action-complete timestamps for one villager."""

    return [
        event.timestamp
        for event in _action_events(engine)
        if event.villager_id == villager_id
    ]


def test_handle_conversation_action_reschedules_single_target() -> None:
    """A joined target's paused action should resume after the conversation delay."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 570
    engine._push(ActionCompleteEvent(timestamp=600, sequence=-1, villager_id="sewalt"))
    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).return_value = (30, ["sewalt"])

    engine._handle_conversation_action("aldric", "sewalt")

    assert 600 not in _action_timestamps_for(engine, "sewalt")
    assert _action_timestamps_for(engine, "sewalt") == [630]


def test_handle_conversation_action_reschedules_multiple_bystanders() -> None:
    """Only reported non-initiator participants should have deadlines shifted."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 570
    engine._push(ActionCompleteEvent(timestamp=600, sequence=-1, villager_id="sewalt"))
    engine._push(ActionCompleteEvent(timestamp=700, sequence=-1, villager_id="harren"))
    engine._push(ActionCompleteEvent(timestamp=500, sequence=-1, villager_id="maren"))
    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).return_value = (45, ["sewalt", "harren"])

    engine._handle_conversation_action("aldric", "sewalt")

    assert _action_timestamps_for(engine, "sewalt") == [645]
    assert _action_timestamps_for(engine, "harren") == [745]
    assert _action_timestamps_for(engine, "maren") == [500]


def test_handle_conversation_action_does_not_schedule_initiator() -> None:
    """The initiator's next event is owned by the caller, not this helper."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).return_value = (30, ["aldric", "sewalt"])

    engine._handle_conversation_action("aldric", "sewalt")

    assert all(event.villager_id != "aldric" for event in _action_events(engine))


def test_handle_conversation_action_skips_participant_without_pending_event() -> None:
    """Participants with no pending action-complete event should be ignored cleanly."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).return_value = (30, ["sewalt"])

    engine._handle_conversation_action("aldric", "sewalt")

    assert _action_events(engine) == []


def test_handle_conversation_action_calls_run_conversation_with_correct_args() -> None:
    """The conversation subsystem should receive the initiator, target, and game time."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 570
    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).return_value = (30, ["sewalt"])

    engine._handle_conversation_action("aldric", "sewalt")

    cast(
        AsyncMock,
        engine.conversation_system.run_conversation,
    ).assert_awaited_once_with("aldric", "sewalt", 570)
