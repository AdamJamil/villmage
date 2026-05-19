# pyre-strict

"""Tests for world-state foundation types and starting invariants."""

import pytest

from villmage.game_types import ItemType
from villmage.world_state import (
    DIRTINESS_PENALTY,
    FUEL_BURN_DURATION_MINUTES,
    DirtinessSource,
    FuelType,
    FuelUnit,
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


def assert_fire_timestamp_invariant(world_state: WorldState) -> None:
    """Assert the fire timestamp matches the lit-and-non-empty queue invariant."""

    has_timestamp = world_state.fire.extinction_timestamp is not None
    has_queued_fuel = world_state.fire.fuel_queue != ()
    assert has_timestamp is (world_state.fire.lit and has_queued_fuel)


def test_light_fire_with_empty_queue_keeps_null_extinction_timestamp() -> None:
    """Lighting an empty fire marks it lit but leaves no scheduled extinction."""

    world_state = WorldState()

    extinction_timestamp = world_state.light_fire(current_time=100)

    assert world_state.is_fire_lit() is True
    assert world_state.fire.extinction_timestamp is None
    assert extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)


def test_light_fire_with_single_fuel_type_sets_extinction_timestamp() -> None:
    """Lighting queued firewood schedules extinction from the current time."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.FIREWOOD, 2, current_time=0)

    extinction_timestamp = world_state.light_fire(current_time=100)

    assert world_state.fire.extinction_timestamp == 140
    assert extinction_timestamp == 140
    assert_fire_timestamp_invariant(world_state)


def test_light_fire_with_mixed_queue_sums_all_burn_minutes() -> None:
    """Lighting mixed queued fuel uses the full queued burn duration."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.STICK, 3, current_time=0)
    world_state.add_fire_fuel(FuelType.FIREWOOD, 1, current_time=0)

    extinction_timestamp = world_state.light_fire(current_time=0)

    assert world_state.fire.extinction_timestamp == 23
    assert extinction_timestamp == 23
    assert_fire_timestamp_invariant(world_state)


def test_extinguish_fire_preserves_queued_fuel() -> None:
    """Manual extinguish clears runtime state but keeps queued fuel intact."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.STICK, 3, current_time=0)
    world_state.add_fire_fuel(FuelType.FIREWOOD, 1, current_time=0)
    queued_fuel = world_state.fire.fuel_queue
    world_state.light_fire(current_time=10)

    world_state.extinguish_fire()

    assert world_state.fire.lit is False
    assert world_state.fire.extinction_timestamp is None
    assert world_state.fire.fuel_queue == queued_fuel
    assert_fire_timestamp_invariant(world_state)


def test_mark_fire_extinguished_clears_queued_fuel() -> None:
    """Scheduled extinguish consumes all queued fuel and resets fire state."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.STICK, 3, current_time=0)
    world_state.add_fire_fuel(FuelType.FIREWOOD, 1, current_time=0)
    world_state.light_fire(current_time=10)

    world_state.mark_fire_extinguished()

    assert world_state.fire.lit is False
    assert world_state.fire.extinction_timestamp is None
    assert world_state.fire.fuel_queue == ()
    assert_fire_timestamp_invariant(world_state)


def test_add_fire_fuel_when_unlit_appends_queue_and_returns_none() -> None:
    """Adding fuel to an unlit fire only mutates the queued fuel."""

    world_state = WorldState()

    extinction_timestamp = world_state.add_fire_fuel(
        FuelType.STICK,
        5,
        current_time=0,
    )

    assert extinction_timestamp is None
    assert world_state.fire.fuel_queue == (FuelUnit(FuelType.STICK, 5),)
    assert_fire_timestamp_invariant(world_state)


