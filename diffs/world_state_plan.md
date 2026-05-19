# world_state — Diff Plan

Eight diffs. The subsystem splits naturally across two files and seven domain areas: shared types, internal types + shell, storage + water, fire state machine, dirtiness, resting spots, carcass tracking, and aggregate read queries.

---

## DIFF 1 of 8

**TITLE:** `[world_state][1/8]` game_types module

**DESCRIPTION:**
Create `villmage/game_types.py`. Pure data leaf: no imports from within the project, no logic.

Three objects:

- `ItemType` — 13-member `enum.Enum`, integer values 1–13 per STRCT-21.
- `RestingSpotType` — 2-member `enum.Enum` (`BED_ROLL=1`, `COT=2`) per the struct in world_state.md.
- `ITEM_WEIGHT_G: dict[ItemType, int]` — maps every `ItemType` to its weight in grams per CONST-22 through CONST-33 and CONST-265.

This file exists because `ItemType` and `RestingSpotType` are shared leaves: both World State and Villager State reference them, and neither may import from the other. Getting the enum values and weight table right here is load-bearing for every inventory weight computation in Villager State and every storage operation in World State. Diff 1 isolates these definitions so all downstream diffs can import from a tested foundation.

**TEST PLAN:**

*`tests/test_game_types.py`*

*Enum completeness and values.* Assert `len(ItemType) == 13`. Then assert each member's integer value exactly, all 13: `PEACH=1, CARCASS=2, RAW_MEAT=3, COOKED_MEAT=4, RAW_HIDE=5, PROCESSED_HIDE=6, LOG=7, FIREWOOD=8, STICK=9, LEAVES=10, COT=11, BED_ROLL=12, SATCHEL=13`. Similarly assert `len(RestingSpotType) == 2` with `BED_ROLL=1, COT=2`. Enum integer values are the API surface used across subsystems; a wrong assignment silently corrupts any code that serializes or dispatches on them.

*Weight table completeness.* Assert `set(ITEM_WEIGHT_G.keys()) == set(ItemType)` — no missing keys, no extra keys. A missing entry means Villager State's weight computation silently crashes or returns wrong totals.

*Weight table correctness.* Assert all 13 weights against spec values: `PEACH=150, CARCASS=30_000, RAW_MEAT=500, COOKED_MEAT=350, RAW_HIDE=5_000, PROCESSED_HIDE=5_000, LOG=18_000, FIREWOOD=8_000, STICK=500, LEAVES=5, COT=0, BED_ROLL=0, SATCHEL=0`. Test every member; a wrong weight is silent until a carry-capacity calculation is wrong in gameplay.

*Non-negative invariant.* Assert all values in `ITEM_WEIGHT_G` are `>= 0`. Belt-and-suspenders: prevents a typo from producing a negative weight.

---

## DIFF 2 of 8

**TITLE:** `[world_state][2/8]` Internal types and WorldState shell

**DESCRIPTION:**
Create `villmage/world_state.py`. No callable methods on `WorldState` yet beyond `__init__`; this diff lays the typed foundation everything else builds on.

Objects added:

