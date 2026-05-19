# Villager State — Implementation Details

## Overview

Villager State is the per-villager mutable survival ledger: raw stats, inventory, and in-progress action tracking. It is a leaf subsystem — it calls nothing and has no runtime dependencies.

Three subsystems mutate it:
- **Simulation Engine** — applies time-based decay, detects threshold crossings, resets compaction counters
- **Action System** — applies stat and inventory mutations resulting from actions
- **Conversation System** — updates social_joy on conversation outcomes, transfers inventory items on trade

Two subsystems read from it:
- **AI Coordinator** — reads stat descriptions, inventory, and current action for prompt assembly
- **Action System** — reads inventory, encumbrance, crafting state, and profession for eligibility gating

---

## Shared-Type Additions to `game_types.py`

Two enums that Villager State owns conceptually but that Action System also references must live in `game_types.py` to avoid circular imports.

### CraftableItem

The three items that the CRAFTER profession can produce (ATTR-140, CONST-141/142/143).

```thrift
enum CraftableItem {
    SATCHEL  = 1,   // 8h total; 1 processed hide consumed at start
    BED_ROLL = 2,   // 5h total; 1 processed hide + 400 leaves consumed at start
    COT      = 3,   // 16h total; 5 logs + 25 sticks + 4 processed hide + 400 leaves consumed at start
}
```

### ActionCategory

Categories of villager actions. The distinction between EXPLORING/HAULING (away) and everything else (at base) drives conversation eligibility and "at base" checks. SLEEPING is the one at-base state that also blocks conversation participation.

```thrift
enum ActionCategory {
    SLEEPING       = 1,   // away from participation; wakefulness increases
    RESTING        = 2,   // "Sit and relax"; activates rest buff on completion
    EXPLORING      = 3,   // away action; detail field names the resource
    HAULING        = 4,   // away action; hauling water from river
    CRAFTING       = 5,
    COOKING        = 6,
    BUTCHERING     = 7,
    CLEANING       = 8,
    WASHING        = 9,
    SPLITTING_LOGS = 10,
    SCRAPING_HIDE  = 11,
    FIRE_TENDING   = 12,
    EATING         = 13,
    DRINKING       = 14,
    STORING        = 15,
    TAKING         = 16,
    PLACING_REST   = 17,  // placing a bed roll or cot
    CONVERSATION   = 18,  // managed by Conversation System; set during run_conversation
}
```

**At-base rule (BHVR-284):** villager is "at base" iff `current_action` is `None` or `category not in {EXPLORING, HAULING}`. Active-participation actions (e.g., conversation) additionally require `category != SLEEPING`.

---

## Core Objects

### ThresholdCrossing

Signals emitted by `apply_decay` when a stat hits a critical boundary. Simulation Engine handles each: WAKEFULNESS_ZERO forces a 4-hour sleep; HEALTH_ZERO causes death. Both can occur in a single decay step; Simulation Engine must handle HEALTH_ZERO first (death takes precedence).

```thrift
enum ThresholdCrossing {
    WAKEFULNESS_ZERO = 1,   // wakefulness reached 0; Simulation Engine forces 4-hour sleep
    HEALTH_ZERO      = 2,   // health reached 0; Simulation Engine kills the villager
}
```

---

### MoodSubcomponent

The five inputs to the mood formula, used by partial-derivative selection (BHVR-174) to choose which subcomponent description to surface in prompts.

```thrift
enum MoodSubcomponent {
    SOCIAL_JOY       = 1,   // VRBTM-178 descriptions
    CONNECTEDNESS    = 2,   // VRBTM-180 descriptions
    CLEANLINESS      = 3,   // VRBTM-183 descriptions
    BASE_CLEANLINESS = 4,   // VRBTM-185 descriptions
    REST             = 5,   // rest bonus; no dedicated description tier; only selected when r < 5 and has highest PD
}
```

---

### HealthSubcomponent

The three inputs to the health formula, used by partial-derivative selection (BHVR-191) to choose which subcomponent description to surface.

