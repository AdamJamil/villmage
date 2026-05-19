# pyre-strict

"""Immediate and completion action-effect mutations."""

from __future__ import annotations

from action_system.eligibility import CRAFTING_REQUIREMENTS
from action_system.types import ActionContext, ActionType, SelectedAction
from villmage.game_types import CraftableItem, ItemType, RestingSpotType
from villmage.villager_state import CraftingProgress
from villmage.world_state import DirtinessSource, item_type_to_fuel_type


def _require_quantity(action: SelectedAction) -> int:
    """Return the selected quantity, rejecting malformed actions."""

    quantity = action.quantity
    if quantity is None:
        raise ValueError(f"Action {action.action_type!r} requires quantity.")
    return quantity


def _require_craftable_item(action: SelectedAction) -> CraftableItem:
    """Return the selected crafting target, rejecting malformed actions."""

    craftable_item = action.craftable_item
    if craftable_item is None:
        raise ValueError(f"Action {action.action_type!r} requires craftable_item.")
    return craftable_item


def _require_hours(action: SelectedAction) -> int:
    """Return the selected sleep hours, rejecting malformed actions."""

    hours = action.hours
    if hours is None:
        raise ValueError(f"Action {action.action_type!r} requires hours.")
    return hours


def _require_liters(action: SelectedAction) -> int:
    """Return the selected liter count, rejecting malformed actions."""

    liters = action.liters
    if liters is None:
        raise ValueError(f"Action {action.action_type!r} requires liters.")
    return liters


def _deduct_inventory_then_base(
    item: ItemType,
    quantity: int,
    ctx: ActionContext,
) -> None:
    """Remove items from inventory first, then base storage, or raise."""

    inventory_count = ctx.vs.inventory.get(item, 0)
    base_count = ctx.ws.get_base_item_count(item)
    if inventory_count + base_count < quantity:
        raise ValueError(f"Insufficient {item!r}: need {quantity}.")

    inventory_to_remove = min(inventory_count, quantity)
    base_to_remove = quantity - inventory_to_remove
    if inventory_to_remove > 0:
        ctx.vs.modify_inventory(item, -inventory_to_remove)
    if base_to_remove > 0:
        ctx.ws.modify_base_item(item, -base_to_remove)


def _start_craft_new(action: SelectedAction, ctx: ActionContext) -> None:
    """Consume recipe materials and create a fresh crafting-progress record."""

    craftable_item = _require_craftable_item(action)
    for item, quantity in CRAFTING_REQUIREMENTS[craftable_item]:
        _deduct_inventory_then_base(item=item, quantity=quantity, ctx=ctx)
    ctx.vs.set_crafting_state(
        CraftingProgress(item=craftable_item, minutes_spent=0)
    )


def _start_add_fuel(
    action: SelectedAction,
    fuel_item: ItemType,
    ctx: ActionContext,
) -> None:
    """Deduct one selected fuel batch and append it to the fire queue."""

    quantity = _require_quantity(action)
    _deduct_inventory_then_base(item=fuel_item, quantity=quantity, ctx=ctx)
    ctx.ws.add_fire_fuel(
        fuel_type=item_type_to_fuel_type(fuel_item),
        quantity=quantity,
        current_time=0,
    )


def _sleep_modifier(ctx: ActionContext) -> float:
    """Return the authored wakefulness modifier for current sleep conditions."""

    sleep_spot = ctx.vs.sleep_spot_claim
    if sleep_spot is RestingSpotType.COT:
        return 1.0
    if sleep_spot is RestingSpotType.BED_ROLL:
        return 0.8 if ctx.ws.is_fire_lit() else 0.65
    if ctx.ws.is_fire_lit():
        return 0.6
    return 0.5