- `FuelType` — internal 2-member enum (`STICK=1`, `FIREWOOD=2`). Burn duration constants live here as a module-level dict: `{STICK: 1, FIREWOOD: 20}` minutes per unit per CONST-116 and CONST-264.
- `FuelUnit` — frozen dataclass (`fuel_type: FuelType`, `quantity: int`). The element type of the fire's FIFO queue.
- `DirtinessSource` — internal 3-member enum (`CARCASS_REMAINS=1`, `MEAT_SCRAPS=2`, `COOKING_SCRAPS=3`). Per-source dirtiness penalties live as a module-level dict matching CONST-132/133/134: `{CARCASS_REMAINS: 30, MEAT_SCRAPS: 5, COOKING_SCRAPS: 3}`.
- `Carcass` — frozen dataclass (`id: int`, `arrival_timestamp: int`).
- `Fire` — frozen dataclass (`lit: bool`, `fuel_queue: tuple[FuelUnit, ...]`, `extinction_timestamp: int | None`). Frozen because all fire state transitions are done by returning a new `Fire`; `WorldState` stores and replaces it.
- `item_type_to_fuel_type(item: ItemType) -> FuelType` — module-level helper. Maps `ItemType.STICK → FuelType.STICK`, `ItemType.FIREWOOD → FuelType.FIREWOOD`; raises `ValueError` for all other items. Used by Action System when adding fuel to the fire.
- `WorldState.__init__` — initializes to the spec-defined starting state (BHVR-278): `base_storage={}`, `water_supply_ml=0`, `fire=Fire(lit=False, fuel_queue=(), extinction_timestamp=None)`, `dirtiness_counts={}`, `placed_resting_spots={}`, `live_carcasses=[]`, `next_carcass_id=1`.

`Fire` is frozen (immutable dataclass) because every mutation on fire state produces a new `Fire` instance. `WorldState` itself is mutable and stores the current `Fire`.

**TEST PLAN:**

*`tests/test_world_state.py`*

*`item_type_to_fuel_type` — valid inputs.* Assert `item_type_to_fuel_type(ItemType.STICK) is FuelType.STICK` and `item_type_to_fuel_type(ItemType.FIREWOOD) is FuelType.FIREWOOD`. These are the only two legal inputs.

*`item_type_to_fuel_type` — invalid inputs.* Assert `ValueError` is raised for at least three non-fuel types: `PEACH`, `LOG` (related but not burnable directly), and `CARCASS`. A non-raising call for a non-fuel item would let Action System silently enqueue garbage fuel.

*FuelType burn durations.* Assert the module-level duration dict maps `STICK → 1` and `FIREWOOD → 20`. These are referenced by all fire time calculations.

*DirtinessSource penalty dict.* Assert penalties are exactly `CARCASS_REMAINS=30, MEAT_SCRAPS=5, COOKING_SCRAPS=3`.

*WorldState starting state.* Construct `WorldState()` and assert every field: `base_storage == {}`, `water_supply_ml == 0`, `fire.lit == False`, `fire.fuel_queue == ()`, `fire.extinction_timestamp is None`, `dirtiness_counts == {}`, `placed_resting_spots == {}`, `live_carcasses == []`, `next_carcass_id == 1`. This test encodes BHVR-278 exactly and will catch any deviation in the starting invariant.

---

## DIFF 3 of 8

**TITLE:** `[world_state][3/8]` Storage and water

**DESCRIPTION:**
Add four methods to `WorldState`:

- `modify_base_item(item: ItemType, delta: int) -> None` — adds or removes items from `base_storage`. Absent keys are treated as 0. Raises `ValueError` if the result would be negative (invariant: base_storage values are never negative).
- `get_base_item_count(item: ItemType) -> int` — returns quantity for an item; 0 if absent.
- `modify_water(delta_ml: int) -> None` — adjusts `water_supply_ml`. Raises `ValueError` if result would be negative (INVR: non-negative).

These are the simplest mutations in the subsystem — no cross-field logic, no derived state. Grouping storage and water together is natural: both represent "what is physically in camp" with the same no-negative invariant.

**TEST PLAN:**

*`tests/test_world_state.py`*

*Absent key returns 0.* On a fresh `WorldState`, assert `get_base_item_count` returns 0 for every `ItemType` checked. Tests the "absent = 0" contract that all callers depend on.

*Positive delta increments.* `modify_base_item(PEACH, 5)`, then `get_base_item_count(PEACH) == 5`. Add again: `modify_base_item(PEACH, 3)` → 8.

*Negative delta decrements.* From 8, `modify_base_item(PEACH, -3)` → 5.

*Negative invariant enforcement.* From 5, `modify_base_item(PEACH, -6)` must raise `ValueError`. Confirms the invariant is enforced by the setter, not just documented.

