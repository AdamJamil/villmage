# villager_state — Diff Plan

Five diffs. The subsystem splits across two files and five domain areas: shared types in game_types, the data model and simple mutators, health and passive decay, derived stat computation, and prompt-facing description output.

---

## DIFF 1 of 5

**TITLE:** `[villager_state][1/5]` game_types additions

**DESCRIPTION:**
Add four new objects to the existing `villmage/game_types.py` (alongside `ItemType`, `RestingSpotType`, and `ITEM_WEIGHT_G` added in world_state diff 1):

- `CraftableItem` — 3-member enum (`SATCHEL=1`, `BED_ROLL=2`, `COT=3`) per ATTR-140. A `total_minutes: int` property returns the per-item crafting budget (SATCHEL=480, BED_ROLL=300, COT=960, from CONST-141/142/143). Action System reads this when scheduling completion; VillagerState reads it when checking whether in-progress crafting is done.

- `ActionCategory` — 18-member enum covering every category of villager activity per the spec. An `is_away: bool` property returns `True` iff the category is `EXPLORING` or `HAULING` (BHVR-284). Centralising the "at base" check here ensures every caller (Simulation Engine, Conversation System, Action System) agrees on the definition without hard-coding the two-element set.

- `WorldContext` — frozen dataclass with five fields: `base_calories: int`, `total_fuel_minutes: int`, `villager_count: int`, `total_dirtiness: int`, `current_game_time: int`. Bundling these five similarly-typed integers prevents argument-order mistakes at `compute_stats` call sites and lets the type checker catch missing fields. Frozen so callers cannot accidentally mutate context they pass in.

- `StatName` — `Literal["wakefulness", "satiation", "hydration", "social_joy", "connectedness", "cleanliness"]` type alias. The six mutable raw stats on `VillagerState`. Used by `modify_stat` to give callers a typed dispatch surface; the implementation's `match stat:` is verified exhaustive by Pyre in strict mode.

These four additions belong in `game_types.py` rather than `villager_state.py` because `CraftableItem` and `ActionCategory` are also consumed by Action System and Simulation Engine — centralising them here breaks potential circular imports (villager_state_impl.md design note).

**TEST PLAN:**

*`tests/test_game_types.py`* (extending the existing test file from world_state diff 1)

*CraftableItem completeness.* Assert `len(CraftableItem) == 3` and each value exactly: `SATCHEL=1`, `BED_ROLL=2`, `COT=3`. Integer values are serialised in checkpoint files; a wrong assignment silently corrupts replay.

*CraftableItem.total_minutes.* Assert all three exactly: `SATCHEL → 480`, `BED_ROLL → 300`, `COT → 960`. These are the schedule lengths; an off-by-one here causes crafting jobs to finish early or run indefinitely.

*ActionCategory completeness.* Assert `len(ActionCategory) == 18` and every member's integer value. Exhaustive check because every new category added later must be consciously accounted for in `is_away`.

*ActionCategory.is_away — True cases.* Assert `ActionCategory.EXPLORING.is_away is True` and `ActionCategory.HAULING.is_away is True`. Only two values are away; getting either wrong silently includes/excludes villagers from conversations and on-base actions.

*ActionCategory.is_away — False for all others.* Iterate every `ActionCategory` member except EXPLORING and HAULING; assert each `.is_away is False`. A wildcard-based check like `category not in {EXPLORING, HAULING}` in callers depends on this property being correct for all 16 non-away categories.

*WorldContext — construction and field access.* Construct a `WorldContext` with distinct values for each field and read them back. Verify frozen: attempt assignment to any field and assert `FrozenInstanceError`.

*WorldContext — field types.* Construct with all-zero values and verify `isinstance` checks: `base_calories: int`, `total_fuel_minutes: int`, `villager_count: int`, `total_dirtiness: int`, `current_game_time: int`. Pyre catches most of this statically, but the runtime check documents the contract for readers of the test.

---

## DIFF 2 of 5

**TITLE:** `[villager_state][2/5]` Data types and simple mutators

**DESCRIPTION:**
Create `villmage/villager_state.py`. No formula-heavy logic yet — only the data model and the mutators whose correctness is purely about invariants, not computation.

Internal types added:

- `DecayResult` — frozen dataclass (`health_zero: bool`, `wakefulness_zero: bool`). Returned by `apply_decay`; named booleans enforce explicit caller handling.
- `MoodSubcomponent` — 5-member enum (`SOCIAL_JOY=1`, `CONNECTEDNESS=2`, `CLEANLINESS=3`, `BASE_CLEANLINESS=4`, `REST=5`). Declaration order determines tie-breaking in `_dominant_mood_input`.
- `HealthSubcomponent` — 3-member enum (`WAKEFULNESS=1`, `SATIATION=2`, `HYDRATION=3`). Same tie-breaking semantics.
- `CraftingProgress` — frozen dataclass (`item: CraftableItem`, `minutes_spent: int`). Snapshot of an in-progress crafting job; materials already consumed before this is created.
- `CurrentAction` — frozen dataclass (`category: ActionCategory`, `detail: str | None`, `completion_timestamp: int`). What the villager is doing right now; written by Action System, read by AI Coordinator.
- `ComputedStats` — frozen dataclass with all 13 fields from the spec (four aggregate scores, six component percentages, `base_cleanliness`, and the two dominant subcomponent fields). Returned by `compute_stats` added in diff 4; declared here so the type is available to callers without depending on the formulas.

`VillagerState` class:

- `__init__(villager_id: str)` — initialises all fields to starting values per CONST-273–277 and BHVR-278: `wakefulness=100`, `satiation=1800`, `hydration=6000`, `social_joy=20`, `connectedness=100.0`, `cleanliness=100`, empty inventory, all optional fields `None`, `awake_minutes_since_compaction=0`, `is_alive=True`.
- `modify_inventory(item: ItemType, delta: int)` — adds or subtracts units; raises `ValueError` if result would be negative. Absent keys treated as 0.
- `modify_stat(stat: StatName, delta: float)` — dispatches via `match stat:` to apply a signed delta and clamp to that stat's valid range: wakefulness 0–100, satiation 0–1800, hydration 0–6000, social_joy 0–100, connectedness 0–100, cleanliness 0–100.
- `is_over_encumbered() -> bool` — total inventory weight > carry capacity. Carry capacity is `40_000g` base plus `30_000g` if inventory contains at least one SATCHEL (CONST-206, BHVR-266). Multiple satchels do not stack.
- `can_fit(item: ItemType) -> bool` — remaining capacity (`carry_capacity - total_weight`) ≥ `ITEM_WEIGHT_G[item]`.
- All simple setters with no logic beyond assignment: `set_crafting_state`, `set_current_action`, `set_sleep_spot`, `set_last_rest_time`, `reset_compaction_counter`.

**TEST PLAN:**

*`tests/test_villager_state.py`*

*Starting values.* Construct `VillagerState("aldric")`. Assert every starting field exactly: `wakefulness==100`, `satiation==1800`, `hydration==6000`, `social_joy==20`, `connectedness==100.0`, `cleanliness==100`, `inventory=={}`, `sleep_spot_claim is None`, `crafting_in_progress is None`, `current_action is None`, `last_rest_game_time is None`, `awake_minutes_since_compaction==0`, `is_alive is True`. This is the spec's CONST-273–277 and BHVR-278 encoded exactly; a wrong starting value produces drift throughout every run.

*modify_inventory — add items.* Start with empty inventory. `modify_inventory(PEACH, 5)` → `inventory[PEACH] == 5`. `modify_inventory(PEACH, 3)` → 8. Absent key treated as 0.

*modify_inventory — remove items.* From 8, `modify_inventory(PEACH, -3)` → 5. From 5, `modify_inventory(PEACH, -5)` → 0 (zero is valid, no error).

*modify_inventory — negative invariant.* From 5, `modify_inventory(PEACH, -6)` raises `ValueError`.

*modify_inventory — multiple item types are independent.* Add PEACH and LOG; assert each query returns its own count.

*modify_stat — delta application for each stat.* For each of the six stats, apply a positive then a negative delta and assert the result. This verifies the `match` dispatch reaches all six branches.

*modify_stat — upper clamp.* `modify_stat("wakefulness", 50)` from 100 stays at 100 (not 150). Test each stat at its own ceiling.

*modify_stat — lower clamp.* `modify_stat("satiation", -2000)` from 1800 clamps to 0 (not negative). Test each stat.

*modify_stat — float precision on connectedness.* `connectedness` is stored as `float`. Apply `modify_stat("connectedness", -100/48)` 48 times; assert result is ≥ 0 and approximately `100 - 100 = 0.0` within a small epsilon. Repeated subtraction of an irrational fraction must not go negative through accumulated rounding.

