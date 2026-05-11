# pyre-strict

"""Autobalance multipliers and their midnight adjustment logic."""

from dataclasses import dataclass


SATIATION_TARGET: float = 0.85
HYDRATION_TARGET: float = 0.50
FOOD_SAFETY_TARGET: float = 1.0


def _resolve_multiplier_value(
    value: float,
    alias_value: float | None,
    field_name: str,
) -> float:
    """Return one multiplier value, rejecting conflicting aliases."""

    if alias_value is None:
        return value
    if value != 1.0 and value != alias_value:
        raise ValueError(
            f"{field_name} and its compatibility alias cannot both set different values."
        )
    return alias_value


def _adjust_multiplier(current: float, actual: float, target: float) -> float:
    """Return the next multiplier after one negative-feedback adjustment."""

    fractional_deviation = (actual - target) / target
    if fractional_deviation >= 0.0:
        return current / (1.0 + fractional_deviation)
    return current * (1.0 + (-fractional_deviation))


@dataclass(init=False)
class AutobalanceMultipliers:
    """Mutable autobalance multipliers owned by the simulation engine."""

    exploration_yield: float = 1.0
    satiation_restore: float = 1.0
    hydration_restore: float = 1.0

    def __init__(
        self,
        exploration_yield: float = 1.0,
        satiation_restore: float = 1.0,
        hydration_restore: float = 1.0,
        *,
        exploration_yield_scale: float | None = None,
        satiation_restore_scale: float | None = None,
        hydration_restore_scale: float | None = None,
    ) -> None:
        """Initialize multipliers from canonical fields or compatibility aliases."""

        self.exploration_yield = _resolve_multiplier_value(
            exploration_yield,
            exploration_yield_scale,
            "exploration_yield",
        )
        self.satiation_restore = _resolve_multiplier_value(
            satiation_restore,
            satiation_restore_scale,
            "satiation_restore",
        )
        self.hydration_restore = _resolve_multiplier_value(
            hydration_restore,
            hydration_restore_scale,
            "hydration_restore",
        )

    @property
    def exploration_yield_scale(self) -> float:
        """Return the exploration multiplier under the legacy field name."""

        return self.exploration_yield

    @exploration_yield_scale.setter
    def exploration_yield_scale(self, value: float) -> None:
        """Set the exploration multiplier through the legacy field name."""

        self.exploration_yield = value

    @property
    def satiation_restore_scale(self) -> float:
        """Return the satiation multiplier under the legacy field name."""

        return self.satiation_restore

    @satiation_restore_scale.setter
    def satiation_restore_scale(self, value: float) -> None:
        """Set the satiation multiplier through the legacy field name."""

        self.satiation_restore = value

    @property
    def hydration_restore_scale(self) -> float:
        """Return the hydration multiplier under the legacy field name."""

        return self.hydration_restore

    @hydration_restore_scale.setter
    def hydration_restore_scale(self, value: float) -> None:
        """Set the hydration multiplier through the legacy field name."""

        self.hydration_restore = value

    def adjust(
        self,
        avg_satiation_pct: float,
        avg_hydration_pct: float,
        avg_food_safety_days: float,
    ) -> None:
        """Multiplicatively nudge all multipliers toward their design targets."""

        self.satiation_restore = _adjust_multiplier(
            self.satiation_restore,
            avg_satiation_pct,
            SATIATION_TARGET,
        )
        self.hydration_restore = _adjust_multiplier(
            self.hydration_restore,
            avg_hydration_pct,
            HYDRATION_TARGET,
        )
        self.exploration_yield = _adjust_multiplier(
            self.exploration_yield,
            avg_food_safety_days,
            FOOD_SAFETY_TARGET,
        )


__all__ = ["AutobalanceMultipliers"]
