# pyre-strict

"""Mutable per-villager state plus small invariant-preserving mutators."""

from dataclasses import dataclass
from enum import Enum

from villmage.game_types import (
    ITEM_WEIGHT_G,
    ActionCategory,
    CraftableItem,
    ItemType,
    RestingSpotType,
    StatName,
    WorldContext,
)


@dataclass(frozen=True)
class DecayResult:
    """Threshold crossings produced by passive stat decay."""

    health_zero: bool
    wakefulness_zero: bool


class MoodSubcomponent(Enum):
    """Mood formula inputs ordered for deterministic tie-breaking."""

    SOCIAL_JOY = 1
    CONNECTEDNESS = 2
    CLEANLINESS = 3
    BASE_CLEANLINESS = 4
    REST = 5


class HealthSubcomponent(Enum):
    """Health formula inputs ordered for deterministic tie-breaking."""

    WAKEFULNESS = 1
    SATIATION = 2
    HYDRATION = 3


@dataclass(frozen=True)
class CraftingProgress:
    """Snapshot of one in-progress crafting job."""

    item: CraftableItem
    minutes_spent: int


@dataclass(frozen=True)
class CurrentAction:
    """Snapshot of the villager's current action."""

    category: ActionCategory
    detail: str | None
    completion_timestamp: int