*is_over_encumbered — base capacity.* Inventory with total weight = 40_000g: `is_over_encumbered() is False`. Weight 40_001g: `True`.

*is_over_encumbered — satchel bonus.* Add 1 SATCHEL to inventory (0g weight). Now capacity = 70_000g. Fill inventory to 70_000g: `False`. 70_001g: `True`.

*is_over_encumbered — satchel does not stack.* Add 2 SATCHELs. Assert capacity is still 70_000g (not 100_000g). Multiple satchels must not compound per BHVR-266.

*can_fit — item that fits.* Empty inventory (40_000g free). `can_fit(PEACH)` where PEACH=150g → `True`.

*can_fit — item that does not fit.* Fill inventory to 39_900g. `can_fit(LOG)` where LOG=18_000g → `False`. `can_fit(PEACH)` where PEACH=150g → `True`. Tests the boundary is per-item, not global.

*can_fit — exact boundary.* Fill to exactly `40_000 - 150 = 39_850g`. `can_fit(PEACH)` → `True`. Fill one more gram: `can_fit(PEACH)` → `False`.

*Simple setters — round-trip.* Call `set_crafting_state`, `set_current_action`, `set_sleep_spot`, `set_last_rest_time` with non-None values, then with `None`. Assert the field reflects the value after each call.

*reset_compaction_counter.* Set `awake_minutes_since_compaction` to a non-zero value (by direct construction or via apply_decay in diff 3). Call `reset_compaction_counter()`. Assert `awake_minutes_since_compaction == 0`.

---

## DIFF 3 of 5

**TITLE:** `[villager_state][3/5]` Health and passive decay

**DESCRIPTION:**
Add `_compute_health` and `apply_decay` to `VillagerState`.

`_compute_health() -> float` — computes `(max(0.1, w) * (32^(s-1) - 1/32)^3 * h^3)^(1/9)` where `w = wakefulness/100`, `s = satiation/1800`, `h = hydration/6000` (CONST-187). Returns a float in [0, 1]. Private: called only by `apply_decay` and `compute_stats`.

`apply_decay(elapsed_hours: float) -> DecayResult` — applies all passive stat drain for the given interval and returns threshold crossings. Drain rules (from the impl spec):
- `wakefulness -= 3 * elapsed_hours` only if not sleeping (`current_action is None or category != SLEEPING`)
- `satiation -= 18 * elapsed_hours` always
- `hydration -= 120 * elapsed_hours` always
- `connectedness -= (100/48) * elapsed_hours` always
- `cleanliness -= 2 * elapsed_hours` always
- `social_joy`: unchanged

All stats floor at 0 after drain. Awake-time tracking: if not sleeping, adds `elapsed_hours * 60` to `awake_minutes_since_compaction`.

Threshold detection (order matters): first check wakefulness (was >0, is now 0 → set `wakefulness_zero=True`). Then call `_compute_health()` on the post-drain values; if result ≤ 0, set `health_zero=True`. Both flags can be True simultaneously. Simulation Engine must check `health_zero` first per the spec's death-before-forced-sleep rule.

**TEST PLAN:**

*`tests/test_villager_state.py`*

*Drain rates — each stat for 1 hour, awake.* From starting values with no current action, call `apply_decay(1.0)`. Assert wakefulness=97, satiation=1782, hydration=5880, connectedness≈97.917 (100 - 100/48), cleanliness=98, social_joy=20 (unchanged). These six checks encode the six rates from CONST-193, CONST-197, CONST-199, CONST-179, CONST-182, and CONST-176 respectively.

*Wakefulness does not drain during sleep.* Set `current_action` to a `CurrentAction` with `category=ActionCategory.SLEEPING`. Call `apply_decay(1.0)`. Assert `wakefulness == 100` (unchanged). Assert all other draining stats still drained. Sleep must suppress only wakefulness decay.

*Social joy never drains.* Call `apply_decay(24.0)` on a villager with `social_joy=50`. Assert `social_joy == 50`. Social joy is only changed by conversations (Conversation System); decay must never touch it.

*All stats floor at 0, never go negative.* Start with `wakefulness=1, satiation=10, hydration=50, connectedness=1.0, cleanliness=1`. Call `apply_decay(100.0)`. Assert all six stats are exactly 0. No negative values.