```thrift
enum HealthSubcomponent {
    WAKEFULNESS = 1,   // VRBTM-194 descriptions
    SATIATION   = 2,   // VRBTM-198 descriptions
    HYDRATION   = 3,   // VRBTM-200 descriptions
}
```

---

### CraftingProgress

In-progress crafting state for a single multi-session crafting action. Materials are consumed at the start of the first session (CONST-141, BHVR-267). Stored on VillagerState and persists across sessions until `minutes_spent >= total_required` for the item.

```thrift
struct CraftingProgress {
    1: CraftableItem item,
    2: i32 minutes_spent,   // cumulative minutes applied so far; always < total_required
}
```

Total required minutes per item: SATCHEL=480, BED_ROLL=300, COT=960. These are constants, not stored in this struct.

---

### CurrentAction

What the villager is currently doing. Written by Action System at action start (via `set_current_action`) and read by AI Coordinator to populate the base summary shown to other villagers (STRCT-234).

```thrift
struct CurrentAction {
    1: ActionCategory category,
    2: optional string detail,        // EXPLORING: resource name (e.g. "logs", "peaches", "boar")
                                      // CRAFTING: item name; COOKING: "raw meat"; otherwise absent
    3: i32 completion_timestamp,      // game-minutes from epoch when action completes
}
```

`detail` is used to generate the "Aldric is exploring for logs" style description in the base summary. Absent for action categories where the category name is self-descriptive.

---

### ComputedStats

Derived stats computed from raw VillagerState values plus caller-supplied world context. Returned by `compute_stats`. Consumed by AI Coordinator for prompt assembly (BHVR-268/269).

```thrift
struct ComputedStats {
    // Primary aggregate scores (all 0.0–1.0)
    1: f64 well_being,             // (m^2 * h^3 * max(0.3, s))^(1/7); CONST-169
    2: f64 mood,                   // CONST-172 formula, clamped to [0,1]
    3: f64 health,                 // CONST-187 formula
    4: f64 safety,                 // average of food_safety and firewood_safety; CONST-205

    // Individual component scores (all 0.0–1.0); needed to generate subcomponent descriptions
    5: f64 wakefulness_pct,        // wakefulness / 100
    6: f64 satiation_pct,          // satiation / 1800
    7: f64 hydration_pct,          // hydration / 6000
    8: f64 social_joy_pct,         // social_joy / 100
    9: f64 connectedness_pct,      // connectedness / 100
    10: f64 cleanliness_pct,       // cleanliness / 100
    11: f64 base_cleanliness,      // max(0, 1 - total_dirtiness/100); CONST-280

    // Dominant subcomponent selection (BHVR-174, BHVR-191)
    12: MoodSubcomponent dominant_mood_input,
    13: HealthSubcomponent dominant_health_input,
}
```

**Partial derivative computation (BHVR-174, BHVR-191):** compute numerically via finite differences (ε = 1e-4). For mood, perturb each of {sj, cn, cl, bc} by ε and compute resulting mood change; for `r` (rest hours), the partial derivative magnitude is `0.06` when `r < 5` else `0` (analytical, since the rest term is linear). Select the highest magnitude. For health, perturb each of {w, s, h} by ε and compare. Ties broken by enum declaration order.

**Note on REST subcomponent:** when r ≥ 5 (never rested or rested >5 hours ago), the rest partial derivative is 0 and REST is never selected as dominant. When REST is selected as dominant, surface... the mood description tier (VRBTM-173) only — there is no separate rest subcomponent description. In practice, the prompt simply includes the mood description without an additional subcomponent line.

---

### VillagerState

The complete mutable state for one living villager.

