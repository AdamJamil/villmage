# pyre-strict

"""Tests for shared game enums and item constants."""

from dataclasses import FrozenInstanceError

import pytest

from villmage.game_types import (
    ITEM_WEIGHT_G,
    ActionCategory,
    CraftableItem,
    ItemType,
    RestingSpotType,
    WorldContext,
)


def test_item_type_values_match_spec() -> None:
    """ItemType contains exactly the authored members and values."""

    assert len(ItemType) == 13
    assert ItemType.PEACH.value == 1
    assert ItemType.CARCASS.value == 2
    assert ItemType.RAW_MEAT.value == 3
    assert ItemType.COOKED_MEAT.value == 4
    assert ItemType.RAW_HIDE.value == 5
    assert ItemType.PROCESSED_HIDE.value == 6
    assert ItemType.LOG.value == 7
    assert ItemType.FIREWOOD.value == 8
    assert ItemType.STICK.value == 9
    assert ItemType.LEAVES.value == 10
    assert ItemType.COT.value == 11
    assert ItemType.BED_ROLL.value == 12
    assert ItemType.SATCHEL.value == 13


def test_resting_spot_type_values_match_spec() -> None:
    """RestingSpotType contains exactly the authored members and values."""

    assert len(RestingSpotType) == 2
    assert RestingSpotType.BED_ROLL.value == 1
    assert RestingSpotType.COT.value == 2


def test_item_weight_table_is_complete() -> None:
    """ITEM_WEIGHT_G covers every item type exactly once."""

    assert set(ITEM_WEIGHT_G.keys()) == set(ItemType)


def test_item_weight_values_match_spec() -> None:
    """ITEM_WEIGHT_G values match the authored weights in grams."""

    assert ITEM_WEIGHT_G[ItemType.PEACH] == 150
    assert ITEM_WEIGHT_G[ItemType.CARCASS] == 30_000
    assert ITEM_WEIGHT_G[ItemType.RAW_MEAT] == 500
    assert ITEM_WEIGHT_G[ItemType.COOKED_MEAT] == 350
    assert ITEM_WEIGHT_G[ItemType.RAW_HIDE] == 5_000
    assert ITEM_WEIGHT_G[ItemType.PROCESSED_HIDE] == 5_000
    assert ITEM_WEIGHT_G[ItemType.LOG] == 18_000
    assert ITEM_WEIGHT_G[ItemType.FIREWOOD] == 8_000
    assert ITEM_WEIGHT_G[ItemType.STICK] == 500
    assert ITEM_WEIGHT_G[ItemType.LEAVES] == 5
    assert ITEM_WEIGHT_G[ItemType.COT] == 0
    assert ITEM_WEIGHT_G[ItemType.BED_ROLL] == 0
    assert ITEM_WEIGHT_G[ItemType.SATCHEL] == 0


def test_item_weights_are_non_negative() -> None:
    """ITEM_WEIGHT_G never contains negative weights."""

    assert all(weight >= 0 for weight in ITEM_WEIGHT_G.values())


def test_craftable_item_values_match_spec() -> None:
    """CraftableItem contains exactly the authored members and values."""

    assert len(CraftableItem) == 3
    assert CraftableItem.SATCHEL.value == 1
    assert CraftableItem.BED_ROLL.value == 2
    assert CraftableItem.COT.value == 3


def test_craftable_item_total_minutes_match_spec() -> None:
    """CraftableItem.total_minutes matches the authored crafting budgets."""

    assert CraftableItem.SATCHEL.total_minutes == 480
    assert CraftableItem.BED_ROLL.total_minutes == 300
    assert CraftableItem.COT.total_minutes == 960


def test_action_category_values_match_spec() -> None:
    """ActionCategory contains exactly the authored members and values."""

    assert len(ActionCategory) == 18
    assert ActionCategory.SLEEPING.value == 1
    assert ActionCategory.RESTING.value == 2
    assert ActionCategory.EXPLORING.value == 3
    assert ActionCategory.HAULING.value == 4
    assert ActionCategory.CRAFTING.value == 5
    assert ActionCategory.COOKING.value == 6
    assert ActionCategory.BUTCHERING.value == 7
    assert ActionCategory.CLEANING.value == 8
    assert ActionCategory.WASHING.value == 9
    assert ActionCategory.SPLITTING_LOGS.value == 10
    assert ActionCategory.SCRAPING_HIDE.value == 11
    assert ActionCategory.FIRE_TENDING.value == 12
    assert ActionCategory.EATING.value == 13
    assert ActionCategory.DRINKING.value == 14
    assert ActionCategory.STORING.value == 15
    assert ActionCategory.TAKING.value == 16
    assert ActionCategory.PLACING_REST.value == 17
    assert ActionCategory.CONVERSATION.value == 18


def test_action_category_is_away_true_cases() -> None:
    """Only exploring and hauling are treated as away-from-base actions."""

    assert ActionCategory.EXPLORING.is_away is True
    assert ActionCategory.HAULING.is_away is True


def test_action_category_is_away_false_for_all_other_categories() -> None:
    """Every non-away action category reports False for is_away."""

    away_categories = {ActionCategory.EXPLORING, ActionCategory.HAULING}

    for category in ActionCategory:
        if category not in away_categories:
            assert category.is_away is False


def test_world_context_construction_and_field_access() -> None:
    """WorldContext stores its five fields and remains immutable."""

    context = WorldContext(
        base_calories=11,
        total_fuel_minutes=22,
        villager_count=33,
        total_dirtiness=44,
        current_game_time=55,
    )

    assert context.base_calories == 11
    assert context.total_fuel_minutes == 22
    assert context.villager_count == 33
    assert context.total_dirtiness == 44
    assert context.current_game_time == 55

    with pytest.raises(FrozenInstanceError):
        context.base_calories = 99


def test_world_context_field_types_are_ints() -> None:
    """WorldContext runtime values are plain ints for all five fields."""

    context = WorldContext(
        base_calories=0,
        total_fuel_minutes=0,
        villager_count=0,
        total_dirtiness=0,
        current_game_time=0,
    )

    assert isinstance(context.base_calories, int)
    assert isinstance(context.total_fuel_minutes, int)
    assert isinstance(context.villager_count, int)
    assert isinstance(context.total_dirtiness, int)
    assert isinstance(context.current_game_time, int)
