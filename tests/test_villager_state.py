# pyre-strict

"""Tests for villager-state data types and simple invariant mutators."""

import pytest

from villmage.game_types import (
    ActionCategory,
    CraftableItem,
    ItemType,
    RestingSpotType,
    StatName,
)
from villmage.villager_state import CraftingProgress, CurrentAction, VillagerState


def _get_stat_value(villager_state: VillagerState, stat_name: StatName) -> float:
    """Read one mutable stat through an explicit typed dispatch."""

    match stat_name:
        case "wakefulness":
            return villager_state.wakefulness
        case "satiation":
            return villager_state.satiation
        case "hydration":
            return villager_state.hydration
        case "social_joy":
            return villager_state.social_joy
        case "connectedness":
            return villager_state.connectedness
        case "cleanliness":
            return villager_state.cleanliness


def test_villager_state_starts_with_spec_defined_values() -> None:
    """VillagerState() encodes the authored starting invariant exactly."""

    villager_state = VillagerState("aldric")

    assert villager_state.villager_id == "aldric"
    assert villager_state.wakefulness == 100
    assert villager_state.satiation == 1800
    assert villager_state.hydration == 6000
    assert villager_state.social_joy == 20
    assert villager_state.connectedness == 100.0
    assert villager_state.cleanliness == 100
    assert villager_state.inventory == {}
    assert villager_state.sleep_spot_claim is None
    assert villager_state.crafting_in_progress is None
    assert villager_state.current_action is None
    assert villager_state.last_rest_game_time is None
    assert villager_state.awake_minutes_since_compaction == 0
    assert villager_state.is_alive is True


def test_modify_inventory_adds_items_from_absent_and_existing_counts() -> None:
    """Positive inventory deltas accumulate from zero and from prior counts."""

    villager_state = VillagerState("aldric")

    villager_state.modify_inventory(ItemType.PEACH, 5)
    assert villager_state.inventory[ItemType.PEACH] == 5

    villager_state.modify_inventory(ItemType.PEACH, 3)
    assert villager_state.inventory[ItemType.PEACH] == 8


def test_modify_inventory_removes_items_down_to_zero() -> None:
    """Negative inventory deltas can reduce a count exactly to zero."""

    villager_state = VillagerState("aldric")
    villager_state.modify_inventory(ItemType.PEACH, 8)

    villager_state.modify_inventory(ItemType.PEACH, -3)
    assert villager_state.inventory[ItemType.PEACH] == 5

    villager_state.modify_inventory(ItemType.PEACH, -5)
    assert villager_state.inventory[ItemType.PEACH] == 0


def test_modify_inventory_rejects_negative_result() -> None:
    """Inventory refuses mutations that would drive an item count below zero."""

    villager_state = VillagerState("aldric")
    villager_state.modify_inventory(ItemType.PEACH, 5)

    with pytest.raises(ValueError):
        villager_state.modify_inventory(ItemType.PEACH, -6)


def test_modify_inventory_keeps_item_types_independent() -> None:
    """Each inventory item count mutates independently of the others."""

    villager_state = VillagerState("aldric")

    villager_state.modify_inventory(ItemType.PEACH, 4)
    villager_state.modify_inventory(ItemType.LOG, 2)

    assert villager_state.inventory[ItemType.PEACH] == 4
    assert villager_state.inventory[ItemType.LOG] == 2


@pytest.mark.parametrize(
    ("stat_name", "positive_delta", "expected_after_positive", "negative_delta", "expected_after_negative"),
    [
        ("wakefulness", 5.0, 100.0, -10.0, 90.0),
        ("satiation", -200.0, 1600.0, 50.0, 1650.0),
        ("hydration", -500.0, 5500.0, 250.0, 5750.0),
        ("social_joy", 10.0, 30.0, -5.0, 25.0),
        ("connectedness", -10.5, 89.5, 3.25, 92.75),
        ("cleanliness", -12.0, 88.0, 7.0, 95.0),
    ],
)
def test_modify_stat_applies_positive_and_negative_deltas(
    stat_name: StatName,
    positive_delta: float,
    expected_after_positive: float,
    negative_delta: float,
    expected_after_negative: float,
) -> None:
    """Each stat branch applies the requested signed delta."""

    villager_state = VillagerState("aldric")

    villager_state.modify_stat(stat_name, positive_delta)
    assert _get_stat_value(villager_state, stat_name) == expected_after_positive

    villager_state.modify_stat(stat_name, negative_delta)
    assert _get_stat_value(villager_state, stat_name) == expected_after_negative


@pytest.mark.parametrize(
    ("stat_name", "delta", "expected"),
    [
        ("wakefulness", 50.0, 100.0),
        ("satiation", 50.0, 1800.0),
        ("hydration", 50.0, 6000.0),
        ("social_joy", 500.0, 100.0),
        ("connectedness", 50.0, 100.0),
        ("cleanliness", 50.0, 100.0),
    ],
)
def test_modify_stat_clamps_to_upper_bound(
    stat_name: StatName,
    delta: float,
    expected: float,
) -> None:
    """Each stat respects its authored ceiling after positive mutation."""

    villager_state = VillagerState("aldric")

    villager_state.modify_stat(stat_name, delta)

    assert _get_stat_value(villager_state, stat_name) == expected


@pytest.mark.parametrize(
    ("stat_name", "delta"),
    [
        ("wakefulness", -500.0),
        ("satiation", -2000.0),
        ("hydration", -7000.0),
        ("social_joy", -500.0),
        ("connectedness", -500.0),
        ("cleanliness", -500.0),
    ],
)
def test_modify_stat_clamps_to_lower_bound(stat_name: StatName, delta: float) -> None:
    """Each stat respects its authored floor after negative mutation."""

    villager_state = VillagerState("aldric")

    villager_state.modify_stat(stat_name, delta)

    assert _get_stat_value(villager_state, stat_name) == 0.0