```thrift
struct VillagerState {
    1: string villager_id,                      // stable key matching VillagerCanon.id

    // Raw survival stats
    2: i32 wakefulness,                         // 0–100; drains 3/hr when awake only (CONST-193)
    3: i32 satiation,                           // 0–1800 cal; drains 18 cal/hr always (CONST-197)
    4: i32 hydration,                           // 0–6000 mL; drains 120 mL/hr always (CONST-199)
    5: i32 social_joy,                          // 0–100; no passive drain; changed only by conversations (CONST-176)
    6: i32 connectedness,                       // 0–100; drains 100/48 per hr always (CONST-179)
    7: i32 cleanliness,                         // 0–100; drains 2/hr always including sleep (CONST-182)

    // Inventory and carry
    8: map<ItemType, i32> inventory,            // item → quantity; absent key = 0; never negative

    // Claim on a placed resting spot (distinct from having the item in inventory)
    9: optional RestingSpotType sleep_spot_claim,

    // In-progress crafting (null when not crafting)
    10: optional CraftingProgress crafting_in_progress,

    // Current action (null when idle between actions)
    11: optional CurrentAction current_action,

    // Timestamp of last completed "Sit and relax" action (BHVR-112)
    // None if villager has never rested; used to compute r in mood formula
    12: optional i32 last_rest_game_time,

    // Awake minutes since last memory compaction; incremented during apply_decay
    // when current_action.category != SLEEPING; reset to 0 on compaction trigger
    13: i32 awake_minutes_since_compaction,

    14: bool is_alive,                          // false after HEALTH_ZERO; archived by Simulation Engine
}
```

**Starting values (CONST-273–277, BHVR-278):**
wakefulness=100, satiation=1800, hydration=6000, social_joy=20, connectedness=100, cleanliness=100, inventory={}, sleep_spot_claim=None, crafting_in_progress=None, current_action=None, last_rest_game_time=None, awake_minutes_since_compaction=0, is_alive=True.

**Carry capacity (CONST-206, BHVR-266):**
`carry_capacity_g = 40_000 + (30_000 if inventory.get(SATCHEL, 0) >= 1 else 0)`
`total_weight_g = sum(ITEM_WEIGHT_G[item] * qty for item, qty in inventory.items())`
`over_encumbered = total_weight_g > carry_capacity_g`
Both are derived on the fly; not stored fields.

**Inventory space for one more item (used in BHVR-102/103):**
`remaining_capacity_g = carry_capacity_g - total_weight_g`
`can_fit(item) = remaining_capacity_g >= ITEM_WEIGHT_G[item]`

---

## Key Logic Notes

### apply_decay

Applies passive stat drain for `elapsed_hours` of game time. Returns the list of threshold crossings that occurred.

**Drain rules:**
- `wakefulness -= 3 * elapsed_hours` only if `current_action is None or current_action.category != SLEEPING`
- `satiation -= 18 * elapsed_hours` always
- `hydration -= 120 * elapsed_hours` always
- `connectedness -= (100/48) * elapsed_hours` always
- `cleanliness -= 2 * elapsed_hours` always
- `social_joy`: NOT drained
- All stats floored at 0 after applying drain.

**Awake time tracking:** if not sleeping, add `elapsed_hours * 60` to `awake_minutes_since_compaction`.

**Threshold detection (in this order):**
1. If wakefulness transitioned from > 0 to 0: emit WAKEFULNESS_ZERO
2. Compute health from final (wakefulness, satiation, hydration) values using `_compute_health`. If health ≤ 0: emit HEALTH_ZERO.

Simulation Engine must handle HEALTH_ZERO before WAKEFULNESS_ZERO (death overrides forced sleep).

### _compute_health (internal)

`health = (max(0.1, w) * (32^(s-1) - 1/32)^3 * h^3)^(1/9)`

where `w = wakefulness/100`, `s = satiation/1800`, `h = hydration/6000`. Returns a float in [0, 1]. Used inside apply_decay (for crossing detection) and inside compute_stats. Not part of the public API.

Edge case: if `satiation == 0`, then `s = 0`, `32^(-1) - 1/32 = 1/32 - 1/32 = 0`, so health = 0. Same if hydration = 0. If wakefulness = 0, `max(0.1, 0) = 0.1`, health is nonzero unless satiation or hydration are also 0.