*Exact zero.* `modify_base_item(PEACH, -5)` from 5 → `get_base_item_count(PEACH) == 0` (no error; zero is valid).

*Multiple types are independent.* Add PEACH and LOG separately; assert each query returns its own count without affecting the other.

*Water — positive delta.* `modify_water(20_000)` → `water_supply_ml == 20_000`.

*Water — negative delta.* `modify_water(-500)` → 19_500.

*Water — negative invariant.* `modify_water(-20_001)` from 20_000 raises `ValueError`.

*Orthogonality.* Modifying storage does not change `water_supply_ml` and vice versa.

---

## DIFF 4 of 8

**TITLE:** `[world_state][4/8]` Fire state machine

**DESCRIPTION:**
Add all fire-related methods to `WorldState`. These form a tightly coupled state machine and cannot be split without breaking invariants between them.

Methods:

- `light_fire(current_time: int) -> int | None` — sets `fire.lit = True`. Computes `extinction_timestamp = current_time + total_queued_minutes` if queue is non-empty; leaves it `None` if empty. Returns `extinction_timestamp` so Simulation Engine can schedule the extinction heap event.
- `extinguish_fire() -> None` — sets `fire.lit = False`, clears `extinction_timestamp` to `None`. **Preserves** the fuel queue (BHVR-119).
- `mark_fire_extinguished() -> None` — called by Simulation Engine when the scheduled extinction event fires. Sets unlit, clears `extinction_timestamp`, and **empties** the fuel queue (all fuel consumed).
- `add_fire_fuel(fuel_type: FuelType, quantity: int, current_time: int) -> int | None` — appends a new `FuelUnit` to the queue. Raises `ValueError` if adding this fuel would push total remaining burn minutes above 240 (INVR-117: 4-hour cap). If fire is lit, extends `extinction_timestamp` by the added minutes and returns the new value so Simulation Engine can reschedule its heap event. If unlit, returns `None`.
- `is_fire_lit() -> bool` — returns `fire.lit`.
- `get_remaining_fuel_minutes(current_time: int) -> int` — if lit: `fire.extinction_timestamp - current_time`. If unlit: sum of `u.quantity * burn_minutes[u.fuel_type]` across the queue.

The invariant "`extinction_timestamp` is set iff `lit == True` and `fuel_queue` is non-empty" is maintained by all four mutation methods; tests must verify it after every transition.

**TEST PLAN:**

*`tests/test_world_state.py`*

*`light_fire` — empty queue.* Light a fire with no queued fuel. Assert `is_fire_lit() == True`, `fire.extinction_timestamp is None`, return value is `None`. This edge case (BHVR: immediately goes out) must not crash.

*`light_fire` — non-empty queue, single fuel type.* Pre-add 2 FIREWOOD (40 min) while unlit. Light at `t=100`. Assert `extinction_timestamp == 140`, return value `== 140`.

*`light_fire` — mixed queue.* Pre-add 3 STICKs and 1 FIREWOOD (23 min total). Light at `t=0`. Assert `extinction_timestamp == 23`, return `23`.

*`extinguish_fire` — queue preserved.* Add fuel, light, then extinguish. Assert `fire.lit == False`, `extinction_timestamp is None`, and the queue still contains the fuel batches that were there before. This is the critical behavioral difference from `mark_fire_extinguished`.

*`mark_fire_extinguished` — queue cleared.* Add fuel, light, then call `mark_fire_extinguished`. Assert `fire.lit == False`, `extinction_timestamp is None`, `fire.fuel_queue == ()`. Any remaining fuel is consumed and gone.

*`add_fire_fuel` — unlit.* Add 5 STICKs to an unlit fire. Assert return value is `None`, queue now contains a `FuelUnit(STICK, 5)`.

*`add_fire_fuel` — lit, extends timestamp.* Light fire after pre-adding 10 min of fuel (extinction at `t=110` from `t=100`). Add 2 FIREWOOD (40 min) at `t=100`. Assert return `== 150`, `extinction_timestamp == 150`.