*awake_minutes_since_compaction — awake.* Start at 0. `apply_decay(2.0)` while awake. Assert `awake_minutes_since_compaction == 120`.

*awake_minutes_since_compaction — sleeping.* Set action to SLEEPING. `apply_decay(2.0)`. Assert `awake_minutes_since_compaction == 0` (no increment during sleep).

*awake_minutes_since_compaction — accumulates across calls.* Three calls of `apply_decay(1.0)` while awake. Assert `awake_minutes_since_compaction == 180`.

*wakefulness_zero — triggered exactly at crossing.* Set `wakefulness=3`. `apply_decay(1.0)` drains exactly 3. Assert `result.wakefulness_zero is True`. Set `wakefulness=4`. `apply_decay(1.0)` drains 3 → wakefulness=1. Assert `result.wakefulness_zero is False`.

*wakefulness_zero — not re-triggered if already 0.* Set `wakefulness=0`. `apply_decay(1.0)`. Assert `wakefulness_zero is False` (already at 0 before the call; no crossing occurred).

*health_zero — triggered by satiation hitting 0.* Set `satiation=18` (1 hour of drain), `hydration=6000`, `wakefulness=100`. `apply_decay(1.0)`. Satiation → 0, health formula gives 0 (when s=0 the middle term collapses). Assert `result.health_zero is True`.

*health_zero — triggered by hydration hitting 0.* Set `hydration=120` (1 hour of drain), `satiation=1800`, `wakefulness=100`. `apply_decay(1.0)`. Hydration → 0, health=0. Assert `result.health_zero is True`.

*health_zero — wakefulness=0 alone does not kill.* Set `wakefulness=3`, `satiation=1800`, `hydration=6000`. `apply_decay(1.0)`. Wakefulness → 0. `max(0.1, 0.0)=0.1` keeps health nonzero. Assert `result.health_zero is False` and `result.wakefulness_zero is True`.

*Both flags simultaneously.* Set `wakefulness=3`, `satiation=18`, `hydration=6000`. `apply_decay(1.0)`. Wakefulness → 0 (crossing) and satiation → 0 (health = 0). Assert both `health_zero is True` and `wakefulness_zero is True`. This scenario is the one where Simulation Engine's "death before forced sleep" ordering matters.

*Health formula — full values → 1.0.* After construction (all starting values), call `_compute_health()` indirectly by checking the formula result: set up a villager with w=100, s=1800, h=6000 and verify that `apply_decay(0.0)` returns `health_zero=False` (health is positive). Then cross-check by computing the formula manually: `(max(0.1,1.0) * (32^0 - 1/32)^3 * 1^3)^(1/9) = (1 * (1 - 0.03125)^3 * 1)^(1/9)` ≈ 0.9898. The exact value isn't needed; confirming it's > 0 and < 1.0 for full values is enough.

*Health formula — numeric spot-check.* Set wakefulness=50, satiation=900, hydration=3000 (all at 50%). Compute expected: w=0.5, s=0.5, h=0.5. `32^(0.5-1) = 32^(-0.5) ≈ 0.1768`. Middle term = `0.1768 - 0.03125 = 0.1456`. `(0.5 * 0.1456^3 * 0.5^3)^(1/9)`. Calculate and assert the value returned by `compute_stats` (added in diff 4) or via a controlled `apply_decay` scenario matches within 1e-6.

---

## DIFF 4 of 5

**TITLE:** `[villager_state][4/5]` Derived stat computation

**DESCRIPTION:**
Add `compute_stats`, `_dominant_mood_input`, and `_dominant_health_input` to `VillagerState`.

`compute_stats(ctx: WorldContext) -> ComputedStats` — assembles all 13 fields of `ComputedStats` from raw state and the supplied `WorldContext`:

**Component percentages:** `wakefulness_pct = wakefulness/100`, `satiation_pct = satiation/1800`, `hydration_pct = hydration/6000`, `social_joy_pct = social_joy/100`, `connectedness_pct = connectedness/100`, `cleanliness_pct = cleanliness/100`, `base_cleanliness = max(0, 1 - total_dirtiness/100)` (CONST-280).

**Health:** delegates to `_compute_health()`.

