# Action System — Implementation Details

## Overview

Action System is the action catalog: what a villager can do, when it is legal, how long it takes, and what it does. It owns no persistent state — it reads from Villager State, World State, Character Canon, and the Simulation Engine's current autobalance multipliers, then mutates Villager State and World State as start/completion effects.

Two subsystems call into it:
- **Simulation Engine** — `get_valid_actions`, `start_action`, `complete_action`, `adjust_active_sleep`
- **AI Coordinator** — reads the `ActionList` produced by `get_valid_actions` to format the action prompt

---

## Shared-Type Notes

`ActionType` is the fine-grained action discriminant used by both Action System (dispatch) and AI Coordinator (mapping LLM idx → action). It lives in `action_system/types.py`; AI Coordinator imports it from there.

`ExploreResource` is the set of explorable resources. Also lives in `action_system/types.py` since exploration is a purely action-system concept. AI Coordinator imports it for explore-prompt formatting.

`AutobalanceMultipliers` is owned by Simulation Engine and passed into Action System at call time. It is defined here for clarity of the cross-subsystem contract but should ultimately live wherever Simulation Engine's types are authored.

`ActionContext` bundles the five read-only inputs that most eligibility and effect functions need. All functions in `eligibility.py` and `effects.py` accept it rather than individual parameters, keeping signatures stable as cross-subsystem dependencies evolve.

`ActiveSleepSegment` captures the in-progress sleep state at the moment a fire-state change interrupts it. Passed to `adjust_active_sleep` to avoid a four-number bare-primitive call site.

---

## Core Objects

### ExploreResource

The five things a villager can explore for (CONST-104, BHVR-105). Profession gating: only `HUNTER` can explore for `BOAR`; only `WOODCUTTER` can explore for `LOGS`; any villager can explore for `PEACHES`, `STICKS`, and `LEAVES` (with a `4x` mean-time penalty on `PEACHES` for non-`GATHERER` villagers per BHVR-38).

```thrift
enum ExploreResource {
    PEACHES = 1,   // mean 10m/item; 4x penalty for non-GATHERER
    STICKS  = 2,   // mean 2m/item
    LEAVES  = 3,   // mean 30s/item
    LOGS    = 4,   // mean 20m/item; WOODCUTTER profession only (locked, ATTR-37)
    BOAR    = 5,   // mean 20h/item; HUNTER profession only (locked, ATTR-37)
}
```

---

### ActionType

Fine-grained action discriminant covering every selectable action type. Used by Action System for dispatch and by AI Coordinator to map an LLM-chosen `idx` back to a typed action before constructing `SelectedAction`.

```thrift
enum ActionType {
    // Eating & drinking (BHVR-79 through BHVR-83)
    EAT_PEACH       = 1,
    EAT_COOKED_MEAT = 2,
    DRINK_WATER     = 3,

    // Storage (BHVR-76, BHVR-77)
    TAKE_FROM_BASE  = 4,
    STORE_IN_BASE   = 5,

    // Resting spots (BHVR-92, BHVR-93)
    PLACE_BED_ROLL  = 6,
    PLACE_COT       = 7,

    // Exploration (BHVR-100)
    EXPLORE         = 8,

    // Resting (BHVR-109)
    REST            = 9,

    // Fire tending (BHVR-113)
    ADD_STICKS      = 10,
    ADD_FIREWOOD    = 11,
    LIGHT_FIRE      = 12,
    EXTINGUISH_FIRE = 13,

    // Misc (VRBTM-123)
    SCRAPE_HIDE     = 14,
    HAUL_WATER      = 15,
    BUTCHER_CARCASS = 16,
    CLEAN_CAMP      = 17,
    SPLIT_LOGS      = 18,

    // Crafting — crafter profession only (ATTR-140)
    CRAFT_NEW          = 19,   // starts a new crafting job; CraftableItem specified in args
    CONTINUE_CRAFTING  = 20,   // resumes an in-progress job

    // Cooking — cook profession only (ATTR-146)
    COOK_MEAT       = 21,
    FINISH_COOKING  = 22,   // shown instead of COOK_MEAT when fire went out mid-cook (BHVR-285)

    // Sleeping (BHVR-152)
    GO_TO_SLEEP     = 23,

    // Washing (VRBTM-164)
    WASH_UP         = 24,

    // Conversation (BHVR-43)
    TALK_TO         = 25,
}
```

---

### AutobalanceMultipliers

