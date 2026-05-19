# pyre-strict

"""Tests for simple action-menu eligibility groups."""

from __future__ import annotations

from action_system.eligibility import (
    cooking_actions,
    crafting_actions,
    eating_and_drinking_actions,
    exploration_actions,
    fire_tending_actions,
    misc_actions,
    rest_action,
    resting_spot_actions,
    storage_actions,
)
from action_system.types import ActionContext, ActionType, AutobalanceMultipliers, ValidAction
from character_canon.canon import CharacterCanon
from villmage.game_types import CraftableItem, ItemType, RestingSpotType
from villmage.villager_state import CraftingProgress, VillagerState
from villmage.world_state import DirtinessSource, FuelType, WorldState


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


def _get_action_with_text(
    actions: list[ValidAction],
    action_type: ActionType,
    text: str,
) -> ValidAction | None:
    """Return the first action of one type whose prompt contains the given text."""

    for action in actions:
        if action.action_type is action_type and text in action.prompt_text:
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


def test_fire_tending_actions_show_light_fire_without_fuel() -> None:
    """An unlit fire still shows light-fire even when no fuel can be added."""

    actions = fire_tending_actions(make_ctx())

    assert _get_action(actions, ActionType.ADD_STICKS) is None
    assert _get_action(actions, ActionType.ADD_FIREWOOD) is None
    assert _get_action(actions, ActionType.LIGHT_FIRE) is not None
    assert _get_action(actions, ActionType.EXTINGUISH_FIRE) is None


def test_fire_tending_actions_add_sticks_from_inventory_when_available() -> None:
    """Stick quantity uses the available total when the cap leaves room."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.STICK, 5)

    actions = fire_tending_actions(ctx)
    add_sticks = _get_action(actions, ActionType.ADD_STICKS)

    assert add_sticks is not None
    assert "1-5" in add_sticks.prompt_text
    assert _get_action(actions, ActionType.LIGHT_FIRE) is not None
    assert _get_action(actions, ActionType.ADD_FIREWOOD) is None


def test_fire_tending_actions_add_firewood_from_base_when_fire_is_lit() -> None:
    """Firewood availability may come entirely from base storage."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.FIREWOOD, 3)
    ctx.ws.add_fire_fuel(FuelType.FIREWOOD, 3, current_time=0)
    ctx.ws.light_fire(current_time=0)

    actions = fire_tending_actions(ctx)
    add_firewood = _get_action(actions, ActionType.ADD_FIREWOOD)

    assert add_firewood is not None
    assert "1-3" in add_firewood.prompt_text
    assert _get_action(actions, ActionType.EXTINGUISH_FIRE) is not None
    assert _get_action(actions, ActionType.LIGHT_FIRE) is None


def test_fire_tending_actions_limit_added_firewood_by_four_hour_cap() -> None:
    """Fuel-add ranges stop at the largest quantity that fits under the cap."""

    ctx = make_ctx()
    ctx.ws.add_fire_fuel(FuelType.FIREWOOD, 10, current_time=0)
    ctx.ws.light_fire(current_time=0)
    ctx.ws.modify_base_item(ItemType.FIREWOOD, 12)

    add_firewood = _get_action(fire_tending_actions(ctx), ActionType.ADD_FIREWOOD)

    assert add_firewood is not None
    assert "1-2" in add_firewood.prompt_text
    assert "1-12" not in add_firewood.prompt_text


def test_fire_tending_actions_omit_fuel_adds_when_fire_is_already_at_cap() -> None:
    """No fuel-add actions appear when remaining burn time is already full."""

    ctx = make_ctx()
    ctx.ws.add_fire_fuel(FuelType.FIREWOOD, 12, current_time=0)
    ctx.ws.light_fire(current_time=0)
    ctx.vs.modify_inventory(ItemType.STICK, 5)
    ctx.ws.modify_base_item(ItemType.FIREWOOD, 5)

    actions = fire_tending_actions(ctx)

    assert _get_action(actions, ActionType.ADD_STICKS) is None
    assert _get_action(actions, ActionType.ADD_FIREWOOD) is None