### compute_stats

Assembles ComputedStats from raw state plus caller-supplied world context.

**Signature:**
```python
def compute_stats(
    self,
    base_calories: int,         # total edible calories in base storage (from WorldState)
    base_fuel_minutes: int,     # total stored fuel burn-minutes in base storage (from WorldState)
    villager_count: int,        # number of living villagers (from Simulation Engine)
    total_dirtiness: int,       # from WorldState.get_total_dirtiness()
    current_game_time: int,
) -> ComputedStats
```

**Safety (CONST-202, CONST-204, CONST-205):**
```
inv_calories = inventory.get(PEACH,0)*60 + inventory.get(COOKED_MEAT,0)*800
food_safety  = ((inv_calories / 2200) + (1/villager_count) * (base_calories / 2200)) / 5
fire_safety  = (base_fuel_minutes / 480) / 5
safety       = (food_safety + fire_safety) / 2
```
Safety is NOT clamped; it can exceed 1.0 if stockpiles are large. Well-being formula uses `max(0.3, safety)`.

**Mood (CONST-172):**
```
sj = social_joy / 100
cn = connectedness / 100
cl = cleanliness / 100
bc = max(0.0, 1.0 - total_dirtiness / 100)
r  = (current_game_time - last_rest_game_time) / 60.0 if last_rest_game_time is not None else 999.0
mood = min(1.0,
    0.5 * (0.5*sj + 0.2*cn + 0.2*cl + 0.1*bc)
    + 0.5 * (sj**10 * cn**4 * cl**4 * bc**2)**(1/22)
    + (0.3/5) * max(0, 5 - r)
)
```
When any multiplicative term in the geometric subexpression is 0, that whole term is 0 (no division-by-zero risk).

**Health:** call `_compute_health(wakefulness, satiation, hydration)`.

**Well-being (CONST-169):**
```
well_being = (mood**2 * health**3 * max(0.3, safety))**(1/7)
```

**Partial derivatives:** computed numerically as described under ComputedStats.

### Work-speed modifier (BHVR-189)

Not stored; derived from health:
```
work_speed_modifier = 1.0 if health >= 0.5 else health * 2.0
```
Action System calls this (or recomputes it) when scheduling action durations.

---

## File Hierarchy

```
villmage/
    game_types.py       — existing; add CraftableItem and ActionCategory enums
    villager_state.py   — all objects and logic below
```

### `villmage/villager_state.py`

> Per-villager mutable state: raw survival stats, inventory, action tracking, and all derived-stat computation. A passive data store with logic only for decay application and stat derivation. Calls nothing; is called by Simulation Engine, Action System, Conversation System, and AI Coordinator.

**Objects:**

- **`ThresholdCrossing`** — Enum of the two stat boundaries that require Simulation Engine intervention: `WAKEFULNESS_ZERO` (force sleep) and `HEALTH_ZERO` (death). Returned as a list from `apply_decay`.

- **`MoodSubcomponent`** — Enum of the five inputs to the mood formula. The one with the highest partial derivative at current values is included as an extra description tier in the villager's prompt (BHVR-174).

- **`HealthSubcomponent`** — Enum of the three inputs to the health formula. Same partial-derivative selection logic as mood (BHVR-191).

- **`CraftingProgress`** — Dataclass tracking an in-progress multi-session crafting action: which item and how many minutes have been spent so far. Materials are already consumed when this exists. Action System creates and clears it; Villager State stores it.

- **`CurrentAction`** — Dataclass holding the category, optional detail string, and completion timestamp of the villager's active action. Written by Action System; read by AI Coordinator for the base summary shown to other villagers.

- **`ComputedStats`** — Dataclass returned by `compute_stats`: all derived scores (well-being, mood, health, safety), individual component percentages, and the dominant subcomponent for mood and health. AI Coordinator consumes this to select which stat description tiers to include in the villager's prompt.

