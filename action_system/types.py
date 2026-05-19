# pyre-strict

"""Pure data types shared across the action-system boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from villmage.game_types import CraftableItem, ItemType

if TYPE_CHECKING:
    from character_canon.canon import CharacterCanon
    from villmage.villager_state import VillagerState
    from villmage.world_state import WorldState

class ExploreResource(Enum):
    """Resource targets available through exploration actions."""

    PEACHES = 1
    # Any profession; mean 10m/item, with a 4x penalty for non-GATHERER villagers.
    STICKS = 2
    # Any profession; mean 2m/item.
    LEAVES = 3
    # Any profession; mean 30s/item.
    LOGS = 4
    # WOODCUTTER only; mean 20m/item.
    BOAR = 5
    # HUNTER only; mean 20h/item.


class ActionType(Enum):
    """Fine-grained discriminant for every selectable villager action."""

    EAT_PEACH = 1
    EAT_COOKED_MEAT = 2
    DRINK_WATER = 3
    TAKE_FROM_BASE = 4
    STORE_IN_BASE = 5
    PLACE_BED_ROLL = 6
    PLACE_COT = 7
    EXPLORE = 8
    REST = 9
    ADD_STICKS = 10
    ADD_FIREWOOD = 11
    LIGHT_FIRE = 12
    EXTINGUISH_FIRE = 13
    SCRAPE_HIDE = 14
    HAUL_WATER = 15
    BUTCHER_CARCASS = 16
    CLEAN_CAMP = 17
    SPLIT_LOGS = 18
    CRAFT_NEW = 19
    CONTINUE_CRAFTING = 20
    COOK_MEAT = 21
    FINISH_COOKING = 22
    GO_TO_SLEEP = 23
    WASH_UP = 24
    TALK_TO = 25


@dataclass(frozen=True)
class AutobalanceMultipliers:
    """Read-only action scaling factors supplied by Simulation Engine."""

    exploration_yield_scale: float = 1.0
    satiation_restore_scale: float = 1.0
    hydration_restore_scale: float = 1.0


@dataclass(frozen=True)
class ActionContext:
    """Read-only snapshot of inputs needed by action eligibility and effects."""

    villager_id: str
    canon: CharacterCanon
    vs: VillagerState
    all_states: dict[str, VillagerState]
    ws: WorldState
    multipliers: AutobalanceMultipliers


@dataclass(frozen=True)
class ActiveSleepSegment:
    """One elapsed sleep segment under a single wakefulness modifier."""

    total_minutes: int
    elapsed_minutes: int
    modifier: float


@dataclass(frozen=True)
class ValidAction:
    """One rendered action-menu entry for the LLM."""

    action_type: ActionType
    prompt_text: str
    selectable: bool
    idx: int | None = None


@dataclass(frozen=True)
class ActionList:
    """Full action menu split into main actions and crafter recipes."""

    main_actions: tuple[ValidAction, ...]
    crafter_recipes: tuple[ValidAction, ...]


@dataclass(frozen=True)
class SelectedAction:
    """Validated typed action choice parsed from one LLM response."""

    action_type: ActionType
    item: ItemType | None = None
    quantity: int | None = None
    resource: ExploreResource | None = None
    duration_minutes: int | None = None
    craftable_item: CraftableItem | None = None
    minutes_to_spend: int | None = None
    hours: int | None = None
    liters: int | None = None
    target_villager_id: str | None = None