The three scaling factors written by Simulation Engine at midnight (BHVR-221) and read by Action System when computing action yields and restoration amounts. All start at `1.0` and drift unboundedly (design.md resolution for the bounded-multipliers ambiguity).

```thrift
struct AutobalanceMultipliers {
    1: f64 exploration_yield_scale = 1.0,
        // > 1.0 means higher yield (shorter effective mean time between items);
        // applied as: effective_mean = base_mean * profession_factor / yield_scale
    2: f64 satiation_restore_scale = 1.0,
        // multiplier on calories restored per food item consumed
    3: f64 hydration_restore_scale = 1.0,
        // multiplier on mL restored per liter of water drunk
}
```

---

### ActionContext

Read-only snapshot of all cross-subsystem inputs needed to evaluate action eligibility and apply effects for one villager at one moment. Passed to every function in `eligibility.py` and `effects.py`.

```thrift
struct ActionContext {
    1: string villager_id,
    2: CharacterCanon canon,
    3: VillagerState vs,
    4: map<string, VillagerState> all_states,   // all living villagers, keyed by id
    5: WorldState ws,
    6: AutobalanceMultipliers multipliers,
}
```

---

### ActiveSleepSegment

The in-progress sleep state passed to `adjust_active_sleep` when a fire-state change (extinguish or relight) splits a sleeping villager's night into two segments with different wakefulness modifiers (BHVR-161, CONST-155).

```thrift
struct ActiveSleepSegment {
    1: i32 total_minutes,     // original planned sleep duration
    2: i32 elapsed_minutes,   // time already slept under the current modifier
    3: f64 modifier,          // wakefulness-restore multiplier for the elapsed portion
}
```

---

### ValidAction

One entry in the action menu as it will be presented to the LLM. AI Coordinator renders the full list and assigns the index prefix. Selectable=false entries appear in the prompt but cannot be chosen.

```thrift
struct ValidAction {
    1: optional i32 idx,         // 1-based sequential index; present only when selectable=true;
                                 // globally unique across both main_actions and crafter_recipes sections
    2: ActionType action_type,   // for mapping LLM idx response back to a typed action
    3: string prompt_text,       // fully-formatted VRBTM line, e.g.:
                                 // 'Eat peach {"quantity": int (1-5)} [need 20 to be sated]'
                                 // 'Explore for peaches (40m/item — no inventory space)'
    4: bool selectable,          // false for: crafter recipes with missing materials,
                                 //            exploration targets with no inventory space
}
```

**On `selectable=false` display:** For exploration entries that cannot be started (BHVR-103), the `prompt_text` includes the "Cannot perform! No inventory space." note inline. For crafter recipes (BHVR-144), the `prompt_text` shows the recipe requirements and notes what is missing; these appear in the separate `crafter_recipes` section.

---

### ActionList

The full action menu for one villager at one moment. The two sections are rendered separately in the prompt (VRBTM-123, BHVR-144). Indices are globally sequential across both sections so the LLM always picks a single unambiguous integer.

```thrift
struct ActionList {
    1: list<ValidAction> main_actions,
        // all actions except crafter recipes; includes both selectable and non-selectable
        // exploration entries (the "no inventory space" inline entries)
    2: list<ValidAction> crafter_recipes,
        // empty for non-CRAFTER villagers; includes all three recipes regardless of
        // whether materials are available; selectable=false when materials missing
}
```

**Index assignment rule:** assign `idx` 1, 2, 3, … in the order: iterate `main_actions` skipping `selectable=false`, then iterate `crafter_recipes` skipping `selectable=false`. Only selectable actions receive an idx. Non-selectable entries are rendered without a number.

---

### SelectedAction

The LLM's parsed and typed action choice, constructed by AI Coordinator from the raw `{"idx": N, "args": {...}}` response. Passed to Simulation Engine, which hands it to `start_action`. Only one action_type is active at a time; only the args fields relevant to that type are populated. AI Coordinator validates field population against `action_type` before returning.