**Mood** (CONST-172): `sj`, `cn`, `cl`, `bc` are the four scaled components; `r = (current_game_time - last_rest_game_time) / 60.0` if `last_rest_game_time` is set, else `999.0`. Formula: `min(1.0, 0.5 * (0.5*sj + 0.2*cn + 0.2*cl + 0.1*bc) + 0.5 * (sj^10 * cn^4 * cl^4 * bc^2)^(1/22) + (0.3/5) * max(0, 5 - r))`.

**Safety** (CONST-202/204/205): `inv_calories = inventory.get(PEACH,0)*60 + inventory.get(COOKED_MEAT,0)*800`. `food_safety = ((inv_calories/2200) + (1/villager_count)*(base_calories/2200)) / 5`. `fire_safety = (total_fuel_minutes/480) / 5`. `safety = (food_safety + fire_safety) / 2`. Not clamped; can exceed 1.0.

**Well-being** (CONST-169): `min(1.0, (mood^2 * health^3 * max(0.3, safety))^(1/7))`. Clamped because safety is uncapped.

**Dominant subcomponents:** delegates to `_dominant_mood_input` and `_dominant_health_input`.

`_dominant_mood_input(sj, cn, cl, bc, r) -> MoodSubcomponent` — computes the partial derivative magnitude for each of the five mood inputs at the given scaled values. For {sj, cn, cl, bc}: numerical finite difference with ε=1e-4 (perturb up by ε, measure mood change). For REST: analytical magnitude = `0.06` when `r < 5` else `0`. Returns the enum with largest absolute magnitude; ties broken by declaration order (`SOCIAL_JOY` before `CONNECTEDNESS` before `CLEANLINESS` before `BASE_CLEANLINESS` before `REST`).

`_dominant_health_input(w, s, h) -> HealthSubcomponent` — same approach: perturb each of {w, s, h} by ε=1e-4 numerically. Returns the enum with largest partial derivative magnitude; ties broken by declaration order.

**TEST PLAN:**

*`tests/test_villager_state.py`*

*compute_stats — component percentages.* Start from defaults (all-max stats, no rest, dirtiness=0). Assert all six component percentages equal 1.0. Assert `base_cleanliness == 1.0` at dirtiness=0, and `== 0.0` at `total_dirtiness=100`.

*compute_stats — base_cleanliness floored at 0.* Construct ctx with `total_dirtiness=150` (above cap). Assert `base_cleanliness == 0.0` (not negative).

*compute_stats — mood at full components.* All stats at max, `last_rest_game_time` set so `r=0`. Compute expected mood manually: sj=cn=cl=bc=1. Formula: `0.5*(0.5+0.2+0.2+0.1) + 0.5*(1)^(1/22) + (0.3/5)*5 = 0.5 + 0.5 + 0.3 = 1.3 → min(1.0, 1.3) = 1.0`. Assert `computed.mood == 1.0`.

*compute_stats — mood with no rest buff.* `last_rest_game_time = None` → `r = 999`. The rest term `(0.3/5)*max(0, 5-999) = 0`. Verify mood value doesn't include a rest contribution.

*compute_stats — mood with active rest buff.* Set `last_rest_game_time` so `r = 2.0`. The rest term adds `(0.3/5)*(5-2) = 0.18`. Set all other components to a known value and verify the exact mood delta from the rest term.

*compute_stats — mood collapses when any multiplicative component is 0.* Set `social_joy=0`. The geometric term `sj^10 * ... = 0`. Mood reduces to the linear half only. Assert mood ≈ `0.5 * (0 + 0.2*cn + 0.2*cl + 0.1*bc)` (plus rest term if any). No NaN or crash.

*compute_stats — health matches _compute_health.* Assert `computed.health` equals `_compute_health()` directly (or via a manually computed value). The two must agree or compute_stats is using a different formula than apply_decay's threshold detection.

*compute_stats — safety not clamped.* Set `base_calories` and `total_fuel_minutes` to very large values. Assert `computed.safety > 1.0`. Safety must be uncapped; the well-being clamp handles display.

*compute_stats — well_being clamped at 1.0.* Drive `safety` well above 1.0 with large stockpiles and full mood/health. Assert `computed.well_being == 1.0`. Without the clamp, the formula's result would be > 1.0.

*compute_stats — well_being uses max(0.3, safety).* Set `safety` to 0.0 (no food, no firewood, single villager). The formula uses `max(0.3, 0.0) = 0.3`. Verify `well_being` is computed with the floor, not with 0 (which would collapse well_being to 0 regardless of mood/health).

