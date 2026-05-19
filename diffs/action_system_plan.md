# action_system — Diff Plan

Thirteen diffs. The subsystem splits across four files (types, timing, eligibility, effects) plus the public api. Within eligibility, diffs follow natural action-group boundaries; within effects, diffs separate start effects from completion-effect domains. The api diff is last because it is pure orchestration over the other three files.

---

## DIFF 1 of 13

**TITLE:** `[action_system][1/13]` types module

**DESCRIPTION:**
Create `villmage/action_system/types.py`. Pure data; no logic, no imports from within the project beyond `game_types`.

Objects defined:

- `CraftableItem` — 3-member `enum.Enum` (`SATCHEL=1`, `BED_ROLL=2`, `COT=3`) per ATTR-140. Kept separate from `ItemType` so signatures requiring a craftable target are statically distinct.
- `ExploreResource` — 5-member `enum.Enum` (`PEACHES=1`, `STICKS=2`, `LEAVES=3`, `LOGS=4`, `BOAR=5`) per the spec block in action_system.md. Comments on each member name the profession gate and mean time (data that lives in `timing.py`).
- `ActionType` — 25-member `enum.Enum`, values 1–25, covering every selectable action discriminant per the enum block in action_system.md.
- `AutobalanceMultipliers` — frozen dataclass with three `float` fields (`exploration_yield_scale=1.0`, `satiation_restore_scale=1.0`, `hydration_restore_scale=1.0`). Owned by Simulation Engine at runtime; passed in via ActionContext. All default to 1.0.
- `ActionContext` — frozen dataclass bundling the five read-only inputs: `villager_id: str`, `canon: CharacterCanon`, `vs: VillagerState`, `all_states: dict[str, VillagerState]`, `ws: WorldState`, `multipliers: AutobalanceMultipliers`.
- `ActiveSleepSegment` — frozen dataclass with `total_minutes: int`, `elapsed_minutes: int`, `modifier: float`.
- `ValidAction` — frozen dataclass with `action_type: ActionType`, `prompt_text: str`, `selectable: bool`, `idx: int | None = None`. The `idx` field is present only when `selectable=True`; eligibility functions leave it `None` (index assignment happens in `build_action_list`).
- `ActionList` — frozen dataclass with `main_actions: tuple[ValidAction, ...]` and `crafter_recipes: tuple[ValidAction, ...]`.
- `SelectedAction` — frozen dataclass with `action_type: ActionType` and ten optional arg fields matching the spec struct exactly.

`ActionContext` is frozen because it is a read-only snapshot passed to every function in eligibility.py and effects.py; accidental mutation in any handler would be a silent correctness bug.

**TEST PLAN:**

*`tests/action_system/test_types.py`*

*Enum completeness.* Assert `len(ActionType) == 25`, `len(ExploreResource) == 5`, `len(CraftableItem) == 3`. Member counts are the primary guard against accidental omission or addition.

*Enum values.* Spot-check representative members against spec values: `ActionType.EAT_PEACH == 1`, `ActionType.TALK_TO == 25`, `ExploreResource.BOAR == 5`, `CraftableItem.COT == 3`. Explicit value assertions catch integer collisions that would silently corrupt LLM idx→action mapping.

*`AutobalanceMultipliers` defaults.* Construct `AutobalanceMultipliers()` with no args. Assert all three fields are exactly `1.0`. The initial multiplier value is the identity; a wrong default causes the entire first day of exploration/restoration to be wrong.

*`ActiveSleepSegment` fields.* Construct with `total_minutes=480, elapsed_minutes=60, modifier=0.8`. Assert readback of all three fields. This is the only constructor used by Simulation Engine.

*`ValidAction` — selectable with idx.* Construct `ValidAction(action_type=ActionType.EAT_PEACH, prompt_text="Eat peach {…}", selectable=True, idx=3)`. Assert `idx == 3`.

*`ValidAction` — non-selectable without idx.* Construct with `selectable=False` and no `idx`. Assert `idx is None`. Non-selectable actions must never carry an index; the LLM must not be able to select them.

*Frozen invariant.* Attempt to assign to a field of any frozen dataclass (`AutobalanceMultipliers`, `ActionContext`, `ActiveSleepSegment`, `ValidAction`, `ActionList`, `SelectedAction`). Assert `FrozenInstanceError` is raised for each. Mutability here would let an eligibility handler corrupt shared context.

---

## DIFF 2 of 13

**TITLE:** `[action_system][2/13]` timing module

**DESCRIPTION:**
Create `villmage/action_system/timing.py`. Pure math; no I/O, no mutation. All four functions are called by both `eligibility.py` (to show modified times in prompts) and `effects.py` (to compute yield on exploration completion).

Functions:

- `work_speed_modifier(health: float) -> float` — returns `1.0` if `health >= 0.5`, else `health * 2` (BHVR-189).
- `apply_duration_modifier(base_minutes: float, work_speed: float, profession_factor: float) -> int` — returns `round(base_minutes * profession_factor / work_speed)` (BHVR-39). `profession_factor` is a multiplier > 1 for slower professions, 1.0 for normal speed.
- `exploration_effective_mean(resource: ExploreResource, profession: Profession, yield_scale: float) -> float` — looks up `BASE_MEAN_MINUTES` per resource (CONST-104; LEAVES = 0.5, STICKS = 2, PEACHES = 10, LOGS = 20, BOAR = 1200), applies the 4× peach penalty for non-GATHERER (BHVR-38), then divides by `yield_scale`. Returns effective mean minutes per item.
- `sample_exploration_yield(effective_mean_minutes: float, work_speed: float, duration_minutes: int, item_weight_kg: float, remaining_capacity_kg: float) -> int` — scales effective mean by `1/work_speed`, samples inter-arrival times via Erlang(k=5) until either `duration_minutes` is exhausted or the next item would exceed `remaining_capacity_kg`, and returns the item count (REQ-99, BHVR-102, BHVR-289).

`BASE_MEAN_MINUTES` is a module-level `dict[ExploreResource, float]` constant.

**TEST PLAN:**

*`tests/action_system/test_timing.py`*

*`work_speed_modifier` — boundary at 0.5.* Assert `work_speed_modifier(0.5) == 1.0` (exactly; this is the "at or above" boundary). Assert `work_speed_modifier(1.0) == 1.0`. Assert `work_speed_modifier(0.0) == 0.0`. Assert `work_speed_modifier(0.25) == 0.5`. The formula `health * 2` below 0.5 is piecewise and the join at 0.5 must be smooth; a discontinuity here breaks work-speed computation for villagers near the boundary.

*`apply_duration_modifier` — identity.* `apply_duration_modifier(60.0, 1.0, 1.0)` → `60`. Verifies baseline before applying any modifiers.

