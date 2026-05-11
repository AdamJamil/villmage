# pyre-strict

"""Action-menu eligibility builders for simple always-local action groups."""

from __future__ import annotations

from dataclasses import replace

from action_system.timing import exploration_effective_mean
from action_system.types import (
    ActionContext,
    ActionList,
    ActionType,
    ExploreResource,
    ValidAction,
)
from character_canon.types import Profession, VillagerId
from villmage.game_types import (
    ActionCategory,
    CraftableItem,
    ITEM_WEIGHT_G,
    ItemType,
    RestingSpotType,
)
from villmage.world_state import FUEL_BURN_DURATION_MINUTES, item_type_to_fuel_type


_EXPLORATION_ITEM_BY_RESOURCE: dict[ExploreResource, ItemType] = {
    ExploreResource.PEACHES: ItemType.PEACH,
    ExploreResource.STICKS: ItemType.STICK,
    ExploreResource.LEAVES: ItemType.LEAVES,
    ExploreResource.LOGS: ItemType.LOG,
    ExploreResource.BOAR: ItemType.CARCASS,
}

_ALL_EXPLORATION_RESOURCES: tuple[ExploreResource, ...] = (
    ExploreResource.PEACHES,
    ExploreResource.STICKS,
    ExploreResource.LEAVES,
    ExploreResource.LOGS,
    ExploreResource.BOAR,
)

_CRAFTABLE_OUTPUT_ITEM: dict[CraftableItem, ItemType] = {
    CraftableItem.SATCHEL: ItemType.SATCHEL,
    CraftableItem.BED_ROLL: ItemType.BED_ROLL,
    CraftableItem.COT: ItemType.COT,
}

CRAFTING_REQUIREMENTS: dict[CraftableItem, tuple[tuple[ItemType, int], ...]] = {
    CraftableItem.SATCHEL: ((ItemType.PROCESSED_HIDE, 1),),
    CraftableItem.BED_ROLL: (
        (ItemType.PROCESSED_HIDE, 1),
        (ItemType.LEAVES, 400),
    ),
    CraftableItem.COT: (
        (ItemType.LOG, 5),
        (ItemType.STICK, 25),
        (ItemType.PROCESSED_HIDE, 4),
        (ItemType.LEAVES, 400),
    ),
}


def _range_spec(argument_name: str, maximum: int) -> str:
    """Return one prompt argument range in the authored `int (1-x)` format."""

    return f'{{"{argument_name}": int (1-{maximum})}}'


def _item_name(item: ItemType) -> str:
    """Return one item enum as the lower-case prompt-facing item label."""

    return item.name.lower().replace("_", " ")


def _resource_name(resource: ExploreResource) -> str:
    """Return one exploration resource as the lower-case prompt-facing label."""

    return resource.name.lower()


def _craftable_name(craftable_item: CraftableItem) -> str:
    """Return one craftable item as the lower-case prompt-facing label."""

    return _item_name(_CRAFTABLE_OUTPUT_ITEM[craftable_item])


def _total_available_item_count(ctx: ActionContext, item: ItemType) -> int:
    """Return the combined inventory-plus-base count for one item type."""

    return ctx.vs.inventory.get(item, 0) + ctx.ws.get_base_item_count(item)


def _remaining_fire_minutes(ctx: ActionContext) -> int:
    """Return the authored fire-minutes snapshot available to eligibility."""

    if ctx.ws.fire.lit:
        extinction_timestamp = ctx.ws.fire.extinction_timestamp
        if extinction_timestamp is None:
            return 0
        return extinction_timestamp
    return sum(
        unit.quantity * FUEL_BURN_DURATION_MINUTES[unit.fuel_type]
        for unit in ctx.ws.fire.fuel_queue
    )


def _max_addable_fuel_units(ctx: ActionContext, item: ItemType) -> int:
    """Return the largest quantity of this fuel that fits under the fire cap."""

    remaining_capacity = 240 - _remaining_fire_minutes(ctx)
    if remaining_capacity <= 0:
        return 0
    fuel_minutes = FUEL_BURN_DURATION_MINUTES[item_type_to_fuel_type(item)]
    return remaining_capacity // fuel_minutes


