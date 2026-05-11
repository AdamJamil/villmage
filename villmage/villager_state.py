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
    rest_hours_since: float
    dominant_mood_input: MoodSubcomponent
    dominant_health_input: HealthSubcomponent


DescriptionTiers = tuple[tuple[float, str], ...]


_WELL_BEING_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You feel deathly terrible. Something is horribly wrong."),
    (10.0, "Life feels rough. You're struggling."),
    (30.0, "Things are okay. Could be better, could be worse."),
    (50.0, "You feel pretty good about how things are going."),
    (85.0, "Life is good. Really, truly good."),
)
_MOOD_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You feel truly miserable. Every waking moment is hell."),
    (10.0, "You're in a foul mood. Irritable, drained, and withdrawn."),
    (30.0, "You feel a bit flat. Not miserable, but not great either."),
    (50.0, "You're in a decent mood. Nothing to complain about."),
    (85.0, "You're in wonderful spirits."),
)
_HEALTH_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You are on the brink of death. You need help immediately."),
    (10.0, "Your body is failing you. Everything aches and nothing feels right."),
    (30.0, "You feel a little run down. Your work speed is reduced."),
    (50.0, "You're in good physical shape."),
    (85.0, "You feel strong and full of energy."),
)
_SAFETY_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "There is almost nothing left. Starvation or freezing feels inevitable."),
    (10.0, "Stores are nearly gone. You dread what happens when they run out."),
    (30.0, "Supplies are getting thin. You're starting to worry about what's ahead."),
    (50.0, "You're not worried. Supplies seem adequate for now."),
    (85.0, "You feel secure. There's plenty of food and fuel to last."),
)
_SOCIAL_JOY_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You are completely alone. Nobody cares, and you know it."),
    (10.0, "You feel disconnected from everyone around you. Conversations feel hollow."),
    (30.0, "Your social life is whatever. You're not lonely, but not fulfilled either."),
    (50.0, "You've got good company. Things feel warm and easy."),
    (85.0, "You feel loved. The people around you make life worth living."),
)
_CONNECTEDNESS_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You are a ghost. You could vanish and no one would notice."),
    (10.0, "You feel like a stranger to everyone. Nobody really knows you."),
    (30.0, "You know people, but it all feels surface level."),
    (50.0, "You feel like you belong. The party knows you well."),
    (85.0, "You feel connected to the people in your life."),
)
_CLEANLINESS_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You are caked in filth. Your stench spreads miles away."),
    (20.0, "You stink and feel gross."),
    (40.0, "You smell a little and could use a wash."),
    (60.0, "You are clean"),
)
_BASE_CLEANLINESS_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "The base is filthy."),
    (20.0, "The base could be cleaner."),
)
_WAKEFULNESS_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You are on the brink of collapse. The world is fading in and out."),
    (10.0, "You can barely keep your eyes open. Your thoughts are soup."),
    (30.0, "You're sleepy. Everything takes a little more effort than it should."),
    (50.0, "You're alert enough. No fog, no complaints."),
    (85.0, "You're wide awake and sharp. The world is vivid."),
)
_SATIATION_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You can barely move. You are starving to death."),
    (10.0, "Your body is eating itself. You need food now."),
    (76.0, "You're starving. It's hard to think about anything else."),
    (90.0, "You could eat. Your stomach is starting to rumble."),
    (96.0, "You're perfectly full."),
)
_HYDRATION_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You can barely swallow. Your body is shutting down."),
    (10.0, "You're parched. Your head is pounding and your lips are cracking."),
    (30.0, "Your mouth is dry. You need water soon."),
    (50.0, "You're fine. Not thirsty, not thinking about it."),
    (85.0, "You feel well hydrated."),
)
_REST_DESCRIPTION_TIERS: DescriptionTiers = (
    (0.0, "You've been going nonstop without a break. You're wound tight."),
    (
        33.0,
        "It's been a while since you've had a moment to just sit and breathe.",
    ),
    (67.0, "You've had time to yourself recently. Your head feels clear."),
)

