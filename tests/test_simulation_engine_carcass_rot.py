# pyre-strict

"""Tests for simulation-engine carcass-rot handling."""

from __future__ import annotations

from typing import cast
from unittest.mock import Mock, call

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import EventLogEntry, EventType, VillagerId as MemoryVillagerId
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import CarcassRotEvent
from villmage.game_types import ActionCategory
from villmage.simulation_engine import SimulationEngine
from villmage.villager_state import CurrentAction


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


def _current_action(category: ActionCategory) -> CurrentAction:
    """Construct one minimal current-action snapshot for tests."""

    return CurrentAction(category=category, detail=None, completion_timestamp=0)


def test_handle_carcass_rot_marks_world_state_rotted() -> None:
    """Carcass rot should mutate world state through the dedicated rot API."""

    engine = _build_engine()
    engine.world_state.mark_carcass_rotted = Mock()

    engine._handle_carcass_rot(CarcassRotEvent(500, 3, carcass_id=2))

    engine.world_state.mark_carcass_rotted.assert_called_once_with(2)


def test_handle_carcass_rot_appends_memory_for_base_awake_only() -> None:
    """Only awake villagers at base should observe a carcass rotting."""

    engine = _build_engine()
    engine.current_game_time = 500
    engine.world_state.mark_carcass_rotted = Mock()
    engine.villager_states["aldric"].set_current_action(_current_action(ActionCategory.RESTING))
    engine.villager_states["maren"].set_current_action(_current_action(ActionCategory.SLEEPING))
    engine.villager_states["sewalt"].set_current_action(_current_action(ActionCategory.EXPLORING))
    for villager_id in ["harren", "ivette", "thessia"]:
        engine.villager_states[villager_id].set_current_action(
            _current_action(ActionCategory.EXPLORING)
        )

    engine._handle_carcass_rot(CarcassRotEvent(500, 3, carcass_id=2))

    expected_entry = EventLogEntry(
        game_time=500,
        type=EventType.BASE_EVENT,
        text="Carcass 2 rotted away.",
    )
    assert cast(Mock, engine.memory_system.append_event).call_args_list == [
        call(MemoryVillagerId("aldric"), expected_entry),
    ]


def test_handle_carcass_rot_with_no_base_awake_villagers_appends_no_memory() -> None:
    """No visible observers should leave the memory system untouched."""

    engine = _build_engine()
    engine.world_state.mark_carcass_rotted = Mock()
    for villager_id, villager_state in engine.villager_states.items():
        category = (
            ActionCategory.SLEEPING
            if villager_id in {"aldric", "maren", "sewalt"}
            else ActionCategory.EXPLORING
        )
        villager_state.set_current_action(_current_action(category))

    engine._handle_carcass_rot(CarcassRotEvent(500, 3, carcass_id=2))

    cast(Mock, engine.memory_system.append_event).assert_not_called()


def test_handle_carcass_rot_threads_event_carcass_id_to_world_state() -> None:
    """The event payload carcass id should be passed through unchanged."""

    engine = _build_engine()
    engine.world_state.mark_carcass_rotted = Mock()
    event = CarcassRotEvent(500, 3, carcass_id=7)

    engine._handle_carcass_rot(event)

    engine.world_state.mark_carcass_rotted.assert_called_once_with(7)
