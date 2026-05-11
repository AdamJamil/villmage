# pyre-strict

"""Tests for the SimulationEngine main event loop."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

from action_system.types import ActionType, SelectedAction
from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import (
    MemorySnapshot,
    VillagerId as MemoryVillagerId,
)
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.ai_coordinator.types import ActionSelectionResult
from villmage.events import (
    ActionCompleteEvent,
    CarcassRotEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
)
from villmage.simulation_engine import SimulationEngine
from villmage.world_state import Fire, FuelType


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


def _selected_rest_action() -> SelectedAction:
    """Build one minimal non-conversation, non-sleep action payload."""

    return SelectedAction(action_type=ActionType.REST)


def test_run_terminates_when_only_recurring_events_remain() -> None:
    """The loop should stop once the last action event is gone."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    for villager_id in list(engine.villager_states):
        if villager_id != "aldric":
            del engine.villager_states[villager_id]
    engine._push(ActionCompleteEvent(timestamp=360, sequence=-1, villager_id="aldric"))
    engine._push(MidnightEvent(timestamp=1440, sequence=-1))
    engine._push(CheckpointEvent(timestamp=540, sequence=-1))
    engine._apply_decay_all = Mock(return_value={})

    def _kill_last_villager(
        event: ActionCompleteEvent,
        crossings: list[object] | None = None,
    ) -> None:
        """Simulate the final villager dying during action handling."""

        del crossings
        engine.villager_states.clear()

    engine._handle_action_complete = Mock(side_effect=_kill_last_villager)
    engine._handle_midnight = Mock()
    engine._handle_checkpoint = Mock()
    engine._sync_fire_event = Mock()

    engine.run()

    engine._handle_action_complete.assert_called_once()
    engine._handle_midnight.assert_not_called()
    engine._handle_checkpoint.assert_not_called()
    assert len(engine.event_heap) == 2
    assert any(isinstance(event, MidnightEvent) for event in engine.event_heap)
    assert any(isinstance(event, CheckpointEvent) for event in engine.event_heap)


def test_run_dispatches_each_event_type_to_its_handler() -> None:
    """The loop should route each scheduled event to the matching handler."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    engine.villager_states.clear()
    engine._push(FireExtinctionEvent(timestamp=360, sequence=-1))
    engine._push(CarcassRotEvent(timestamp=420, sequence=-1, carcass_id=7))
    engine._push(MidnightEvent(timestamp=480, sequence=-1))
    engine._push(CheckpointEvent(timestamp=540, sequence=-1))
    engine._push(ActionCompleteEvent(timestamp=600, sequence=-1, villager_id="aldric"))
    engine._apply_decay_all = Mock(return_value={})
    engine._handle_fire_extinction = Mock()
    engine._handle_carcass_rot = Mock()
    engine._handle_midnight = Mock()
    engine._handle_checkpoint = Mock()
    engine._handle_action_complete = Mock()
    engine._sync_fire_event = Mock()

    engine.run()

    engine._handle_fire_extinction.assert_called_once_with()
    engine._handle_carcass_rot.assert_called_once_with(
        CarcassRotEvent(timestamp=420, sequence=1, carcass_id=7)
    )
    engine._handle_midnight.assert_called_once_with()
    engine._handle_checkpoint.assert_called_once_with()
    engine._handle_action_complete.assert_called_once_with(
        ActionCompleteEvent(timestamp=600, sequence=4, villager_id="aldric"),
        [],
    )


def test_run_calls_sync_fire_event_after_every_dispatch() -> None:
    """Every popped event should be followed by exactly one fire reconciliation."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    engine.villager_states.clear()
    engine._push(FireExtinctionEvent(timestamp=360, sequence=-1))
    engine._push(CarcassRotEvent(timestamp=420, sequence=-1, carcass_id=2))
    engine._push(ActionCompleteEvent(timestamp=480, sequence=-1, villager_id="aldric"))
    engine._apply_decay_all = Mock(return_value={})
    engine._handle_fire_extinction = Mock()
    engine._handle_carcass_rot = Mock()
    engine._handle_action_complete = Mock()
    engine._sync_fire_event = Mock()

    engine.run()

    assert engine._sync_fire_event.call_count == 3


