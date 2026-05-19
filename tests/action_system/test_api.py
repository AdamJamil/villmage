# pyre-strict

"""Tests for the public action-system API surface."""

from __future__ import annotations

import pytest

from action_system.api import (
    adjust_active_sleep,
    complete_action,
    get_valid_actions,
    start_action,
)
from action_system.types import (
    ActionContext,
    ActionType,
    ActiveSleepSegment,
    AutobalanceMultipliers,
    SelectedAction,
)
from character_canon.canon import CharacterCanon
from villmage.game_types import ItemType
from villmage.villager_state import VillagerState
from villmage.world_state import FuelType, WorldState


class _FixedHealthVillagerState(VillagerState):
    """Villager state test double with a stable authored health value."""

    _health: float

    def __init__(self, villager_id: str, health: float) -> None:
        """Initialize the villager and pin its computed health."""

        super().__init__(villager_id)
        self._health = health

    def _compute_health(self) -> float:
        """Return the fixed authored health used by duration tests."""

        return self._health


class _AlwaysOverEncumberedVillagerState(VillagerState):
    """Villager state test double that always reports over-encumbrance."""

    def is_over_encumbered(self) -> bool:
        """Return the forced over-encumbered test state."""

        return True


def _make_ctx(vs: VillagerState | None = None) -> ActionContext:
    """Build one minimal action context around the provided villager state."""

    villager_state = VillagerState("ivette") if vs is None else vs
    return ActionContext(
        villager_id=villager_state.villager_id,
        canon=CharacterCanon(),
        vs=villager_state,
        all_states={villager_state.villager_id: villager_state},
        ws=WorldState(),
        multipliers=AutobalanceMultipliers(),
    )


def _make_action(action_type: ActionType, **args: object) -> SelectedAction:
    """Build one selected action with the provided action-specific args."""

    return SelectedAction(action_type=action_type, **args)


def test_get_valid_actions_returns_full_split_for_normal_villager() -> None:
    """Normal unencumbered villagers should receive the integrated full menu."""

    ctx = _make_ctx()
    ctx.vs.modify_inventory(ItemType.PEACH, 3)
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)
    ctx.ws.modify_base_item(ItemType.RAW_HIDE, 2)
    ctx.ws.modify_base_item(ItemType.LOG, 5)
    ctx.ws.modify_base_item(ItemType.STICK, 25)
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 4)
    ctx.ws.modify_base_item(ItemType.LEAVES, 500)
    ctx.ws.add_fire_fuel(FuelType.STICK, 5, current_time=0)

    action_list = get_valid_actions(ctx)

    assert len(action_list.main_actions) > 5
    assert len(action_list.crafter_recipes) == 3
    assert all(
        action.action_type is not ActionType.CRAFT_NEW
        for action in action_list.main_actions
    )
    assert all(
        action.action_type is ActionType.CRAFT_NEW
        for action in action_list.crafter_recipes
    )


def test_get_valid_actions_over_encumbered_returns_only_store_actions() -> None:
    """Over-encumbered villagers should only be offered store-in-base actions."""

    ctx = _make_ctx()
    ctx.vs.modify_inventory(ItemType.LOG, 3)
    ctx.vs.modify_inventory(ItemType.RAW_HIDE, 1)

    assert ctx.vs.is_over_encumbered() is True

    action_list = get_valid_actions(ctx)

    assert action_list.crafter_recipes == ()
    assert len(action_list.main_actions) == 2
    assert all(
        action.action_type is ActionType.STORE_IN_BASE
        for action in action_list.main_actions
    )
    assert [action.idx for action in action_list.main_actions] == [1, 2]


def test_get_valid_actions_over_encumbered_with_empty_inventory_returns_empty() -> None:
    """Over-encumbered gating should still return no store actions without inventory."""

    ctx = _make_ctx(_AlwaysOverEncumberedVillagerState("ivette"))

    action_list = get_valid_actions(ctx)

    assert action_list.main_actions == ()
    assert action_list.crafter_recipes == ()


def test_start_action_returns_zero_for_talk_to() -> None:
    """Conversation starts should not schedule a completion event."""

    duration = start_action(
        _make_action(ActionType.TALK_TO, target_villager_id="sewalt"),
        _make_ctx(),
    )

    assert duration == 0


def test_start_action_returns_eat_peach_duration() -> None:
    """Peach-eating duration should follow the authored 1 minute per peach."""

    duration = start_action(
        _make_action(ActionType.EAT_PEACH, quantity=3),
        _make_ctx(_FixedHealthVillagerState("ivette", health=1.0)),
    )

    assert duration == 3


def test_start_action_applies_work_speed_modifier() -> None:
    """Low health should increase authored durations through work-speed scaling."""

    duration = start_action(
        _make_action(ActionType.EAT_PEACH, quantity=2),
        _make_ctx(_FixedHealthVillagerState("ivette", health=0.25)),
    )

    assert duration == 4


def test_start_action_explore_duration_passes_through() -> None:
    """Exploration should keep the villager's chosen duration unchanged."""

    duration = start_action(
        _make_action(
            ActionType.EXPLORE,
            resource=None,
            duration_minutes=120,
        ),
        _make_ctx(_FixedHealthVillagerState("ivette", health=0.1)),
    )

    assert duration == 120


def test_complete_action_delegates_to_effects() -> None:
    """Completion API should apply the integrated effects handler."""

    ctx = _make_ctx()
    ctx.vs.satiation = 0
    ctx.vs.modify_inventory(ItemType.PEACH, 2)

    complete_action(
        _make_action(ActionType.EAT_PEACH, quantity=2),
        ctx,
        current_time=0,
    )

    assert ctx.vs.satiation == 120.0


def test_adjust_active_sleep_applies_elapsed_wakefulness_gain() -> None:
    """Interrupted sleep should restore wakefulness only for the elapsed segment."""

    villager_state = VillagerState("ivette")
    villager_state.wakefulness = 0

    remaining_minutes = adjust_active_sleep(
        villager_state,
        ActiveSleepSegment(total_minutes=480, elapsed_minutes=120, modifier=0.8),
        new_modifier=0.6,
    )

    assert villager_state.wakefulness == pytest.approx((51.0 / 7.0) * 0.8 * 2.0)
    assert remaining_minutes == 360


def test_adjust_active_sleep_caps_wakefulness_at_one_hundred() -> None:
    """Interrupted sleep restoration should still honor the wakefulness cap."""

    villager_state = VillagerState("ivette")
    villager_state.wakefulness = 95.0

    adjust_active_sleep(
        villager_state,
        ActiveSleepSegment(total_minutes=480, elapsed_minutes=420, modifier=1.0),
        new_modifier=0.6,
    )

    assert villager_state.wakefulness == 100.0


def test_adjust_active_sleep_returns_remaining_minutes() -> None:
    """Sleep splitting should always report the unslept remainder."""

    remaining_minutes = adjust_active_sleep(
        VillagerState("ivette"),
        ActiveSleepSegment(total_minutes=300, elapsed_minutes=75, modifier=0.5),
        new_modifier=1.0,
    )

    assert remaining_minutes == 225