*`add_fire_fuel` — 4-hour cap, exact boundary.* Add exactly 240 minutes of fuel (e.g., 12 FIREWOOD) while unlit. Assert it succeeds. Then attempt to add 1 more STICK. Assert `ValueError`. Attempting to exceed 240 is forbidden by INVR-117.

*`add_fire_fuel` — cap counted correctly when lit.* Light fire, add 200 min of fuel (total remaining = 200 min). Add 40 more min → success (total = 240). Add 1 more STICK → `ValueError`.

*`is_fire_lit` state tracking.* Assert False initially, True after `light_fire`, False after `extinguish_fire`, False after `mark_fire_extinguished`.

*`get_remaining_fuel_minutes` — unlit, empty queue.* Returns 0.

*`get_remaining_fuel_minutes` — unlit, mixed queue.* 3 STICKs + 2 FIREWOOD = 43 min. Assert 43.

*`get_remaining_fuel_minutes` — lit.* Light at `t=0` with 30 min of fuel. Call `get_remaining_fuel_minutes(t=10)`. Assert 20.

*Extinction timestamp invariant — after each transition.* After `light_fire` with empty queue: `None`. After `light_fire` with fuel: set. After `extinguish_fire`: `None`. After `add_fire_fuel` while lit: updated. After `mark_fire_extinguished`: `None`. This table-driven invariant check is the single most important test for this diff.

---

## DIFF 5 of 8

**TITLE:** `[world_state][5/8]` Dirtiness system

**DESCRIPTION:**
Add three methods to `WorldState`:

- `update_cleanliness_source(source: DirtinessSource, delta: int) -> None` — increments or decrements the count for a dirtiness source in `dirtiness_counts`. Absent keys treated as 0. (Used directly for MEAT_SCRAPS and COOKING_SCRAPS; CARCASS_REMAINS is updated internally by `remove_carcass` in diff 7.)
- `get_total_dirtiness() -> int` — returns `min(100, 30*count[CARCASS_REMAINS] + 5*count[MEAT_SCRAPS] + 3*count[COOKING_SCRAPS])`. Cap at 100 per CONST-279.
- `clear_dirtiness() -> int` — zeroes all source counts and returns the total dirtiness that was present before clearing. The returned value is used by Action System to compute the cleaner's cleanliness penalty (BHVR-137).

**TEST PLAN:**

*`tests/test_world_state.py`*

*Initial dirtiness is 0.* Fresh `WorldState`: `get_total_dirtiness() == 0`.

*Per-source contribution.* Assert each source in isolation: 1 `CARCASS_REMAINS` → 30; 1 `MEAT_SCRAPS` → 5; 1 `COOKING_SCRAPS` → 3. These are the unit-level spec constants CONST-132/133/134.

*Additive across sources.* Set 1 of each source. Assert total = 38 (30+5+3).

*Cap at 100.* Add 4 `CARCASS_REMAINS` (would be 120). Assert `get_total_dirtiness() == 100`. Cap must apply even when individual sources would sum beyond it; a silent overflow here would corrupt mood calculations.

*`clear_dirtiness` return value.* Set 1 `MEAT_SCRAPS` and 1 `COOKING_SCRAPS` (total=8). Call `clear_dirtiness()`. Assert return value `== 8`. This return value is the only way Action System computes the penalty in BHVR-137; a wrong return corrupts cleanliness.

*`clear_dirtiness` zeroes state.* After clearing, assert `get_total_dirtiness() == 0`. Each source count must be 0.

*`clear_dirtiness` on already-zero state.* Call when total is 0. Assert returns 0, no error.

*Decrement via `update_cleanliness_source`.* Increment MEAT_SCRAPS by 2, then decrement by 1. Assert total = 5 (one remaining). Decrement is used when adjusting counts.

---

## DIFF 6 of 8

**TITLE:** `[world_state][6/8]` Resting spots