*`apply_duration_modifier` — work speed reduction.* `apply_duration_modifier(60.0, 0.5, 1.0)` → `120`. At half work speed, duration doubles.

*`apply_duration_modifier` — profession factor.* `apply_duration_modifier(60.0, 1.0, 2.0)` → `120`. Profession factor slows similarly.

*`apply_duration_modifier` — both factors.* `apply_duration_modifier(60.0, 0.5, 2.0)` → `240`. Combined multiplicative effect.

*`apply_duration_modifier` — rounding.* `apply_duration_modifier(61.0, 1.0, 1.0)` → `61`. `apply_duration_modifier(60.0, 1.0, 1.5)` → `90`. Confirm `round()` behavior, not `int()` truncation.

*`exploration_effective_mean` — base means per resource.* For GATHERER profession with `yield_scale=1.0`, assert: LEAVES → 0.5, STICKS → 2.0, PEACHES → 10.0, LOGS → 20.0, BOAR → 1200.0. These are CONST-104 values; any mismatch corrupts every exploration yield calculation.

*`exploration_effective_mean` — 4× peach penalty for non-GATHERER.* Use WOODCUTTER profession. Assert `exploration_effective_mean(PEACHES, WOODCUTTER, 1.0) == 40.0` (10 × 4). Assert `exploration_effective_mean(PEACHES, GATHERER, 1.0) == 10.0` (no penalty). BHVR-38 is profession-specific; all six non-GATHERER professions should produce 40.0.

*`exploration_effective_mean` — yield_scale.* Assert `exploration_effective_mean(STICKS, GATHERER, 2.0) == 1.0` (base 2.0 / scale 2.0). Assert `exploration_effective_mean(STICKS, GATHERER, 0.5) == 4.0`. Autobalancing scales effective mean inversely.

*`sample_exploration_yield` — zero capacity.* Assert `sample_exploration_yield(2.0, 1.0, 240, 0.5, 0.0) == 0`. No capacity means no items regardless of duration; BHVR-102.

*`sample_exploration_yield` — capacity exactly one item.* Use a very short effective mean (say 1.0 min/item) with very long duration (10000 min) and capacity for exactly one item (weight=0.5, capacity=0.5). Assert result is exactly 1. The carry-cap truncation must fire at the second item.

*`sample_exploration_yield` — zero duration.* Assert `sample_exploration_yield(2.0, 1.0, 0, 0.5, 100.0) == 0`. Zero time means no finds regardless of capacity.

*`sample_exploration_yield` — statistical mean.* Use `effective_mean_minutes=2.0, work_speed=1.0, duration_minutes=2000, item_weight_kg=0.005, remaining_capacity_kg=1000.0`. Run 200 trials, collect item counts. Assert sample mean is within ±10% of expected mean = `2000 / 2.0 = 1000` items. This verifies the Erlang(k=5) sampler is calibrated correctly, not just that it produces non-negative integers.

*`sample_exploration_yield` — work speed reduces yield.* Same params as statistical test, but `work_speed=0.5`. Expected mean = `2000 / (2.0 / 0.5) = 500`. Assert sample mean (200 trials) is within ±15% of 500. Confirms BHVR-289: duration unchanged but fewer items found.

---

## DIFF 3 of 13

**TITLE:** `[action_system][3/13]` eligibility: eating, drinking, storage, resting spots

**DESCRIPTION:**
Create `villmage/action_system/eligibility.py` with four functions. These cover the simplest eligibility groups — no profession gating, no complex state machines — and establish the file's conventions (function signature, return type, prompt-text format).

Functions added:

- `eating_and_drinking_actions(ctx: ActionContext) -> list[ValidAction]` — includes EAT_PEACH if `PEACH` is in inventory (quantity 1 to inventory count); EAT_COOKED_MEAT if `COOKED_MEAT` is in inventory; DRINK_WATER if `ws.water_supply_ml > 0` (quantity 1 to floor of available liters). Per BHVR-81, BHVR-82, BHVR-83. Prompt text shows quantity range and the "need X to be sated/hydrated" note per VRBTM-35.
- `storage_actions(ctx: ActionContext) -> list[ValidAction]` — TAKE_FROM_BASE for each item type present in `ws.base_storage` with quantity > 0; STORE_IN_BASE for each item type in inventory with quantity > 0. Per BHVR-76, BHVR-77.
- `resting_spot_actions(ctx: ActionContext) -> list[ValidAction]` — PLACE_BED_ROLL if BED_ROLL is in inventory and the villager has no placed resting spot for BED_ROLL; PLACE_COT if COT is in inventory and no COT placed. Per BHVR-92, BHVR-93. Uses `ws.placed_resting_spots` and `vs.sleep_spot_claim` to check. Each placed spot takes 1 minute (CONST-94).
- `rest_action(ctx: ActionContext) -> list[ValidAction]` — always returns a single REST `ValidAction` with the VRBTM-110 prompt text. Always selectable.

All returned `ValidAction` objects have `idx=None`; index assignment is deferred to `build_action_list`.

**TEST PLAN:**

*`tests/action_system/test_eligibility.py`*

Establish a `make_ctx()` test helper that builds a minimal `ActionContext` with a fresh `VillagerState` and `WorldState` and a BUILDER-profession `CharacterCanon` (no profession gates). Tests override specific fields as needed.

*`rest_action` — always present.* Call on a default ctx. Assert exactly one `ValidAction` returned with `action_type == REST` and `selectable == True`. Rest is unconditional; this is a smoke test for the function.

*`eating_and_drinking_actions` — empty inventory, no water.* Assert returns empty list. No items in inventory and no base water means no eating/drinking options.

*`eating_and_drinking_actions` — peach in inventory.* Add 3 PEACH to `vs.inventory`. Assert one `ValidAction` with `action_type == EAT_PEACH`, `selectable == True`, and `prompt_text` contains `"1-3"` (quantity range up to inventory count).

*`eating_and_drinking_actions` — cooked meat in inventory.* Add 2 COOKED_MEAT. Assert one `ValidAction` with `action_type == EAT_COOKED_MEAT` and quantity range `"1-2"`.

*`eating_and_drinking_actions` — both in inventory.* Assert two entries returned, one per food type.

*`eating_and_drinking_actions` — water available.* Set `ws.water_supply_ml = 3000` (3L). Assert DRINK_WATER entry with quantity range `"1-3"`. Quantity is `floor(3000/1000) = 3`.

*`eating_and_drinking_actions` — fractional liters.* Set `ws.water_supply_ml = 1500`. Assert quantity range `"1-1"` (floor(1.5) = 1).

*`eating_and_drinking_actions` — water = 0.* Assert no DRINK_WATER entry.

*`storage_actions` — nothing in base, nothing in inventory.* Assert empty list.