def test_run_advances_game_time_monotonically() -> None:
    """Handlers should only observe a non-decreasing current game time."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    engine.villager_states.clear()
    engine._push(FireExtinctionEvent(timestamp=360, sequence=-1))
    engine._push(CheckpointEvent(timestamp=540, sequence=-1))
    engine._push(ActionCompleteEvent(timestamp=720, sequence=-1, villager_id="aldric"))
    engine._apply_decay_all = Mock(return_value={})
    observed_times: list[int] = []

    def _record_fire() -> None:
        """Capture current game time during fire dispatch."""

        observed_times.append(engine.current_game_time)

    def _record_checkpoint() -> None:
        """Capture current game time during checkpoint dispatch."""

        observed_times.append(engine.current_game_time)

    def _record_action(
        event: ActionCompleteEvent,
        crossings: list[object] | None = None,
    ) -> None:
        """Capture current game time during action dispatch."""

        del event
        del crossings
        observed_times.append(engine.current_game_time)

    engine._handle_fire_extinction = Mock(side_effect=_record_fire)
    engine._handle_checkpoint = Mock(side_effect=_record_checkpoint)
    engine._handle_action_complete = Mock(side_effect=_record_action)
    engine._sync_fire_event = Mock()

    engine.run()

    assert observed_times == sorted(observed_times)


def test_run_calls_apply_decay_all_with_elapsed_hours_between_events() -> None:
    """Decay should use the elapsed wall-clock interval from the last dispatch."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 360
    engine.villager_states.clear()
    engine._push(ActionCompleteEvent(timestamp=360, sequence=-1, villager_id="aldric"))
    engine._push(ActionCompleteEvent(timestamp=480, sequence=-1, villager_id="aldric"))
    elapsed_hours: list[float] = []
    dispatch_count = 0

    def _record_decay(hours: float) -> dict[str, list[object]]:
        """Capture each elapsed-hours value used for decay."""

        elapsed_hours.append(hours)
        return {}

    def _handle_action(
        event: ActionCompleteEvent,
        crossings: list[object] | None = None,
    ) -> None:
        """Stop the loop after the second action dispatch."""

        del event
        del crossings
        nonlocal dispatch_count
        dispatch_count += 1
        if dispatch_count == 2:
            engine.villager_states.clear()

    engine._apply_decay_all = Mock(side_effect=_record_decay)
    engine._handle_action_complete = Mock(side_effect=_handle_action)
    engine._sync_fire_event = Mock()

    engine.run()

    assert elapsed_hours == [0.0, 2.0]