**DESCRIPTION:**
Add two methods to `WorldState`:

- `place_resting_spot(villager_id: str, spot_type: RestingSpotType) -> None` — records a placed resting spot in `placed_resting_spots`. The map is keyed by villager id; overwriting is permitted at the WorldState level (Action System enforces the one-spot-per-villager eligibility check via BHVR-92/93 before calling this).
- `has_placed_spot(villager_id: str) -> bool` — returns whether the villager currently has a resting spot placed on the ground.

`placed_resting_spots` is distinct from `base_storage`: a placed bed roll or cot is removed from the villager's inventory and recorded here, not entered into base_storage.

**TEST PLAN:**

*`tests/test_world_state.py`*

*Initially no spots.* `has_placed_spot("aldric") == False` on fresh state.

*Place and check.* `place_resting_spot("aldric", BED_ROLL)` → `has_placed_spot("aldric") == True`.

*Spot type stored.* After placing, assert `placed_resting_spots["aldric"] == RestingSpotType.BED_ROLL`. WorldState must store the type, not just a flag — callers read it for prompt assembly.

*Villager isolation.* Place a COT for "sewalt". Assert `has_placed_spot("aldric")` (from prior test body) is independent; "sewalt"'s spot doesn't affect "aldric"'s.

*Both resting spot types accepted.* Place `BED_ROLL` for one villager, `COT` for another. Assert both are present and have their correct types.

---

## DIFF 7 of 8

**TITLE:** `[world_state][7/8]` Carcass tracking

**DESCRIPTION:**
Add two methods to `WorldState`:

- `add_carcass(arrival_timestamp: int) -> int` — creates a `Carcass` with the next available id (`next_carcass_id`), increments `next_carcass_id`, inserts the new carcass into `live_carcasses` maintaining ascending sort by `arrival_timestamp`, and returns the assigned id. The caller (Action System) separately adds the CARCASS item to the appropriate inventory or base_storage.
- `remove_carcass(carcass_id: int) -> None` — removes the tracker for the given id from `live_carcasses` (raises `ValueError` if not found) and increments the `CARCASS_REMAINS` count in `dirtiness_counts` by 1 (+30 dirtiness, per BHVR-282). The caller separately removes the CARCASS item from wherever it currently lives.

Both butchering and rotting go through `remove_carcass`; both produce carcass remains. This diff depends on diff 5 being present because `remove_carcass` calls `update_cleanliness_source` internally.

**TEST PLAN:**

*`tests/test_world_state.py`*

*First id is 1.* `add_carcass(t=0)` returns 1. `next_carcass_id` is now 2.

*Ids auto-increment.* Three sequential adds return 1, 2, 3 in order.

*`live_carcasses` populated correctly.* After `add_carcass(500)`, assert `live_carcasses` contains exactly one entry with `id=1, arrival_timestamp=500`.

*Sort maintained on insert.* Add carcass at `t=100`, then at `t=50`. Assert `live_carcasses` is `[t=50, t=100]` — ascending order, regardless of insertion order. Simulation Engine and Action System rely on this sort to find the oldest carcass for butcher priority.

*`remove_carcass` removes the right entry.* Add carcasses at t=0, t=100, t=200. Remove id=2. Assert `live_carcasses` contains only ids 1 and 3.

*`remove_carcass` increments CARCASS_REMAINS.* After removal, assert `get_total_dirtiness() == 30`. Each removal adds exactly one unit of carcass remains (+30 dirtiness per CONST-132). This is the primary way carcass remains accumulate.

*`remove_carcass` nonexistent id raises.* `remove_carcass(999)` on a state with no such id must raise `ValueError`. A silent no-op would break the carcass–item invariant (item still exists in inventory/storage but tracker is gone).

*Multiple removes accumulate dirtiness.* Add 3 carcasses, remove all 3. Assert `get_total_dirtiness() == 90` (3 × 30). At 4 removals it would cap at 100 — test that boundary too.

---

## DIFF 8 of 8

