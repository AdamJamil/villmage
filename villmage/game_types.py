# pyre-strict

"""Shared game enums and constants used across leaf subsystems."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


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


class CraftableItem(Enum):
    """Items that can be produced through multi-minute crafting work."""

    SATCHEL = 1
    BED_ROLL = 2
    COT = 3

    @property
    def total_minutes(self) -> int:
        """Return the total crafting time budget for this item."""

        match self:
            case CraftableItem.SATCHEL:
                return 480
            case CraftableItem.BED_ROLL:
                return 300
            case CraftableItem.COT:
                return 960


class ActionCategory(Enum):
    """Categories of villager activity used across simulation subsystems."""

    SLEEPING = 1
    RESTING = 2
    EXPLORING = 3
    HAULING = 4
    CRAFTING = 5
    COOKING = 6
    BUTCHERING = 7
    CLEANING = 8
    WASHING = 9
    SPLITTING_LOGS = 10
    SCRAPING_HIDE = 11
    FIRE_TENDING = 12
    EATING = 13
    DRINKING = 14
    STORING = 15
    TAKING = 16
    PLACING_REST = 17
    CONVERSATION = 18

    @property
    def is_away(self) -> bool:
        """Return whether this action takes the villager away from base."""

        return self in {ActionCategory.EXPLORING, ActionCategory.HAULING}


@dataclass(frozen=True)
class WorldContext:
    """World-level inputs required to compute derived villager stats."""

    base_calories: int
    total_fuel_minutes: int
    villager_count: int
    total_dirtiness: int
    current_game_time: int


StatName = Literal[
    "wakefulness",
    "satiation",
    "hydration",
    "social_joy",
    "connectedness",
    "cleanliness",
]


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
