# pyre-strict

"""Immediate start-effect mutations for selected actions."""

from __future__ import annotations

from action_system.eligibility import CRAFTING_REQUIREMENTS
from action_system.types import ActionContext, ActionType, SelectedAction
from villmage.game_types import CraftableItem, ItemType
from villmage.villager_state import CraftingProgress
from villmage.world_state import item_type_to_fuel_type


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
