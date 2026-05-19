# pyre-strict

"""Tests for simple action-menu eligibility groups."""

from __future__ import annotations

from action_system.eligibility import (
    eating_and_drinking_actions,
    exploration_actions,
    rest_action,
    resting_spot_actions,
    storage_actions,
)
from action_system.types import ActionContext, ActionType, AutobalanceMultipliers, ValidAction
from character_canon.canon import CharacterCanon
from villmage.game_types import ItemType, RestingSpotType
from villmage.villager_state import VillagerState
from villmage.world_state import WorldState


def make_ctx(villager_id: str = "harren") -> ActionContext:
    """Build a minimal authored-villager action context for eligibility tests."""

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


def _get_exploration_action(
    ctx: ActionContext,
    resource_name: str,
) -> ValidAction | None:
    """Return the exploration entry for one prompt-facing resource label."""

    for action in exploration_actions(ctx):
        if action.action_type is not ActionType.EXPLORE:
            continue
        if f"Explore for {resource_name}" in action.prompt_text:
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


def test_exploration_actions_show_profession_free_resources_for_builder() -> None:
    """Peaches, sticks, and leaves always appear for any profession."""

    ctx = make_ctx("harren")

    peaches = _get_exploration_action(ctx, "peaches")
    sticks = _get_exploration_action(ctx, "sticks")
    leaves = _get_exploration_action(ctx, "leaves")

    assert peaches is not None
    assert peaches.selectable is True
    assert sticks is not None
    assert sticks.selectable is True
    assert leaves is not None
    assert leaves.selectable is True


def test_exploration_actions_show_logs_only_for_woodcutter() -> None:
    """Logs are excluded entirely for non-woodcutters and present for woodcutters."""

    for villager_id in ("harren", "sewalt", "thessia", "ivette", "maren"):
        assert _get_exploration_action(make_ctx(villager_id), "logs") is None

    logs = _get_exploration_action(make_ctx("aldric"), "logs")

    assert logs is not None
    assert logs.selectable is True


def test_exploration_actions_show_boar_only_for_hunter() -> None:
    """Boar is excluded entirely for non-hunters and present for hunters."""

    for villager_id in ("harren", "aldric", "thessia", "ivette", "maren"):
        assert _get_exploration_action(make_ctx(villager_id), "boar") is None

    boar = _get_exploration_action(make_ctx("sewalt"), "boar")

    assert boar is not None
    assert boar.selectable is True


def test_exploration_actions_show_non_gatherer_peach_penalty_in_prompt() -> None:
    """Non-gatherers see the 4x peach mean time in the prompt."""

    peaches = _get_exploration_action(make_ctx("harren"), "peaches")

    assert peaches is not None
    assert "40.0 min/item" in peaches.prompt_text


def test_exploration_actions_show_gatherer_peach_mean_in_prompt() -> None:
    """Gatherers see the unpenalized peach mean time in the prompt."""

    peaches = _get_exploration_action(make_ctx("maren"), "peaches")

    assert peaches is not None
    assert "10.0 min/item" in peaches.prompt_text


def test_exploration_actions_show_non_selectable_entry_with_no_space() -> None:
    """No room for one peach keeps the entry visible but non-selectable."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.CARCASS, 1)
    ctx.vs.modify_inventory(ItemType.LOG, 1)
    ctx.vs.modify_inventory(ItemType.STICK, 20)

    peaches = _get_exploration_action(ctx, "peaches")

    assert peaches is not None
    assert peaches.selectable is False
    assert peaches.idx is None
    assert "Cannot perform! No inventory space." in peaches.prompt_text


def test_exploration_actions_are_selectable_with_exact_single_item_capacity() -> None:
    """Exactly enough room for one peach still counts as selectable."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.CARCASS, 1)
    ctx.vs.modify_inventory(ItemType.RAW_MEAT, 19)
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 1)

    peaches = _get_exploration_action(ctx, "peaches")

    assert peaches is not None
    assert peaches.selectable is True


def test_exploration_actions_respect_single_satchel_capacity_bonus() -> None:
    """A satchel raises capacity to 70 kg, allowing sticks that otherwise do not fit."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.CARCASS, 1)
    ctx.vs.modify_inventory(ItemType.STICK, 20)

    sticks_without_satchel = _get_exploration_action(ctx, "sticks")

    assert sticks_without_satchel is not None
    assert sticks_without_satchel.selectable is False

    ctx.vs.modify_inventory(ItemType.SATCHEL, 1)
    sticks_with_satchel = _get_exploration_action(ctx, "sticks")

    assert sticks_with_satchel is not None
    assert sticks_with_satchel.selectable is True


def test_exploration_actions_do_not_stack_multiple_satchels() -> None:
    """Multiple satchels still cap carrying capacity at 70 kg."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.SATCHEL, 2)
    ctx.vs.modify_inventory(ItemType.CARCASS, 1)
    ctx.vs.modify_inventory(ItemType.LOG, 2)
    ctx.vs.modify_inventory(ItemType.STICK, 68)

    sticks = _get_exploration_action(ctx, "sticks")

    assert sticks is not None
    assert sticks.selectable is False


def test_exploration_actions_show_duration_range_for_selectable_entries() -> None:
    """Selectable exploration prompts include the authored duration range."""

    peaches = _get_exploration_action(make_ctx("harren"), "peaches")

    assert peaches is not None
    assert '{"duration_minutes": int (60-240)}' in peaches.prompt_text


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