*_dominant_mood_input — each subcomponent can be dominant.* Construct five scenarios, each designed so exactly one input has a much larger partial derivative than the others:
  - SOCIAL_JOY: set sj near 0 (steep gradient), cn=cl=bc=1, r=999. The power-10 exponent makes sj's gradient dominant at low values.
  - CONNECTEDNESS: sj=1, cn near 0, cl=bc=1, r=999.
  - CLEANLINESS: sj=1, cn=1, cl near 0, bc=1, r=999.
  - BASE_CLEANLINESS: sj=1, cn=1, cl=1, bc near 0, r=999. The power-2 exponent is smallest; need the other components high so bc stands out.
  - REST: set r=0 (magnitude=0.06) and all other components high enough that their numerical PD is < 0.06.
  For each scenario assert the expected dominant enum is returned. These are the only tests that prove the partial derivative logic works correctly end-to-end.

*_dominant_mood_input — REST never selected when r >= 5.* Set r=5 (magnitude=0). Ensure REST is not returned even when all other components also have small gradients (tie broken by declaration order, not REST). Assert return is not `MoodSubcomponent.REST`.

*_dominant_mood_input — tie-breaking by declaration order.* Construct a case where two subcomponents have equal partial derivative magnitude (e.g., at perfectly symmetric values). Assert the earlier-declared enum wins. This is non-trivial to construct precisely; a near-tie within ε of each other is sufficient to verify the tiebreak direction.

*_dominant_health_input — each of WAKEFULNESS, SATIATION, HYDRATION can be dominant.* Three scenarios analogous to the mood tests:
  - WAKEFULNESS: w near 0 (max(0.1, w)=0.1, high gradient), s=h=1.
  - SATIATION: w=1, s near 0 (the 32^(s-1) term has steep gradient at low s), h=1.
  - HYDRATION: w=1, s=1, h near 0 (h^3 term has gradient 3h^2 → large at low h relative to others).
  Assert each scenario returns the expected enum.

*compute_stats — dominant_mood_input and dominant_health_input fields populated.* Assert `computed.dominant_mood_input` is a valid `MoodSubcomponent` and `computed.dominant_health_input` is a valid `HealthSubcomponent`. Smoke test that the fields are actually set.

---

## DIFF 5 of 5

**TITLE:** `[villager_state][5/5]` Stat descriptions and work speed

**DESCRIPTION:**
Add `get_stat_descriptions` and `get_work_speed_modifier` to `VillagerState`.

`get_stat_descriptions(computed: ComputedStats) -> dict[str, str]` — returns prompt-ready VRBTM tier descriptions keyed by stat name. The implementation encodes each stat's thresholds as a `list[tuple[float, str]]` of `(lower_bound, text)` pairs sorted ascending, resolved by a single shared helper that walks the list and returns the text of the first tier whose lower bound is ≤ the value. This helper is the only branching logic; the function body itself contains no conditionals (per the impl spec).

Always included (4 entries): `"well_being"` (VRBTM-170, 5 tiers), `"mood"` (VRBTM-173), `"health"` (VRBTM-188), `"safety"` (VRBTM-291).

Always included — dominant subcomponents: the tier text for `computed.dominant_mood_input` (one of VRBTM-178/180/183/185/292) and `computed.dominant_health_input` (one of VRBTM-194/198/200) are added under their respective stat names.

Conditionally included (BHVR-268/269): `"satiation"` if `satiation_pct < 0.90`; `"hydration"` if `hydration_pct < 0.50`; `"wakefulness"` if `wakefulness_pct < 0.50`.

Deduplication: the result is a `dict` keyed by stat name, so a stat that appears both as a dominant subcomponent and as a conditional inclusion produces only one entry (the same tier text — both paths select the same tier for the same value).

The REST tier text (VRBTM-292) is keyed as `"rest"` and its value for tiering is `max(0, 5 - r) / 5 * 100` (percentage of maximum rest benefit remaining): tier [67-100] = "You've had time to yourself recently. Your head feels clear.", [33-67] = "It's been a while since you've had a moment to just sit and breathe.", [0-33] = "You've been going nonstop without a break. You're wound tight."

`get_work_speed_modifier(computed: ComputedStats) -> float` — returns `1.0` if `computed.health >= 0.5`, else `computed.health * 2.0` (BHVR-189). One line of logic; its own method so Action System can call it without recomputing stats.

