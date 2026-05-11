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
