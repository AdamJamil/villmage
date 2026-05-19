# pyre-strict

"""Tests for action-system timing math."""

from __future__ import annotations

from statistics import mean

from action_system.timing import (
    apply_duration_modifier,
    exploration_effective_mean,
    sample_exploration_yield,
    work_speed_modifier,
)
from action_system.types import ExploreResource
from character_canon.types import Profession


def test_work_speed_modifier_respects_half_health_boundary() -> None:
    """Work speed is full at or above half health and linear below it."""

    assert work_speed_modifier(0.5) == 1.0
    assert work_speed_modifier(1.0) == 1.0
    assert work_speed_modifier(0.0) == 0.0
    assert work_speed_modifier(0.25) == 0.5


def test_apply_duration_modifier_is_identity_at_baseline() -> None:
    """Baseline duration remains unchanged with identity modifiers."""

    assert apply_duration_modifier(60.0, 1.0, 1.0) == 60


def test_apply_duration_modifier_scales_for_work_speed() -> None:
    """Lower work speed lengthens the action proportionally."""

    assert apply_duration_modifier(60.0, 0.5, 1.0) == 120


def test_apply_duration_modifier_scales_for_profession_factor() -> None:
    """Profession factor slows the action proportionally."""

    assert apply_duration_modifier(60.0, 1.0, 2.0) == 120


def test_apply_duration_modifier_combines_both_factors() -> None:
    """Work-speed and profession modifiers combine multiplicatively."""

    assert apply_duration_modifier(60.0, 0.5, 2.0) == 240


def test_apply_duration_modifier_uses_rounding() -> None:
    """Duration adjustment rounds rather than truncating."""

    assert apply_duration_modifier(61.0, 1.0, 1.0) == 61
    assert apply_duration_modifier(60.0, 1.0, 1.5) == 90


def test_exploration_effective_mean_uses_authored_base_means() -> None:
    """Each resource uses the CONST-104 mean time."""

    assert exploration_effective_mean(
        ExploreResource.LEAVES,
        Profession.GATHERER,
        1.0,
    ) == 0.5
    assert exploration_effective_mean(
        ExploreResource.STICKS,
        Profession.GATHERER,
        1.0,
    ) == 2.0
    assert exploration_effective_mean(
        ExploreResource.PEACHES,
        Profession.GATHERER,
        1.0,
    ) == 10.0
    assert exploration_effective_mean(
        ExploreResource.LOGS,
        Profession.GATHERER,
        1.0,
    ) == 20.0
    assert exploration_effective_mean(
        ExploreResource.BOAR,
        Profession.GATHERER,
        1.0,
    ) == 1200.0


def test_exploration_effective_mean_applies_peach_penalty_to_non_gatherers() -> None:
    """Non-gatherers take four times as long to find peaches."""

    non_gatherers: tuple[Profession, ...] = (
        Profession.CRAFTER,
        Profession.WOODCUTTER,
        Profession.HUNTER,
        Profession.COOK,
        Profession.BUILDER,
    )

    for profession in non_gatherers:
        assert exploration_effective_mean(
            ExploreResource.PEACHES,
            profession,
            1.0,
        ) == 40.0

    assert exploration_effective_mean(
        ExploreResource.PEACHES,
        Profession.GATHERER,
        1.0,
    ) == 10.0


def test_exploration_effective_mean_scales_inverse_to_yield_scale() -> None:
    """Higher yield scale shortens the effective mean time."""

    assert exploration_effective_mean(
        ExploreResource.STICKS,
        Profession.GATHERER,
        2.0,
    ) == 1.0
    assert exploration_effective_mean(
        ExploreResource.STICKS,
        Profession.GATHERER,
        0.5,
    ) == 4.0


def test_sample_exploration_yield_returns_zero_with_no_capacity() -> None:
    """Exploration produces nothing when no further weight can be carried."""

    assert sample_exploration_yield(2.0, 1.0, 240, 0.5, 0.0) == 0


def test_sample_exploration_yield_stops_at_exact_single_item_capacity() -> None:
    """Carry capacity prevents taking a second item once exactly full."""

    assert sample_exploration_yield(1.0, 1.0, 10000, 0.5, 0.5) == 1


def test_sample_exploration_yield_returns_zero_for_zero_duration() -> None:
    """No elapsed exploration time means no items found."""

    assert sample_exploration_yield(2.0, 1.0, 0, 0.5, 100.0) == 0


def test_sample_exploration_yield_matches_expected_mean() -> None:
    """Erlang sampling stays close to the authored average yield."""

    trials: list[int] = [
        sample_exploration_yield(2.0, 1.0, 2000, 0.005, 1000.0)
        for _ in range(200)
    ]

    assert abs(mean(trials) - 1000.0) <= 100.0


def test_sample_exploration_yield_reduces_with_lower_work_speed() -> None:
    """Lower work speed decreases yield for the same chosen duration."""

    trials: list[int] = [
        sample_exploration_yield(2.0, 0.5, 2000, 0.005, 1000.0)
        for _ in range(200)
    ]

    assert abs(mean(trials) - 500.0) <= 75.0