@dataclass(frozen=True)
class ComputedStats:
    """Derived stat bundle returned by future computation helpers."""

    well_being: float
    mood: float
    health: float
    safety: float
    wakefulness_pct: float
    satiation_pct: float
    hydration_pct: float
    social_joy_pct: float
    connectedness_pct: float
    cleanliness_pct: float
    base_cleanliness: float
    dominant_mood_input: MoodSubcomponent
    dominant_health_input: HealthSubcomponent


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp one numeric value into an inclusive range."""

    return max(minimum, min(value, maximum))


def _is_sleeping(current_action: CurrentAction | None) -> bool:
    """Return whether the villager is currently in the sleeping action."""

    return (
        current_action is not None
        and current_action.category is ActionCategory.SLEEPING
    )


def _compute_mood_value(
    social_joy_pct: float,
    connectedness_pct: float,
    cleanliness_pct: float,
    base_cleanliness: float,
    rest_hours_since: float,
) -> float:
    """Compute the authored mood score from scaled component inputs."""

    linear_term = 0.5 * social_joy_pct
    linear_term += 0.2 * connectedness_pct
    linear_term += 0.2 * cleanliness_pct
    linear_term += 0.1 * base_cleanliness
    geometric_term = (
        social_joy_pct**10
        * connectedness_pct**4
        * cleanliness_pct**4
        * base_cleanliness**2
    ) ** (1.0 / 22.0)
    rest_term = (0.3 / 5.0) * max(0.0, 5.0 - rest_hours_since)
    return min(1.0, (0.5 * linear_term) + (0.5 * geometric_term) + rest_term)


class VillagerState:
    """Mutable survival ledger for one villager."""

    villager_id: str
    wakefulness: float
    satiation: float
    hydration: float
    social_joy: float
    connectedness: float
    cleanliness: float
    inventory: dict[ItemType, int]
    sleep_spot_claim: RestingSpotType | None
    crafting_in_progress: CraftingProgress | None
    current_action: CurrentAction | None
    last_rest_game_time: int | None
    awake_minutes_since_compaction: int
    is_alive: bool

    def __init__(self, villager_id: str) -> None:
        """Initialize the authored starting state for one villager."""

        self.villager_id = villager_id
        self.wakefulness = 100
        self.satiation = 1800
        self.hydration = 6000
        self.social_joy = 20
        self.connectedness = 100.0
        self.cleanliness = 100
        self.inventory = {}
        self.sleep_spot_claim = None
        self.crafting_in_progress = None
        self.current_action = None
        self.last_rest_game_time = None
        self.awake_minutes_since_compaction = 0
        self.is_alive = True

    def modify_inventory(self, item: ItemType, delta: int) -> None:
        """Apply a signed inventory delta while keeping counts non-negative."""

        next_count = self.inventory.get(item, 0) + delta
        if next_count < 0:
            raise ValueError(f"Inventory count for {item!r} cannot be negative.")
        self.inventory[item] = next_count

    def modify_stat(self, stat: StatName, delta: float) -> None:
        """Apply a signed delta to one raw stat and clamp it to its range."""

        match stat:
            case "wakefulness":
                self.wakefulness = _clamp(self.wakefulness + delta, 0.0, 100.0)
            case "satiation":
                self.satiation = _clamp(self.satiation + delta, 0.0, 1800.0)
            case "hydration":
                self.hydration = _clamp(self.hydration + delta, 0.0, 6000.0)
            case "social_joy":
                self.social_joy = _clamp(self.social_joy + delta, 0.0, 100.0)
            case "connectedness":
                self.connectedness = _clamp(self.connectedness + delta, 0.0, 100.0)
            case "cleanliness":
                self.cleanliness = _clamp(self.cleanliness + delta, 0.0, 100.0)

    def _carry_capacity_g(self) -> int:
        """Return the current carrying capacity in grams."""

        has_satchel = self.inventory.get(ItemType.SATCHEL, 0) >= 1
        return 40_000 + (30_000 if has_satchel else 0)

    def _total_inventory_weight_g(self) -> int:
        """Return the total current carried weight in grams."""

        return sum(ITEM_WEIGHT_G[item] * quantity for item, quantity in self.inventory.items())

    def is_over_encumbered(self) -> bool:
        """Return whether carried weight exceeds current carrying capacity."""

        return self._total_inventory_weight_g() > self._carry_capacity_g()

    def can_fit(self, item: ItemType) -> bool:
        """Return whether one more unit of the item fits in current capacity."""

        remaining_capacity_g = self._carry_capacity_g() - self._total_inventory_weight_g()
        return remaining_capacity_g >= ITEM_WEIGHT_G[item]

    def set_crafting_state(self, crafting_state: CraftingProgress | None) -> None:
        """Replace the current crafting-progress snapshot."""

        self.crafting_in_progress = crafting_state

    def set_current_action(self, current_action: CurrentAction | None) -> None:
        """Replace the current action snapshot."""

        self.current_action = current_action

    def set_sleep_spot(self, sleep_spot: RestingSpotType | None) -> None:
        """Replace the claimed sleeping-spot reference."""

        self.sleep_spot_claim = sleep_spot

    def set_last_rest_time(self, game_time: int | None) -> None:
        """Replace the last completed rest timestamp."""

        self.last_rest_game_time = game_time

    def reset_compaction_counter(self) -> None:
        """Reset awake minutes since the last memory compaction."""

        self.awake_minutes_since_compaction = 0

    def _compute_health(self) -> float:
        """Compute the authored health score from wakefulness, satiation, and hydration."""

        wakefulness_pct = self.wakefulness / 100.0
        satiation_pct = self.satiation / 1800.0
        hydration_pct = self.hydration / 6000.0
        satiation_term = (32.0 ** (satiation_pct - 1.0)) - (1.0 / 32.0)
        health = (
            max(0.1, wakefulness_pct)
            * (satiation_term**3)
            * (hydration_pct**3)
        ) ** (1.0 / 9.0)
        return _clamp(health, 0.0, 1.0)

    def compute_stats(self, ctx: WorldContext) -> ComputedStats:
        """Assemble the full derived-stat bundle from raw state and world context."""

        wakefulness_pct = self.wakefulness / 100.0
        satiation_pct = self.satiation / 1800.0
        hydration_pct = self.hydration / 6000.0
        social_joy_pct = self.social_joy / 100.0
        connectedness_pct = self.connectedness / 100.0
        cleanliness_pct = self.cleanliness / 100.0
        base_cleanliness = max(0.0, 1.0 - (ctx.total_dirtiness / 100.0))
        health = self._compute_health()
        rest_hours_since = (
            (ctx.current_game_time - self.last_rest_game_time) / 60.0
            if self.last_rest_game_time is not None
            else 999.0
        )
        mood = _compute_mood_value(
            social_joy_pct=social_joy_pct,
            connectedness_pct=connectedness_pct,
            cleanliness_pct=cleanliness_pct,
            base_cleanliness=base_cleanliness,
            rest_hours_since=rest_hours_since,
        )
        inventory_calories = (self.inventory.get(ItemType.PEACH, 0) * 60) + (
            self.inventory.get(ItemType.COOKED_MEAT, 0) * 800
        )
        food_safety = (
            (inventory_calories / 2200.0)
            + ((1.0 / ctx.villager_count) * (ctx.base_calories / 2200.0))
        ) / 5.0
        fire_safety = (ctx.total_fuel_minutes / 480.0) / 5.0
        safety = (food_safety + fire_safety) / 2.0
        well_being = min(
            1.0,
            (mood**2 * health**3 * max(0.3, safety)) ** (1.0 / 7.0),
        )
        return ComputedStats(
            well_being=well_being,
            mood=mood,
            health=health,
            safety=safety,
            wakefulness_pct=wakefulness_pct,
            satiation_pct=satiation_pct,
            hydration_pct=hydration_pct,
            social_joy_pct=social_joy_pct,
            connectedness_pct=connectedness_pct,
            cleanliness_pct=cleanliness_pct,
            base_cleanliness=base_cleanliness,
            dominant_mood_input=self._dominant_mood_input(
                social_joy_pct,
                connectedness_pct,
                cleanliness_pct,
                base_cleanliness,
                rest_hours_since,
            ),
            dominant_health_input=self._dominant_health_input(
                wakefulness_pct,
                satiation_pct,
                hydration_pct,
            ),
        )

    def _dominant_mood_input(
        self,
        sj: float,
        cn: float,
        cl: float,
        bc: float,
        r: float,
    ) -> MoodSubcomponent:
        """Return the mood input with the largest partial-derivative magnitude."""

        epsilon = 1e-4
        baseline = _compute_mood_value(sj, cn, cl, bc, r)
        gradients: list[tuple[MoodSubcomponent, float]] = [
            (
                MoodSubcomponent.SOCIAL_JOY,
                abs(_compute_mood_value(sj + epsilon, cn, cl, bc, r) - baseline),
            ),
            (
                MoodSubcomponent.CONNECTEDNESS,
                abs(_compute_mood_value(sj, cn + epsilon, cl, bc, r) - baseline),
            ),
            (
                MoodSubcomponent.CLEANLINESS,
                abs(_compute_mood_value(sj, cn, cl + epsilon, bc, r) - baseline),
            ),
            (
                MoodSubcomponent.BASE_CLEANLINESS,
                abs(_compute_mood_value(sj, cn, cl, bc + epsilon, r) - baseline),
            ),
            (
                MoodSubcomponent.REST,
                0.06 if r < 5.0 else 0.0,
            ),
        ]
        return max(gradients, key=lambda pair: pair[1])[0]

    def _dominant_health_input(
        self,
        w: float,
        s: float,
        h: float,
    ) -> HealthSubcomponent:
        """Return the health input with the largest partial-derivative magnitude."""

        epsilon = 1e-4
        satiation_term = (32.0 ** (s - 1.0)) - (1.0 / 32.0)
        baseline = _clamp(
            (max(0.1, w) * (satiation_term**3) * (h**3)) ** (1.0 / 9.0),
            0.0,
            1.0,
        )
        gradients: list[tuple[HealthSubcomponent, float]] = [
            (
                HealthSubcomponent.WAKEFULNESS,
                abs(
                    _clamp(
                        (
                            max(0.1, w + epsilon)
                            * (satiation_term**3)
                            * (h**3)
                        )
                        ** (1.0 / 9.0),
                        0.0,
                        1.0,
                    )
                    - baseline
                ),
            ),
            (
                HealthSubcomponent.SATIATION,
                abs(
                    _clamp(
                        (
                            max(0.1, w)
                            * ((((32.0 ** ((s + epsilon) - 1.0)) - (1.0 / 32.0)) ** 3))
                            * (h**3)
                        )
                        ** (1.0 / 9.0),
                        0.0,
                        1.0,
                    )
                    - baseline
                ),
            ),
            (
                HealthSubcomponent.HYDRATION,
                abs(
                    _clamp(
                        (max(0.1, w) * (satiation_term**3) * ((h + epsilon) ** 3))
                        ** (1.0 / 9.0),
                        0.0,
                        1.0,
                    )
                    - baseline
                ),
            ),
        ]
        return max(gradients, key=lambda pair: pair[1])[0]

    def apply_decay(self, elapsed_hours: float) -> DecayResult:
        """Apply passive stat decay for one interval and report threshold crossings."""

        was_awake = not _is_sleeping(self.current_action)
        previous_wakefulness = self.wakefulness

        if was_awake:
            self.wakefulness = max(0.0, self.wakefulness - (3.0 * elapsed_hours))
            self.awake_minutes_since_compaction += int(elapsed_hours * 60.0)

        self.satiation = max(0.0, self.satiation - (18.0 * elapsed_hours))
        self.hydration = max(0.0, self.hydration - (120.0 * elapsed_hours))
        self.connectedness = max(
            0.0,
            self.connectedness - ((100.0 / 48.0) * elapsed_hours),
        )
        self.cleanliness = max(0.0, self.cleanliness - (2.0 * elapsed_hours))

        wakefulness_zero = previous_wakefulness > 0.0 and self.wakefulness == 0.0
        health_zero = self._compute_health() <= 0.0
        return DecayResult(
            health_zero=health_zero,
            wakefulness_zero=wakefulness_zero,
        )