def _has_placed_spot(
    ctx: ActionContext,
    resting_spot_type: RestingSpotType,
) -> bool:
    """Return whether this villager already has the given resting spot placed."""

    return (
        ctx.ws.placed_resting_spots.get(ctx.villager_id) is resting_spot_type
        or ctx.vs.sleep_spot_claim is resting_spot_type
    )


def _villager_profession(ctx: ActionContext) -> Profession:
    """Return the acting villager's authored profession."""

    villager = ctx.canon.get_villager(VillagerId(ctx.villager_id))
    return villager.profession


def _missing_material_requirements(
    ctx: ActionContext,
    craftable_item: CraftableItem,
) -> list[str]:
    """Return authored missing-material descriptions for one crafting recipe."""

    missing_materials: list[str] = []
    for item, needed_count in CRAFTING_REQUIREMENTS[craftable_item]:
        if _total_available_item_count(ctx, item) < needed_count:
            missing_materials.append(f"{needed_count} {_item_name(item)}")
    return missing_materials


def _hours_text(total_minutes: int) -> str:
    """Return one authored duration in prompt-facing hour text."""

    if total_minutes % 60 == 0:
        total_hours = total_minutes // 60
        unit = "hour" if total_hours == 1 else "hours"
        return f"{total_hours} {unit}"
    return f"{total_minutes / 60:.1f} hours"


def _craft_recipe_action(
    ctx: ActionContext,
    craftable_item: CraftableItem,
) -> ValidAction:
    """Return one always-visible crafter recipe action entry."""

    requirements_text = ", ".join(
        f"{needed_count} {_item_name(item)}"
        for item, needed_count in CRAFTING_REQUIREMENTS[craftable_item]
    )
    prompt_text = (
        f"Craft {_craftable_name(craftable_item)} "
        f"({_hours_text(craftable_item.total_minutes)}; requires {requirements_text})"
    )
    missing_materials = _missing_material_requirements(ctx, craftable_item)
    if len(missing_materials) == 0:
        return ValidAction(
            action_type=ActionType.CRAFT_NEW,
            prompt_text=prompt_text,
            selectable=True,
        )
    return ValidAction(
        action_type=ActionType.CRAFT_NEW,
        prompt_text=(
            f"{prompt_text} "
            f"(Cannot perform! Missing materials: {', '.join(missing_materials)}.)"
        ),
        selectable=False,
    )


def _current_inventory_weight_g(ctx: ActionContext) -> int:
    """Return the total carried inventory weight in grams."""

    return sum(
        ITEM_WEIGHT_G[item] * quantity for item, quantity in ctx.vs.inventory.items()
    )


def _carry_capacity_g(ctx: ActionContext) -> int:
    """Return the villager's current carrying capacity in grams."""

    has_satchel = ctx.vs.inventory.get(ItemType.SATCHEL, 0) >= 1
    return 40_000 + (30_000 if has_satchel else 0)


def _can_access_resource(resource: ExploreResource, profession: Profession) -> bool:
    """Return whether the resource should appear for this profession."""

    if resource is ExploreResource.LOGS:
        return profession is Profession.WOODCUTTER
    if resource is ExploreResource.BOAR:
        return profession is Profession.HUNTER
    return True


def _exploration_action(
    ctx: ActionContext,
    resource: ExploreResource,
    profession: Profession,
) -> ValidAction:
    """Return one exploration entry for an accessible resource."""

    item = _EXPLORATION_ITEM_BY_RESOURCE[resource]
    remaining_capacity_g = _carry_capacity_g(ctx) - _current_inventory_weight_g(ctx)
    effective_mean = exploration_effective_mean(
        resource=resource,
        profession=profession,
        yield_scale=ctx.multipliers.exploration_yield_scale,
    )
    if remaining_capacity_g < ITEM_WEIGHT_G[item]:
        return ValidAction(
            action_type=ActionType.EXPLORE,
            prompt_text=(
                f"Explore for {_resource_name(resource)} "
                f"({effective_mean:.1f} min/item) "
                "(Cannot perform! No inventory space.)"
            ),
            selectable=False,
        )
    return ValidAction(
        action_type=ActionType.EXPLORE,
        prompt_text=(
            f"Explore for {_resource_name(resource)} "
            '{"duration_minutes": int (60-240)} '
            f"({effective_mean:.1f} min/item)"
        ),
        selectable=True,
    )


