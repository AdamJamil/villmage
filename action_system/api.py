# pyre-strict

"""Public API surface for action-system eligibility, timing, and effects."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from action_system import effects, eligibility, timing
from action_system.types import (
    ActionContext,
    ActionList,
    ActionType,
    ActiveSleepSegment,
    SelectedAction,
    ValidAction,
)
from villmage.villager_state import VillagerState


_DurationFn = Callable[[SelectedAction, ActionContext], float]


def _require_quantity(action: SelectedAction) -> int:
    """Return the action quantity, rejecting malformed actions."""

    quantity = action.quantity
    if quantity is None:
        raise ValueError(f"Action {action.action_type!r} requires quantity.")
    return quantity


def _require_liters(action: SelectedAction) -> int:
    """Return the action liters, rejecting malformed actions."""

    liters = action.liters
    if liters is None:
        raise ValueError(f"Action {action.action_type!r} requires liters.")
    return liters


def _require_duration_minutes(action: SelectedAction) -> int:
    """Return the chosen duration, rejecting malformed actions."""

    duration_minutes = action.duration_minutes
    if duration_minutes is None:
        raise ValueError(f"Action {action.action_type!r} requires duration_minutes.")
    return duration_minutes


def _require_minutes_to_spend(action: SelectedAction) -> int:
    """Return the chosen crafting minutes, rejecting malformed actions."""

    minutes_to_spend = action.minutes_to_spend
    if minutes_to_spend is None:
        raise ValueError(f"Action {action.action_type!r} requires minutes_to_spend.")
    return minutes_to_spend


def _require_hours(action: SelectedAction) -> int:
    """Return the chosen sleep hours, rejecting malformed actions."""

    hours = action.hours
    if hours is None:
        raise ValueError(f"Action {action.action_type!r} requires hours.")
    return hours


def _clean_camp_duration(
    action: SelectedAction,
    ctx: ActionContext,
) -> float:
    """Return the current authored camp-cleaning duration."""

    del action
    return float(ctx.ws.get_total_dirtiness())


def _identity_profession_factor(action: SelectedAction, ctx: ActionContext) -> float:
    """Return the authored profession duration factor for current actions."""

    del action, ctx
    return 1.0


_BASE_DURATION: dict[ActionType, _DurationFn] = {
    ActionType.EAT_PEACH: lambda action, ctx: float(_require_quantity(action)),
    ActionType.EAT_COOKED_MEAT: lambda action, ctx: 14.0 * _require_quantity(action),
    ActionType.DRINK_WATER: lambda action, ctx: float(_require_liters(action)),
    ActionType.TAKE_FROM_BASE: lambda action, ctx: float(_require_quantity(action)),
    ActionType.STORE_IN_BASE: lambda action, ctx: float(_require_quantity(action)),
    ActionType.PLACE_BED_ROLL: lambda action, ctx: 1.0,
    ActionType.PLACE_COT: lambda action, ctx: 1.0,
    ActionType.REST: lambda action, ctx: 60.0,
    ActionType.ADD_STICKS: lambda action, ctx: float(_require_quantity(action)),
    ActionType.ADD_FIREWOOD: lambda action, ctx: float(_require_quantity(action)),
    ActionType.LIGHT_FIRE: lambda action, ctx: 10.0,
    ActionType.EXTINGUISH_FIRE: lambda action, ctx: 1.0,
    ActionType.SCRAPE_HIDE: lambda action, ctx: 60.0 * _require_quantity(action),
    ActionType.HAUL_WATER: lambda action, ctx: 120.0,
    ActionType.BUTCHER_CARCASS: lambda action, ctx: 120.0,
    ActionType.CLEAN_CAMP: _clean_camp_duration,
    ActionType.SPLIT_LOGS: lambda action, ctx: 10.0 * _require_quantity(action),
    ActionType.CRAFT_NEW: lambda action, ctx: float(_require_minutes_to_spend(action)),
    ActionType.CONTINUE_CRAFTING: lambda action, ctx: float(
        _require_minutes_to_spend(action)
    ),
    ActionType.COOK_MEAT: lambda action, ctx: 30.0,
    ActionType.FINISH_COOKING: lambda action, ctx: 30.0,
    ActionType.GO_TO_SLEEP: lambda action, ctx: 60.0 * _require_hours(action),
    ActionType.WASH_UP: lambda action, ctx: 10.0,
}

_PROFESSION_FACTOR: dict[ActionType, _DurationFn] = {
    action_type: _identity_profession_factor
    for action_type in _BASE_DURATION
}


def _assign_indices(actions: list[ValidAction]) -> tuple[ValidAction, ...]:
    """Return one action tuple with 1-based indices on selectable entries."""

    indexed_actions: list[ValidAction] = []
    next_idx = 1
    for action in actions:
        idx = next_idx if action.selectable else None
        indexed_actions.append(replace(action, idx=idx))
        if action.selectable:
            next_idx += 1
    return tuple(indexed_actions)


def get_valid_actions(ctx: ActionContext) -> ActionList:
    """Return the villager's current action menu, honoring over-encumbrance."""

    if not ctx.vs.is_over_encumbered():
        return eligibility.build_action_list(ctx)
    store_actions = [
        action
        for action in eligibility.storage_actions(ctx)
        if action.action_type is ActionType.STORE_IN_BASE
    ]
    return ActionList(
        main_actions=_assign_indices(store_actions),
        crafter_recipes=(),
    )


def start_action(action: SelectedAction, ctx: ActionContext) -> int:
    """Apply start effects and return the authored action duration in minutes."""

    effects.apply_start_effect(action, ctx)
    if action.action_type is ActionType.TALK_TO:
        return 0
    if action.action_type is ActionType.EXPLORE:
        return _require_duration_minutes(action)
    health = ctx.vs._compute_health()
    return timing.apply_duration_modifier(
        base_minutes=_BASE_DURATION[action.action_type](action, ctx),
        work_speed=timing.work_speed_modifier(health),
        profession_factor=_PROFESSION_FACTOR[action.action_type](action, ctx),
    )


def complete_action(
    action: SelectedAction,
    ctx: ActionContext,
    current_time: int,
) -> None:
    """Apply completion effects for one finished non-conversation action."""

    effects.apply_completion_effect(action, ctx, current_time)


def adjust_active_sleep(
    vs: VillagerState,
    segment: ActiveSleepSegment,
    new_modifier: float,
) -> int:
    """Apply elapsed sleep restoration and return the remaining minutes."""

    del new_modifier
    vs.modify_stat(
        "wakefulness",
        (51.0 / 7.0) * segment.modifier * (segment.elapsed_minutes / 60.0),
    )
    return segment.total_minutes - segment.elapsed_minutes
