# pyre-strict

"""Tests for simulation-engine autobalance multipliers."""

import pytest

from villmage.autobalance import AutobalanceMultipliers


def test_autobalance_multipliers_defaults_are_identity() -> None:
    """Fresh autobalance multipliers start at exact identity values."""

    multipliers = AutobalanceMultipliers()

    assert multipliers.exploration_yield == 1.0
    assert multipliers.satiation_restore == 1.0
    assert multipliers.hydration_restore == 1.0


def test_adjust_at_target_leaves_all_multipliers_unchanged() -> None:
    """Target averages are the fixed point of the adjustment rule."""

    multipliers = AutobalanceMultipliers()

    multipliers.adjust(0.85, 0.50, 1.0)

    assert multipliers.exploration_yield == 1.0
    assert multipliers.satiation_restore == 1.0
    assert multipliers.hydration_restore == 1.0


def test_adjust_above_target_decreases_only_affected_multiplier() -> None:
    """Values above target reduce only the corresponding multiplier."""

    multipliers = AutobalanceMultipliers()
    fractional_deviation = (1.0 - 0.85) / 0.85

    multipliers.adjust(1.0, 0.50, 1.0)

    assert multipliers.satiation_restore == pytest.approx(
        1.0 / (1.0 + fractional_deviation)
    )
    assert multipliers.hydration_restore == 1.0
    assert multipliers.exploration_yield == 1.0
    assert multipliers.satiation_restore < 1.0


def test_adjust_below_target_increases_only_affected_multiplier() -> None:
    """Values below target increase only the corresponding multiplier."""

    multipliers = AutobalanceMultipliers()
    fractional_deviation = (0.50 - 0.10) / 0.50

    multipliers.adjust(0.85, 0.10, 1.0)

    assert multipliers.hydration_restore == pytest.approx(
        1.0 * (1.0 + fractional_deviation)
    )
    assert multipliers.satiation_restore == 1.0
    assert multipliers.exploration_yield == 1.0
    assert multipliers.hydration_restore > 1.0


def test_adjust_updates_all_three_multipliers_independently() -> None:
    """Each multiplier should follow its own target comparison without interference."""

    multipliers = AutobalanceMultipliers()
    satiation_deviation = (0.85 - 0.68) / 0.85
    hydration_deviation = (0.75 - 0.50) / 0.50
    food_safety_deviation = (1.0 - 0.5) / 1.0

    multipliers.adjust(0.68, 0.75, 0.5)

    assert multipliers.satiation_restore == pytest.approx(
        1.0 * (1.0 + satiation_deviation)
    )
    assert multipliers.hydration_restore == pytest.approx(
        1.0 / (1.0 + hydration_deviation)
    )
    assert multipliers.exploration_yield == pytest.approx(
        1.0 * (1.0 + food_safety_deviation)
    )
    assert multipliers.satiation_restore > 1.0
    assert multipliers.hydration_restore < 1.0
    assert multipliers.exploration_yield > 1.0


def test_adjust_compounds_across_multiple_days() -> None:
    """Repeated adjustments should compound from the prior day's multiplier."""

    multipliers = AutobalanceMultipliers()
    fractional_deviation = (1.0 - 0.85) / 0.85

    multipliers.adjust(1.0, 0.50, 1.0)
    multipliers.adjust(1.0, 0.50, 1.0)

    assert multipliers.satiation_restore == pytest.approx(
        1.0 / ((1.0 + fractional_deviation) ** 2)
    )