def test_fire_tending_actions_show_remaining_minutes_inline_for_fuel_adds() -> None:
    """Fuel-add prompts include the current remaining-burn figure inline."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.STICK, 2)

    add_sticks = _get_action(fire_tending_actions(ctx), ActionType.ADD_STICKS)

    assert add_sticks is not None
    assert "0" in add_sticks.prompt_text


def test_misc_actions_add_scrape_hide_for_inventory_raw_hide() -> None:
    """Inventory raw hide produces one scrape-hide quantity range."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.RAW_HIDE, 2)

    scrape_hide = _get_action(misc_actions(ctx), ActionType.SCRAPE_HIDE)

    assert scrape_hide is not None
    assert "1-2" in scrape_hide.prompt_text


def test_misc_actions_add_scrape_hide_for_base_raw_hide() -> None:
    """Base-only raw hide still produces the combined-count scrape action."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.RAW_HIDE, 3)

    scrape_hide = _get_action(misc_actions(ctx), ActionType.SCRAPE_HIDE)

    assert scrape_hide is not None
    assert "1-3" in scrape_hide.prompt_text


def test_misc_actions_always_include_haul_water() -> None:
    """Haul water has no prerequisite and always appears."""

    assert _get_action(misc_actions(make_ctx()), ActionType.HAUL_WATER) is not None


def test_misc_actions_only_include_butcher_when_live_carcass_exists() -> None:
    """Butchering requires at least one tracked live carcass."""

    ctx = make_ctx()

    assert _get_action(misc_actions(ctx), ActionType.BUTCHER_CARCASS) is None

    ctx.ws.add_carcass(0)

    assert _get_action(misc_actions(ctx), ActionType.BUTCHER_CARCASS) is not None


def test_misc_actions_only_include_clean_camp_when_dirty() -> None:
    """Clean camp appears only when the camp has positive total dirtiness."""

    ctx = make_ctx()

    assert _get_action(misc_actions(ctx), ActionType.CLEAN_CAMP) is None

    ctx.ws.update_cleanliness_source(DirtinessSource.CARCASS_REMAINS, 1)
    clean_camp = _get_action(misc_actions(ctx), ActionType.CLEAN_CAMP)

    assert clean_camp is not None
    assert "30" in clean_camp.prompt_text


def test_misc_actions_only_include_split_logs_when_logs_exist() -> None:
    """Log splitting requires at least one combined inventory/base log."""

    ctx = make_ctx()

    assert _get_action(misc_actions(ctx), ActionType.SPLIT_LOGS) is None

    ctx.ws.modify_base_item(ItemType.LOG, 2)
    split_logs = _get_action(misc_actions(ctx), ActionType.SPLIT_LOGS)

    assert split_logs is not None
    assert "1-2" in split_logs.prompt_text


def test_crafting_actions_returns_empty_for_non_crafter() -> None:
    """Crafting is completely hidden from non-CRAFTER villagers."""

    assert crafting_actions(make_ctx("harren")) == []


def test_crafting_actions_show_all_recipes_for_crafter_without_materials() -> None:
    """All three recipes stay visible even when none are currently makeable."""

    actions = crafting_actions(make_ctx("ivette"))

    satchel = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft satchel")
    bed_roll = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft bed roll")
    cot = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft cot")

    assert satchel is not None
    assert satchel.selectable is False
    assert "Missing materials" in satchel.prompt_text
    assert bed_roll is not None
    assert bed_roll.selectable is False
    assert cot is not None
    assert cot.selectable is False


def test_crafting_actions_make_only_satchel_selectable_when_only_hide_is_available() -> None:
    """One processed hide unlocks satchel but not the more expensive recipes."""

    ctx = make_ctx("ivette")
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)

    actions = crafting_actions(ctx)

    satchel = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft satchel")
    bed_roll = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft bed roll")
    cot = _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft cot")

    assert satchel is not None
    assert satchel.selectable is True
    assert bed_roll is not None
    assert bed_roll.selectable is False
    assert cot is not None
    assert cot.selectable is False


def test_crafting_actions_make_bed_roll_selectable_when_hide_and_leaves_are_available() -> None:
    """Bed roll becomes selectable only when both authored materials are present."""

    ctx = make_ctx("ivette")
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)
    ctx.vs.modify_inventory(ItemType.LEAVES, 400)

    bed_roll = _get_action_with_text(
        crafting_actions(ctx),
        ActionType.CRAFT_NEW,
        "Craft bed roll",
    )

    assert bed_roll is not None
    assert bed_roll.selectable is True


def test_crafting_actions_make_cot_selectable_only_when_all_materials_are_present() -> None:
    """Cot requires logs, sticks, processed hide, and leaves simultaneously."""

    ctx = make_ctx("ivette")
    ctx.vs.modify_inventory(ItemType.LOG, 5)
    ctx.vs.modify_inventory(ItemType.STICK, 25)
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 4)
    ctx.vs.modify_inventory(ItemType.LEAVES, 400)

    cot = _get_action_with_text(crafting_actions(ctx), ActionType.CRAFT_NEW, "Craft cot")

    assert cot is not None
    assert cot.selectable is True


def test_crafting_actions_pool_materials_across_inventory_and_base() -> None:
    """Crafting material checks use the combined inventory-plus-base total."""

    ctx = make_ctx("ivette")
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 1)

    satchel = _get_action_with_text(
        crafting_actions(ctx),
        ActionType.CRAFT_NEW,
        "Craft satchel",
    )

    assert satchel is not None
    assert satchel.selectable is True


def test_crafting_actions_add_continue_crafting_without_hiding_recipes() -> None:
    """Continue crafting appears alongside the always-visible recipe entries."""

    ctx = make_ctx("ivette")
    ctx.vs.set_crafting_state(
        CraftingProgress(item=CraftableItem.BED_ROLL, minutes_spent=120)
    )

    actions = crafting_actions(ctx)
    continue_crafting = _get_action(actions, ActionType.CONTINUE_CRAFTING)

    assert continue_crafting is not None
    assert continue_crafting.selectable is True
    assert "60-180" in continue_crafting.prompt_text
    assert _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft satchel") is not None
    assert _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft bed roll") is not None
    assert _get_action_with_text(actions, ActionType.CRAFT_NEW, "Craft cot") is not None


def test_cooking_actions_returns_empty_for_non_cook() -> None:
    """Cooking is completely hidden from non-COOK villagers."""

    assert cooking_actions(make_ctx("ivette")) == []


def test_cooking_actions_return_empty_without_raw_meat() -> None:
    """No raw meat means there is nothing to cook even if the fire is lit."""

    ctx = make_ctx("thessia")
    ctx.ws.add_fire_fuel(FuelType.STICK, 1, current_time=0)
    ctx.ws.light_fire(current_time=0)

    assert cooking_actions(ctx) == []


def test_cooking_actions_show_selectable_cook_meat_with_raw_meat_and_lit_fire() -> None:
    """Raw meat plus a lit fire produces one selectable cook action."""

    ctx = make_ctx("thessia")
    ctx.vs.modify_inventory(ItemType.RAW_MEAT, 2)
    ctx.ws.add_fire_fuel(FuelType.STICK, 30, current_time=0)
    ctx.ws.light_fire(current_time=0)

    cook_meat = _get_action(cooking_actions(ctx), ActionType.COOK_MEAT)

    assert cook_meat is not None
    assert cook_meat.selectable is True
    assert "30 m" in cook_meat.prompt_text


def test_cooking_actions_show_non_selectable_cook_meat_when_fire_is_out() -> None:
    """Cook-meat stays visible but disabled when the fire is out."""

    ctx = make_ctx("thessia")
    ctx.vs.modify_inventory(ItemType.RAW_MEAT, 2)

    cook_meat = _get_action(cooking_actions(ctx), ActionType.COOK_MEAT)

    assert cook_meat is not None
    assert cook_meat.selectable is False


def test_cooking_actions_show_finish_cooking_instead_of_cook_meat_when_paused_and_relit() -> None:
    """Paused cooking replaces new cooking once the fire has been relit."""

    ctx = make_ctx("thessia")
    ctx.vs.modify_inventory(ItemType.RAW_MEAT, 2)
    ctx.vs.cooking_paused = True
    ctx.ws.add_fire_fuel(FuelType.STICK, 30, current_time=0)
    ctx.ws.light_fire(current_time=0)

    actions = cooking_actions(ctx)

    finish_cooking = _get_action(actions, ActionType.FINISH_COOKING)
    assert finish_cooking is not None
    assert finish_cooking.selectable is True
    assert _get_action(actions, ActionType.COOK_MEAT) is None


def test_cooking_actions_show_non_selectable_finish_cooking_when_fire_is_still_out() -> None:
    """Paused cooking remains visible but disabled until the fire is relit."""

    ctx = make_ctx("thessia")
    ctx.vs.cooking_paused = True

    finish_cooking = _get_action(cooking_actions(ctx), ActionType.FINISH_COOKING)

    assert finish_cooking is not None
    assert finish_cooking.selectable is False
