# pyre-strict

"""Shared mutable world state and its internal typed records."""

from dataclasses import dataclass
from enum import Enum

from villmage.game_types import ItemType, RestingSpotType


class FuelType(Enum):
    """Internal fuel categories accepted by the fire queue."""

    STICK = 1
    FIREWOOD = 2


FUEL_BURN_DURATION_MINUTES: dict[FuelType, int] = {
    FuelType.STICK: 1,
    FuelType.FIREWOOD: 20,
}


@dataclass(frozen=True)
class FuelUnit:
    """One queued batch of homogeneous fuel."""

    fuel_type: FuelType
    quantity: int


class DirtinessSource(Enum):
    """Internal sources that contribute to camp dirtiness."""

    CARCASS_REMAINS = 1
    MEAT_SCRAPS = 2
    COOKING_SCRAPS = 3


DIRTINESS_PENALTY: dict[DirtinessSource, int] = {
    DirtinessSource.CARCASS_REMAINS: 30,
    DirtinessSource.MEAT_SCRAPS: 5,
    DirtinessSource.COOKING_SCRAPS: 3,
}


@dataclass(frozen=True)
class Carcass:
    """A tracked carcass and the game-minute when it arrived."""

    id: int
    arrival_timestamp: int


@dataclass(frozen=True)
class Fire:
    """Immutable fire snapshot stored by WorldState."""

    lit: bool
    fuel_queue: tuple[FuelUnit, ...]
    extinction_timestamp: int | None


def item_type_to_fuel_type(item: ItemType) -> FuelType:
    """Convert a burnable item type into its internal fuel type."""

    if item is ItemType.STICK:
        return FuelType.STICK
    if item is ItemType.FIREWOOD:
        return FuelType.FIREWOOD
    raise ValueError(f"Item type {item!r} cannot be used as fuel.")


class WorldState:
    """Mutable container for shared camp state."""

    base_storage: dict[ItemType, int]
    water_supply_ml: int
    fire: Fire
    dirtiness_counts: dict[DirtinessSource, int]
    placed_resting_spots: dict[str, RestingSpotType]
    live_carcasses: list[Carcass]
    next_carcass_id: int

    def __init__(self) -> None:
        """Initialize the spec-defined empty starting state."""

        self.base_storage = {}
        self.water_supply_ml = 0
        self.fire = Fire(
            lit=False,
            fuel_queue=(),
            extinction_timestamp=None,
        )
        self.dirtiness_counts = {}
        self.placed_resting_spots = {}
        self.live_carcasses = []
        self.next_carcass_id = 1
