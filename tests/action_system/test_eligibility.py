# pyre-strict

"""Tests for simple action-menu eligibility groups."""

from __future__ import annotations

from action_system.eligibility import (
    eating_and_drinking_actions,
    rest_action,
    resting_spot_actions,
    storage_actions,
)
from action_system.types import ActionContext, ActionType, AutobalanceMultipliers, ValidAction
from character_canon.canon import CharacterCanon
from villmage.game_types import ItemType, RestingSpotType
from villmage.villager_state import VillagerState
from villmage.world_state import WorldState


def make_ctx() -> ActionContext:
    """Build a minimal builder-villager action context for eligibility tests."""

    villager_id = "harren"
    villager_state = VillagerState(villager_id)
    return ActionContext(
        villager_id=villager_id,
        canon=CharacterCanon(),
        vs=villager_state,
        all_states={villager_id: villager_state},
        ws=WorldState(),
        multipliers=AutobalanceMultipliers(),
    )


def _get_action(
    actions: list[ValidAction],
    action_type: ActionType,
) -> ValidAction | None:
    """Return the first action of the requested type, if present."""

    for action in actions:
        if action.action_type is action_type:
            return action
    return None


def test_rest_action_is_always_present() -> None:
    """Rest is always available as one selectable action."""

    actions = rest_action(make_ctx())

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.REST
    assert actions[0].selectable is True


def test_eating_and_drinking_actions_returns_empty_with_no_food_or_water() -> None:
    """No inventory food and no water means no eating or drinking actions."""

    assert eating_and_drinking_actions(make_ctx()) == []


def test_eating_and_drinking_actions_adds_peach_action_for_inventory_peaches() -> None:
    """Peach quantity range reflects the inventory count."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PEACH, 3)

    actions = eating_and_drinking_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.EAT_PEACH
    assert actions[0].selectable is True
    assert "1-3" in actions[0].prompt_text


def test_eating_and_drinking_actions_adds_cooked_meat_action_for_inventory_meat() -> None:
    """Cooked-meat quantity range reflects the inventory count."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 2)

    actions = eating_and_drinking_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.EAT_COOKED_MEAT
    assert "1-2" in actions[0].prompt_text


def test_eating_and_drinking_actions_returns_both_food_entries_when_both_exist() -> None:
    """Each food type produces its own action entry."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PEACH, 1)
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 1)

    actions = eating_and_drinking_actions(ctx)

    assert {action.action_type for action in actions} == {
        ActionType.EAT_PEACH,
        ActionType.EAT_COOKED_MEAT,
    }


def test_eating_and_drinking_actions_adds_drink_water_for_available_liters() -> None:
    """Water quantity range uses floor(base water liters)."""

    ctx = make_ctx()
    ctx.ws.water_supply_ml = 3000

    action = _get_action(eating_and_drinking_actions(ctx), ActionType.DRINK_WATER)

    assert action is not None
    assert "1-3" in action.prompt_text


def test_eating_and_drinking_actions_floors_fractional_liters() -> None:
    """Partial liters do not increase the maximum drinkable quantity."""

    ctx = make_ctx()
    ctx.ws.water_supply_ml = 1500

    action = _get_action(eating_and_drinking_actions(ctx), ActionType.DRINK_WATER)

    assert action is not None
    assert "1-1" in action.prompt_text


def test_eating_and_drinking_actions_omits_drink_water_when_supply_is_zero() -> None:
    """Zero stored water produces no drink action."""

    action = _get_action(eating_and_drinking_actions(make_ctx()), ActionType.DRINK_WATER)

    assert action is None


def test_storage_actions_returns_empty_with_no_base_or_inventory_items() -> None:
    """Storage actions require at least one positive-count item somewhere."""

    assert storage_actions(make_ctx()) == []


def test_storage_actions_add_take_action_for_base_item() -> None:
    """Base items produce take actions with the authored quantity range."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.PEACH, 5)

    actions = storage_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.TAKE_FROM_BASE
    assert "1-5" in actions[0].prompt_text
    assert not any(action.action_type is ActionType.STORE_IN_BASE for action in actions)


def test_storage_actions_add_store_action_for_inventory_item() -> None:
    """Inventory items produce store actions with the authored quantity range."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.RAW_HIDE, 2)

    actions = storage_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.STORE_IN_BASE
    assert "1-2" in actions[0].prompt_text
    assert not any(action.action_type is ActionType.TAKE_FROM_BASE for action in actions)


def test_storage_actions_return_one_action_per_distinct_item_in_each_group() -> None:
    """Base and inventory items each produce one action per item type."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.PEACH, 1)
    ctx.ws.modify_base_item(ItemType.LOG, 2)
    ctx.vs.modify_inventory(ItemType.STICK, 3)
    ctx.vs.modify_inventory(ItemType.LEAVES, 4)

    actions = storage_actions(ctx)

    take_actions = [action for action in actions if action.action_type is ActionType.TAKE_FROM_BASE]
    store_actions = [action for action in actions if action.action_type is ActionType.STORE_IN_BASE]

    assert len(take_actions) == 2
    assert len(store_actions) == 2


def test_resting_spot_actions_returns_empty_with_no_spots_or_inventory() -> None:
    """No carried resting spots means no place-and-claim actions."""

    assert resting_spot_actions(make_ctx()) == []


def test_resting_spot_actions_add_bed_roll_action_when_unplaced() -> None:
    """An unplaced carried bed roll can be placed and claimed."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.BED_ROLL, 1)

    actions = resting_spot_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.PLACE_BED_ROLL
    assert actions[0].selectable is True
    assert "1 minute" in actions[0].prompt_text


def test_resting_spot_actions_add_cot_action_when_unplaced() -> None:
    """An unplaced carried cot can be placed and claimed."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.COT, 1)

    actions = resting_spot_actions(ctx)

    assert len(actions) == 1
    assert actions[0].action_type is ActionType.PLACE_COT
    assert actions[0].selectable is True
    assert "1 minute" in actions[0].prompt_text


def test_resting_spot_actions_omit_bed_roll_when_this_villager_already_placed_one() -> None:
    """A villager cannot place the same resting-spot type twice."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.BED_ROLL, 1)
    ctx.ws.place_resting_spot(ctx.villager_id, RestingSpotType.BED_ROLL)

    action = _get_action(resting_spot_actions(ctx), ActionType.PLACE_BED_ROLL)

    assert action is None


def test_resting_spot_actions_allow_both_spot_types_when_neither_is_placed() -> None:
    """Both carried spot types remain eligible until one is actually placed."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.BED_ROLL, 1)
    ctx.vs.modify_inventory(ItemType.COT, 1)

    assert {
        action.action_type for action in resting_spot_actions(ctx)
    } == {
        ActionType.PLACE_BED_ROLL,
        ActionType.PLACE_COT,
    }
