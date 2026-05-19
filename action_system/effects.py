# pyre-strict

"""Immediate and completion action-effect mutations."""

from __future__ import annotations

from action_system.eligibility import CRAFTING_REQUIREMENTS
from action_system import timing
from action_system.types import (
    ActionContext,
    ActionType,
    ExploreResource,
    SelectedAction,
)
from character_canon.types import VillagerId
from villmage.game_types import CraftableItem, ITEM_WEIGHT_G, ItemType, RestingSpotType
from villmage.villager_state import CraftingProgress
from villmage.world_state import DirtinessSource, item_type_to_fuel_type

_EXPLORATION_ITEM_BY_RESOURCE: dict[ExploreResource, ItemType] = {
    ExploreResource.PEACHES: ItemType.PEACH,
    ExploreResource.STICKS: ItemType.STICK,
    ExploreResource.LEAVES: ItemType.LEAVES,
    ExploreResource.LOGS: ItemType.LOG,
    ExploreResource.BOAR: ItemType.CARCASS,
}

_EXPLORATION_CALORIES_PER_HOUR: dict[ExploreResource, float] = {
    ExploreResource.PEACHES: 50.0,
    ExploreResource.STICKS: 50.0,
    ExploreResource.LEAVES: 50.0,
    ExploreResource.LOGS: 100.0,
    ExploreResource.BOAR: 100.0,
}


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


def _require_resource(action: SelectedAction) -> ExploreResource:
    """Return the selected exploration resource, rejecting malformed actions."""

    resource = action.resource
    if resource is None:
        raise ValueError(f"Action {action.action_type!r} requires resource.")
    return resource


def _require_duration_minutes(action: SelectedAction) -> int:
    """Return the selected duration in minutes, rejecting malformed actions."""

    duration_minutes = action.duration_minutes
    if duration_minutes is None:
        raise ValueError(f"Action {action.action_type!r} requires duration_minutes.")
    return duration_minutes


def _require_minutes_to_spend(action: SelectedAction) -> int:
    """Return the selected crafting minutes, rejecting malformed actions."""

    minutes_to_spend = action.minutes_to_spend
    if minutes_to_spend is None:
        raise ValueError(f"Action {action.action_type!r} requires minutes_to_spend.")
    return minutes_to_spend


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


def _charge_activity_calories(calories: float, ctx: ActionContext) -> None:
    """Deduct authored activity calories from villager satiation."""

    ctx.vs.modify_stat("satiation", -calories)


def _reduce_cleanliness(penalty: float, ctx: ActionContext) -> None:
    """Deduct authored cleanliness while preserving stat clamping."""

    ctx.vs.modify_stat("cleanliness", -penalty)


def _crafted_item_type(craftable_item: CraftableItem) -> ItemType:
    """Return the inventory item produced by the selected crafting job."""

    match craftable_item:
        case CraftableItem.SATCHEL:
            return ItemType.SATCHEL
        case CraftableItem.BED_ROLL:
            return ItemType.BED_ROLL
        case CraftableItem.COT:
            return ItemType.COT


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


def _remaining_capacity_kg(ctx: ActionContext) -> float:
    """Return current unused carrying capacity in kilograms."""

    total_inventory_weight_g = sum(
        ITEM_WEIGHT_G[item] * quantity for item, quantity in ctx.vs.inventory.items()
    )
    has_satchel = ctx.vs.inventory.get(ItemType.SATCHEL, 0) >= 1
    carry_capacity_g = 40_000 + (30_000 if has_satchel else 0)
    return (carry_capacity_g - total_inventory_weight_g) / 1000.0


def _complete_explore(
    action: SelectedAction,
    ctx: ActionContext,
    current_time: int,
) -> None:
    """Sample exploration yield, add found items, and charge authored calories."""

    resource = _require_resource(action)
    duration_minutes = _require_duration_minutes(action)
    villager = ctx.canon.get_villager(VillagerId(ctx.villager_id))
    item_type = _EXPLORATION_ITEM_BY_RESOURCE[resource]
    item_weight_kg = ITEM_WEIGHT_G[item_type] / 1000.0
    items_found = timing.sample_exploration_yield(
        effective_mean_minutes=timing.exploration_effective_mean(
            resource=resource,
            profession=villager.profession,
            yield_scale=ctx.multipliers.exploration_yield_scale,
        ),
        work_speed=timing.work_speed_modifier(ctx.vs._compute_health()),
        duration_minutes=duration_minutes,
        item_weight_kg=item_weight_kg,
        remaining_capacity_kg=_remaining_capacity_kg(ctx),
    )
    if items_found > 0:
        ctx.vs.modify_inventory(item_type, items_found)
        if resource is ExploreResource.BOAR:
            for _ in range(items_found):
                ctx.ws.add_carcass(current_time)
    ctx.vs.modify_stat(
        "satiation",
        -_EXPLORATION_CALORIES_PER_HOUR[resource] * (duration_minutes / 60.0),
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


def _complete_scrape_hide(action: SelectedAction, ctx: ActionContext) -> None:
    """Turn raw hides from inventory/base into processed hides in inventory."""

    quantity = _require_quantity(action)
    _deduct_inventory_then_base(ItemType.RAW_HIDE, quantity, ctx)
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, quantity)


