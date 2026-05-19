# pyre-strict

"""Tests for simulation-engine action-complete dispatch behavior."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock, call

from action_system.types import ActionType, SelectedAction
from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import (
    CompactionReason,
    VillagerId as MemoryVillagerId,
)
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.ai_coordinator.types import ActionSelectionResult
from villmage.events import ActionCompleteEvent
from villmage.game_types import ActionCategory
from villmage.simulation_engine import CrossingType, SimulationEngine
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


def _selected_action(
    action_type: ActionType,
    *,
    target_villager_id: str | None = None,
    hours: int | None = None,
) -> SelectedAction:
    """Build one minimal selected-action payload for the handler tests."""

    return SelectedAction(
        action_type=action_type,
        target_villager_id=target_villager_id,
        hours=hours,
    )


def _action_events(engine: SimulationEngine) -> list[ActionCompleteEvent]:
    """Return only action-complete events from the engine heap."""

    return [
        event for event in engine.event_heap if isinstance(event, ActionCompleteEvent)
    ]


def _current_action() -> CurrentAction:
    """Build one minimal existing-action snapshot for completion-path tests."""

    return CurrentAction(
        category=ActionCategory.RESTING,
        detail=None,
        completion_timestamp=0,
    )


def test_handle_action_complete_initial_event_skips_complete_action() -> None:
    """Initial t=360 dispatches should choose and start an action without completion."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    engine.villager_states["aldric"].set_current_action(None)
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=_selected_action(ActionType.REST),
            thought="Need a breather.",
        )
    )
    engine.action_system.start_action.return_value = 420

    engine._handle_action_complete(ActionCompleteEvent(360, 0, "aldric"))

    engine.action_system.complete_action.assert_not_called()
    engine.action_system.start_action.assert_called_once()


def test_handle_action_complete_normal_flow_sequences_calls_and_schedules() -> None:
    """Normal completion should finish the old action, log thought, and schedule the next."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 480
    engine.villager_states["aldric"].current_action = _current_action()
    engine.villager_states["aldric"].awake_minutes_since_compaction = 100
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=_selected_action(ActionType.REST),
            thought="Rest, then reassess.",
        )
    )
    engine.action_system.start_action.return_value = 540

    manager = Mock()
    manager.attach_mock(engine.action_system.complete_action, "complete_action")
    manager.attach_mock(engine.ai_coordinator.select_action, "select_action")
    manager.attach_mock(engine.memory_system.append_thought, "append_thought")
    manager.attach_mock(engine.action_system.start_action, "start_action")

    engine._handle_action_complete(ActionCompleteEvent(480, 0, "aldric"))

    assert manager.mock_calls == [
        call.complete_action("aldric"),
        call.select_action("aldric", 480),
        call.append_thought(
            MemoryVillagerId("aldric"),
            480,
            "Rest, then reassess.",
        ),
        call.start_action(
            "aldric",
            _selected_action(ActionType.REST),
        ),
    ]
    cast(
        AsyncMock,
        engine.memory_system.trigger_short_term_compaction,
    ).assert_not_called()
    assert _action_events(engine) == [ActionCompleteEvent(540, 0, "aldric")]


def test_handle_action_complete_awake_threshold_triggers_compaction() -> None:
    """BHVR-252 should compact at 4 awake hours before selecting a new action."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 600
    engine.villager_states["aldric"].current_action = _current_action()
    engine.villager_states["aldric"].awake_minutes_since_compaction = 240
    engine.villager_states["aldric"].reset_compaction_counter = Mock()
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=_selected_action(ActionType.REST),
            thought="Time to regroup.",
        )
    )
    engine.action_system.start_action.return_value = 660

    engine._handle_action_complete(ActionCompleteEvent(600, 0, "aldric"))

    cast(
        AsyncMock,
        engine.memory_system.trigger_short_term_compaction,
    ).assert_awaited_once_with(
        MemoryVillagerId("aldric"),
        600,
        CompactionReason.AWAKE_THRESHOLD,
    )
    engine.villager_states["aldric"].reset_compaction_counter.assert_called_once_with()
    engine.action_system.start_action.assert_called_once()


def test_handle_action_complete_sleep_choice_triggers_compaction() -> None:
    """BHVR-251 should compact when sleep is chosen without prior awake-threshold compaction."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 720
    engine.villager_states["aldric"].current_action = _current_action()
    engine.villager_states["aldric"].awake_minutes_since_compaction = 100
    sleep_action = _selected_action(ActionType.GO_TO_SLEEP, hours=8)
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=sleep_action,
            thought="I need sleep.",
        )
    )
    engine.action_system.start_action.return_value = 1200

    engine._handle_action_complete(ActionCompleteEvent(720, 0, "aldric"))

    cast(
        AsyncMock,
        engine.memory_system.trigger_short_term_compaction,
    ).assert_awaited_once_with(
        MemoryVillagerId("aldric"),
        720,
        CompactionReason.SLEEP,
    )
    engine.action_system.start_action.assert_called_once_with("aldric", sleep_action)


def test_handle_action_complete_sleep_choice_skips_duplicate_compaction() -> None:
    """Sleep-start compaction should not run when awake-threshold compaction already did."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 840
    engine.villager_states["aldric"].current_action = _current_action()
    engine.villager_states["aldric"].awake_minutes_since_compaction = 240
    sleep_action = _selected_action(ActionType.GO_TO_SLEEP, hours=6)
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=sleep_action,
            thought="Enough for today.",
        )
    )
    engine.action_system.start_action.return_value = 1200

    engine._handle_action_complete(ActionCompleteEvent(840, 0, "aldric"))

    cast(
        AsyncMock,
        engine.memory_system.trigger_short_term_compaction,
    ).assert_awaited_once_with(
        MemoryVillagerId("aldric"),
        840,
        CompactionReason.AWAKE_THRESHOLD,
    )


def test_handle_action_complete_threshold_crossing_returns_early() -> None:
    """Threshold handling should stop the action cycle before action selection."""

    engine = _build_engine()
    engine.villager_states["aldric"].current_action = _current_action()

    engine._handle_action_complete(
        ActionCompleteEvent(900, 0, "aldric"),
        [CrossingType.HEALTH_ZERO],
    )

    engine.ai_coordinator.select_action.assert_not_called()
    engine.action_system.start_action.assert_not_called()


def test_handle_action_complete_conversation_routes_to_handler() -> None:
    """Talk-to choices should route into the conversation branch instead of start_action."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 960
    engine.villager_states["aldric"].current_action = _current_action()
    engine._handle_conversation_action = Mock()
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=_selected_action(
                ActionType.TALK_TO,
                target_villager_id="sewalt",
            ),
            thought="I should talk to Sewalt.",
        )
    )

    engine._handle_action_complete(ActionCompleteEvent(960, 0, "aldric"))

    engine._handle_conversation_action.assert_called_once_with("aldric", "sewalt")
    engine.action_system.start_action.assert_not_called()