def test_add_fire_fuel_when_lit_extends_extinction_timestamp() -> None:
    """Adding fuel to a lit fire extends the already scheduled extinction."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.STICK, 10, current_time=0)
    world_state.light_fire(current_time=100)

    extinction_timestamp = world_state.add_fire_fuel(
        FuelType.FIREWOOD,
        2,
        current_time=100,
    )

    assert extinction_timestamp == 150
    assert world_state.fire.extinction_timestamp == 150
    assert_fire_timestamp_invariant(world_state)


def test_add_fire_fuel_allows_exact_cap_and_rejects_overflow() -> None:
    """Queued fuel may reach but not exceed the 240-minute cap."""

    world_state = WorldState()

    world_state.add_fire_fuel(FuelType.FIREWOOD, 12, current_time=0)
    assert world_state.get_remaining_fuel_minutes(current_time=0) == 240
    assert_fire_timestamp_invariant(world_state)

    with pytest.raises(ValueError):
        world_state.add_fire_fuel(FuelType.STICK, 1, current_time=0)


def test_add_fire_fuel_cap_counts_remaining_minutes_while_lit() -> None:
    """The cap uses live remaining fuel time after the fire is lit."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.FIREWOOD, 10, current_time=0)
    world_state.light_fire(current_time=0)

    world_state.add_fire_fuel(FuelType.FIREWOOD, 2, current_time=0)
    assert world_state.fire.extinction_timestamp == 240
    assert_fire_timestamp_invariant(world_state)

    with pytest.raises(ValueError):
        world_state.add_fire_fuel(FuelType.STICK, 1, current_time=0)


def test_is_fire_lit_tracks_state_transitions() -> None:
    """The lit getter reflects lighting and both extinguish paths."""

    world_state = WorldState()

    assert world_state.is_fire_lit() is False

    world_state.light_fire(current_time=0)
    assert world_state.is_fire_lit() is True

    world_state.extinguish_fire()
    assert world_state.is_fire_lit() is False

    world_state.light_fire(current_time=0)
    world_state.mark_fire_extinguished()
    assert world_state.is_fire_lit() is False


def test_get_remaining_fuel_minutes_for_unlit_empty_queue_is_zero() -> None:
    """An unlit fire with no queued fuel has zero remaining burn time."""

    world_state = WorldState()

    assert world_state.get_remaining_fuel_minutes(current_time=50) == 0


def test_get_remaining_fuel_minutes_for_unlit_mixed_queue_sums_queue() -> None:
    """An unlit fire reports the full queued burn duration."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.STICK, 3, current_time=0)
    world_state.add_fire_fuel(FuelType.FIREWOOD, 2, current_time=0)

    assert world_state.get_remaining_fuel_minutes(current_time=50) == 43


def test_get_remaining_fuel_minutes_for_lit_fire_uses_current_time() -> None:
    """A lit fire reports time remaining until scheduled extinction."""

    world_state = WorldState()
    world_state.add_fire_fuel(FuelType.FIREWOOD, 1, current_time=0)
    world_state.add_fire_fuel(FuelType.STICK, 10, current_time=0)
    world_state.light_fire(current_time=0)

    assert world_state.get_remaining_fuel_minutes(current_time=10) == 20


def test_fire_extinction_timestamp_invariant_after_each_transition() -> None:
    """Every fire transition preserves the timestamp iff lit-and-fueled invariant."""

    world_state = WorldState()

    world_state.light_fire(current_time=0)
    assert world_state.fire.extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)

    world_state.extinguish_fire()
    assert world_state.fire.extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)

    world_state.add_fire_fuel(FuelType.FIREWOOD, 1, current_time=0)
    assert world_state.fire.extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)

    world_state.light_fire(current_time=10)
    assert world_state.fire.extinction_timestamp == 30
    assert_fire_timestamp_invariant(world_state)

    world_state.add_fire_fuel(FuelType.STICK, 5, current_time=10)
    assert world_state.fire.extinction_timestamp == 35
    assert_fire_timestamp_invariant(world_state)

    world_state.extinguish_fire()
    assert world_state.fire.extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)

    world_state.light_fire(current_time=20)
    assert world_state.fire.extinction_timestamp == 45
    assert_fire_timestamp_invariant(world_state)

    world_state.mark_fire_extinguished()
    assert world_state.fire.extinction_timestamp is None
    assert_fire_timestamp_invariant(world_state)