- **`VillagerState`** — Top-level mutable state for one villager. Exposes `apply_decay`, `compute_stats`, `get_stat_descriptions`, and explicit mutators. All stat floors and ceilings enforced by the mutators, not by callers.

---

## Core Functions

### `villmage/villager_state.py`

#### `VillagerState`

```python
def __init__(self, villager_id: str) -> None:
    """Initialize all stats to starting values (CONST-273–277), empty inventory, alive."""

def apply_decay(self, elapsed_hours: float) -> list[ThresholdCrossing]:
    """Apply passive stat drain for elapsed_hours. Drain wakefulness only when not sleeping.
    Return all threshold crossings that occurred; Simulation Engine handles them after this returns."""

def compute_stats(
    self,
    base_calories: int,
    base_fuel_minutes: int,
    villager_count: int,
    total_dirtiness: int,
    current_game_time: int,
) -> ComputedStats:
    """Compute all derived scores (health, mood, well-being, safety) and identify dominant
    subcomponents for mood and health via numerical partial derivatives."""

def get_stat_descriptions(self, computed: ComputedStats) -> dict[str, str]:
    """Return prompt-ready natural-language descriptions keyed by stat name.
    Always includes well_being, mood, health, safety, dominant_mood_input, dominant_health_input.
    Conditionally includes satiation (if satiation_pct < 0.90), hydration (if < 0.50),
    wakefulness (if wakefulness_pct < 0.50). Deduplicates (BHVR-268)."""

def get_work_speed_modifier(self, computed: ComputedStats) -> float:
    """Return 1.0 if health >= 0.5, else health * 2.0 (BHVR-189)."""

def modify_inventory(self, item: ItemType, delta: int) -> None:
    """Add (delta>0) or remove (delta<0) items. Raises if result would be negative."""

def modify_stat(self, stat: str, delta: float) -> None:
    """Apply a delta to a named stat (wakefulness, satiation, hydration, social_joy,
    connectedness, cleanliness), clamping to valid range."""

def set_crafting_state(self, progress: CraftingProgress | None) -> None:
    """Set or clear in-progress crafting."""

def set_current_action(self, action: CurrentAction | None) -> None:
    """Set the villager's current action. Pass None when the villager becomes idle."""

def set_sleep_spot(self, spot: RestingSpotType | None) -> None:
    """Record the villager's sleep spot claim."""

def set_last_rest_time(self, game_time: int) -> None:
    """Called when a 'Sit and relax' action completes (BHVR-112). Updates the rest buff timer."""

def reset_compaction_counter(self) -> None:
    """Zero awake_minutes_since_compaction. Called by Simulation Engine after triggering compaction."""

def _compute_health(self) -> float:
    """Internal: compute health from current wakefulness, satiation, hydration (CONST-187)."""
```

**`get_stat_descriptions` description tiers:** use the VRBTM threshold tables verbatim:
- well_being: VRBTM-170 (5 tiers: 0–10, 10–30, 30–50, 50–85, 85–100)
- mood: VRBTM-173
- health: VRBTM-188
- safety: (no dedicated VRBTM table; use well_being-style tier descriptions — TODO: confirm)
- social_joy (MoodSubcomponent.SOCIAL_JOY): VRBTM-178
- connectedness (MoodSubcomponent.CONNECTEDNESS): VRBTM-180
- cleanliness (MoodSubcomponent.CLEANLINESS): VRBTM-183
- base_cleanliness (MoodSubcomponent.BASE_CLEANLINESS): VRBTM-185
- wakefulness (HealthSubcomponent.WAKEFULNESS): VRBTM-194
- satiation (HealthSubcomponent.SATIATION): VRBTM-198
- hydration (HealthSubcomponent.HYDRATION): VRBTM-200
- rest (MoodSubcomponent.REST): no dedicated VRBTM table; omit the extra description line when REST is dominant

---

## Step 1 — File Hierarchy and Object Assignment

### File Hierarchy

