# World State — Implementation Details

## Overview

World State is the shared mutable base: storage, fire, water, carcasses, placed objects, and dirtiness tracking. It is a leaf subsystem — it calls nothing and has no runtime dependencies.

Three subsystems mutate it:
- **Simulation Engine** — advance fire consumption, mark carcasses rotted
- **Action System** — apply all base mutations resulting from villager actions

Two subsystems read from it:
- **Action System** — check eligibility, compute fuel headroom, check water supply
- **AI Coordinator** — read base summary for prompt assembly

---

## Shared-Type Note

`ItemType` and `RestingSpotType` are referenced by both World State (base_storage, placed_resting_spots) and Villager State (inventory, sleep_spot_claim). Because both are leaves — neither may import from the other — these two enums must live in a shared `game_types` module imported by both, as well as by Action System and AI Coordinator. All other types below (`FuelType`, `DirtinessSource`) are internal to World State.

The item weight table also belongs in `game_types` alongside `ItemType`, since Villager State needs it to compute total inventory weight.

---

## Core Objects

### ItemType

All thirteen item types in the simulation (STRCT-21). Used as the key in `base_storage` and in Villager State's inventory.

```thrift
enum ItemType {
    PEACH          = 1,
    CARCASS        = 2,
    RAW_MEAT       = 3,
    COOKED_MEAT    = 4,
    RAW_HIDE       = 5,
    PROCESSED_HIDE = 6,
    LOG            = 7,
    FIREWOOD       = 8,
    STICK          = 9,
    LEAVES         = 10,
    COT            = 11,
    BED_ROLL       = 12,
    SATCHEL        = 13,
}
```

Weight in grams per unit (CONST-22 through CONST-33, CONST-265):

| ItemType       | Grams  |
|----------------|--------|
| PEACH          | 150    |
| CARCASS        | 30,000 |
| RAW_MEAT       | 500    |
| COOKED_MEAT    | 350    |
| RAW_HIDE       | 5,000  |
| PROCESSED_HIDE | 5,000  |
| LOG            | 18,000 |
| FIREWOOD       | 8,000  |
| STICK          | 500    |
| LEAVES         | 5      |
| COT            | 0      |
| BED_ROLL       | 0      |
| SATCHEL        | 0      |

This table lives in `game_types` as a `dict[ItemType, int]` constant.

---

### FuelType

The two burnable fuel types. Burn duration is fixed per type (CONST-116, CONST-264).

```thrift
enum FuelType {
    STICK    = 1,   // 1 game-minute per unit
    FIREWOOD = 2,   // 20 game-minutes per unit
}
```

---

### FuelUnit

One contiguous batch of homogeneous fuel placed into the fire queue at the same time.

```thrift
struct FuelUnit {
    1: FuelType fuel_type,
    2: i32 quantity,    // count of this fuel type in this batch; always >= 1
}
```

The fuel queue is `list[FuelUnit]`, ordered by insertion time (FIFO). Front is consumed first (BHVR-118). Total remaining burn minutes = `sum(u.quantity * minutes_per[u.fuel_type] for u in queue)`. The 4-hour cap (INVR-117) means this sum must never exceed 240 after any mutation.

---

### Fire

Complete fire state. The fuel queue is preserved when extinguished (BHVR-119); the extinction timestamp is only meaningful when lit.

```thrift
struct Fire {
    1: bool lit,
    2: list<FuelUnit> fuel_queue,          // FIFO; preserved across extinguish/relight cycles
    3: optional i32 extinction_timestamp,  // game-minutes from epoch; null when unlit or no fuel
}
```

**Invariants:**
- `extinction_timestamp` is set iff `lit == true` and `fuel_queue` is non-empty.
- When lit: `extinction_timestamp = time_when_lit_or_last_fueled + total_fuel_minutes`.
- When unlit: remaining fuel is read directly from the queue (unchanged).
- Adding fuel to a lit fire extends `extinction_timestamp` by the added minutes; the Simulation Engine must reschedule its fire-extinction heap event.
- Lighting a fire with an empty queue sets `lit = true` and leaves `extinction_timestamp` null; the fire immediately goes out (this state should be prevented in the UI by only allowing light when fuel exists, but the data model permits it for defensive safety).