_DESCRIPTION_SPECS: dict[str, tuple[DescriptionTiers, float]] = {
    "well_being": (_WELL_BEING_DESCRIPTION_TIERS, 100.0),
    "mood": (_MOOD_DESCRIPTION_TIERS, 100.0),
    "health": (_HEALTH_DESCRIPTION_TIERS, 100.0),
    "safety": (_SAFETY_DESCRIPTION_TIERS, 100.0),
    "social_joy": (_SOCIAL_JOY_DESCRIPTION_TIERS, 100.0),
    "connectedness": (_CONNECTEDNESS_DESCRIPTION_TIERS, 100.0),
    "cleanliness": (_CLEANLINESS_DESCRIPTION_TIERS, 100.0),
    "base_cleanliness": (_BASE_CLEANLINESS_DESCRIPTION_TIERS, 100.0),
    "wakefulness": (_WAKEFULNESS_DESCRIPTION_TIERS, 100.0),
    "satiation": (_SATIATION_DESCRIPTION_TIERS, 100.0),
    "hydration": (_HYDRATION_DESCRIPTION_TIERS, 100.0),
    "rest": (_REST_DESCRIPTION_TIERS, 1.0),
}
_MOOD_DESCRIPTION_KEYS: dict[MoodSubcomponent, str] = {
    MoodSubcomponent.SOCIAL_JOY: "social_joy",
    MoodSubcomponent.CONNECTEDNESS: "connectedness",
    MoodSubcomponent.CLEANLINESS: "cleanliness",
    MoodSubcomponent.BASE_CLEANLINESS: "base_cleanliness",
    MoodSubcomponent.REST: "rest",
}
_HEALTH_DESCRIPTION_KEYS: dict[HealthSubcomponent, str] = {
    HealthSubcomponent.WAKEFULNESS: "wakefulness",
    HealthSubcomponent.SATIATION: "satiation",
    HealthSubcomponent.HYDRATION: "hydration",
}


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


def _get_description_tier(value: float, tiers: DescriptionTiers) -> str:
    """Return the authored description for one thresholded stat value."""

    for lower_bound, text in reversed(tiers):
        if value >= lower_bound:
            return text
    raise ValueError(f"No description tier matched value {value}.")


def _rest_description_value(rest_hours_since: float) -> float:
    """Convert hours since rest into remaining-rest-benefit percentage."""

    return (max(0.0, 5.0 - rest_hours_since) / 5.0) * 100.0


def _description_text(stat_name: str, stat_value: float) -> str:
    """Resolve one stat name and normalized value to its authored prompt text."""

    tiers, scale = _DESCRIPTION_SPECS[stat_name]
    return _get_description_tier(stat_value * scale, tiers)


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
            rest_hours_since=rest_hours_since,
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

    def get_stat_descriptions(self, computed: ComputedStats) -> dict[str, str]:
        """Return authored prompt-ready stat descriptions keyed by stat name."""

        stat_values: dict[str, float] = {
            "well_being": computed.well_being,
            "mood": computed.mood,
            "health": computed.health,
            "safety": computed.safety,
            "social_joy": computed.social_joy_pct,
            "connectedness": computed.connectedness_pct,
            "cleanliness": computed.cleanliness_pct,
            "base_cleanliness": computed.base_cleanliness,
            "wakefulness": computed.wakefulness_pct,
            "satiation": computed.satiation_pct,
            "hydration": computed.hydration_pct,
            "rest": _rest_description_value(computed.rest_hours_since),
        }
        always_included_keys = ("well_being", "mood", "health", "safety")
        included_keys = (
            list(always_included_keys)
            + [_MOOD_DESCRIPTION_KEYS[computed.dominant_mood_input]]
            + [_HEALTH_DESCRIPTION_KEYS[computed.dominant_health_input]]
            + (["satiation"] * (computed.satiation_pct < 0.90))
            + (["hydration"] * (computed.hydration_pct < 0.50))
            + (["wakefulness"] * (computed.wakefulness_pct < 0.50))
        )
        return {
            key: _description_text(key, stat_values[key])
            for key in included_keys
        }

    def get_work_speed_modifier(self, computed: ComputedStats) -> float:
        """Return the authored health-based work-speed multiplier."""

        return 1.0 if computed.health >= 0.5 else computed.health * 2.0

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