```thrift
struct SelectedAction {
    1: ActionType action_type,

    // Item args — used by EAT_PEACH, EAT_COOKED_MEAT, TAKE_FROM_BASE, STORE_IN_BASE,
    //             SPLIT_LOGS, SCRAPE_HIDE, ADD_STICKS, ADD_FIREWOOD
    2: optional ItemType item,      // present for TAKE/STORE (identifies which item)
    3: optional i32 quantity,       // present for all quantity-bearing actions

    // Exploration args — used by EXPLORE
    4: optional ExploreResource resource,
    5: optional i32 duration_minutes,  // 60–240; chosen by villager

    // Crafting args — used by CRAFT_NEW, CONTINUE_CRAFTING
    6: optional CraftableItem craftable_item,  // present for CRAFT_NEW only (CONTINUE_CRAFTING
                                               // infers item from crafting_in_progress)
    7: optional i32 minutes_to_spend,          // 60–480 for CRAFT_NEW; 60–remaining for CONTINUE

    // Sleep args — used by GO_TO_SLEEP
    8: optional i32 hours,    // 4–12

    // Drink args — used by DRINK_WATER
    9: optional i32 liters,   // 1–floor(base water supply)

    // Conversation args — used by TALK_TO
    10: optional string target_villager_id,
}
```

---

---

## File Hierarchy

### `action_system/types.py`

Pure data types for the action system — item and resource enums, action discriminants, autobalance multipliers, the `ActionContext` read-only input bundle, the `ActiveSleepSegment` sleep-state snapshot, and the `ValidAction`/`ActionList`/`SelectedAction` DTOs that flow between Action System, AI Coordinator, and Simulation Engine. No logic; import from here, never the reverse.

### `action_system/eligibility.py`

Per-action-group eligibility checks that inspect Villager State, World State, and Character Canon to produce `ValidAction` entries for one villager at one moment. Each function accepts an `ActionContext` and covers one logical group (eating, exploration, fire tending, crafting, etc.), returning a list of `ValidAction` objects with fully-formatted prompt text and selectability flags already set. Called exclusively by `api.py`.

### `action_system/timing.py`

Duration computation and exploration yield sampling. Contains: modified duration formulas (base time × health work-speed modifier × profession factor), and the Erlang(k=5) sampler used during exploration completion to determine how many items were found. Work-speed modifies exploration yield rate (mean time per item) but does not change the villager's chosen exploration duration — the villager explores for the selected number of minutes as-is, finding fewer items per hour at lower work speeds (BHVR-289). Exploration calorie costs (CONST-106, CONST-107) are charged on top of passive satiation decay (BHVR-288). Called by `eligibility.py` (to show modified times in prompts) and `effects.py` (to compute yield on exploration completion).

### `action_system/effects.py`

Start-effect and completion-effect implementations for every action type. Each action type has its own handler function; `apply_start_effect` and `apply_completion_effect` are thin dispatchers over these handlers. Start effects apply immediately when an action is chosen (e.g., consuming crafting materials at the start of a `CRAFT_NEW` job). Completion effects fire when Simulation Engine pops the scheduled event. All mutations are routed through Villager State and World State APIs — this file owns no state of its own.

### `action_system/api.py`

Public API surface for the Action System: `get_valid_actions`, `start_action`, `complete_action`, and `adjust_active_sleep`. Thin orchestration — delegates eligibility and prompt construction to `eligibility.py`, duration math to `timing.py`, and state mutations to `effects.py`. The only file other subsystems import from.

---

## Object Assignments and Docstrings

### `action_system/types.py`

**`ItemType`** — Enum of every item type in the simulation (STRCT-21: peach, carcass, raw_meat, cooked_meat, raw_hide, processed_hide, log, firewood, stick, leaves, cot, bed_roll, satchel). Used wherever items are named in action args, inventory, and base storage.

**`CraftableItem`** — Enum of the three crafter-profession crafting targets: satchel, bed_roll, cot. Subset of `ItemType` restricted to items produced by `CRAFT_NEW`. Kept separate so function signatures requiring a craftable item are statically distinct from those accepting any item.

**`ExploreResource`** — Enum of the five explorable resource types. Each value carries its profession-gating semantics and mean-time constant in comments; the actual numeric data lives in `timing.py`. Shared by Action System (dispatch) and AI Coordinator (prompt formatting).

**`ActionType`** — Fine-grained discriminant for every action a villager can take. Used by Action System to dispatch to the correct start/completion handler, and by AI Coordinator to map a raw LLM `idx` integer back to a typed action before constructing `SelectedAction`.

**`AutobalanceMultipliers`** — The three scaling factors (exploration yield, satiation restoration, hydration restoration) written by Simulation Engine at midnight and read by Action System at call time. Defined here for explicitness of the cross-subsystem contract; the authoritative instance lives in Simulation Engine.