**TEST PLAN:**

*`tests/test_villager_state.py`*

*get_stat_descriptions — always-included keys.* Call with any valid `ComputedStats`. Assert `"well_being"`, `"mood"`, `"health"`, `"safety"` all appear in the result. These four keys must always be present regardless of values.

*get_stat_descriptions — dominant subcomponents always included.* Construct a `ComputedStats` with `dominant_mood_input=MoodSubcomponent.CONNECTEDNESS` and `dominant_health_input=HealthSubcomponent.SATIATION`. Assert `"connectedness"` and `"satiation"` appear in the result even when their conditional-include thresholds are not met (connectedness has no conditional threshold; satiation's threshold is < 0.90 — set `satiation_pct=0.95` so the conditional would exclude it, then verify the dominant-subcomponent path still includes it).

*get_stat_descriptions — conditional satiation.* At `satiation_pct=0.89`: assert `"satiation"` included. At `satiation_pct=0.90`: assert `"satiation"` NOT included (unless it's also the dominant health subcomponent).

*get_stat_descriptions — conditional hydration.* At `hydration_pct=0.49`: `"hydration"` included. At `hydration_pct=0.50`: not included (unless dominant).

*get_stat_descriptions — conditional wakefulness.* At `wakefulness_pct=0.49`: `"wakefulness"` included. At `wakefulness_pct=0.50`: not included (unless dominant).

*get_stat_descriptions — deduplication.* Set `dominant_health_input=HealthSubcomponent.SATIATION` and `satiation_pct=0.80` (below 0.90 threshold). Both paths would include `"satiation"`. Assert it appears exactly once in the result dict (dict by definition deduplicates) and the value is the correct tier text for `satiation_pct=0.80`.

*get_stat_descriptions — tier text correctness, well_being.* Test all five tiers at boundary values:
  - `well_being=0.05` → "You feel deathly terrible. Something is horribly wrong."
  - `well_being=0.20` → "Life feels rough. You're struggling."
  - `well_being=0.40` → "Things are okay. Could be better, could be worse."
  - `well_being=0.67` → "You feel pretty good about how things are going."
  - `well_being=0.90` → "Life is good. Really, truly good."
  Test each tier's lower boundary (the minimum value that triggers that tier) exactly.

*get_stat_descriptions — tier text correctness for all 12 stat tables.* For each of the 12 stat description tables (well_being, mood, health, safety, social_joy, connectedness, cleanliness, base_cleanliness, wakefulness, satiation, hydration, rest), test at least two points: one clearly in the bottom tier and one in the top tier. This proves the tier tables are wired correctly without requiring a full boundary-by-boundary sweep of every tier.

*get_stat_descriptions — REST tier at r=0.* `last_rest_game_time = current_game_time` → `r=0` → rest value = 100% → tier [67-100]: "You've had time to yourself recently. Your head feels clear." Assert `"rest"` key maps to that string when REST is the dominant mood input.

*get_stat_descriptions — REST tier at r=3.* r=3 → rest value = `max(0,5-3)/5*100 = 40%` → tier [33-67]: "It's been a while since you've had a moment to just sit and breathe." Assert correct.

*get_stat_descriptions — REST tier at r=4.5.* r=4.5 → rest value = 10% → tier [0-33]: "You've been going nonstop without a break. You're wound tight." Assert correct.

*get_stat_descriptions — values are strings.* Assert every value in the returned dict is a non-empty `str`. The dict must never contain `None`, missing entries, or empty strings — the AI Coordinator joins these directly into prompts.

*get_work_speed_modifier — above threshold.* `computed.health = 0.5` → `1.0`. `computed.health = 1.0` → `1.0`. `computed.health = 0.51` → `1.0`.

*get_work_speed_modifier — below threshold.* `computed.health = 0.4` → `0.8`. `computed.health = 0.0` → `0.0`. `computed.health = 0.25` → `0.5`. Verify the formula `health * 2.0` exactly, not an approximation.

*get_work_speed_modifier — boundary.* `computed.health = 0.5` is exactly 1.0 (the `>= 0.5` condition), not `0.5 * 2 = 1.0` via the other branch. Both branches happen to give 1.0 at exactly 0.5, but the spec says `>= 0.5` → 1.0, so assert the return is 1.0 at this boundary.
