# pyre-strict

"""Tests for world-state foundation types and starting invariants."""

import pytest

from villmage.game_types import ItemType
from villmage.world_state import (
    DIRTINESS_PENALTY,
    FUEL_BURN_DURATION_MINUTES,
    DirtinessSource,
    FuelType,
    WorldState,
    item_type_to_fuel_type,
)


def test_item_type_to_fuel_type_accepts_only_fuel_items() -> None:
    """Fuel item types map to their corresponding internal fuel enum."""

    assert item_type_to_fuel_type(ItemType.STICK) is FuelType.STICK
    assert item_type_to_fuel_type(ItemType.FIREWOOD) is FuelType.FIREWOOD


@pytest.mark.parametrize(
    "item_type",
    [ItemType.PEACH, ItemType.LOG, ItemType.CARCASS],
)
def test_item_type_to_fuel_type_rejects_non_fuel_items(item_type: ItemType) -> None:
    """Non-fuel items raise ValueError instead of entering the fire queue."""

    with pytest.raises(ValueError):
        item_type_to_fuel_type(item_type)


def test_fuel_burn_duration_minutes_match_spec() -> None:
    """Per-unit fuel burn durations match authored constants."""

    assert FUEL_BURN_DURATION_MINUTES[FuelType.STICK] == 1
    assert FUEL_BURN_DURATION_MINUTES[FuelType.FIREWOOD] == 20


def test_dirtiness_penalty_matches_spec() -> None:
    """Per-source dirtiness penalties match authored constants."""

    assert DIRTINESS_PENALTY[DirtinessSource.CARCASS_REMAINS] == 30
    assert DIRTINESS_PENALTY[DirtinessSource.MEAT_SCRAPS] == 5
    assert DIRTINESS_PENALTY[DirtinessSource.COOKING_SCRAPS] == 3


def test_world_state_starts_with_empty_spec_defined_state() -> None:
    """WorldState() encodes the authored empty base invariant."""

    world_state = WorldState()

    assert world_state.base_storage == {}
    assert world_state.water_supply_ml == 0
    assert world_state.fire.lit is False
    assert world_state.fire.fuel_queue == ()
    assert world_state.fire.extinction_timestamp is None
    assert world_state.dirtiness_counts == {}
    assert world_state.placed_resting_spots == {}
    assert world_state.live_carcasses == []
    assert world_state.next_carcass_id == 1


@pytest.mark.parametrize("item_type", [ItemType.PEACH, ItemType.LOG, ItemType.CARCASS])
def test_get_base_item_count_returns_zero_for_absent_items(item_type: ItemType) -> None:
    """Absent storage entries read back as zero."""

    world_state = WorldState()

    assert world_state.get_base_item_count(item_type) == 0


def test_modify_base_item_accumulates_positive_and_negative_deltas() -> None:
    """Base storage applies signed deltas to the existing item count."""

    world_state = WorldState()

    world_state.modify_base_item(ItemType.PEACH, 5)
    assert world_state.get_base_item_count(ItemType.PEACH) == 5

    world_state.modify_base_item(ItemType.PEACH, 3)
    assert world_state.get_base_item_count(ItemType.PEACH) == 8

    world_state.modify_base_item(ItemType.PEACH, -3)
    assert world_state.get_base_item_count(ItemType.PEACH) == 5


def test_modify_base_item_rejects_negative_result() -> None:
    """Base storage refuses mutations that would drive a count below zero."""

    world_state = WorldState()
    world_state.modify_base_item(ItemType.PEACH, 5)

    with pytest.raises(ValueError):
        world_state.modify_base_item(ItemType.PEACH, -6)


def test_modify_base_item_allows_exact_zero() -> None:
    """Reducing an item count exactly to zero remains valid."""

    world_state = WorldState()
    world_state.modify_base_item(ItemType.PEACH, 5)

    world_state.modify_base_item(ItemType.PEACH, -5)

    assert world_state.get_base_item_count(ItemType.PEACH) == 0


def test_modify_base_item_keeps_item_types_independent() -> None:
    """Each base item count changes independently of the others."""

    world_state = WorldState()

    world_state.modify_base_item(ItemType.PEACH, 4)
    world_state.modify_base_item(ItemType.LOG, 2)

    assert world_state.get_base_item_count(ItemType.PEACH) == 4
    assert world_state.get_base_item_count(ItemType.LOG) == 2


def test_modify_water_applies_positive_and_negative_deltas() -> None:
    """Water supply applies signed deltas without side effects."""

    world_state = WorldState()

    world_state.modify_water(20_000)
    assert world_state.water_supply_ml == 20_000

    world_state.modify_water(-500)
    assert world_state.water_supply_ml == 19_500


def test_modify_water_rejects_negative_result() -> None:
    """Water supply refuses mutations that would drive it below zero."""

    world_state = WorldState()
    world_state.modify_water(20_000)

    with pytest.raises(ValueError):
        world_state.modify_water(-20_001)


def test_storage_and_water_mutations_are_orthogonal() -> None:
    """Storage changes do not affect water, and water changes do not affect storage."""

    world_state = WorldState()

    world_state.modify_base_item(ItemType.PEACH, 5)
    assert world_state.water_supply_ml == 0

    world_state.modify_water(20_000)
    assert world_state.get_base_item_count(ItemType.PEACH) == 5
