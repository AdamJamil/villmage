# pyre-strict

"""Action-menu eligibility builders for simple always-local action groups."""

from __future__ import annotations

from action_system.types import ActionContext, ActionType, ValidAction
from villmage.game_types import ItemType, RestingSpotType


def _range_spec(argument_name: str, maximum: int) -> str:
    """Return one prompt argument range in the authored `int (1-x)` format."""

    return f'{{"{argument_name}": int (1-{maximum})}}'


def _item_name(item: ItemType) -> str:
    """Return one item enum as the lower-case prompt-facing item label."""

    return item.name.lower().replace("_", " ")


def _has_placed_spot(
    ctx: ActionContext,
    resting_spot_type: RestingSpotType,
) -> bool:
    """Return whether this villager already has the given resting spot placed."""

    return (
        ctx.ws.placed_resting_spots.get(ctx.villager_id) is resting_spot_type
        or ctx.vs.sleep_spot_claim is resting_spot_type
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