**TITLE:** `[world_state][8/8]` Aggregate queries

**DESCRIPTION:**
Add the three aggregate read queries and the `BaseSummary` return type:

- `BaseSummary` — frozen dataclass holding the full base snapshot: `storage: dict[ItemType, int]`, `water_supply_ml: int`, `fire_lit: bool`, `remaining_fuel_minutes: int`, `total_dirtiness: int`, `live_carcass_count: int`, `placed_resting_spots: dict[str, RestingSpotType]`. Defined in this file (not `game_types`) because it's only returned by `WorldState`.
- `get_total_edible_calories() -> int` — peaches × 60 + cooked_meat × 800 from base_storage. Used for food safety score (CONST-202) and autobalancing target.
- `get_total_fuel_minutes(current_time: int) -> int` — total combustible fuel in minutes: `base_storage[FIREWOOD] × 20 + base_storage[STICK] × 1` plus `get_remaining_fuel_minutes(current_time)` for fuel already in the fire queue. This double-counts nothing: base storage items have not yet been added to the fire; fire queue items are distinct.
- `get_base_summary(current_time: int) -> BaseSummary` — snapshot of all base state for AI Coordinator prompt assembly. Delegates to the other queries for derived fields.

**TEST PLAN:**

*`tests/test_world_state.py`*

*`get_total_edible_calories` — empty storage.* Returns 0.

*`get_total_edible_calories` — peaches only.* Add 5 PEACH. Assert 300 (5 × 60).

*`get_total_edible_calories` — cooked meat only.* Add 3 COOKED_MEAT. Assert 2400 (3 × 800).

*`get_total_edible_calories` — both.* 5 PEACH + 3 COOKED_MEAT. Assert 2700.

*`get_total_edible_calories` — non-edible items ignored.* Add RAW_MEAT, LOG, FIREWOOD. Assert still returns 0 for those (combined with no peach/cooked_meat → total = 0). RAW_MEAT is inedible per CONST-82/87 which only lists cooked_meat; raw meat must not contribute.

*`get_total_fuel_minutes` — empty.* Returns 0.

*`get_total_fuel_minutes` — base storage only.* Add 3 FIREWOOD and 10 STICK to storage. Assert 3×20 + 10×1 = 70.

*`get_total_fuel_minutes` — fire queue only (unlit).* Add 4 FIREWOOD to fire queue (unlit). Assert 80.

*`get_total_fuel_minutes` — fire queue only (lit).* Light the fire after adding 4 FIREWOOD. At `current_time=0`, extinction is at `t=80`. Assert `get_total_fuel_minutes(t=20) == 60` (80−20 remaining in fire).

*`get_total_fuel_minutes` — both base and fire.* Add 5 FIREWOOD to base storage, then 2 FIREWOOD to fire queue and light it. At `t=0`, extinction at `t=40`. Assert `get_total_fuel_minutes(t=0) == 5×20 + 40 = 140`. Confirms the two pools add without double-counting.

*`get_base_summary` — snapshot correctness.* Set up state: 10 PEACH and 2 COOKED_MEAT in storage, 1000 mL water, lit fire with 30 min remaining at `t=0`, 2 CARCASS_REMAINS dirtiness increments (total=60), 1 live carcass, one resting spot for "aldric". Call `get_base_summary(t=0)`. Assert every field: `storage[PEACH]=10, storage[COOKED_MEAT]=2`, `water_supply_ml=1000`, `fire_lit=True`, `remaining_fuel_minutes=30`, `total_dirtiness=60`, `live_carcass_count=1`, `placed_resting_spots={"aldric": BED_ROLL}`. A single composite assertion here is more valuable than separately testing each field in isolation — it proves the snapshot is consistent with the live state at the moment of the call.

*`BaseSummary` is frozen.* Construct a `BaseSummary` and attempt to assign to any field. Assert `FrozenInstanceError` is raised. AI Coordinator receives this snapshot and must not be able to mutate shared state through it.
