# pyre-strict

"""Tests for shared game enums and item constants."""

from villmage.game_types import ITEM_WEIGHT_G, ItemType, RestingSpotType


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