---

### DirtinessSource

The three additive sources of camp dirtiness (STRCT-131, CONST-132/133/134).

```thrift
enum DirtinessSource {
    CARCASS_REMAINS = 1,   // +30 per count
    MEAT_SCRAPS     = 2,   // +5 per count  (from eating meat)
    COOKING_SCRAPS  = 3,   // +3 per count  (from cooking meat)
}
```

`total_dirtiness = min(100, 30*count[CARCASS_REMAINS] + 5*count[MEAT_SCRAPS] + 3*count[COOKING_SCRAPS])`. Capped at 100 (CONST-279). Cleaning zeroes all counts.

---

### RestingSpotType

The two types of placed sleeping objects (BHVR-92/93). Shared with Villager State (see Shared-Type Note above).

```thrift
enum RestingSpotType {
    BED_ROLL = 1,
    COT      = 2,
}
```

World State tracks the physical object on the ground (`placed_resting_spots`). Villager State tracks the claim (`sleep_spot_claim`). Action System keeps them consistent when placing.

---

### Carcass

One boar carcass present anywhere in camp (in a villager's inventory or in base storage). Tracked here for rot scheduling regardless of physical location.

```thrift
struct Carcass {
    1: i32 id,                  // auto-incrementing from 1; unique within simulation run
    2: i32 arrival_timestamp,   // game-minutes from epoch; Simulation Engine fires rot at arrival_timestamp + 1440
}
```

**Invariant:** `len(live_carcasses) == base_storage.get(CARCASS, 0) + sum(v.inventory.get(CARCASS, 0) for v in villagers)`. Action System is responsible for keeping this consistent on every hunt completion, butcher, storage transfer, and rot event.

When a rot event fires for `carcass_id`:
1. Remove the matching `Carcass` record from `live_carcasses`.
2. Remove one `CARCASS` item from wherever it currently is (search inventory first, then base_storage).
3. Increment `dirtiness_counts[CARCASS_REMAINS]` by 1 (+30 dirtiness).

When butchering:
1. Remove one `CARCASS` from the butchering villager's inventory (or base_storage if that is where it was taken from — Action System resolves this).
2. Remove the oldest `Carcass` record (minimum `arrival_timestamp`) from `live_carcasses`.
3. Increment `dirtiness_counts[CARCASS_REMAINS]` by 1.

---

### WorldState

The top-level mutable container. Not passed between subsystems directly; accessed through the API surface.

```thrift
struct WorldState {
    1: map<ItemType, i32> base_storage,                    // quantity per type; absent key = 0; never negative
    2: i32 water_supply_liters,                            // non-negative integer; haul adds 20, drink subtracts
    3: Fire fire,
    4: map<DirtinessSource, i32> dirtiness_counts,         // count per source; absent key = 0
    5: map<string, RestingSpotType> placed_resting_spots,  // villager_id → spot; at most 1 per villager
    6: list<Carcass> live_carcasses,                       // sorted ascending by arrival_timestamp
}
```

**Notes:**
- `base_storage` may include `CARCASS` entries; these are also mirrored in `live_carcasses` for rot tracking.
- Water is base-only (INVR-84); `water_supply_liters` is the only water store.
- `dirtiness_counts` accumulates until a "Clean up camp" action completes, which zeroes all counts.
- `placed_resting_spots` is distinct from `base_storage`: a placed bed roll or cot is removed from the placer's inventory, does NOT enter base_storage, and is recorded here instead.
- `live_carcasses` is sorted for efficient oldest-first selection during butcher resolution; maintain sort order on insert.

**Starting state:** all fields empty/zero (BHVR-278: base begins with no resources).

---

## File Hierarchy

Two files. `game_types` is a shared leaf imported across subsystems; `world_state` is the World State subsystem proper.

### `villmage/game_types.py`

> Shared enums and constants used by multiple subsystems. Contains `ItemType`, `RestingSpotType`, and the item-weight table. World State and Villager State are both leaves that cannot import from each other, so these shared types live here instead. Action System and AI Coordinator also import from this module. Nothing in this file imports from any other project module.

**Objects:**

- **`ItemType`** — Enum of all thirteen item types in the simulation. Used as the key in `WorldState.base_storage` and in each villager's inventory dict.

- **`RestingSpotType`** — Enum of the two placed sleeping objects (`BED_ROLL`, `COT`). World State uses it to record what physical object is on the ground; Villager State uses it to record which spot a villager has claimed.

- **`ITEM_WEIGHT_G`** — `dict[ItemType, int]` mapping each item to its weight in grams. Used by Villager State to compute total inventory weight and derive the over-encumbered flag.

---

### `villmage/world_state.py`

> Mutable shared base state for the simulation: storage, fire, water, carcasses, placed resting spots, and camp dirtiness. Exposes a `WorldState` class with explicit setters (all mutations) and side-effect-free getters (all reads). Calls nothing; is called by Simulation Engine, Action System, and AI Coordinator.

**Objects:**

- **`FuelType`** — Internal enum of the two burnable fuel types (`STICK`, `FIREWOOD`), each with a fixed per-unit burn duration in game-minutes. Not shared outside this module.

- **`FuelUnit`** — Dataclass representing one contiguous batch of a single fuel type added to the fire queue at the same time. The fire's fuel queue is a `list[FuelUnit]` consumed FIFO; this is the element type.

- **`DirtinessSource`** — Internal enum of the three sources of camp dirtiness (`CARCASS_REMAINS`, `MEAT_SCRAPS`, `COOKING_SCRAPS`), each contributing a fixed dirtiness amount per count. `WorldState` stores a count per source; total dirtiness is their weighted sum capped at 100.

- **`Carcass`** — Dataclass for a single tracked boar carcass, carrying its unique id and the game-time it arrived. Present in `WorldState.live_carcasses` regardless of whether the carcass item is in base storage or a villager's inventory; Simulation Engine uses the arrival timestamp to schedule the rot event.

- **`Fire`** — Dataclass holding the complete fire state: `lit` flag, `fuel_queue` (preserved across extinguish/relight), and `extinction_timestamp` (set only when lit and fuel exists). The single authoritative record of fire status read by Action System for cooking eligibility and by Simulation Engine for scheduling extinction events.

- **`WorldState`** — Top-level mutable container for all shared base state. Every field is mutated through an explicit setter and read through a side-effect-free getter. The single source of truth for what exists at camp outside individual villager inventories.

---

## Core Functions

### `villmage/game_types.py`

No functions. All content is pure data — enums and the weight table constant.

---

### `villmage/world_state.py`

#### `WorldState` — Mutations

```python
def modify_base_item(self, item: ItemType, delta: int) -> None:
    """Add (delta > 0) or remove (delta < 0) items from base storage. Absent keys treated as 0."""
```

```python
def modify_water(self, delta_liters: int) -> None:
    """Adjust base water supply; positive hauls, negative drinks."""
```

```python
def add_fire_fuel(self, fuel_type: FuelType, quantity: int, current_time: int) -> int | None:
    """Append fuel to the fire queue. If lit, extends extinction_timestamp by the added minutes and returns the new value so Simulation Engine can reschedule. Returns None if unlit."""
```

```python
def light_fire(self, current_time: int) -> int | None:
    """Set fire lit and compute extinction_timestamp from queued fuel. Returns extinction_timestamp so Simulation Engine can schedule the extinction event, or None if the queue is empty."""
```

```python
def extinguish_fire(self) -> None:
    """Set fire unlit; preserve the fuel queue for future relighting."""
```

```python
def mark_fire_extinguished(self) -> None:
    """Called by Simulation Engine when the fire-extinction event fires. Sets unlit and empties the fuel queue (all fuel consumed)."""
```

```python
def update_cleanliness_source(self, source: DirtinessSource, delta: int) -> None:
    """Increment or decrement a dirtiness source count. Used on butcher (carcass_remains+1), eat meat (meat_scraps+1), cook meat (cooking_scraps+1), or rot (carcass_remains+1)."""
```

```python
def clear_dirtiness(self) -> None:
    """Zero all dirtiness source counts. Called when 'Clean up camp' completes."""
```

```python
def place_resting_spot(self, villager_id: str, spot_type: RestingSpotType) -> None:
    """Record a resting spot physically placed on the ground by a villager."""
```

```python
def add_carcass(self, arrival_timestamp: int) -> int:
    """Register a new carcass and return its auto-incremented id. Caller is responsible for adding the CARCASS item to base_storage or inventory separately."""
```

```python
def remove_carcass(self, carcass_id: int) -> None:
    """Remove a carcass record on butcher or rot. Caller handles associated item removal and dirtiness update."""
```

#### `WorldState` — Queries

```python
def get_base_item_count(self, item: ItemType) -> int:
    """Return quantity of an item in base storage; 0 if absent."""
```

```python
def is_fire_lit(self) -> bool:
    """Return whether the fire is currently burning."""
```

```python
def get_remaining_fuel_minutes(self, current_time: int) -> int:
    """Return remaining fire burn time in minutes. If lit, derived from extinction_timestamp minus current_time; if not, summed directly from the fuel queue."""
```

```python
def get_total_dirtiness(self) -> int:
    """Return summed camp dirtiness across all sources, capped at 100."""
```

```python
def get_total_edible_calories(self) -> int:
    """Return total edible calories in base storage (peaches × 60 + cooked_meat × 800). Used for safety score and autobalancing."""
```

```python
def get_total_stored_fuel_minutes(self) -> int:
    """Return total burn minutes from base_storage fuel items (firewood × 20 + sticks × 1). Excludes the active fire queue. Used for the firewood safety score per CONST-204."""
```

```python
def has_placed_spot(self, villager_id: str) -> bool:
    """Return whether the villager has a resting spot currently placed on the ground."""
```

```python
def get_base_summary(self) -> BaseSummary:
    """Return a structured snapshot of all base state for AI Coordinator prompt assembly. BaseSummary is a dataclass (defined in this module) containing: storage counts, water supply, fire state, total dirtiness, live carcass count, and placed resting spots."""
```

---

## Flags And Issues

→ FLAG: CONST-204 says "convert base firewood to total burn minutes" for the firewood safety score. The implementation (`get_total_stored_fuel_minutes`) counts both FIREWOOD and STICK items from base storage, since both are combustible fuel. However, the spec consistently treats FIREWOOD and STICK as distinct item types and names only "firewood" in CONST-204. It is unclear whether "firewood" there refers to the FIREWOOD item type specifically or all fuel items.
    Should sticks in base storage count toward the firewood safety score, or only FIREWOOD items?

→ FLAG: `get_total_stored_fuel_minutes` counts only fuel items in base_storage. When a villager adds fuel to the fire, those items are removed from base_storage and placed in the fire queue — so they are excluded from the safety score. A party that has pre-loaded 4 hours of fuel into the fire but holds nothing in base_storage would show a safety score of zero. It is unclear whether CONST-204's "base firewood" is meant to mean the stockpile only or all committed fuel.
    Should fuel already loaded into the fire queue count toward the firewood safety score?

→ ISSUE: `water_supply_liters` is declared as `i32` (integer liters), but CONST-165 specifies washing costs 500 mL (0.5 L), which cannot be represented as a whole liter. Water supply must be stored in mL to handle this precisely.

→ ISSUE: `WorldState` has no field for an auto-incrementing carcass ID counter. `add_carcass` promises to return a unique auto-incremented ID, but the struct definition provides no `next_carcass_id` or equivalent field. The counter mechanism is unspecified.

→ ISSUE: `extinguish_fire` documents that it sets the fire unlit and preserves the fuel queue, but does not state that `extinction_timestamp` is cleared to `None`. The Fire struct invariant implies this ("`extinction_timestamp` is set iff `lit == true`"), but the function contract is silent on it.

→ ISSUE: `get_base_summary` takes no parameters, but producing a meaningful fire status — specifically remaining burn minutes — requires `current_time` to compute `extinction_timestamp - current_time`. The function signature and `BaseSummary` description leave unresolved whether `BaseSummary` exposes the raw `extinction_timestamp` (requiring callers to subtract current time themselves) or a pre-computed remaining-minutes value (requiring `current_time` as a parameter).