```
villmage/
    game_types.py       — existing file; add CraftableItem and ActionCategory here
    villager_state.py   — all VS-specific types and the VillagerState class
```

**Why two files and not more?**
The subsystem has one meaningful split already mandated by the design: `CraftableItem` and `ActionCategory` must live in `game_types.py` to prevent circular imports (Action System references both, and Action System also imports VillagerState). Everything else belongs together — the enums, progress/action structs, computed-stats bundle, and the VillagerState class are all tightly coupled and have no natural internal seam that would benefit from separation. Splitting further (e.g., pulling stat descriptions into their own file) would add indirection with no architectural payoff.

---

### File Docstrings

#### `villmage/game_types.py` (additions)

> Shared primitive types used by more than one subsystem. Centralised here to break circular-import chains — types that would be defined closer to their primary consumer but are also needed upstream live here. New additions for Villager State: `CraftableItem` (the three items the crafter profession can produce, used by both Action System and Villager State to track in-progress crafting) and `ActionCategory` (the exhaustive list of things a villager can be doing, used by Villager State, Action System, and the Simulation Engine to enforce the "at base" rule and conversation eligibility).

#### `villmage/villager_state.py`

> Per-villager mutable state: raw survival stats, inventory, in-progress action, and all derived-stat computation. Defines the VillagerState-specific enums (`ThresholdCrossing`, `MoodSubcomponent`, `HealthSubcomponent`), the small structs Simulation Engine and AI Coordinator consume (`CraftingProgress`, `CurrentAction`, `ComputedStats`), and the `VillagerState` class that owns the authoritative data and exposes decay, computation, description generation, and targeted mutation. This is a leaf subsystem — it imports only `game_types` and the standard library; nothing here calls into other subsystems.

---

### Object Assignments and Docstrings

#### `villmage/game_types.py`

**`CraftableItem`** (enum)
> The three items the crafter profession can produce. Used by `CraftingProgress` to identify what is being crafted and by Action System to look up material requirements and time budgets. Values: `SATCHEL`, `BED_ROLL`, `COT`.

**`ActionCategory`** (enum)
> Exhaustive classification of everything a villager can be doing at a given moment. Determines "at base" status (any category except `EXPLORING` and `HAULING`) and conversation eligibility (additionally excludes `SLEEPING`). Written by Action System into `CurrentAction`; read by Simulation Engine, Conversation System, and AI Coordinator.

---

#### `villmage/villager_state.py`

**`ThresholdCrossing`** (enum)
> A critical stat boundary that requires Simulation Engine intervention. Returned as a list by `apply_decay`; the engine acts on each crossing after the call returns. `WAKEFULNESS_ZERO` triggers a forced 4-hour sleep; `HEALTH_ZERO` triggers death. If both occur in one decay step, the engine handles `HEALTH_ZERO` first.

**`MoodSubcomponent`** (enum)
> One of the five inputs to the mood formula (`SOCIAL_JOY`, `CONNECTEDNESS`, `CLEANLINESS`, `BASE_CLEANLINESS`, `REST`). `compute_stats` identifies which one has the highest partial derivative at current values; AI Coordinator uses that to pick which extra description line to surface in the villager's prompt.

**`HealthSubcomponent`** (enum)
> One of the three inputs to the health formula (`WAKEFULNESS`, `SATIATION`, `HYDRATION`). Selected by the same partial-derivative mechanism as `MoodSubcomponent`. AI Coordinator surfaces the corresponding description tier in the prompt.

**`CraftingProgress`** (dataclass)
> Snapshot of an in-progress multi-session crafting job: which `CraftableItem` is being made and how many minutes have been spent so far. Exists only while a crafting job is underway; materials are already consumed when this struct is created. Action System creates and clears it; `VillagerState` stores it.

**`CurrentAction`** (dataclass)
> What the villager is doing right now: an `ActionCategory`, an optional detail string (e.g. the resource name for exploration), and the game-minute timestamp when the action completes. Written by Action System at action start; read by AI Coordinator to generate the per-villager activity lines in the base summary shown to other villagers.