*`storage_actions` — item in base.* Add 5 PEACH to `ws.base_storage`. Assert one TAKE_FROM_BASE entry for PEACH with quantity range `"1-5"`. Confirm no STORE_IN_BASE entries.

*`storage_actions` — item in inventory.* Add 2 RAW_HIDE to `vs.inventory`. Assert one STORE_IN_BASE entry for RAW_HIDE with range `"1-2"`. Confirm no TAKE_FROM_BASE entries.

*`storage_actions` — multiple items in both.* Add PEACH and LOG to base, STICK and LEAVES to inventory. Assert 2 TAKE entries and 2 STORE entries — one per distinct item. Ordering within each group doesn't matter.

*`resting_spot_actions` — no spots, no inventory.* Assert empty list.

*`resting_spot_actions` — bed roll in inventory, no placed spot.* Add BED_ROLL to `vs.inventory`. Assert one PLACE_BED_ROLL entry, selectable. Prompt text includes "1 minute".

*`resting_spot_actions` — cot in inventory, no placed spot.* Same as above for PLACE_COT.

*`resting_spot_actions` — bed roll already placed by this villager.* Add BED_ROLL to inventory but set `ws.placed_resting_spots[ctx.villager_id] = RestingSpotType.BED_ROLL`. Assert PLACE_BED_ROLL is absent (INVR-97: cannot place duplicates).

*`resting_spot_actions` — both in inventory, neither placed.* Add both BED_ROLL and COT to inventory. Assert both PLACE_BED_ROLL and PLACE_COT are present. (Though this combination is unusual, the eligibility check must allow it until the villager places one.)

---

## DIFF 4 of 13

**TITLE:** `[action_system][4/13]` eligibility: exploration

**DESCRIPTION:**
Add `exploration_actions(ctx: ActionContext) -> list[ValidAction]` to `eligibility.py`.

This function is complex enough for its own diff because it weaves together three independent concerns:

1. **Profession gating** — LOGS shown only to WOODCUTTER; BOAR shown only to HUNTER; PEACHES/STICKS/LEAVES shown to all (BHVR-100, ATTR-37). Profession-locked resources are excluded entirely, not shown as non-selectable.
2. **Inventory-space check** — if the villager cannot hold even one unit of the target item, the entry is included as `selectable=False` with the "Cannot perform! No inventory space." note inline (BHVR-103). Otherwise the entry is selectable with duration args `60–240` and the effective mean time shown in the prompt (BHVR-39, VRBTM-101).
3. **Prompt text** — shows the effective mean time per item for each accessible resource, computed via `timing.exploration_effective_mean`. Uses the work-speed-modified mean so the player sees what they will actually experience (BHVR-39).

Carry-capacity math: carry capacity is `CONST-206 (40 kg)` plus `30 kg` if the villager holds a satchel (BHVR-266). Remaining capacity = capacity − current_carried_weight. If `remaining_capacity_kg < item_weight_kg`, the entry is non-selectable.

**TEST PLAN:**

*`tests/action_system/test_eligibility.py`*

*PEACHES/STICKS/LEAVES always appear for any profession (with space).* Use a BUILDER (no gate). Give ample inventory capacity. Assert all three are selectable. Profession-free resources must appear regardless of who is exploring.

*LOGS requires WOODCUTTER.* Assert LOGS absent for BUILDER, HUNTER, COOK, CRAFTER, GATHERER. Assert LOGS present and selectable for WOODCUTTER with space. A wrong gate here locks or unlocks an action incorrectly for the entire run.

*BOAR requires HUNTER.* Same pattern: absent for all other professions, present and selectable for HUNTER with space.

*4× peach penalty reflected in non-GATHERER prompt text.* Use a BUILDER. Assert the PEACHES entry's `prompt_text` shows `40.0` min/item (base 10 × 4). Use a GATHERER. Assert prompt shows `10.0` min/item. The LLM's decision of how long to explore for peaches depends on seeing the correct time.

*No inventory space — non-selectable entry.* Fill the villager's inventory to exactly at or over capacity (no remaining space for even one peach at 0.15 kg). Assert the PEACHES entry is present with `selectable=False` and `prompt_text` contains the "no inventory space" phrase. Assert the entry has `idx=None`.

*Enough space for exactly one item — selectable.* Set remaining capacity to exactly 0.15 kg (one peach). Assert PEACHES is selectable.

*Satchel expands capacity.* Villager at exactly 40 kg without satchel (would have 0 space for a 0.5 kg STICK). Add a satchel to inventory (BHVR-266). Assert STICKS is now selectable (remaining capacity = 30 kg).

*Multiple satchels do not stack.* Add two satchels. Assert capacity is still `40 + 30 = 70 kg`, not `40 + 60 = 100 kg` (BHVR-266: capped at +30 kg).

*Prompt shows duration range `60–240`.* Assert VRBTM-101 format appears in the prompt text for a selectable exploration entry.

---

## DIFF 5 of 13

**TITLE:** `[action_system][5/13]` eligibility: fire tending, misc actions

**DESCRIPTION:**
Add two functions to `eligibility.py`:

- `fire_tending_actions(ctx: ActionContext) -> list[ValidAction]` — returns ADD_STICKS, ADD_FIREWOOD, and LIGHT_FIRE or EXTINGUISH_FIRE (mutually exclusive per fire state). Per BHVR-113, VRBTM-114. Quantities for ADD_STICKS and ADD_FIREWOOD are `min(available fuel, max addable without exceeding 240 min cap)`. Available fuel = inventory count + base count (BHVR-115 priority is an effects concern; eligibility just needs the total). Fuel remaining is shown inline. If no fuel is available or the cap is already met, ADD_STICKS/ADD_FIREWOOD are omitted. LIGHT_FIRE (10 min) shown when fire is unlit; EXTINGUISH_FIRE when lit.
- `misc_actions(ctx: ActionContext) -> list[ValidAction]` — returns the five misc entries when conditions are met per VRBTM-123: SCRAPE_HIDE if raw hide exists in inventory or base; HAUL_WATER (always; 2h); BUTCHER_CARCASS if at least one live carcass exists in `ws.live_carcasses`; CLEAN_CAMP if `ws.get_total_dirtiness() > 0` (shown with current dirtiness in prompt); SPLIT_LOGS if logs exist in inventory or base.

**TEST PLAN:**

*`tests/action_system/test_eligibility.py`*

*`fire_tending_actions` — no fuel, fire unlit.* Assert no ADD_STICKS, no ADD_FIREWOOD. Assert LIGHT_FIRE present (fire is unlit; fuel queue irrelevant to showing the light option — villager can light an empty fire). Assert no EXTINGUISH_FIRE.

*`fire_tending_actions` — sticks available, fire unlit.* Add 5 STICKs to inventory. Assert ADD_STICKS with quantity range `"1-5"` (5 min would be added; 240-cap not hit). Assert LIGHT_FIRE present. Assert ADD_FIREWOOD absent (none available).

