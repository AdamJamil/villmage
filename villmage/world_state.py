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

    def modify_base_item(self, item: ItemType, delta: int) -> None:
        """Apply a signed item delta while keeping base storage non-negative."""

        next_count = self.get_base_item_count(item) + delta
        if next_count < 0:
            raise ValueError(f"Base item count for {item!r} cannot be negative.")
        self.base_storage[item] = next_count

    def get_base_item_count(self, item: ItemType) -> int:
        """Return the stored quantity for one item type."""

        return self.base_storage.get(item, 0)

    def modify_water(self, delta_ml: int) -> None:
        """Apply a signed water delta while keeping supply non-negative."""

        next_supply_ml = self.water_supply_ml + delta_ml
        if next_supply_ml < 0:
            raise ValueError("Water supply cannot be negative.")
        self.water_supply_ml = next_supply_ml

    def update_cleanliness_source(self, source: DirtinessSource, delta: int) -> None:
        """Adjust one dirtiness source count while keeping it non-negative."""

        next_count = self.dirtiness_counts.get(source, 0) + delta
        if next_count < 0:
            raise ValueError(f"Dirtiness count for {source!r} cannot be negative.")
        self.dirtiness_counts[source] = next_count

    def clear_dirtiness(self) -> int:
        """Zero all dirtiness counts and return the pre-clear total dirtiness."""

        total_dirtiness = self.get_total_dirtiness()
        for source in DirtinessSource:
            self.dirtiness_counts[source] = 0
        return total_dirtiness

    def place_resting_spot(
        self,
        villager_id: str,
        spot_type: RestingSpotType,
    ) -> None:
        """Record the resting spot a villager has physically placed on the ground."""

        self.placed_resting_spots[villager_id] = spot_type

    def _get_carcass_insert_index(self, arrival_timestamp: int) -> int:
        """Return the insertion index that preserves ascending carcass timestamps."""

        for index, carcass in enumerate(self.live_carcasses):
            if arrival_timestamp < carcass.arrival_timestamp:
                return index
        return len(self.live_carcasses)

    def _get_live_carcass_index(self, carcass_id: int) -> int:
        """Return the list index for a tracked carcass id."""

        for index, carcass in enumerate(self.live_carcasses):
            if carcass.id == carcass_id:
                return index
        raise ValueError(f"Unknown carcass id: {carcass_id}.")

    def add_carcass(self, arrival_timestamp: int) -> int:
        """Track one carcass by id and arrival time, preserving oldest-first order."""

        carcass_id = self.next_carcass_id
        self.next_carcass_id += 1
        insert_index = self._get_carcass_insert_index(arrival_timestamp)
        self.live_carcasses.insert(
            insert_index,
            Carcass(id=carcass_id, arrival_timestamp=arrival_timestamp),
        )
        return carcass_id

    def remove_carcass(self, carcass_id: int) -> None:
        """Drop one tracked carcass and add one unit of carcass-remains dirtiness."""

        carcass_index = self._get_live_carcass_index(carcass_id)
        self.live_carcasses.pop(carcass_index)
        self.update_cleanliness_source(DirtinessSource.CARCASS_REMAINS, 1)

    def _get_queued_fuel_minutes(self) -> int:
        """Return the total burn minutes represented by the queued fuel."""

        return sum(
            unit.quantity * FUEL_BURN_DURATION_MINUTES[unit.fuel_type]
            for unit in self.fire.fuel_queue
        )

    def _replace_fire(
        self,
        *,
        lit: bool,
        fuel_queue: tuple[FuelUnit, ...] | None = None,
        extinction_timestamp: int | None,
    ) -> None:
        """Write a new fire snapshot while preserving unspecified queued fuel."""

        next_queue = self.fire.fuel_queue if fuel_queue is None else fuel_queue
        self.fire = Fire(
            lit=lit,
            fuel_queue=next_queue,
            extinction_timestamp=extinction_timestamp,
        )

    def light_fire(self, current_time: int) -> int | None:
        """Light the fire and derive its extinction timestamp from queued fuel."""

        queued_minutes = self._get_queued_fuel_minutes()
        extinction_timestamp = (
            None if queued_minutes == 0 else current_time + queued_minutes
        )
        self._replace_fire(lit=True, extinction_timestamp=extinction_timestamp)
        return extinction_timestamp

    def extinguish_fire(self) -> None:
        """Extinguish the fire without discarding queued fuel."""

        self._replace_fire(lit=False, extinction_timestamp=None)

    def mark_fire_extinguished(self) -> None:
        """Mark scheduled fuel consumption complete and clear the queue."""

        self._replace_fire(lit=False, fuel_queue=(), extinction_timestamp=None)

    def add_fire_fuel(
        self,
        fuel_type: FuelType,
        quantity: int,
        current_time: int,
    ) -> int | None:
        """Append fuel, enforcing the four-hour cap and updating live burn time."""

        added_minutes = quantity * FUEL_BURN_DURATION_MINUTES[fuel_type]
        queued_minutes = self._get_queued_fuel_minutes()
        if queued_minutes + added_minutes > 240:
            raise ValueError("Fire fuel cannot exceed 240 remaining burn minutes.")

        next_queue = self.fire.fuel_queue + (FuelUnit(fuel_type=fuel_type, quantity=quantity),)
        if not self.fire.lit:
            self._replace_fire(
                lit=False,
                fuel_queue=next_queue,
                extinction_timestamp=None,
            )
            return None

        current_extinction = self.fire.extinction_timestamp
        if current_extinction is None:
            current_extinction = current_time
        next_extinction = current_extinction + added_minutes
        self._replace_fire(
            lit=True,
            fuel_queue=next_queue,
            extinction_timestamp=next_extinction,
        )
        return next_extinction

    def is_fire_lit(self) -> bool:
        """Return whether the fire is currently lit."""

        return self.fire.lit

    def get_remaining_fuel_minutes(self, current_time: int) -> int:
        """Return live remaining fuel time or queued fuel time if unlit."""

        if self.fire.lit:
            extinction_timestamp = self.fire.extinction_timestamp
            if extinction_timestamp is None:
                return 0
            return extinction_timestamp - current_time
        return self._get_queued_fuel_minutes()

    def get_total_dirtiness(self) -> int:
        """Return weighted camp dirtiness across all sources, capped at 100."""

        total_dirtiness = sum(
            self.dirtiness_counts.get(source, 0) * DIRTINESS_PENALTY[source]
            for source in DirtinessSource
        )
        return min(100, total_dirtiness)

    def has_placed_spot(self, villager_id: str) -> bool:
        """Return whether the villager currently has a resting spot on the ground."""

        return villager_id in self.placed_resting_spots
