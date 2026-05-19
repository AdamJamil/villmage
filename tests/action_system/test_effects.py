# pyre-strict

"""Tests for immediate action start effects."""

from __future__ import annotations

from copy import deepcopy

import pytest

from action_system.effects import apply_start_effect
from action_system.types import ActionContext, ActionType, AutobalanceMultipliers, SelectedAction
from character_canon.canon import CharacterCanon
from villmage.game_types import CraftableItem, ItemType
from villmage.villager_state import CraftingProgress, VillagerState
from villmage.world_state import FuelType, WorldState


def make_ctx(villager_id: str = "ivette") -> ActionContext:
    """Build a minimal action context for one authored villager."""

    villager_state = VillagerState(villager_id)
    return ActionContext(
        villager_id=villager_id,
        canon=CharacterCanon(),
        vs=villager_state,
        all_states={villager_id: villager_state},
        ws=WorldState(),
        multipliers=AutobalanceMultipliers(),
    )


def make_action(action_type: ActionType, **args: object) -> SelectedAction:
    """Build one selected action with the provided authored args."""

    return SelectedAction(action_type=action_type, **args)


def test_craft_new_consumes_materials_from_inventory_only() -> None:
    """Crafting should spend inventory materials before touching base storage."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 2)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.PROCESSED_HIDE] == 1
    assert ctx.vs.crafting_in_progress == CraftingProgress(
        item=CraftableItem.SATCHEL,
        minutes_spent=0,
    )


def test_craft_new_consumes_materials_from_base_when_inventory_is_empty() -> None:
    """Crafting should fall back to base storage when inventory lacks materials."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 1)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    assert ctx.ws.base_storage[ItemType.PROCESSED_HIDE] == 0


def test_craft_new_splits_material_consumption_across_inventory_and_base() -> None:
    """Crafting should exhaust inventory first and then consume the remainder from base."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)
    ctx.ws.modify_base_item(ItemType.LOG, 5)
    ctx.ws.modify_base_item(ItemType.STICK, 25)
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 3)
    ctx.ws.modify_base_item(ItemType.LEAVES, 400)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.COT,
        ),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.PROCESSED_HIDE] == 0
    assert ctx.ws.base_storage[ItemType.PROCESSED_HIDE] == 0


def test_craft_new_raises_when_materials_are_insufficient() -> None:
    """Crafting should reject malformed starts that lack enough materials."""

    ctx = make_ctx()

    with pytest.raises(ValueError):
        apply_start_effect(
            make_action(
                ActionType.CRAFT_NEW,
                craftable_item=CraftableItem.SATCHEL,
            ),
            ctx,
        )


def test_craft_new_sets_crafting_in_progress() -> None:
    """Crafting should start a fresh progress snapshot at zero minutes."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    crafting = ctx.vs.crafting_in_progress
    assert crafting is not None
    assert crafting.item is CraftableItem.SATCHEL
    assert crafting.minutes_spent == 0


def test_continue_crafting_is_a_no_op() -> None:
    """Continuing a job should not spend materials or mutate progress."""

    ctx = make_ctx()
    ctx.vs.set_crafting_state(
        CraftingProgress(item=CraftableItem.SATCHEL, minutes_spent=60)
    )
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 2)
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 3)
    before_vs = deepcopy(ctx.vs)
    before_ws = deepcopy(ctx.ws)

    apply_start_effect(make_action(ActionType.CONTINUE_CRAFTING), ctx)

    assert ctx.vs.__dict__ == before_vs.__dict__
    assert ctx.ws.__dict__ == before_ws.__dict__


def test_add_sticks_prefers_inventory_over_base() -> None:
    """Adding sticks should consume carried sticks before stored sticks."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.STICK, 3)
    ctx.ws.modify_base_item(ItemType.STICK, 5)

    apply_start_effect(
        make_action(ActionType.ADD_STICKS, quantity=4),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.STICK] == 0
    assert ctx.ws.base_storage[ItemType.STICK] == 4
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.STICK
    assert ctx.ws.fire.fuel_queue[-1].quantity == 4


def test_add_sticks_consumes_from_base_when_inventory_is_empty() -> None:
    """Adding sticks should fall back to base storage when needed."""

    ctx = make_ctx("harren")
    ctx.ws.modify_base_item(ItemType.STICK, 5)

    apply_start_effect(
        make_action(ActionType.ADD_STICKS, quantity=3),
        ctx,
    )

    assert ctx.ws.base_storage[ItemType.STICK] == 2
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.STICK
    assert ctx.ws.fire.fuel_queue[-1].quantity == 3


def test_add_firewood_uses_inventory_first() -> None:
    """Adding firewood should use the same inventory-first deduction rule."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.FIREWOOD, 1)
    ctx.ws.modify_base_item(ItemType.FIREWOOD, 4)

    apply_start_effect(
        make_action(ActionType.ADD_FIREWOOD, quantity=3),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.FIREWOOD] == 0
    assert ctx.ws.base_storage[ItemType.FIREWOOD] == 2
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.FIREWOOD
    assert ctx.ws.fire.fuel_queue[-1].quantity == 3


def test_other_action_types_have_no_start_effect() -> None:
    """Non-start-effect actions should leave villager and world state unchanged."""

    no_op_actions = (
        ActionType.EAT_PEACH,
        ActionType.EXPLORE,
        ActionType.REST,
        ActionType.GO_TO_SLEEP,
        ActionType.TALK_TO,
    )

    for action_type in no_op_actions:
        ctx = make_ctx("harren")
        ctx.vs.modify_inventory(ItemType.PEACH, 2)
        ctx.ws.modify_base_item(ItemType.STICK, 3)
        before_vs = deepcopy(ctx.vs)
        before_ws = deepcopy(ctx.ws)

        apply_start_effect(make_action(action_type), ctx)

        assert ctx.vs.__dict__ == before_vs.__dict__
        assert ctx.ws.__dict__ == before_ws.__dict__
