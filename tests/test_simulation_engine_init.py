# pyre-strict

"""Tests for simulation-engine initialization and heap helper primitives."""

from heapq import heappop
from typing import cast
from unittest.mock import Mock

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
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


def _build_engine() -> SimulationEngine:
    """Construct one engine with mocked non-init subsystem dependencies."""

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


def _action_events(events: list[ScheduledEvent]) -> list[ActionCompleteEvent]:
    """Return only action-complete events from one scheduled-event list."""

    return [event for event in events if isinstance(event, ActionCompleteEvent)]


def test_init_prepopulates_heap_with_expected_event_types() -> None:
    """Startup heap contains only the authored initial event set."""

    engine = _build_engine()

    assert len(engine.event_heap) == 8
    assert len(_action_events(engine.event_heap)) == 6
    assert sum(isinstance(event, MidnightEvent) for event in engine.event_heap) == 1
    assert sum(isinstance(event, CheckpointEvent) for event in engine.event_heap) == 1
    assert not any(isinstance(event, FireExtinctionEvent) for event in engine.event_heap)
    assert not any(isinstance(event, CarcassRotEvent) for event in engine.event_heap)


def test_init_prepopulates_heap_with_expected_timestamps_and_villagers() -> None:
    """Startup heap timestamps and villager coverage match the authored spec."""

    engine = _build_engine()
    canon_ids = {
        str(villager.id) for villager in engine.character_canon.get_all_villagers()
    }
    action_events = _action_events(engine.event_heap)
    midnight_event = next(
        event for event in engine.event_heap if isinstance(event, MidnightEvent)
    )
    checkpoint_event = next(
        event for event in engine.event_heap if isinstance(event, CheckpointEvent)
    )

    assert {event.timestamp for event in action_events} == {360}
    assert {event.villager_id for event in action_events} == canon_ids
    assert midnight_event.timestamp == 1440
    assert checkpoint_event.timestamp == 540


def test_init_assigns_monotone_sequences_and_updates_next_sequence() -> None:
    """Startup pushes stamp action events 0-5 and leave next_sequence at 8."""

    engine = _build_engine()
    action_events = _action_events(engine.event_heap)
    non_action_sequences = {
        event.sequence
        for event in engine.event_heap
        if isinstance(event, (MidnightEvent, CheckpointEvent))
    }

    assert {event.sequence for event in action_events} == {0, 1, 2, 3, 4, 5}
    assert non_action_sequences == {6, 7}
    assert engine.next_sequence == 8


def test_init_sets_current_game_time_and_default_autobalance() -> None:
    """Startup clock and autobalance multipliers match the authored defaults."""

    engine = _build_engine()

    assert engine.current_game_time == 360
    assert engine.autobalance.exploration_yield == 1.0
    assert engine.autobalance.satiation_restore == 1.0
    assert engine.autobalance.hydration_restore == 1.0


def test_init_builds_six_villager_states_at_starting_values() -> None:
    """Startup villager-state table mirrors the authored initial stat bundle."""

    engine = _build_engine()

    assert len(engine.villager_states) == 6
    for villager_state in engine.villager_states.values():
        assert villager_state.wakefulness == 100
        assert villager_state.satiation == 1800
        assert villager_state.hydration == 6000
        assert villager_state.connectedness == 100
        assert villager_state.cleanliness == 100
        assert villager_state.social_joy == 20
        assert villager_state.inventory == {}


def test_push_stamps_current_sequence_and_increments_counter() -> None:
    """_push uses the pre-increment sequence and advances next_sequence once."""

    engine = _build_engine()
    starting_sequence = engine.next_sequence
    event = MidnightEvent(timestamp=2000, sequence=-1)

    engine._push(event)

    assert engine.next_sequence == starting_sequence + 1
    assert MidnightEvent(timestamp=2000, sequence=starting_sequence) in engine.event_heap


def test_cancel_removes_all_matching_events_and_preserves_heap_invariant() -> None:
    """_cancel drops matching entries and leaves the heap pop order valid."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine._push(ActionCompleteEvent(timestamp=500, sequence=-1, villager_id="aldric"))
    engine._push(ActionCompleteEvent(timestamp=400, sequence=-1, villager_id="sewalt"))
    engine._push(ActionCompleteEvent(timestamp=300, sequence=-1, villager_id="aldric"))

    engine._cancel(
        lambda event: isinstance(event, ActionCompleteEvent)
        and event.villager_id == "aldric"
    )

    assert engine.event_heap == [ActionCompleteEvent(400, 1, "sewalt")]
    assert heappop(engine.event_heap) == ActionCompleteEvent(400, 1, "sewalt")