def test_modify_stat_connectedness_stays_non_negative_under_repeated_fractional_decay() -> None:
    """Connectedness never slips below zero through floating-point accumulation."""

    villager_state = VillagerState("aldric")

    for _ in range(48):
        villager_state.modify_stat("connectedness", -(100.0 / 48.0))

    assert villager_state.connectedness >= 0.0
    assert villager_state.connectedness == pytest.approx(0.0, abs=1e-9)


def test_is_over_encumbered_uses_base_capacity_boundary() -> None:
    """Base carrying capacity allows 40 kg exactly and rejects the next realizable excess."""

    exact_capacity = VillagerState("aldric")
    exact_capacity.modify_inventory(ItemType.CARCASS, 1)
    exact_capacity.modify_inventory(ItemType.STICK, 20)

    assert exact_capacity.is_over_encumbered() is False

    overweight = VillagerState("aldric")
    overweight.modify_inventory(ItemType.CARCASS, 1)
    overweight.modify_inventory(ItemType.STICK, 20)
    overweight.modify_inventory(ItemType.LEAVES, 1)

    assert overweight.is_over_encumbered() is True


def test_is_over_encumbered_applies_single_satchel_bonus() -> None:
    """Any positive satchel count raises capacity to 70 kg, but no higher."""

    exact_capacity = VillagerState("aldric")
    exact_capacity.modify_inventory(ItemType.SATCHEL, 1)
    exact_capacity.modify_inventory(ItemType.CARCASS, 1)
    exact_capacity.modify_inventory(ItemType.LOG, 2)
    exact_capacity.modify_inventory(ItemType.STICK, 8)

    assert exact_capacity.is_over_encumbered() is False

    overweight = VillagerState("aldric")
    overweight.modify_inventory(ItemType.SATCHEL, 1)
    overweight.modify_inventory(ItemType.CARCASS, 1)
    overweight.modify_inventory(ItemType.LOG, 2)
    overweight.modify_inventory(ItemType.STICK, 8)
    overweight.modify_inventory(ItemType.LEAVES, 1)

    assert overweight.is_over_encumbered() is True


def test_is_over_encumbered_does_not_stack_multiple_satchels() -> None:
    """Multiple satchels still grant only one 30 kg carrying-capacity bonus."""

    villager_state = VillagerState("aldric")
    villager_state.modify_inventory(ItemType.SATCHEL, 2)
    villager_state.modify_inventory(ItemType.CARCASS, 1)
    villager_state.modify_inventory(ItemType.LOG, 2)
    villager_state.modify_inventory(ItemType.STICK, 68)

    assert villager_state.is_over_encumbered() is True


def test_can_fit_accepts_item_that_fits() -> None:
    """An item fits when its weight is at most the remaining capacity."""

    villager_state = VillagerState("aldric")

    assert villager_state.can_fit(ItemType.PEACH) is True


def test_can_fit_rejects_only_items_heavier_than_remaining_capacity() -> None:
    """Fit checks are item-specific rather than a generic near-full rejection."""

    villager_state = VillagerState("aldric")
    villager_state.modify_inventory(ItemType.CARCASS, 1)
    villager_state.modify_inventory(ItemType.RAW_MEAT, 18)

    assert villager_state.can_fit(ItemType.LOG) is False
    assert villager_state.can_fit(ItemType.PEACH) is True


def test_can_fit_respects_exact_boundary() -> None:
    """An item fits at exact capacity and fails after the next realizable increment."""

    villager_state = VillagerState("aldric")
    villager_state.modify_inventory(ItemType.LOG, 2)
    villager_state.modify_inventory(ItemType.COOKED_MEAT, 5)
    villager_state.modify_inventory(ItemType.PEACH, 14)

    assert villager_state.can_fit(ItemType.PEACH) is True

    villager_state.modify_inventory(ItemType.LEAVES, 1)

    assert villager_state.can_fit(ItemType.PEACH) is False


def test_simple_setters_round_trip_between_values_and_none() -> None:
    """Simple setters store whichever snapshot or optional value they receive."""

    villager_state = VillagerState("aldric")
    crafting_progress = CraftingProgress(
        item=CraftableItem.SATCHEL,
        minutes_spent=120,
    )
    current_action = CurrentAction(
        category=ActionCategory.CRAFTING,
        detail="satchel",
        completion_timestamp=500,
    )

    villager_state.set_crafting_state(crafting_progress)
    assert villager_state.crafting_in_progress == crafting_progress
    villager_state.set_crafting_state(None)
    assert villager_state.crafting_in_progress is None

    villager_state.set_current_action(current_action)
    assert villager_state.current_action == current_action
    villager_state.set_current_action(None)
    assert villager_state.current_action is None

    villager_state.set_sleep_spot(RestingSpotType.COT)
    assert villager_state.sleep_spot_claim is RestingSpotType.COT
    villager_state.set_sleep_spot(None)
    assert villager_state.sleep_spot_claim is None

    villager_state.set_last_rest_time(700)
    assert villager_state.last_rest_game_time == 700
    villager_state.set_last_rest_time(None)
    assert villager_state.last_rest_game_time is None


def test_reset_compaction_counter_sets_awake_minutes_to_zero() -> None:
    """Compaction counter reset clears any prior accumulated awake minutes."""

    villager_state = VillagerState("aldric")
    villager_state.awake_minutes_since_compaction = 45

    villager_state.reset_compaction_counter()

    assert villager_state.awake_minutes_since_compaction == 0