def eating_and_drinking_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return food and water actions that are currently available at base."""

    actions: list[ValidAction] = []

    peach_count = ctx.vs.inventory.get(ItemType.PEACH, 0)
    if peach_count > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.EAT_PEACH,
                prompt_text=(
                    f'Eat peach {_range_spec("quantity", peach_count)} '
                    "[need 20 to be sated]"
                ),
                selectable=True,
            )
        )

    cooked_meat_count = ctx.vs.inventory.get(ItemType.COOKED_MEAT, 0)
    if cooked_meat_count > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.EAT_COOKED_MEAT,
                prompt_text=(
                    f'Eat cooked meat {_range_spec("quantity", cooked_meat_count)} '
                    "[need 20 to be sated]"
                ),
                selectable=True,
            )
        )

    available_liters = ctx.ws.water_supply_ml // 1000
    if available_liters > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.DRINK_WATER,
                prompt_text=(
                    f'Drink water {_range_spec("liters", available_liters)} '
                    "[need 2 to be hydrated]"
                ),
                selectable=True,
            )
        )

    return actions


def storage_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return take/store actions for all positive-count base and inventory items."""

    actions: list[ValidAction] = []

    for item in ItemType:
        base_count = ctx.ws.base_storage.get(item, 0)
        if base_count > 0:
            actions.append(
                ValidAction(
                    action_type=ActionType.TAKE_FROM_BASE,
                    prompt_text=(
                        "Take item from base "
                        f'{{"item": str ({_item_name(item)}), "quantity": int (1-{base_count})}}'
                    ),
                    selectable=True,
                )
            )

    for item in ItemType:
        inventory_count = ctx.vs.inventory.get(item, 0)
        if inventory_count > 0:
            actions.append(
                ValidAction(
                    action_type=ActionType.STORE_IN_BASE,
                    prompt_text=(
                        "Store item in base "
                        f'{{"item": str ({_item_name(item)}), "quantity": int (1-{inventory_count})}}'
                    ),
                    selectable=True,
                )
            )

    return actions


def exploration_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return accessible exploration entries with prompt and capacity metadata."""

    profession = _villager_profession(ctx)
    actions: list[ValidAction] = []

    for resource in _ALL_EXPLORATION_RESOURCES:
        if not _can_access_resource(resource, profession):
            continue
        actions.append(_exploration_action(ctx, resource, profession))

    return actions


def resting_spot_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return place-and-claim actions for unplaced carried resting spots."""

    actions: list[ValidAction] = []

    if (
        ctx.vs.inventory.get(ItemType.BED_ROLL, 0) > 0
        and not _has_placed_spot(ctx, RestingSpotType.BED_ROLL)
    ):
        actions.append(
            ValidAction(
                action_type=ActionType.PLACE_BED_ROLL,
                prompt_text="Place and claim bed roll (1 minute)",
                selectable=True,
            )
        )

    if (
        ctx.vs.inventory.get(ItemType.COT, 0) > 0
        and not _has_placed_spot(ctx, RestingSpotType.COT)
    ):
        actions.append(
            ValidAction(
                action_type=ActionType.PLACE_COT,
                prompt_text="Place and claim cot (1 minute)",
                selectable=True,
            )
        )

    return actions


def rest_action(ctx: ActionContext) -> list[ValidAction]:
    """Return the always-available authored rest action."""

    del ctx
    return [
        ValidAction(
            action_type=ActionType.REST,
            prompt_text="Sit and relax, to recover energy and improve your mood (1 hour)",
            selectable=True,
        )
    ]