*`fire_tending_actions` — firewood from base, fire lit.* Add 3 FIREWOOD to `ws.base_storage`, set fire lit with 60 min remaining. Available FIREWOOD: 3. Adding 3 more = 60 extra min; 60+60=120 ≤ 240. Assert ADD_FIREWOOD range `"1-3"`. Assert EXTINGUISH_FIRE present. Assert LIGHT_FIRE absent.

*`fire_tending_actions` — 4-hour cap limits quantity.* Fire lit with 200 min remaining. Add 12 FIREWOOD to base. Max addable = floor((240-200)/20) = 2. Assert ADD_FIREWOOD range `"1-2"` (not `"1-12"`). Exceeding the cap (INVR-117) would corrupt the fire state machine.

*`fire_tending_actions` — fuel at cap already.* Fire lit with exactly 240 min remaining. Assert ADD_STICKS and ADD_FIREWOOD both absent (nothing can be added).

*`fire_tending_actions` — fuel remaining shown inline.* Assert `prompt_text` for any fuel-add entry contains the remaining-minutes figure.

*`misc_actions` — raw hide in inventory.* Add 2 RAW_HIDE to inventory. Assert SCRAPE_HIDE present with quantity range `"1-2"`.

*`misc_actions` — raw hide in base only.* Add 3 RAW_HIDE to base_storage. Assert SCRAPE_HIDE present with quantity range `"1-3"`. Combined inventory+base sources per BHVR-122.

*`misc_actions` — haul water always available.* Assert HAUL_WATER always present on any ctx. It has no prerequisite.

*`misc_actions` — butcher requires live carcass.* Without any `ws.live_carcasses`, assert BUTCHER_CARCASS absent. Add one via `ws.add_carcass(0)`. Assert BUTCHER_CARCASS present.

*`misc_actions` — clean camp only when dirty.* With `total_dirtiness == 0`, assert CLEAN_CAMP absent. Add dirtiness. Assert CLEAN_CAMP present with current dirtiness value in `prompt_text`. The duration is shown as `<dirtiness> minutes` per VRBTM-123.

*`misc_actions` — split logs requires logs.* No logs: SPLIT_LOGS absent. Add 2 LOG to base: SPLIT_LOGS present with quantity `"1-2"`.

---

## DIFF 6 of 13

**TITLE:** `[action_system][6/13]` eligibility: crafting, cooking

**DESCRIPTION:**
Add two functions to `eligibility.py`:

- `crafting_actions(ctx: ActionContext) -> list[ValidAction]` — for CRAFTER villagers only. Always returns all three recipes (SATCHEL, BED_ROLL, COT) regardless of material availability (BHVR-144), as `selectable=False` with missing-materials note when materials are lacking. Materials are checked across inventory + base (BHVR-122). If `vs.crafting_in_progress` is set, also returns CONTINUE_CRAFTING with `minutes_to_spend_now` range `60` to remaining minutes. Returns empty list for non-CRAFTER villagers.
- `cooking_actions(ctx: ActionContext) -> list[ValidAction]` — for COOK villagers only. If `vs.cooking_paused` is set, returns FINISH_COOKING (non-selectable if fire is out). Otherwise returns COOK_MEAT if raw meat is available (inventory + base) and fire is lit; shown as non-selectable if fire is out (BHVR-285, CONST-147). Returns empty list for non-COOK villagers.

Material availability for satchel (CONST-141): 1 processed hide. Bed roll (CONST-142): 1 processed hide, 400 leaves. Cot (CONST-143): 5 logs, 25 sticks, 4 processed hide, 400 leaves.

**TEST PLAN:**

*`tests/action_system/test_eligibility.py`*

*`crafting_actions` — non-CRAFTER.* BUILDER profession. Assert empty list. Crafting is profession-locked.

*`crafting_actions` — CRAFTER, no materials.* Assert all three recipes present with `selectable=False`. BHVR-144 mandates they appear even when unmakeable; failing to show them removes a key piece of long-term planning information from the LLM.

*`crafting_actions` — CRAFTER, satchel materials met.* Add 1 PROCESSED_HIDE to inventory. Assert SATCHEL is `selectable=True`. Assert BED_ROLL still `selectable=False` (no leaves). Assert COT still `selectable=False`.

*`crafting_actions` — CRAFTER, bed roll materials met.* Add 1 PROCESSED_HIDE + 400 LEAVES. Assert BED_ROLL `selectable=True`.

*`crafting_actions` — CRAFTER, cot materials met.* Add 5 LOG + 25 STICK + 4 PROCESSED_HIDE + 400 LEAVES. Assert COT `selectable=True`. All four materials must be present simultaneously; missing any one makes it `selectable=False`.

*`crafting_actions` — materials span inventory and base.* Satchel needs 1 PROCESSED_HIDE. Put 0 in inventory, 1 in base. Assert SATCHEL `selectable=True`. Confirms BHVR-122 source pooling.

*`crafting_actions` — crafting_in_progress.* Set `vs.crafting_in_progress = (CraftableItem.BED_ROLL, 120)` (120 min spent; total = 300 min; remaining = 180). Assert CONTINUE_CRAFTING present with `selectable=True` and `minutes_to_spend_now` range `"60-180"`. Also assert the three recipe entries still appear (BHVR-144 always shows them).

*`cooking_actions` — non-COOK.* Assert empty list.

*`cooking_actions` — COOK, no raw meat.* Assert empty list even with fire lit.

*`cooking_actions` — COOK, raw meat available, fire lit.* Add 2 RAW_MEAT to inventory, set fire lit. Assert COOK_MEAT present, `selectable=True`, prompt shows "30 m".

*`cooking_actions` — COOK, raw meat available, fire out.* Same but fire unlit. Assert COOK_MEAT present, `selectable=False`. The entry is shown as a non-option (the LLM knows cooking would happen if the fire were lit).

*`cooking_actions` — cooking_paused, fire relit.* Set `vs.cooking_paused = True`, fire lit. Assert FINISH_COOKING present, `selectable=True`. COOK_MEAT must not appear alongside FINISH_COOKING (BHVR-285).

*`cooking_actions` — cooking_paused, fire still out.* Set `vs.cooking_paused = True`, fire unlit. Assert FINISH_COOKING present, `selectable=False`.

---

## DIFF 7 of 13

**TITLE:** `[action_system][7/13]` eligibility: sleeping, washing, conversation, action list assembly

**DESCRIPTION:**
Add four functions to `eligibility.py` and complete the module:

