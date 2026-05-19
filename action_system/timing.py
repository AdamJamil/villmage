# pyre-strict

"""Pure timing and exploration-yield math for the action system."""

from __future__ import annotations

import random

from action_system.types import ExploreResource
from character_canon.types import Profession


BASE_MEAN_MINUTES: dict[ExploreResource, float] = {
    ExploreResource.LEAVES: 0.5,
    ExploreResource.STICKS: 2.0,
    ExploreResource.PEACHES: 10.0,
    ExploreResource.LOGS: 20.0,
    ExploreResource.BOAR: 1200.0,
}

_ERLANG_SHAPE: int = 5


def work_speed_modifier(health: float) -> float:
    """Return the health-based work-speed multiplier."""

    if health >= 0.5:
        return 1.0
    return health * 2.0


def apply_duration_modifier(
    base_minutes: float,
    work_speed: float,
    profession_factor: float,
) -> int:
    """Return duration after work-speed and profession modifiers are applied."""

    return round(base_minutes * profession_factor / work_speed)


def exploration_effective_mean(
    resource: ExploreResource,
    profession: Profession,
    yield_scale: float,
) -> float:
    """Return effective mean minutes per explored item before work-speed scaling."""

    base_mean_minutes: float = BASE_MEAN_MINUTES[resource]
    if resource is ExploreResource.PEACHES and profession is not Profession.GATHERER:
        base_mean_minutes *= 4.0
    return base_mean_minutes / yield_scale


def sample_exploration_yield(
    effective_mean_minutes: float,
    work_speed: float,
    duration_minutes: int,
    item_weight_kg: float,
    remaining_capacity_kg: float,
) -> int:
    """Sample how many items are found before time or capacity is exhausted."""

    if duration_minutes <= 0 or remaining_capacity_kg < item_weight_kg:
        return 0
    adjusted_mean_minutes: float = effective_mean_minutes / work_speed
    rng = random.Random()
    elapsed_minutes: float = 0.0
    items_found: int = 0
    while True:
        if (items_found + 1) * item_weight_kg > remaining_capacity_kg:
            return items_found
        elapsed_minutes += _sample_erlang_minutes(
            rng=rng,
            mean_minutes=adjusted_mean_minutes,
        )
        if elapsed_minutes > duration_minutes:
            return items_found
        items_found += 1


def _sample_erlang_minutes(rng: random.Random, mean_minutes: float) -> float:
    """Sample one Erlang-distributed inter-arrival duration in minutes."""

    return rng.gammavariate(_ERLANG_SHAPE, mean_minutes / _ERLANG_SHAPE)