**`ComputedStats`** (dataclass)
> All derived scores produced by `compute_stats` in a single bundle: the four aggregate scores (`well_being`, `mood`, `health`, `safety`), the individual component percentages, and the dominant subcomponent for mood and health. Consumed by AI Coordinator to select stat description tiers and by Action System to derive the work-speed modifier.

**`VillagerState`** (class)
> The authoritative mutable ledger for one living villager. Owns the six raw survival stats, inventory, sleep-spot claim, in-progress crafting, and current-action record. Exposes `apply_decay` (time-based stat drain and threshold detection), `compute_stats` (derived score computation), `get_stat_descriptions` (prompt-ready natural-language text), and targeted mutators for each caller. Never calls into other subsystems.

---

## Step 1 — Core Functions

### `game_types.py`

#### `CraftableItem`

```python
@property
def total_minutes(self) -> int:
```
Total crafting time budget in game minutes. SATCHEL=480, BED_ROLL=300, COT=960 (CONST-141/142/143). Used by Action System when scheduling completion and by VillagerState when evaluating whether crafting_in_progress is done.

#### `ActionCategory`

```python
@property
def is_away(self) -> bool:
```
True iff this category is an away action (EXPLORING or HAULING). Used wherever the "at base" rule (BHVR-284) is evaluated; centralising the check avoids hard-coding the two-element set in multiple callers.

#### `StatName` (type alias)

```python
StatName = Literal["wakefulness", "satiation", "hydration", "social_joy", "connectedness", "cleanliness"]
```
Exhaustive set of mutable raw stat names on `VillagerState`. Used as the `stat` parameter in `modify_stat` so Pyre can verify callers pass a valid name.

---

### `villager_state.py`

#### `VillagerState`

```python
def __init__(self, villager_id: str) -> None:
```
Set all stats to starting values (CONST-273–277, BHVR-278): wakefulness=100, satiation=1800, hydration=6000, social_joy=20, connectedness=100, cleanliness=100, empty inventory, is_alive=True.

```python
def apply_decay(self, elapsed_hours: float) -> list[ThresholdCrossing]:
```
Drain passive stats for `elapsed_hours`. Wakefulness drains only when the villager is not sleeping. Returns all threshold crossings (WAKEFULNESS_ZERO, HEALTH_ZERO) that occurred during this interval; Simulation Engine acts on them after this returns.

```python
def compute_stats(
    self,
    base_calories: int,
    base_fuel_minutes: int,
    villager_count: int,
    total_dirtiness: int,
    current_game_time: int,
) -> ComputedStats:
```
Compute health, mood, well-being, safety, and the dominant partial-derivative subcomponent for mood and health. Caller must supply world-context values because safety requires cross-subsystem data (CONST-202/204/205).

```python
def get_stat_descriptions(self, computed: ComputedStats) -> dict[str, str]:
```
Return prompt-ready VRBTM tier descriptions keyed by stat name. Always includes well-being, mood, health, safety, and the dominant subcomponent of each. Conditionally adds satiation (if < 90%), hydration (if < 50%), and wakefulness (if < 50%) per BHVR-268/269. Deduplicates entries.

```python
def get_work_speed_modifier(self, computed: ComputedStats) -> float:
```
Return 1.0 if health >= 0.5, else health * 2.0 (BHVR-189). Action System applies this when computing action durations.

```python
def is_over_encumbered(self) -> bool:
```
True if total inventory weight exceeds carry capacity (40 kg base + 30 kg with a satchel, CONST-206/BHVR-266). When true, Action System disables every action except storing to base (INVR-208).

```python
def can_fit(self, item: ItemType) -> bool:
```
True if one more unit of `item` fits without breaching carry capacity. Used by Action System to stop exploration mid-action when inventory fills (BHVR-102) and to show "Cannot perform" labels before starting (BHVR-103).

```python
def modify_inventory(self, item: ItemType, delta: int) -> None:
```
Add (delta > 0) or remove (delta < 0) units of `item`. Raises ValueError if the result would go negative.