- `sleeping_actions(ctx: ActionContext) -> list[ValidAction]` — always returns GO_TO_SLEEP with hours range `4–12` (BHVR-152).
- `washing_action(ctx: ActionContext) -> list[ValidAction]` — returns WASH_UP if `ws.water_supply_ml >= 500` (VRBTM-164, CONST-165). Otherwise empty.
- `conversation_actions(ctx: ActionContext) -> list[ValidAction]` — returns one TALK_TO entry per other villager who is at base and awake and not on an away action. "At base" = `all_states[id].current_action` is not EXPLORE or HAUL_WATER; "awake" = `all_states[id].wakefulness > 0` (BHVR-43, BHVR-284). Dead villagers are excluded (absent from `all_states`).
- `build_action_list(ctx: ActionContext) -> ActionList` — calls all ten eligibility functions, collects results, splits crafter recipes into the `crafter_recipes` field, assigns sequential 1-based `idx` to selectable entries (main_actions first, then crafter_recipes, per the index-assignment rule in action_system.md), and returns an `ActionList`.

Index-assignment rule: iterate `main_actions` (in the order produced by concatenating all non-recipe eligibility functions), skip `selectable=False` entries, assign 1, 2, 3, … Then continue the same counter through `crafter_recipes`. Only selectable entries receive an `idx`; non-selectable entries keep `idx=None`.

**TEST PLAN:**

*`tests/action_system/test_eligibility.py`*

*`sleeping_actions` — always present.* Assert one GO_TO_SLEEP entry on any ctx, selectable, prompt contains "4-12".

*`washing_action` — below threshold.* Set `water_supply_ml = 499`. Assert empty list.

*`washing_action` — at threshold.* Set `water_supply_ml = 500`. Assert WASH_UP present, selectable. Threshold is inclusive (CONST-165 says "costs 500 mL" — if exactly 500 is available, the action is doable).

*`conversation_actions` — no other villagers.* Empty `all_states`. Assert empty list.

*`conversation_actions` — other villager at base, awake.* Add one other villager with `wakefulness=50` and `current_action=REST`. Assert one TALK_TO entry for that villager.

*`conversation_actions` — other villager sleeping.* Set `wakefulness=0`. Assert TALK_TO absent (BHVR-284: active participation requires awake).

*`conversation_actions` — other villager exploring.* Set `current_action=EXPLORE`. Assert TALK_TO absent (away action).

*`conversation_actions` — other villager hauling.* Set `current_action=HAUL_WATER`. Assert TALK_TO absent.

*`conversation_actions` — multiple villagers, mixed availability.* Three others: one at base+awake, one exploring, one sleeping. Assert exactly one TALK_TO entry (only the at-base+awake one).

*`build_action_list` — index assignment: sequential across main+crafter.* Construct a ctx with a CRAFTER who has all crafting materials and some food/fire/misc. Manually count selectable entries in main and crafter sections. Assert that the `idx` values form the exact sequence `1, 2, 3, …` without gaps, covering both sections in order. Non-selectable entries must have `idx=None`.

*`build_action_list` — non-selectable entries have no idx.* Fill inventory to capacity (exploration entries become non-selectable). Assert those entries have `idx=None` and that the selectable entries around them still have consecutive indices (no gap in the count).

*`build_action_list` — crafter recipes in separate section.* Assert `action_list.crafter_recipes` contains only recipe entries (CRAFT_NEW) and `action_list.main_actions` contains no CRAFT_NEW entries (except CONTINUE_CRAFTING, which goes to main).

*`build_action_list` — CONTINUE_CRAFTING is in main.* Set `vs.crafting_in_progress` for a CRAFTER. Assert CONTINUE_CRAFTING is in `main_actions`, not `crafter_recipes`.

*`build_action_list` — globally unique indices.* Assert all `idx` values across `main_actions + crafter_recipes` form a set with no duplicates and no gaps from 1 to the count of selectable actions.

---

## DIFF 8 of 13

**TITLE:** `[action_system][8/13]` effects: start effects

**DESCRIPTION:**
Create `villmage/action_system/effects.py` with `apply_start_effect` and the start-effect handlers it dispatches to. Only two action types have non-trivial start effects:

- `CRAFT_NEW` — consumes the recipe's materials at job start. Draws from inventory first, then base storage for the remainder (BHVR-122, CONST-141/142/143). Sets `vs.crafting_in_progress = (craftable_item, 0)`. Raises `ValueError` if materials are insufficient (eligibility should prevent this, but the effect must guard it).
- Fire-tending actions (`ADD_STICKS`, `ADD_FIREWOOD`) — deduct the chosen quantity from inventory first, then base for the remainder (BHVR-115); call `ws.add_fire_fuel`.

All other action types have no start effect; `apply_start_effect` is a no-op for them. `CONTINUE_CRAFTING` is explicitly a no-op (materials already consumed at the `CRAFT_NEW` start).

```python
def apply_start_effect(action: SelectedAction, ctx: ActionContext) -> None:
    """Dispatch start-effect handler for the given action type."""
```

**TEST PLAN:**

*`tests/action_system/test_effects.py`*

Establish a `make_ctx()` helper (similar to eligibility tests). Add a `make_action(action_type, **args)` helper that returns a `SelectedAction` with the given type and args.

*CRAFT_NEW — materials from inventory only.* Give crafter 2 PROCESSED_HIDE in inventory. Start SATCHEL (needs 1 hide). Assert `vs.inventory[PROCESSED_HIDE] == 1` after. Assert `vs.crafting_in_progress == (CraftableItem.SATCHEL, 0)`.

*CRAFT_NEW — materials from base when inventory insufficient.* Give crafter 0 hide in inventory, 1 in base. Start SATCHEL. Assert `ws.base_storage[PROCESSED_HIDE] == 0` after.

*CRAFT_NEW — materials split across inventory and base.* Cot needs 4 PROCESSED_HIDE. Put 1 in inventory, 3 in base. Assert 0 remain in inventory and 0 in base after.

*CRAFT_NEW — insufficient materials raises.* No materials at all. Assert `ValueError` raised. The eligibility check normally prevents this, but the effect must not silently corrupt state.

*CRAFT_NEW — sets crafting_in_progress.* Assert `vs.crafting_in_progress.item == CraftableItem.SATCHEL` and `vs.crafting_in_progress.minutes_spent == 0` after a successful start.

*CONTINUE_CRAFTING — no-op.* Set `vs.crafting_in_progress = (SATCHEL, 60)`. Apply start effect for CONTINUE_CRAFTING. Assert crafting_in_progress unchanged and no inventory/base mutations occurred.

*ADD_STICKS — inventory preferred.* Put 3 STICKs in inventory, 5 in base. Apply ADD_STICKS with `quantity=4`. Assert `vs.inventory[STICK] == 0` (all 3 from inventory) and `ws.base_storage[STICK] == 4` (1 from base). Assert fuel queue contains a STICK batch of 4.

