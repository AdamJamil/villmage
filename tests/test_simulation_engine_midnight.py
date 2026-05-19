# pyre-strict

"""Tests for simulation-engine midnight autobalance and compaction handling."""

from __future__ import annotations

import math
from typing import cast
from unittest.mock import AsyncMock, Mock

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import MidnightEvent
from villmage.game_types import ItemType
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


def _midnight_events(engine: SimulationEngine) -> list[MidnightEvent]:
    """Return only midnight events from the engine heap."""

    return [event for event in engine.event_heap if isinstance(event, MidnightEvent)]


def test_compute_autobalance_aggregates_averages_all_living_villagers() -> None:
    """Autobalance aggregates should use the corrected shared-base food formula."""

    engine = _build_engine()
    aldric = engine.villager_states["aldric"]
    maren = engine.villager_states["maren"]
    sewalt = engine.villager_states["sewalt"]
    for villager_id in list(engine.villager_states):
        if villager_id not in {"aldric", "maren", "sewalt"}:
            del engine.villager_states[villager_id]

    aldric.satiation = 1800.0
    maren.satiation = 900.0
    sewalt.satiation = 450.0
    aldric.hydration = 6000.0
    maren.hydration = 3000.0
    sewalt.hydration = 1500.0
    aldric.modify_inventory(ItemType.PEACH, 5)
    maren.modify_inventory(ItemType.COOKED_MEAT, 1)
    sewalt.modify_inventory(ItemType.PEACH, 1)
    sewalt.modify_inventory(ItemType.COOKED_MEAT, 1)
    engine.world_state.modify_base_item(ItemType.PEACH, 10)
    engine.world_state.modify_base_item(ItemType.COOKED_MEAT, 2)

    avg_satiation_pct, avg_hydration_pct, avg_food_safety_days = (
        engine._compute_autobalance_aggregates()
    )

    expected_satiation_pct = ((1800.0 / 1800.0) + (900.0 / 1800.0) + (450.0 / 1800.0)) / 3.0
    expected_hydration_pct = ((6000.0 / 6000.0) + (3000.0 / 6000.0) + (1500.0 / 6000.0)) / 3.0
    base_calories = (10 * 60) + (2 * 800)
    expected_food_safety_days = (
        ((((5 * 60) / 2200.0) + ((base_calories / 3.0) / 2200.0)) / 5.0)
        + ((((1 * 800) / 2200.0) + ((base_calories / 3.0) / 2200.0)) / 5.0)
        + (((((1 * 60) + (1 * 800)) / 2200.0) + ((base_calories / 3.0) / 2200.0)) / 5.0)
    ) / 3.0

    assert math.isclose(avg_satiation_pct, expected_satiation_pct)
    assert math.isclose(avg_hydration_pct, expected_hydration_pct)
    assert math.isclose(avg_food_safety_days, expected_food_safety_days)


def test_compute_autobalance_aggregates_single_villager_uses_full_base_share() -> None:
    """A single villager should receive the full 1/n shared-base calorie term."""

    engine = _build_engine()
    for villager_id in list(engine.villager_states):
        if villager_id != "aldric":
            del engine.villager_states[villager_id]

    aldric = engine.villager_states["aldric"]
    aldric.modify_inventory(ItemType.COOKED_MEAT, 2)
    engine.world_state.modify_base_item(ItemType.PEACH, 5)

    _, _, avg_food_safety_days = engine._compute_autobalance_aggregates()

    expected_food_safety_days = (
        ((2 * 800) / 2200.0) + ((5 * 60) / 2200.0)
    ) / 5.0
    assert math.isclose(avg_food_safety_days, expected_food_safety_days)


def test_handle_midnight_adjusts_autobalance_with_computed_aggregates() -> None:
    """Midnight should pass the aggregate tuple straight into autobalance.adjust."""

    engine = _build_engine()
    engine._apply_decay_all = Mock(return_value={})
    engine._compute_autobalance_aggregates = Mock(return_value=(0.9, 0.4, 0.8))
    engine.autobalance.adjust = Mock()

    engine._handle_midnight()

    engine.autobalance.adjust.assert_called_once_with(0.9, 0.4, 0.8)


def test_handle_midnight_triggers_midnight_compaction_once() -> None:
    """Midnight should trigger one memory-system compaction for the current time."""

    engine = _build_engine()
    engine.current_game_time = 1440
    engine._apply_decay_all = Mock(return_value={})
    engine._compute_autobalance_aggregates = Mock(return_value=(1.0, 1.0, 1.0))
    trigger_midnight_compaction = cast(
        AsyncMock,
        engine.memory_system.trigger_midnight_compaction,
    )

    engine._handle_midnight()

    trigger_midnight_compaction.assert_awaited_once_with(current_game_time=1440)


def test_handle_midnight_schedules_the_next_midnight() -> None:
    """Midnight should schedule exactly one new midnight event 1440 minutes later."""

    engine = _build_engine()
    engine.current_game_time = 1440
    engine.event_heap = []
    engine.next_sequence = 0
    engine._apply_decay_all = Mock(return_value={})
    engine._compute_autobalance_aggregates = Mock(return_value=(1.0, 1.0, 1.0))

    engine._handle_midnight()

    midnight_events = _midnight_events(engine)
    assert len(midnight_events) == 1
    assert midnight_events[0].timestamp == 2880


def test_handle_midnight_applies_decay_before_computing_aggregates() -> None:
    """Midnight aggregates should observe state after threshold-processing decay."""

    engine = _build_engine()
    call_order: list[str] = []

    def _record_decay(_: float) -> dict[str, list[object]]:
        """Record the decay step and return no crossings."""

        call_order.append("decay")
        return {}

    def _record_aggregates() -> tuple[float, float, float]:
        """Record aggregate computation and return one placeholder bundle."""

        call_order.append("aggregates")
        return (1.0, 1.0, 1.0)

    engine._apply_decay_all = Mock(side_effect=_record_decay)
    engine._compute_autobalance_aggregates = Mock(side_effect=_record_aggregates)

    engine._handle_midnight()

    assert call_order == ["decay", "aggregates"]
