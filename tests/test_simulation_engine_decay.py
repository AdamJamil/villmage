# pyre-strict

"""Tests for simulation-engine decay, thresholds, forced sleep, and death."""

from unittest.mock import Mock, call

from character_canon.canon import CharacterCanon
from conversation_system.conversation import ConversationSystem
from memory_system.memory import MemorySystem
from memory_system.types import EventLogEntry, EventType, VillagerId as MemoryVillagerId
from villmage.ai_coordinator.coordinator import AICoordinator
from villmage.events import ActionCompleteEvent
from villmage.game_types import ActionCategory
from villmage.simulation_engine import CrossingType, SimulationEngine
from villmage.villager_state import CurrentAction, DecayResult


def _build_engine() -> SimulationEngine:
    """Construct one engine with mocked subsystem dependencies."""

    return SimulationEngine(
        character_canon=CharacterCanon(),
        action_system=Mock(),
        ai_coordinator=Mock(spec=AICoordinator),
        conversation_system=Mock(spec=ConversationSystem),
        memory_system=Mock(spec=MemorySystem),
    )


def _current_action(category: ActionCategory) -> CurrentAction:
    """Construct one minimal current-action snapshot for tests."""

    return CurrentAction(category=category, detail=None, completion_timestamp=0)


def _action_events_for(
    engine: SimulationEngine,
    villager_id: str,
) -> list[ActionCompleteEvent]:
    """Return all scheduled action-complete events for one villager."""

    return [
        event
        for event in engine.event_heap
        if isinstance(event, ActionCompleteEvent) and event.villager_id == villager_id
    ]


def test_apply_decay_all_decays_all_living_villagers() -> None:
    """Each living villager should decay once and only crossings should be returned."""

    engine = _build_engine()
    villagers = list(engine.villager_states.items())
    expected: dict[str, list[CrossingType]] = {}
    for index, (villager_id, villager_state) in enumerate(villagers):
        decay_result = DecayResult(
            health_zero=index == 0,
            wakefulness_zero=index in {1, 2},
        )
        if decay_result.health_zero or decay_result.wakefulness_zero:
            crossings: list[CrossingType] = []
            if decay_result.health_zero:
                crossings.append(CrossingType.HEALTH_ZERO)
            if decay_result.wakefulness_zero:
                crossings.append(CrossingType.WAKEFULNESS_ZERO)
            expected[villager_id] = crossings
        villager_state.apply_decay = Mock(return_value=decay_result)

    result = engine._apply_decay_all(2.0)

    assert result == expected
    for _, villager_state in villagers:
        villager_state.apply_decay.assert_called_once_with(2.0)


def test_apply_decay_all_only_calls_living_villagers() -> None:
    """Removed villagers should not be decayed."""

    engine = _build_engine()
    removed_villager = engine.villager_states.pop("aldric")
    removed_villager.apply_decay = Mock(
        return_value=DecayResult(health_zero=False, wakefulness_zero=False)
    )
    for villager_state in engine.villager_states.values():
        villager_state.apply_decay = Mock(
            return_value=DecayResult(health_zero=False, wakefulness_zero=False)
        )

    result = engine._apply_decay_all(2.0)

    assert result == {}
    removed_villager.apply_decay.assert_not_called()
    for villager_state in engine.villager_states.values():
        villager_state.apply_decay.assert_called_once_with(2.0)


def test_apply_thresholds_health_zero_kills() -> None:
    """HEALTH_ZERO should kill and stop further processing."""

    engine = _build_engine()
    engine._kill_villager = Mock()

    result = engine._apply_thresholds("aldric", [CrossingType.HEALTH_ZERO])

    engine._kill_villager.assert_called_once_with("aldric")
    assert result is True


def test_apply_thresholds_wakefulness_zero_force_sleeps() -> None:
    """WAKEFULNESS_ZERO should force sleep and stop further processing."""

    engine = _build_engine()
    engine._force_sleep = Mock()

    result = engine._apply_thresholds("aldric", [CrossingType.WAKEFULNESS_ZERO])

    engine._force_sleep.assert_called_once_with("aldric")
    assert result is True


def test_apply_thresholds_health_zero_takes_precedence() -> None:
    """A dead villager should not also be force-slept."""

    engine = _build_engine()
    engine._kill_villager = Mock()
    engine._force_sleep = Mock()

    result = engine._apply_thresholds(
        "aldric",
        [CrossingType.HEALTH_ZERO, CrossingType.WAKEFULNESS_ZERO],
    )

    engine._kill_villager.assert_called_once_with("aldric")
    engine._force_sleep.assert_not_called()
    assert result is True


def test_apply_thresholds_with_no_crossings_returns_false() -> None:
    """No threshold crossings should leave the villager unchanged."""

    engine = _build_engine()
    engine._kill_villager = Mock()
    engine._force_sleep = Mock()

    result = engine._apply_thresholds("aldric", [])

    engine._kill_villager.assert_not_called()
    engine._force_sleep.assert_not_called()
    assert result is False


def test_force_sleep_cancels_existing_event_and_schedules_new_one() -> None:
    """Forced sleep should replace an old action event with a 4-hour sleep event."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 500
    engine._push(ActionCompleteEvent(timestamp=700, sequence=-1, villager_id="aldric"))

    engine._force_sleep("aldric")

    events = _action_events_for(engine, "aldric")
    assert len(events) == 1
    assert events[0].timestamp == 740
    assert engine.villager_states["aldric"].current_action == CurrentAction(
        category=ActionCategory.SLEEPING,
        detail=None,
        completion_timestamp=740,
    )


def test_force_sleep_with_no_existing_event_still_schedules_sleep() -> None:
    """Forced sleep should still schedule wake-up if the old event was already popped."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine.current_game_time = 1000

    engine._force_sleep("aldric")

    events = _action_events_for(engine, "aldric")
    assert len(events) == 1
    assert events[0].timestamp == 1240


def test_kill_villager_removes_from_villager_states() -> None:
    """Killing a villager should remove them from the living-state table."""

    engine = _build_engine()

    engine._kill_villager("aldric")

    assert "aldric" not in engine.villager_states


def test_kill_villager_cancels_pending_event() -> None:
    """Killing a villager should remove their scheduled action completion."""

    engine = _build_engine()
    engine.event_heap = []
    engine.next_sequence = 0
    engine._push(ActionCompleteEvent(timestamp=700, sequence=-1, villager_id="aldric"))

    engine._kill_villager("aldric")

    assert _action_events_for(engine, "aldric") == []


def test_kill_villager_appends_death_event_for_base_awake_observers() -> None:
    """Only awake villagers at base should observe a villager death."""

    engine = _build_engine()
    engine.current_game_time = 777
    engine.villager_states["maren"].set_current_action(_current_action(ActionCategory.RESTING))
    engine.villager_states["sewalt"].set_current_action(None)
    engine.villager_states["harren"].set_current_action(_current_action(ActionCategory.SLEEPING))
    engine.villager_states["ivette"].set_current_action(_current_action(ActionCategory.EXPLORING))
    engine.villager_states["thessia"].set_current_action(_current_action(ActionCategory.HAULING))

    engine._kill_villager("aldric")

    append_event = engine.memory_system.append_event
    expected_entry = EventLogEntry(
        game_time=777,
        type=EventType.BASE_EVENT,
        text="aldric died.",
    )
    assert sorted(append_event.call_args_list, key=str) == sorted([
        call(MemoryVillagerId("maren"), expected_entry),
        call(MemoryVillagerId("sewalt"), expected_entry),
    ], key=str)
