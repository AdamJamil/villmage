# pyre-strict

"""Action-menu eligibility builders for simple always-local action groups."""

from __future__ import annotations

from action_system.timing import exploration_effective_mean
from action_system.types import (
    ActionContext,
    ActionType,
    ExploreResource,
    ValidAction,
)
from character_canon.types import Profession, VillagerId
from villmage.game_types import ITEM_WEIGHT_G, ItemType, RestingSpotType


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


def _range_spec(argument_name: str, maximum: int) -> str:
    """Return one prompt argument range in the authored `int (1-x)` format."""

    return f'{{"{argument_name}": int (1-{maximum})}}'


def _item_name(item: ItemType) -> str:
    """Return one item enum as the lower-case prompt-facing item label."""

    return item.name.lower().replace("_", " ")


def _resource_name(resource: ExploreResource) -> str:
    """Return one exploration resource as the lower-case prompt-facing label."""

    return resource.name.lower()


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