*ADD_STICKS — from base when inventory empty.* No inventory sticks, 5 in base. Apply ADD_STICKS with `quantity=3`. Assert base reduced by 3. Assert fuel queue contains STICK batch of 3.

*ADD_FIREWOOD — same inventory-first behavior.* Parallel test for FIREWOOD.

*No-op for all other action types.* Apply start effect for EAT_PEACH, EXPLORE, REST, GO_TO_SLEEP, TALK_TO. Assert no mutation to any field of `vs` or `ws`. A stray start-effect mutation here would silently corrupt state before the action even completes.

---

## DIFF 9 of 13

**TITLE:** `[action_system][9/13]` effects: stat restoration completions

**DESCRIPTION:**
Add completion handlers to `effects.py` for actions whose primary effect is restoring villager stats. Also add `apply_completion_effect`, the dispatcher, initially routing only these types.

Actions covered:

- `EAT_PEACH` — restores `60 * quantity * multipliers.satiation_restore_scale` calories (CONST-86 scaled by autobalance). Caps satiation at 1800.
- `EAT_COOKED_MEAT` — restores `800 * quantity * multipliers.satiation_restore_scale` calories (CONST-87). Caps. Also adds `+5 dirtiness` per meat eaten (CONST-133, one MEAT_SCRAPS unit per piece).
- `DRINK_WATER` — restores `1000 * liters * multipliers.hydration_restore_scale` mL (CONST-85). Caps hydration at 6000. Deducts `liters * 1000` mL from `ws.water_supply_ml`.
- `REST` — no explicit stat change at completion time; the rest buff is timer-based in VillagerState. Completion effect is a no-op (the rest buff activation is handled by Simulation Engine calling `vs.set_rest_timestamp`).
- `GO_TO_SLEEP` — increases wakefulness by `(51/7) * modifier * hours` (BHVR-156, CONST-157). Modifier from `CONST-155` based on sleep spot and fire state at completion. Caps wakefulness at 100.
- `PLACE_BED_ROLL` / `PLACE_COT` — removes the item from inventory, records in `ws.placed_resting_spots`, and sets `vs.sleep_spot_claim`.
- `WASH_UP` — resets `vs.cleanliness = 100` (BHVR-166). Deducts 500 mL from `ws.water_supply_ml`.

**TEST PLAN:**

*`tests/action_system/test_effects.py`*

*`EAT_PEACH` — basic restoration.* Start at 0 satiation, eat 2 peaches with `satiation_restore_scale=1.0`. Assert satiation = 120 cal.

*`EAT_PEACH` — autobalance scale.* Eat 1 peach with `satiation_restore_scale=2.0`. Assert satiation += 120. Scale doubles the per-item restoration.

*`EAT_PEACH` — cap at 1800.* Start at 1700 cal, eat 5 peaches (would be +300). Assert satiation == 1800, not 2000.

*`EAT_COOKED_MEAT` — restoration.* Start at 0, eat 1 cooked meat with scale=1.0. Assert satiation == 800.

*`EAT_COOKED_MEAT` — dirtiness increment.* Eat 2 cooked meats. Assert `ws.get_total_dirtiness()` increased by `2 * 5 = 10` (CONST-133, one MEAT_SCRAPS unit per piece). Meat eating is the primary dirtiness source in normal play; a missing increment silently breaks camp hygiene.

*`DRINK_WATER` — restoration.* Start at 0 hydration, drink 2 L with scale=1.0. Assert hydration == 2000 mL. Assert `ws.water_supply_ml` decreased by 2000.

*`DRINK_WATER` — autobalance scale.* Drink 1 L with `hydration_restore_scale=1.5`. Assert hydration += 1500 mL.

*`DRINK_WATER` — cap at 6000.* Start at 5500 mL, drink 2 L. Assert hydration == 6000, not 7000. Water supply still decreases by 2000 (the action consumed it even if the cap is hit).

*`GO_TO_SLEEP` — modifier from sleep spot + fire.* Test all five modifier combinations from CONST-155: cot (1.0), bed_roll+fire (0.8), bed_roll alone (0.65), fire alone (0.6), neither (0.5). For each, sleep 7 hours and assert wakefulness increase = `51/7 * modifier * 7 = 51 * modifier`. (7 hours with cot should restore exactly 51.)

*`GO_TO_SLEEP` — cap at 100.* Sleep 12 hours with cot modifier. Assert wakefulness == 100, not > 100.

*`PLACE_BED_ROLL` — inventory deducted, spot recorded, claim set.* Add BED_ROLL to inventory. Apply completion. Assert BED_ROLL removed from inventory, `ws.placed_resting_spots[villager_id] == BED_ROLL`, `vs.sleep_spot_claim == BED_ROLL`.

*`PLACE_COT` — same pattern.* Parallel test for COT.

*`WASH_UP` — cleanliness reset.* Set cleanliness to 20. Apply WASH_UP. Assert `vs.cleanliness == 100` and `ws.water_supply_ml` decreased by 500.

---

## DIFF 10 of 13

**TITLE:** `[action_system][10/13]` effects: exploration completion

**DESCRIPTION:**
Add the EXPLORE completion handler to `effects.py` and wire it into `apply_completion_effect`.

On completion:
1. Call `timing.sample_exploration_yield(effective_mean, work_speed, duration_minutes, item_weight_kg, remaining_capacity_kg)` to determine how many items were found.
2. Add the item(s) to `vs.inventory`.
3. Charge the activity calorie cost on top of passive decay: `CONST-106` (50 cal/hour for PEACHES/STICKS/LEAVES) or `CONST-107` (100 cal/hour for LOGS/BOAR). Charge = `rate * (duration_minutes / 60)`. Deduct from `vs.satiation`, floored at 0 (BHVR-288).

For BOAR exploration, the item type is CARCASS; additionally call `ws.add_carcass(current_time)` so the rot timer starts (BHVR-105, CONST-128). The number of carcasses added equals the yield.

`current_time` must be threaded through from `apply_completion_effect`; this diff adds `current_time: int` as a parameter to `apply_completion_effect`.

**TEST PLAN:**

*`tests/action_system/test_effects.py`*

*Peach yield added to inventory.* Patch `timing.sample_exploration_yield` to return 5. Apply EXPLORE for PEACHES with duration=60. Assert `vs.inventory[PEACH] == 5`. The patching avoids stochasticity in the effects test; timing accuracy is tested in test_timing.py.

*Stick yield.* Patch yield=10. Apply EXPLORE for STICKS. Assert `vs.inventory[STICK] == 10`.

*Leaves yield.* Patch yield=20. Apply EXPLORE for LEAVES.

*Log yield.* Patch yield=2. Apply EXPLORE for LOGS. Assert `vs.inventory[LOG] == 2`.