def fire_tending_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return authored fire-tending entries gated by fuel, cap, and lit state."""

    actions: list[ValidAction] = []
    remaining_fire_minutes = _remaining_fire_minutes(ctx)

    for item, action_type in (
        (ItemType.STICK, ActionType.ADD_STICKS),
        (ItemType.FIREWOOD, ActionType.ADD_FIREWOOD),
    ):
        available_count = _total_available_item_count(ctx, item)
        max_addable_count = min(available_count, _max_addable_fuel_units(ctx, item))
        if max_addable_count <= 0:
            continue
        actions.append(
            ValidAction(
                action_type=action_type,
                prompt_text=(
                    f"Add {_item_name(item)} "
                    f'{_range_spec("quantity", max_addable_count)} '
                    f"({remaining_fire_minutes} min remaining)"
                ),
                selectable=True,
            )
        )

    if ctx.ws.is_fire_lit():
        actions.append(
            ValidAction(
                action_type=ActionType.EXTINGUISH_FIRE,
                prompt_text="Extinguish fire",
                selectable=True,
            )
        )
    else:
        actions.append(
            ValidAction(
                action_type=ActionType.LIGHT_FIRE,
                prompt_text="Light fire (10 minutes)",
                selectable=True,
            )
        )

    return actions


def misc_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return authored miscellaneous base actions whose prerequisites are met."""

    actions: list[ValidAction] = []

    raw_hide_count = _total_available_item_count(ctx, ItemType.RAW_HIDE)
    if raw_hide_count > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.SCRAPE_HIDE,
                prompt_text=f'Scrape hide {_range_spec("quantity", raw_hide_count)} (1 hour each)',
                selectable=True,
            )
        )

    actions.append(
        ValidAction(
            action_type=ActionType.HAUL_WATER,
            prompt_text="Haul water (2 hours)",
            selectable=True,
        )
    )

    if len(ctx.ws.live_carcasses) > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.BUTCHER_CARCASS,
                prompt_text="Butcher carcass (2 hours)",
                selectable=True,
            )
        )

    total_dirtiness = ctx.ws.get_total_dirtiness()
    if total_dirtiness > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.CLEAN_CAMP,
                prompt_text=(
                    f"Clean camp ({total_dirtiness} dirtiness, {total_dirtiness} minutes)"
                ),
                selectable=True,
            )
        )

    log_count = _total_available_item_count(ctx, ItemType.LOG)
    if log_count > 0:
        actions.append(
            ValidAction(
                action_type=ActionType.SPLIT_LOGS,
                prompt_text=f'Split logs {_range_spec("quantity", log_count)}',
                selectable=True,
            )
        )

    return actions


def crafting_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return crafter recipes and any authored continue-crafting entry."""

    if _villager_profession(ctx) is not Profession.CRAFTER:
        return []

    actions = [
        _craft_recipe_action(ctx, craftable_item)
        for craftable_item in (
            CraftableItem.SATCHEL,
            CraftableItem.BED_ROLL,
            CraftableItem.COT,
        )
    ]

    crafting_progress = ctx.vs.crafting_in_progress
    if crafting_progress is None:
        return actions

    remaining_minutes = crafting_progress.item.total_minutes - crafting_progress.minutes_spent
    actions.append(
        ValidAction(
            action_type=ActionType.CONTINUE_CRAFTING,
            prompt_text=(
                f"Continue crafting {_craftable_name(crafting_progress.item)} "
                f'{{"minutes_to_spend_now": int (60-{remaining_minutes})}} '
                f"({remaining_minutes} minutes to completion)"
            ),
            selectable=True,
        )
    )
    return actions


def cooking_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return cook-only cooking actions for new or paused cooking work."""

    if _villager_profession(ctx) is not Profession.COOK:
        return []

    fire_lit = ctx.ws.is_fire_lit()
    if ctx.vs.cooking_paused:
        prompt_text = "Finish cooking (30 m)"
        if not fire_lit:
            prompt_text += " (Cannot perform! Fire is out.)"
        return [
            ValidAction(
                action_type=ActionType.FINISH_COOKING,
                prompt_text=prompt_text,
                selectable=fire_lit,
            )
        ]

    if _total_available_item_count(ctx, ItemType.RAW_MEAT) <= 0:
        return []

    prompt_text = "Cook meat (30 m)"
    if not fire_lit:
        prompt_text += " (Cannot perform! Fire is out.)"
    return [
        ValidAction(
            action_type=ActionType.COOK_MEAT,
            prompt_text=prompt_text,
            selectable=fire_lit,
        )
    ]


