# pyre-strict

"""Tests for SimulationEngine fire-extinction heap reconciliation."""

from typing import cast
from unittest.mock import Mock

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import FireExtinctionEvent, ScheduledEvent
from villmage.simulation_engine import SimulationEngine
from villmage.world_state import Fire


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


def _fire_events(events: list[ScheduledEvent]) -> list[FireExtinctionEvent]:
    """Return only fire-extinction events from one scheduled-event list."""

    return [event for event in events if isinstance(event, FireExtinctionEvent)]


def test_sync_fire_event_schedules_event_when_fire_is_lit_with_fuel() -> None:
    """A lit fire with an extinction timestamp schedules exactly one heap event."""

    engine = _build_engine()
    engine.event_heap = []
    engine.world_state.fire = Fire(
        lit=True,
        fuel_queue=(),
        extinction_timestamp=720,
    )

    engine._sync_fire_event()

    fire_events = _fire_events(engine.event_heap)
    assert len(fire_events) == 1
    assert fire_events[0].timestamp == 720


def test_sync_fire_event_leaves_no_event_when_fire_is_unlit() -> None:
    """An unlit fire leaves the fire-extinction event absent."""

    engine = _build_engine()
    engine.event_heap = []
    engine.world_state.fire = Fire(
        lit=False,
        fuel_queue=(),
        extinction_timestamp=720,
    )

    engine._sync_fire_event()

    assert _fire_events(engine.event_heap) == []


def test_sync_fire_event_leaves_no_event_when_fire_has_no_timestamp() -> None:
    """A lit fire without queued fuel leaves the fire-extinction event absent."""

    engine = _build_engine()
    engine.event_heap = []
    engine.world_state.fire = Fire(
        lit=True,
        fuel_queue=(),
        extinction_timestamp=None,
    )

    engine._sync_fire_event()

    assert _fire_events(engine.event_heap) == []


def test_sync_fire_event_is_idempotent_without_fire_state_changes() -> None:
    """Repeated reconciliation does not accumulate duplicate fire events."""

    engine = _build_engine()
    engine.event_heap = []
    engine.world_state.fire = Fire(
        lit=True,
        fuel_queue=(),
        extinction_timestamp=720,
    )

    engine._sync_fire_event()
    engine._sync_fire_event()

    fire_events = _fire_events(engine.event_heap)
    assert len(fire_events) == 1
    assert fire_events[0].timestamp == 720


def test_sync_fire_event_replaces_existing_event_when_timestamp_changes() -> None:
    """Reconciliation replaces the old fire-extinction timestamp with the new one."""

    engine = _build_engine()
    engine.event_heap = []
    engine.world_state.fire = Fire(
        lit=True,
        fuel_queue=(),
        extinction_timestamp=600,
    )

    engine._sync_fire_event()
    fire_events = _fire_events(engine.event_heap)
    assert len(fire_events) == 1
    assert fire_events[0].timestamp == 600

    engine.world_state.fire = Fire(
        lit=True,
        fuel_queue=(),
        extinction_timestamp=800,
    )
    engine._sync_fire_event()

    fire_events = _fire_events(engine.event_heap)
    assert len(fire_events) == 1
    assert fire_events[0].timestamp == 800


def test_sync_fire_event_removes_existing_event_after_fire_is_extinguished() -> None:
    """Reconciliation removes a pending fire-extinction event once the fire is out."""

    engine = _build_engine()
    engine.event_heap = [FireExtinctionEvent(600, 99)]
    engine.world_state.fire = Fire(
        lit=False,
        fuel_queue=(),
        extinction_timestamp=None,
    )

    engine._sync_fire_event()

    assert _fire_events(engine.event_heap) == []