**`ActionContext`** — Read-only snapshot of all cross-subsystem inputs needed to evaluate action eligibility and apply effects: villager id, character canon, villager state, all living villager states, world state, and current autobalance multipliers. Passed to every function in `eligibility.py` and `effects.py` to keep signatures stable.

**`ActiveSleepSegment`** — The in-progress sleep state at the moment a fire-state change splits a sleeping villager's night. Carries `total_minutes`, `elapsed_minutes`, and `modifier` (the wakefulness multiplier active for the elapsed portion). Passed to `adjust_active_sleep`.

**`ValidAction`** — A single entry in the action menu as it will be presented to the LLM. Carries the fully-formatted VRBTM prompt text, the `ActionType` for reverse-mapping, whether the action is selectable, and (when selectable) its 1-based index. Non-selectable entries are rendered without an index.

**`ActionList`** — The complete action menu for one villager at one moment. Two sections rendered separately: `main_actions` (everything except crafter recipes) and `crafter_recipes` (always all three recipes for a CRAFTER, empty otherwise). Indices are globally unique across both sections so the LLM always picks one unambiguous integer.

**`SelectedAction`** — The LLM's parsed and validated action choice, constructed by AI Coordinator from the raw JSON response and passed to Simulation Engine, which hands it to `start_action`. Carries the `ActionType` and only the args fields relevant to that type; all other optional fields are absent. AI Coordinator validates field population against `action_type` before returning.

---

## What This Subsystem Does NOT Own

- **Autobalance multiplier values** — written and stored by Simulation Engine; passed in via `ActionContext`.
- **Exploration randomness state** — Erlang sampling is stateless (seeded per call); no persistent RNG state is needed.
- **Conversation execution** — `TALK_TO` is dispatched directly by Simulation Engine to Conversation System; `start_action` returns `0` for `TALK_TO` and `complete_action` is never called for it.
- **Memory or logs** — start/completion effects are applied silently through Villager State and World State mutations; event logging is the caller's responsibility.

---

## Function Specifications

### `action_system/timing.py`

```python
def work_speed_modifier(health: float) -> float:
    """Work-speed multiplier from health. Returns 1.0 when health >= 0.5, else health * 2 (BHVR-189)."""

def apply_duration_modifier(base_minutes: float, work_speed: float, profession_factor: float) -> int:
    """Adjusted action duration in minutes after applying work-speed and profession modifiers."""

def exploration_effective_mean(
    resource: ExploreResource,
    profession: Profession,
    yield_scale: float,
) -> float:
    """Mean minutes per item for exploration, incorporating the 4x non-gatherer peach penalty
    and autobalance yield scale (BHVR-38, CONST-104). Work-speed is a per-villager factor
    applied separately in sample_exploration_yield."""

def sample_exploration_yield(
    effective_mean_minutes: float,
    work_speed: float,
    duration_minutes: int,
    item_weight_kg: float,
    remaining_capacity_kg: float,
) -> int:
    """Items found during exploration. Scales effective_mean by work_speed, then samples
    inter-arrival times via Erlang(k=5) until time or carry capacity is exhausted
    (REQ-99, BHVR-102, BHVR-289)."""
```

---

### `action_system/eligibility.py`

All functions assume the villager is at base and alive. Each accepts an `ActionContext` and returns `ValidAction` entries for one logical action group.

