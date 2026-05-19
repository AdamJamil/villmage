# pyre-strict

"""Shared game enums and constants used across leaf subsystems."""

from enum import Enum


class ItemType(Enum):
    """All item types that can exist in inventories or storage."""

    PEACH = 1
    CARCASS = 2
    RAW_MEAT = 3
    COOKED_MEAT = 4
    RAW_HIDE = 5
    PROCESSED_HIDE = 6
    LOG = 7
    FIREWOOD = 8
    STICK = 9
    LEAVES = 10
    COT = 11
    BED_ROLL = 12
    SATCHEL = 13


class RestingSpotType(Enum):
    """Placed resting-spot objects that villagers can claim."""

    BED_ROLL = 1
    COT = 2


ITEM_WEIGHT_G: dict[ItemType, int] = {
    ItemType.PEACH: 150,
    ItemType.CARCASS: 30_000,
    ItemType.RAW_MEAT: 500,
    ItemType.COOKED_MEAT: 350,
    ItemType.RAW_HIDE: 5_000,
    ItemType.PROCESSED_HIDE: 5_000,
    ItemType.LOG: 18_000,
    ItemType.FIREWOOD: 8_000,
    ItemType.STICK: 500,
    ItemType.LEAVES: 5,
    ItemType.COT: 0,
    ItemType.BED_ROLL: 0,
    ItemType.SATCHEL: 0,
}