def _complete_eat_peach(action: SelectedAction, ctx: ActionContext) -> None:
    """Consume peaches and restore authored satiation calories."""

    quantity = _require_quantity(action)
    ctx.vs.modify_inventory(ItemType.PEACH, -quantity)
    ctx.vs.modify_stat(
        "satiation",
        60.0 * quantity * ctx.multipliers.satiation_restore_scale,
    )


def _complete_eat_cooked_meat(action: SelectedAction, ctx: ActionContext) -> None:
    """Consume cooked meat, restore satiation, and add meat-scraps dirtiness."""

    quantity = _require_quantity(action)
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, -quantity)
    ctx.vs.modify_stat(
        "satiation",
        800.0 * quantity * ctx.multipliers.satiation_restore_scale,
    )
    ctx.ws.update_cleanliness_source(DirtinessSource.MEAT_SCRAPS, quantity)


def _complete_drink_water(action: SelectedAction, ctx: ActionContext) -> None:
    """Consume base water and restore authored hydration milliliters."""

    liters = _require_liters(action)
    ctx.ws.modify_water(-(liters * 1000))
    ctx.vs.modify_stat(
        "hydration",
        1000.0 * liters * ctx.multipliers.hydration_restore_scale,
    )


def _complete_rest(action: SelectedAction, ctx: ActionContext) -> None:
    """Leave rest completion to Simulation Engine's timestamp handling."""

    del action, ctx


def _complete_go_to_sleep(action: SelectedAction, ctx: ActionContext) -> None:
    """Restore wakefulness using the current sleeping-condition modifier."""

    hours = _require_hours(action)
    ctx.vs.modify_stat("wakefulness", (51.0 / 7.0) * _sleep_modifier(ctx) * hours)


def _complete_place_resting_spot(
    item_type: ItemType,
    spot_type: RestingSpotType,
    ctx: ActionContext,
) -> None:
    """Move one carried resting spot into the placed-spot world record."""

    ctx.vs.modify_inventory(item_type, -1)
    ctx.ws.place_resting_spot(ctx.villager_id, spot_type)
    ctx.vs.set_sleep_spot(spot_type)


def _complete_wash_up(action: SelectedAction, ctx: ActionContext) -> None:
    """Consume wash water and reset villager cleanliness to full."""

    del action
    ctx.ws.modify_water(-500)
    ctx.vs.modify_stat("cleanliness", 100.0 - ctx.vs.cleanliness)


def apply_start_effect(action: SelectedAction, ctx: ActionContext) -> None:
    """Dispatch start-effect handler for the given action type."""

    match action.action_type:
        case ActionType.CRAFT_NEW:
            _start_craft_new(action, ctx)
        case ActionType.ADD_STICKS:
            _start_add_fuel(action, ItemType.STICK, ctx)
        case ActionType.ADD_FIREWOOD:
            _start_add_fuel(action, ItemType.FIREWOOD, ctx)
        case _:
            return


def apply_completion_effect(action: SelectedAction, ctx: ActionContext) -> None:
    """Dispatch end-of-action effects for the currently implemented action types."""

    match action.action_type:
        case ActionType.EAT_PEACH:
            _complete_eat_peach(action, ctx)
        case ActionType.EAT_COOKED_MEAT:
            _complete_eat_cooked_meat(action, ctx)
        case ActionType.DRINK_WATER:
            _complete_drink_water(action, ctx)
        case ActionType.REST:
            _complete_rest(action, ctx)
        case ActionType.GO_TO_SLEEP:
            _complete_go_to_sleep(action, ctx)
        case ActionType.PLACE_BED_ROLL:
            _complete_place_resting_spot(
                item_type=ItemType.BED_ROLL,
                spot_type=RestingSpotType.BED_ROLL,
                ctx=ctx,
            )
        case ActionType.PLACE_COT:
            _complete_place_resting_spot(
                item_type=ItemType.COT,
                spot_type=RestingSpotType.COT,
                ctx=ctx,
            )
        case ActionType.WASH_UP:
            _complete_wash_up(action, ctx)
        case _:
            return