def _complete_haul_water(action: SelectedAction, ctx: ActionContext) -> None:
    """Add hauled water to base supply and charge authored calories."""

    del action
    ctx.ws.modify_water(20_000)
    _charge_activity_calories(200.0, ctx)


def _earliest_live_carcass_id(ctx: ActionContext) -> int:
    """Return the oldest tracked live carcass id, or raise if none exist."""

    if not ctx.ws.live_carcasses:
        raise ValueError("No live carcass available to butcher.")
    return ctx.ws.live_carcasses[0].id


def _complete_butcher_carcass(action: SelectedAction, ctx: ActionContext) -> None:
    """Convert the oldest tracked carcass into meat, dirtiness, and stat costs."""

    del action
    ctx.vs.modify_inventory(ItemType.CARCASS, -1)
    ctx.ws.remove_carcass(_earliest_live_carcass_id(ctx))
    ctx.vs.modify_inventory(ItemType.RAW_MEAT, 14)
    _reduce_cleanliness(50.0, ctx)
    _charge_activity_calories(200.0, ctx)


def _complete_clean_camp(action: SelectedAction, ctx: ActionContext) -> None:
    """Clear base dirtiness and apply the proportional cleanliness penalty."""

    del action
    total_dirtiness = ctx.ws.clear_dirtiness()
    _reduce_cleanliness(total_dirtiness / 3.0, ctx)


def _complete_split_logs(action: SelectedAction, ctx: ActionContext) -> None:
    """Turn carried/stored logs into twice as much carried firewood."""

    quantity = _require_quantity(action)
    _deduct_inventory_then_base(ItemType.LOG, quantity, ctx)
    ctx.vs.modify_inventory(ItemType.FIREWOOD, quantity * 2)


def _current_crafting_progress(ctx: ActionContext) -> CraftingProgress:
    """Return the active crafting job, rejecting malformed completion state."""

    crafting_progress = ctx.vs.crafting_in_progress
    if crafting_progress is None:
        raise ValueError("No crafting job is currently in progress.")
    return crafting_progress


def _complete_crafting(action: SelectedAction, ctx: ActionContext) -> None:
    """Advance active crafting progress and award the finished item when done."""

    minutes_to_spend = _require_minutes_to_spend(action)
    crafting_progress = _current_crafting_progress(ctx)
    updated_minutes = crafting_progress.minutes_spent + minutes_to_spend
    if updated_minutes >= crafting_progress.item.total_minutes:
        ctx.vs.set_crafting_state(None)
        ctx.vs.modify_inventory(_crafted_item_type(crafting_progress.item), 1)
        return
    ctx.vs.set_crafting_state(
        CraftingProgress(
            item=crafting_progress.item,
            minutes_spent=updated_minutes,
        )
    )


def _complete_cooking(action: SelectedAction, ctx: ActionContext) -> None:
    """Cook one raw meat into one cooked meat and record cooking scraps."""

    del action
    _deduct_inventory_then_base(ItemType.RAW_MEAT, 1, ctx)
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 1)
    ctx.ws.update_cleanliness_source(DirtinessSource.COOKING_SCRAPS, 1)
    ctx.vs.cooking_paused = False


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


def apply_completion_effect(
    action: SelectedAction,
    ctx: ActionContext,
    current_time: int,
) -> None:
    """Dispatch end-of-action effects for the currently implemented action types."""

    match action.action_type:
        case ActionType.EXPLORE:
            _complete_explore(action, ctx, current_time)
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
        case ActionType.SCRAPE_HIDE:
            _complete_scrape_hide(action, ctx)
        case ActionType.HAUL_WATER:
            _complete_haul_water(action, ctx)
        case ActionType.BUTCHER_CARCASS:
            _complete_butcher_carcass(action, ctx)
        case ActionType.CLEAN_CAMP:
            _complete_clean_camp(action, ctx)
        case ActionType.SPLIT_LOGS:
            _complete_split_logs(action, ctx)
        case ActionType.CRAFT_NEW | ActionType.CONTINUE_CRAFTING:
            _complete_crafting(action, ctx)
        case ActionType.COOK_MEAT | ActionType.FINISH_COOKING:
            _complete_cooking(action, ctx)
        case _:
            return