def test_run_integration_advances_through_midnight_and_checkpoints(
    tmp_path: Path,
) -> None:
    """One live run should coordinate action, checkpoint, fire, rot, and midnight flow."""

    engine = _build_engine()
    engine.checkpoint_dir = tmp_path
    engine.current_game_time = 360
    engine.event_heap = []
    engine.next_sequence = 0
    for villager_id in list(engine.villager_states):
        if villager_id != "aldric":
            del engine.villager_states[villager_id]
    engine._push(ActionCompleteEvent(timestamp=360, sequence=-1, villager_id="aldric"))
    engine._push(MidnightEvent(timestamp=1440, sequence=-1))
    engine._push(CheckpointEvent(timestamp=540, sequence=-1))
    carcass_id = engine.world_state.add_carcass(arrival_timestamp=400)
    engine._push(CarcassRotEvent(timestamp=900, sequence=-1, carcass_id=carcass_id))
    engine.world_state.add_fire_fuel(FuelType.FIREWOOD, quantity=2, current_time=360)
    engine.world_state.light_fire(current_time=360)
    engine.ai_coordinator.select_action = Mock(
        return_value=ActionSelectionResult(
            action=_selected_rest_action(),
            thought="Keep going.",
        )
    )
    engine.action_system.start_action = Mock(
        side_effect=lambda _villager_id, _action: engine.current_game_time + 60
    )
    trigger_midnight_compaction = cast(
        AsyncMock,
        engine.memory_system.trigger_midnight_compaction,
    )
    engine.memory_system.get_full_state.return_value = MemorySnapshot(
        active_context_log={},
        short_term_memories={},
        medium_term_memories={},
        long_term_memories={},
        relationships={},
        last_long_term_compaction_day=0,
    )
    real_handle_midnight = engine._handle_midnight
    real_handle_checkpoint = engine._handle_checkpoint
    real_handle_fire_extinction = engine._handle_fire_extinction
    real_handle_carcass_rot = engine._handle_carcass_rot
    real_handle_action_complete = engine._handle_action_complete
    real_sync_fire_event = engine._sync_fire_event
    midnight_times: list[int] = []
    checkpoint_times: list[int] = []
    fire_times: list[int] = []
    carcass_rot_times: list[int] = []
    action_times: list[int] = []
    sync_fire_call_count = 0

    def _wrapped_midnight() -> None:
        """Record midnight dispatch and terminate the run after the first midnight."""

        midnight_times.append(engine.current_game_time)
        real_handle_midnight()
        engine._cancel(lambda event: isinstance(event, ActionCompleteEvent))
        engine.villager_states.clear()

    def _wrapped_checkpoint() -> None:
        """Record checkpoint dispatches while preserving real behavior."""

        checkpoint_times.append(engine.current_game_time)
        real_handle_checkpoint()

    def _wrapped_fire_extinction() -> None:
        """Record fire-extinction dispatches while preserving real behavior."""

        fire_times.append(engine.current_game_time)
        real_handle_fire_extinction()

    def _wrapped_carcass_rot(event: CarcassRotEvent) -> None:
        """Record carcass-rot dispatches while preserving real behavior."""

        carcass_rot_times.append(engine.current_game_time)
        real_handle_carcass_rot(event)

    def _wrapped_action_complete(
        event: ActionCompleteEvent,
        crossings: list[object] | None = None,
    ) -> None:
        """Record action dispatches while preserving real behavior."""

        action_times.append(engine.current_game_time)
        real_handle_action_complete(event, crossings)

    def _wrapped_sync_fire_event() -> None:
        """Record the per-dispatch fire-sync call count."""

        nonlocal sync_fire_call_count
        sync_fire_call_count += 1
        real_sync_fire_event()

    engine._handle_midnight = Mock(side_effect=_wrapped_midnight)
    engine._handle_checkpoint = Mock(side_effect=_wrapped_checkpoint)
    engine._handle_fire_extinction = Mock(side_effect=_wrapped_fire_extinction)
    engine._handle_carcass_rot = Mock(side_effect=_wrapped_carcass_rot)
    engine._handle_action_complete = Mock(side_effect=_wrapped_action_complete)
    engine._sync_fire_event = Mock(side_effect=_wrapped_sync_fire_event)

    engine.run()

    assert midnight_times == [1440]
    trigger_midnight_compaction.assert_awaited_once_with(current_game_time=1440)
    assert any(
        isinstance(event, MidnightEvent) and event.timestamp == 2880
        for event in engine.event_heap
    )
    assert checkpoint_times == [540, 720, 900, 1080, 1260]
    assert fire_times == [400]
    assert carcass_rot_times == [900]
    total_dispatch_count = (
        len(midnight_times)
        + len(checkpoint_times)
        + len(fire_times)
        + len(carcass_rot_times)
        + len(action_times)
    )
    assert sync_fire_call_count >= total_dispatch_count
    assert any(
        isinstance(event, CheckpointEvent) and event.timestamp == 1440
        for event in engine.event_heap
    )
    engine.memory_system.append_thought.assert_any_call(
        MemoryVillagerId("aldric"),
        360,
        "Keep going.",
    )