def sleeping_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return the always-available authored sleeping action."""

    del ctx
    return [
        ValidAction(
            action_type=ActionType.GO_TO_SLEEP,
            prompt_text='Go to sleep {"hours": int (4-12)}',
            selectable=True,
        )
    ]


def washing_action(ctx: ActionContext) -> list[ValidAction]:
    """Return the wash-up action when the base has enough water."""

    if ctx.ws.water_supply_ml < 500:
        return []
    return [
        ValidAction(
            action_type=ActionType.WASH_UP,
            prompt_text="Wash up (500 mL water)",
            selectable=True,
        )
    ]


def _can_talk_to_villager(villager_id: str, ctx: ActionContext) -> bool:
    """Return whether one other living villager is available for conversation."""

    if villager_id == ctx.villager_id:
        return False
    other_state = ctx.all_states.get(villager_id)
    if other_state is None or other_state.wakefulness <= 0:
        return False
    current_action = other_state.current_action
    if current_action is None:
        return True
    return current_action.category not in {
        ActionCategory.EXPLORING,
        ActionCategory.HAULING,
    }


def conversation_actions(ctx: ActionContext) -> list[ValidAction]:
    """Return one talk-to action for each other villager available at base."""

    actions: list[ValidAction] = []
    for villager in ctx.canon.get_all_villagers():
        villager_id = str(villager.id)
        if not _can_talk_to_villager(villager_id, ctx):
            continue
        actions.append(
            ValidAction(
                action_type=ActionType.TALK_TO,
                prompt_text=f'Talk to {villager.name} {{"target_villager_id": "{villager_id}"}}',
                selectable=True,
            )
        )
    return actions


def _with_idx(action: ValidAction, idx: int | None) -> ValidAction:
    """Return one action entry with the requested menu index."""

    return replace(action, idx=idx)


def _assign_indices(
    main_actions: list[ValidAction],
    crafter_recipes: list[ValidAction],
) -> ActionList:
    """Return an action list with globally sequential indices on selectable entries."""

    next_idx = 1
    indexed_main_actions: list[ValidAction] = []
    indexed_crafter_recipes: list[ValidAction] = []

    for action in main_actions:
        if action.selectable:
            indexed_main_actions.append(_with_idx(action, next_idx))
            next_idx += 1
        else:
            indexed_main_actions.append(_with_idx(action, None))

    for action in crafter_recipes:
        if action.selectable:
            indexed_crafter_recipes.append(_with_idx(action, next_idx))
            next_idx += 1
        else:
            indexed_crafter_recipes.append(_with_idx(action, None))

    return ActionList(
        main_actions=tuple(indexed_main_actions),
        crafter_recipes=tuple(indexed_crafter_recipes),
    )


def build_action_list(ctx: ActionContext) -> ActionList:
    """Assemble the full action menu, split recipes, and assign global indices."""

    main_actions: list[ValidAction] = []
    crafter_recipes: list[ValidAction] = []

    for action_group in (
        eating_and_drinking_actions(ctx),
        storage_actions(ctx),
        resting_spot_actions(ctx),
        exploration_actions(ctx),
        rest_action(ctx),
        fire_tending_actions(ctx),
        misc_actions(ctx),
        crafting_actions(ctx),
        cooking_actions(ctx),
        sleeping_actions(ctx),
        washing_action(ctx),
        conversation_actions(ctx),
    ):
        for action in action_group:
            if action.action_type is ActionType.CRAFT_NEW:
                crafter_recipes.append(action)
            else:
                main_actions.append(action)

    return _assign_indices(main_actions, crafter_recipes)