```python
def modify_stat(self, stat: StatName, delta: float) -> None:
```
Apply a signed delta to a named raw stat, clamping the result to that stat's valid range.

```python
def set_crafting_state(self, progress: CraftingProgress | None) -> None:
```
Set or clear the in-progress crafting record. Materials are already consumed before this is called; this only tracks accumulated minutes.

```python
def set_current_action(self, action: CurrentAction | None) -> None:
```
Set or clear the villager's active action. Written by Action System at action start; read by AI Coordinator to populate the activity lines in other villagers' base-summary prompts (STRCT-234).

```python
def set_sleep_spot(self, spot: RestingSpotType | None) -> None:
```
Record the villager's claimed resting-spot type. Action System calls this when a placed bed roll or cot is claimed (BHVR-95).

```python
def set_last_rest_time(self, game_time: int) -> None:
```
Update the rest buff timestamp after a "Sit and relax" action completes (BHVR-112). Used by `compute_stats` to evaluate the rest term in the mood formula.

```python
def reset_compaction_counter(self) -> None:
```
Zero `awake_minutes_since_compaction`. Called by Simulation Engine immediately after it triggers a Memory System compaction for this villager.

---

## Flags and Issues

→ FLAG: The spec includes VRBTM-style tier descriptions for every stat except safety. The `get_stat_descriptions` implementation marks safety descriptions as "TODO: confirm." Without spec-authored text, the implementation must invent tiers — which is a creative/functional vision decision.
    What should the description tiers for the safety score be?

→ FLAG: BHVR-268 requires always including the description for the highest-partial-derivative mood subcomponent. `MoodSubcomponent.REST` has no dedicated VRBTM description table. The implementation resolves this by omitting the extra description line when REST is dominant — directly violating BHVR-268.
    When REST is the dominant mood input, what description (if any) should be surfaced in the prompt?

→ FLAG: BHVR-266 says "when a satchel is in a villmager's inventory, their carry capacity is increased by 30kg" with no stacking rule stated. A crafter could accumulate multiple satchels over time. The implementation treats this as a binary check (≥1 satchel → +30 kg), capping the bonus at one satchel regardless of count.
    Does carrying more than one satchel grant additional capacity, or is the bonus fixed at +30 kg regardless of satchel count?

→ ISSUE: `connectedness` is declared as `i32` in the VillagerState struct but drains at `100/48 ≈ 2.083/hr` — a non-integer rate. Every other passive drain is an exact integer per hour; connectedness is the exception. Applying `(100/48) * elapsed_hours` to an integer field truncates on each step and accumulates drift over a game day.

→ ISSUE: The spec (BHVR-174) says to "select the subcomponent with the highest partial derivative." REST's partial derivative w.r.t. `r` is `−0.06` when `r < 5` — negative, because larger `r` harms mood. All other mood inputs have positive partial derivatives, so signed comparison means REST can never be the highest. The implementation uses magnitude (`0.06`) for REST without stating this departure from the spec's signed framing or documenting what "highest" means in this mixed-sign context.

→ ISSUE: Safety is correctly uncapped (can exceed 1.0 with large stockpiles), but this propagates into well-being: `(mood^2 * health^3 * max(0.3, safety))^(1/7)`. When mood ≈ 1 and health ≈ 1 and safety > 1, well-being exceeds 1.0 and falls above all VRBTM-170 tiers (which top out at [85-100] on a 0–100 scale). `get_stat_descriptions` will silently produce no tier match for this case.

→ ISSUE: `compute_stats` takes `base_fuel_minutes: int`, but WorldState's documented getter is `get_total_firewood`. Converting the fuel queue — sticks (CONST-264: 1 min each) and firewood (CONST-116: 20 min each) — into total burn minutes is not assigned to any subsystem. The caller (Simulation Engine) would need to read WorldState and do this conversion before calling `compute_stats`, but that responsibility appears nowhere.