```python
def eating_and_drinking_actions(ctx: ActionContext) -> list[ValidAction]:
    """Eat-peach and eat-cooked-meat entries if those items are in inventory; drink-water if base supply > 0 (BHVR-81–83)."""

def storage_actions(ctx: ActionContext) -> list[ValidAction]:
    """Take-from-base for items in base storage; store-in-base for items in inventory (BHVR-76–77)."""

def resting_spot_actions(ctx: ActionContext) -> list[ValidAction]:
    """Place-and-claim bed-roll or cot if the villager holds one and has not already placed that spot type (BHVR-92–93)."""

def exploration_actions(ctx: ActionContext) -> list[ValidAction]:
    """Explore entries for each resource the villager can access: PEACHES/STICKS/LEAVES for
    all villagers (PEACHES at 4x mean for non-GATHERER); LOGS for WOODCUTTER only; BOAR for
    HUNTER only. Full-inventory entries are included non-selectable with the 'no inventory
    space' note; profession-locked resources are excluded entirely (BHVR-100–103)."""

def rest_action(ctx: ActionContext) -> list[ValidAction]:
    """Sit-and-relax entry, always available at base (BHVR-109)."""

def fire_tending_actions(ctx: ActionContext) -> list[ValidAction]:
    """Add-sticks, add-firewood, and light/extinguish entries. Quantities respect the 4-hour fuel cap; fuel remaining is shown inline (BHVR-113–119)."""

def misc_actions(ctx: ActionContext) -> list[ValidAction]:
    """Scrape-hide, haul-water, butcher-carcass, clean-camp, and split-logs entries when relevant materials or conditions exist (VRBTM-123)."""

def crafting_actions(ctx: ActionContext) -> list[ValidAction]:
    """All three crafter recipes (always shown to CRAFTER villagers) plus continue-crafting if a job is in progress. Non-selectable entries include the missing-materials note (BHVR-144–145)."""

def cooking_actions(ctx: ActionContext) -> list[ValidAction]:
    """Cook-meat (or finish-cooking when ctx.vs.cooking_paused is set) for COOK profession
    villagers when raw meat is available. Requires lit fire; shown as non-selectable if fire
    is out (CONST-147, BHVR-285). cooking_paused is a VillagerState field set by Simulation
    Engine when fire extinguishes mid-cook and cleared when cooking resumes or is cancelled."""

def sleeping_actions(ctx: ActionContext) -> list[ValidAction]:
    """Go-to-sleep entry with 4–12 hour range (BHVR-152)."""

def washing_action(ctx: ActionContext) -> list[ValidAction]:
    """Wash-up entry when base water supply >= 500 mL (VRBTM-164, CONST-165)."""

def conversation_actions(ctx: ActionContext) -> list[ValidAction]:
    """Talk-to entries for each other villager who is at base, awake, and not on an away action (BHVR-43, BHVR-284)."""

def build_action_list(ctx: ActionContext) -> ActionList:
    """Full action menu for one villager. Calls each action-group builder, assigns sequential 1-based indices to selectable actions, and splits crafter recipes into the separate section."""
```

---

### `action_system/effects.py`

Each action type has its own handler function (e.g., `_start_craft_new`, `_complete_explore`). `apply_start_effect` and `apply_completion_effect` are thin dispatchers over these.

```python
def apply_start_effect(
    action: SelectedAction,
    ctx: ActionContext,
) -> None:
    """Immediate pre-action mutations. CRAFT_NEW consumes crafting materials at job start
    (drawn from inventory then base); CONTINUE_CRAFTING does not consume materials again.
    Fire-tending actions deduct fuel from inventory then base (BHVR-115, CONST-141)."""

def apply_completion_effect(
    action: SelectedAction,
    ctx: ActionContext,
) -> None:
    """End-of-action mutations, dispatched per action type. Covers: exploration yield added
    to inventory; stat restoration for eating/drinking/sleeping (scaled by autobalance
    multipliers); per-activity calorie charges for exploration (CONST-106, CONST-107) and
    hauling water (CONST-126); base storage updates; camp dirtiness increments from
    butchering (CONST-132), eating meat (CONST-133), and cooking meat (CONST-134); crafting
    completion; and carcass-rot effects (BHVR-282)."""
```

---

### `action_system/api.py`

```python
def get_valid_actions(ctx: ActionContext) -> ActionList:
    """Full action menu for one villager. When over-encumbered, returns only store-in-base actions (INVR-208)."""

def start_action(
    action: SelectedAction,
    ctx: ActionContext,
) -> int:
    """Applies start effects and returns the action duration in minutes so Simulation Engine
    can schedule the completion event. Returns 0 for TALK_TO; Simulation Engine routes that
    directly to Conversation System without scheduling a completion event."""

def complete_action(
    action: SelectedAction,
    ctx: ActionContext,
) -> None:
    """Applies completion effects for a finished action. Never called for TALK_TO."""

def adjust_active_sleep(
    vs: VillagerState,
    segment: ActiveSleepSegment,
) -> int:
    """Splits an in-progress sleep on any fire-state change (extinguish or relight). Applies
    wakefulness gain for segment.elapsed_minutes at segment.modifier, then returns the
    remaining duration (total_minutes − elapsed_minutes) so Simulation Engine can schedule
    a new sleep segment under the updated modifier (BHVR-161, CONST-155). Simulation Engine
    calls this for every sleeping villager whenever LIGHT_FIRE completes or fire extinction
    fires."""
```