*Boar yield — inventory and carcass tracker.* Patch yield=1. Apply EXPLORE for BOAR with `current_time=500`. Assert `vs.inventory[CARCASS] == 1` and `ws.live_carcasses` has one entry with `arrival_timestamp=500`. The carcass tracker is essential for the rot deadline; missing it causes silent carcass accumulation.

*Boar yield=0 — no carcass added.* Patch yield=0. Assert `ws.live_carcasses` is empty.

*Calorie charge — light exploration.* Start at satiation=1800. Apply EXPLORE for PEACHES with duration=120 (2h). Assert satiation reduced by `50 * 2 = 100` cal (on top of zero passive decay since effects don't decay time). CONST-106: 50 cal/hour.

*Calorie charge — heavy exploration.* Apply EXPLORE for BOAR with duration=60. Assert satiation reduced by `100 * 1 = 100` cal. CONST-107: 100 cal/hour.

*Calorie charge — floor at 0.* Start at satiation=10. Apply EXPLORE for LOGS with duration=1200 (20h × 100 cal/h = 2000 cal charge). Assert satiation == 0, not negative.

*Correct item_weight passed to sampler.* Assert the patch was called with the correct `item_weight_kg` for each resource type (e.g., PEACH = 0.15, LOG = 18.0). A wrong weight fed to the capacity-truncation logic would cause wrong yield even when the Erlang sampler is correct.

---

## DIFF 11 of 13

**TITLE:** `[action_system][11/13]` effects: misc action completions

**DESCRIPTION:**
Add completion handlers for the five misc actions to `effects.py`:

- `SCRAPE_HIDE` — removes `quantity` RAW_HIDE from inventory then base; adds `quantity` PROCESSED_HIDE to inventory (BHVR-124). Each unit takes 1 hour; duration is `quantity * 60`.
- `HAUL_WATER` — adds 20,000 mL to `ws.water_supply_ml` (BHVR-125, CONST-126). Charges 200 cal activity cost (CONST-126).
- `BUTCHER_CARCASS` — removes one CARCASS from inventory, calls `ws.remove_carcass(carcass_id)` for the matching tracker, adds 14 RAW_MEAT to inventory (BHVR-127), decreases `vs.cleanliness` by 50 (CONST-129), charges 200 cal activity cost. The carcass_id is resolved as the earliest live carcass in `ws.live_carcasses` (sort by arrival_timestamp; earliest = most urgent to butcher before rot).
- `CLEAN_CAMP` — calls `ws.clear_dirtiness()` (returns total dirtiness before clear), decreases `vs.cleanliness` by `total_dirtiness / 3` (BHVR-137), floored at 0.
- `SPLIT_LOGS` — removes `quantity` LOG from inventory then base; adds `quantity * 2` FIREWOOD to inventory (BHVR-138, CONST-139).

**TEST PLAN:**

*`tests/action_system/test_effects.py`*

*`SCRAPE_HIDE` — transforms inventory items.* Put 3 RAW_HIDE in inventory. Apply SCRAPE_HIDE quantity=2. Assert `vs.inventory[RAW_HIDE] == 1` and `vs.inventory[PROCESSED_HIDE] == 2`.

*`SCRAPE_HIDE` — draws from inventory then base.* Put 1 RAW_HIDE in inventory, 2 in base. Apply quantity=2. Assert inventory RAW_HIDE == 0, base RAW_HIDE == 1, and inventory PROCESSED_HIDE == 2.

*`HAUL_WATER` — water added.* Apply HAUL_WATER. Assert `ws.water_supply_ml` increased by 20,000.

*`HAUL_WATER` — calorie cost.* Start at satiation=1800. Apply HAUL_WATER. Assert satiation decreased by 200. CONST-126 specifies both duration and calorie cost; only the cost is an effect (duration is start_action's concern).

*`BUTCHER_CARCASS` — produces raw meat.* Add 1 CARCASS to inventory, add carcass tracker. Apply BUTCHER_CARCASS. Assert `vs.inventory[RAW_MEAT] == 14` and CARCASS removed from inventory.

*`BUTCHER_CARCASS` — removes tracker and adds dirtiness.* After butchering, assert `ws.live_carcasses` is empty and `ws.get_total_dirtiness() == 30` (CARCASS_REMAINS from `remove_carcass`).

*`BUTCHER_CARCASS` — cleanliness penalty.* Set `vs.cleanliness = 80`. Apply. Assert `vs.cleanliness == 30` (−50 per CONST-129).

*`BUTCHER_CARCASS` — cleanliness floored at 0.* Set `vs.cleanliness = 30`. Apply. Assert `vs.cleanliness == 0`, not −20.

*`BUTCHER_CARCASS` — calorie cost.* Start at 1800 satiation. Apply. Assert satiation == 1600 (−200).

*`BUTCHER_CARCASS` — chooses earliest carcass.* Add two carcasses at t=100 and t=50. Apply. Assert carcass with arrival_timestamp=50 was removed (not t=100). The earliest carcass is most at risk of rotting.

*`CLEAN_CAMP` — dirtiness zeroed.* Set dirtiness contributors to give total=45. Apply CLEAN_CAMP. Assert `ws.get_total_dirtiness() == 0`.

*`CLEAN_CAMP` — cleanliness penalty proportional.* Total dirtiness = 45 before clean. Penalty = 45/3 = 15. Set cleanliness=80. Assert cleanliness == 65 after.

*`SPLIT_LOGS` — transformation.* Put 3 LOG in inventory. Apply quantity=2. Assert `vs.inventory[LOG] == 1`, `vs.inventory[FIREWOOD] == 4` (+2 per log).

*`SPLIT_LOGS` — sources span inventory and base.* Put 1 LOG in inventory, 3 in base. Apply quantity=3. Assert inventory LOG == 0, base LOG == 1, inventory FIREWOOD == 6.

---

## DIFF 12 of 13

**TITLE:** `[action_system][12/13]` effects: crafting and cooking completions

**DESCRIPTION:**
Add completion handlers for CRAFT_NEW, CONTINUE_CRAFTING, COOK_MEAT, and FINISH_COOKING to `effects.py`.

- `CRAFT_NEW` / `CONTINUE_CRAFTING` — increments `vs.crafting_in_progress.minutes_spent` by `action.minutes_to_spend`. If `minutes_spent >= total_required_minutes`, clears `crafting_in_progress` and adds the finished item to `vs.inventory` (BHVR-267). SATCHEL takes 480 min total (CONST-141), BED_ROLL 300 min (CONST-142), COT 960 min (CONST-143).
- `COOK_MEAT` / `FINISH_COOKING` — removes 1 RAW_MEAT from inventory (then base), adds 1 COOKED_MEAT to inventory. Charges `+3 dirtiness` (one COOKING_SCRAPS unit per CONST-134). These two action types share the same completion logic; FINISH_COOKING is just COOK_MEAT that was previously paused.

**TEST PLAN:**

*`tests/action_system/test_effects.py`*

*`CRAFT_NEW` — partial progress.* Start SATCHEL (total=480 min). Apply CRAFT_NEW completion with `minutes_to_spend=120`. Assert `vs.crafting_in_progress.minutes_spent == 120` and no SATCHEL in inventory yet.

*`CRAFT_NEW` — completion.* Apply CRAFT_NEW with `minutes_to_spend=480` (or accumulate to 480 across two completions). Assert `vs.crafting_in_progress is None` and `vs.inventory[SATCHEL] == 1`.

*`CONTINUE_CRAFTING` — advances progress.* Set `vs.crafting_in_progress = (BED_ROLL, 180)` (300 min total, 180 spent). Apply CONTINUE_CRAFTING with `minutes_to_spend=60`. Assert `minutes_spent == 240`. Not done yet.

*`CONTINUE_CRAFTING` — completes item.* `minutes_spent=240`, apply `minutes_to_spend=60`. Assert `crafting_in_progress is None` and BED_ROLL in inventory.

*`CONTINUE_CRAFTING` — COT completion.* Set up 960-min total, accumulate to completion in two steps. Assert COT added to inventory when done.

*`COOK_MEAT` — removes raw, adds cooked.* Put 2 RAW_MEAT in inventory. Apply COOK_MEAT. Assert `vs.inventory[RAW_MEAT] == 1` and `vs.inventory[COOKED_MEAT] == 1`.

*`COOK_MEAT` — raw meat from base when inventory empty.* Put 0 in inventory, 1 in base. Apply. Assert base RAW_MEAT == 0 and inventory COOKED_MEAT == 1.

*`COOK_MEAT` — dirtiness increment.* Apply COOK_MEAT. Assert `ws.get_total_dirtiness()` increased by 3 (CONST-134: +3 per cook event).

*`FINISH_COOKING` — same effect as COOK_MEAT.* Set `vs.cooking_paused = True`. Apply FINISH_COOKING. Assert same inventory transformation and dirtiness increment as COOK_MEAT. After completion, assert `vs.cooking_paused == False`.

---

## DIFF 13 of 13

**TITLE:** `[action_system][13/13]` public api

**DESCRIPTION:**
Create `villmage/action_system/api.py` — the only file other subsystems import from.

Functions:

- `get_valid_actions(ctx: ActionContext) -> ActionList` — if `vs` is over-encumbered, returns an `ActionList` containing only STORE_IN_BASE entries from `storage_actions` and empty `crafter_recipes` (INVR-208). Otherwise delegates to `eligibility.build_action_list`.
- `start_action(action: SelectedAction, ctx: ActionContext) -> int` — calls `effects.apply_start_effect`, then computes and returns the action duration in minutes. Duration uses `timing.apply_duration_modifier` with `timing.work_speed_modifier(health)` and the appropriate profession factor. Returns `0` for TALK_TO (Simulation Engine routes that to Conversation System with no completion event). The profession factor and base duration per action type live in a module-level `_BASE_DURATION` and `_PROFESSION_FACTOR` table in this file.
- `complete_action(action: SelectedAction, ctx: ActionContext, current_time: int) -> None` — calls `effects.apply_completion_effect(action, ctx, current_time)`. Never called for TALK_TO.
- `adjust_active_sleep(vs: VillagerState, segment: ActiveSleepSegment, new_modifier: float) -> int` — applies wakefulness gain for `segment.elapsed_minutes` at `segment.modifier`, then returns `segment.total_minutes - segment.elapsed_minutes` so Simulation Engine can schedule the remaining sleep under `new_modifier` (BHVR-161, CONST-155). Does not apply wakefulness for the remaining segment — that happens when the new sleep event completes.

**TEST PLAN:**

*`tests/action_system/test_api.py`*

*`get_valid_actions` — normal villager.* Unencumbered CRAFTER with food, fire, and crafting materials. Assert the returned `ActionList` is non-trivially populated and has the correct split between `main_actions` and `crafter_recipes`. This is an integration test of the entire eligibility stack; correctness of individual groups is already proven in test_eligibility.py.

*`get_valid_actions` — over-encumbered.* Set `vs.over_encumbered = True` with multiple item types in base. Assert `main_actions` contains only STORE_IN_BASE entries (one per base item type), `crafter_recipes` is empty, and no other action types appear. INVR-208 is a hard gate; any other action being present when over-encumbered is a serious gameplay bug.

*`get_valid_actions` — over-encumbered with empty base.* Assert `main_actions` is empty and `crafter_recipes` is empty. Even STORE_IN_BASE requires something to store; the only thing disabled here is the eligibility branching logic.

*`start_action` — returns TALK_TO duration of 0.* Assert `start_action(SelectedAction(TALK_TO, target_villager_id="sewalt"), ctx)` returns exactly `0`. This is the Simulation Engine's signal not to schedule a completion event; returning any non-zero value here would hang the conversation flow.

*`start_action` — EAT_PEACH duration.* Eat 3 peaches. Base duration = 3 min. At full health (work_speed=1.0, no profession factor). Assert return == 3.

*`start_action` — duration modified by work speed.* Set health to 0.25 (work_speed = 0.5). EAT_PEACH quantity=2 (base 2 min). Assert return == 4 (doubled by work-speed penalty).

*`start_action` — EXPLORE duration passes through.* EXPLORE uses the villager-chosen duration, not a base formula. Assert `start_action` for EXPLORE with `duration_minutes=120` returns `120` regardless of work speed. The villager explores for their chosen time; only yield is affected by work speed (BHVR-289).

*`complete_action` — delegates to effects.* Apply COMPLETE for EAT_PEACH with 2 peaches in inventory. Assert `vs.satiation` increased. This is an integration smoke test, not a repetition of the detailed effects tests.

*`adjust_active_sleep` — wakefulness applied for elapsed portion.* Start `vs.wakefulness = 0`. Segment: `total=480, elapsed=120, modifier=0.8`. Call `adjust_active_sleep(vs, segment, new_modifier=0.6)`. Expected wakefulness gain = `(51/7) * 0.8 * (120/60)` = `(51/7) * 0.8 * 2 ≈ 11.66`. Assert `vs.wakefulness ≈ 11.66` (within float tolerance). Assert return value == `480 - 120 = 360` (remaining minutes).

*`adjust_active_sleep` — wakefulness capped at 100.* Set `vs.wakefulness = 95`. Segment with large `elapsed_minutes`. Assert `vs.wakefulness == 100` after, not > 100.

*`adjust_active_sleep` — return value is remaining minutes.* Assert the return value is always `segment.total_minutes - segment.elapsed_minutes` regardless of wakefulness cap.
