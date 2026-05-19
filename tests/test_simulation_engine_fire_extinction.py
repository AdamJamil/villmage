# pyre-strict

"""Tests for simulation-engine fire-extinction handling."""

from __future__ import annotations

from typing import cast
from unittest.mock import Mock, call

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from villmage.ai_coordinator.coordinator import AICoordinator
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


def test_handle_fire_extinction_marks_world_state_extinguished() -> None:
    """Fire extinction should mark the world-state fire as naturally burned out."""

    engine = _build_engine()
    engine.world_state.mark_fire_extinguished = Mock()

    engine._handle_fire_extinction()

    engine.world_state.mark_fire_extinguished.assert_called_once_with()


def test_handle_fire_extinction_adjusts_only_sleeping_villagers() -> None:
    """Only sleeping villagers should have active sleep resplit after burnout."""

    engine = _build_engine()
    engine.villager_states["aldric"].set_current_action(
        _current_action(ActionCategory.SLEEPING)
    )
    engine.villager_states["maren"].set_current_action(
        _current_action(ActionCategory.EXPLORING)
    )
    engine.villager_states["sewalt"].set_current_action(
        _current_action(ActionCategory.SLEEPING)
    )

    engine._handle_fire_extinction()

    adjust_active_sleep = cast(Mock, engine.action_system.adjust_active_sleep)
    assert adjust_active_sleep.call_args_list == [
        call("aldric"),
        call("sewalt"),
    ]


def test_handle_fire_extinction_with_no_sleepers_makes_no_adjustments() -> None:
    """No active sleepers should leave the action system untouched."""

    engine = _build_engine()
    for villager_state in engine.villager_states.values():
        villager_state.set_current_action(_current_action(ActionCategory.HAULING))

    engine._handle_fire_extinction()

    cast(Mock, engine.action_system.adjust_active_sleep).assert_not_called()


def test_handle_fire_extinction_adjusts_all_sleeping_villagers() -> None:
    """Every living villager should be adjusted when all are sleeping."""

    engine = _build_engine()
    for villager_state in engine.villager_states.values():
        villager_state.set_current_action(_current_action(ActionCategory.SLEEPING))

    engine._handle_fire_extinction()

    adjust_active_sleep = cast(Mock, engine.action_system.adjust_active_sleep)
    assert adjust_active_sleep.call_count == 6
    assert adjust_active_sleep.call_args_list == [
        call(villager_id) for villager_id in engine.villager_states
    ]
