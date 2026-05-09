# Simulation Engine — Implementation Details

## Overview

The Simulation Engine is the top-level orchestrator. It owns the discrete-event heap and the autobalance multipliers. It calls into every other subsystem; nothing calls into it. It is the only entry point for running the simulation.

Four subsystems are called by it:
- **Villager State** — `apply_decay`, `compute_stats`, `set_current_action`, `reset_compaction_counter`
- **World State** — `advance_fire`, `mark_carcass_rotted`, read aggregates for autobalancing
- **Action System** — `get_valid_actions`, `start_action`, `complete_action`, `adjust_active_sleep`
- **AI Coordinator** — `select_action`
- **Conversation System** — `run_conversation` (synchronous, blocks until complete)
- **Memory System** — `append_event`, `trigger_compaction`, `trigger_midnight_compaction`

---

## Game Time

Game time is a plain `int` counting **minutes from epoch**, where epoch 0 = midnight at the start of Day 1. The simulation loop starts at `t = 360` (Day 1, 6:00 AM). Midnight detection: `t % 1440 == 0`. The first midnight fires at `t = 1440`.

Human-readable conversion utilities exist for logging but are not part of the core data model.

---

## Core Objects

### EventType

The five scheduleable event types. Each maps to a distinct dispatch handler inside the engine.

```thrift
enum EventType {
    ACTION_COMPLETE  = 1,   // villager finished current action; prompt next action
    FIRE_EXTINCTION  = 2,   // fire fuel exhausted; adjust sleeping villagers
    CARCASS_ROT      = 3,   // carcass 24h deadline reached; destroy and add dirtiness
    MIDNIGHT         = 4,   // daily tick; autobalancing + medium-term memory compaction
    CHECKPOINT       = 5,   // every 3 in-game hours; dump full state snapshot to disk
}
```

---

### ScheduledEvent

A single entry on the event heap. The heap is ordered by `(timestamp, sequence)`. `sequence` is a monotone counter assigned at insertion; it ensures total ordering and deterministic processing of simultaneous events (FIFO by insertion order).

Only one payload field is populated per event, determined by `event_type`:
- `ACTION_COMPLETE` → `villager_id` is set
- `CARCASS_ROT` → `carcass_id` is set
- `FIRE_EXTINCTION`, `MIDNIGHT`, `CHECKPOINT` → neither payload field is set

```thrift
struct ScheduledEvent {
    1: i32 timestamp,               // game-minutes from epoch; primary heap key
    2: i32 sequence,                // insertion-order counter; secondary heap key for tie-breaking
    3: EventType event_type,
    4: optional string villager_id, // ACTION_COMPLETE only
    5: optional i32 carcass_id,     // CARCASS_ROT only
}
```

**Heap invariant:** the heap is a min-heap on `(timestamp, sequence)`. Direct removal is O(n) via linear scan + `heapify`; acceptable given the small event count (≤ ~15 concurrent events at any time: 6 action completions + fire + active carcasses + midnight + checkpoint).

---

### AutobalanceMultipliers

Scaling factors adjusted daily at midnight (BHVR-221). All three start at `1.0` and are unbounded (design doc resolution: self-regulating feedback loop). Action System reads these when computing exploration yield and calorie/hydration restoration amounts.

```thrift
struct AutobalanceMultipliers {
    1: f64 exploration_yield = 1.0,   // scales yield from all exploration actions (peaches, boar, logs, sticks, leaves)
    2: f64 satiation_restore = 1.0,   // scales caloric gain from eating (peach, cooked meat)
    3: f64 hydration_restore = 1.0,   // scales hydration gain from drinking water
}
```

**Autobalance adjustment (BHVR-221):** at each MIDNIGHT event, read the aggregate stats across all living villagers and compare to targets:
- `satiation_restore`: compares average `satiation_pct` across villagers to target `0.85` (CONST-216). If actual is `x%` above target, divide `satiation_restore` by `(1 + x/100)`; if below, multiply by `(1 + x/100)`.
- `hydration_restore`: same logic against target `0.50` (CONST-217), using `hydration_pct`.
- `exploration_yield`: compares average `food_safety` score across villagers to target `1.0` (one day of food, CONST-218). Same multiplicative adjustment.

Firewood safety (CONST-219) has no multiplier in this struct; the spec names it as a target but lists no corresponding autobalanceable yield. The midnight handler computes it but takes no corrective action unless the implementation later adds a log/firewood yield multiplier.

**Access pattern:** the Simulation Engine holds the single `AutobalanceMultipliers` instance. It passes a reference to Action System at construction so Action System always reads current values without the engine needing to pass them per-call.

---

### SimulationEngine (owned data)

Not a passed-between-subsystems struct — the top-level class. Listed here to make owned state explicit.

```thrift
struct SimulationEngine {
    1: i32 current_game_time,                      // advances to each event's timestamp before dispatch
    2: list<ScheduledEvent> event_heap,            // min-heap by (timestamp, sequence); direct-removal on cancel
    3: i32 next_sequence,                          // monotone counter; incremented on every heap insertion
    4: AutobalanceMultipliers autobalance,
    5: map<string, VillagerState> villager_states, // keyed by villager_id; dead villagers removed
    6: WorldState world_state,
    // subsystem references (not serialized in checkpoints):
    //   action_system, ai_coordinator, conversation_system, memory_system, character_canon
}
```

**Starting conditions:**
- `current_game_time = 360` (Day 1, 6:00 AM)
- `event_heap` pre-populated with:
  - One `ACTION_COMPLETE` per villager at `t = 360` with `sequence = 0..5` — triggers first action selection for each
  - One `MIDNIGHT` at `t = 1440`
  - One `CHECKPOINT` at `t = 360 + 180 = 540`
- `next_sequence = 6` (after the six initial ACTION_COMPLETE insertions)
- `autobalance` all multipliers = 1.0
- `villager_states`: six VillagerState instances at starting values (one per canon villager)
- `world_state`: empty WorldState

---

## Event Handlers (summary)

Precise handler logic belongs in the implementation, not this document, but the contracts are:

**ACTION_COMPLETE(villager_id):**
1. Call `apply_decay` on the villager for elapsed hours since last event; handle threshold crossings (HEALTH_ZERO → die, WAKEFULNESS_ZERO → force 4-hour sleep, schedule new ACTION_COMPLETE).
2. If alive and not force-sleeping: call `complete_action(villager_id)` on Action System.
3. Optionally trigger Memory System short-term compaction: if `awake_minutes_since_compaction >= 240` and villager is not sleeping.
4. If alive: call `select_action(villager_id)` on AI Coordinator; call `start_action(villager_id, chosen_action)` on Action System; schedule new ACTION_COMPLETE at returned completion timestamp.

**FIRE_EXTINCTION:**
1. Call `mark_fire_extinguished()` on WorldState.
2. For each villager whose `current_action.category == SLEEPING`: call `adjust_active_sleep(villager_id, new_modifier)` on Action System, which reschedules their ACTION_COMPLETE under the updated wakefulness modifier.

**CARCASS_ROT(carcass_id):**
1. Remove from WorldState (destroys the carcass item, increments `CARCASS_REMAINS` dirtiness).
2. Append rot event to Memory System for any villager who can observe it (at base and awake).

**MIDNIGHT:**
1. Apply decay to all villagers for elapsed hours.
2. Run autobalancing: read aggregate stats, adjust `AutobalanceMultipliers`.
3. Call `trigger_midnight_compaction()` on Memory System (compacts prior day's short-term memories into medium-term for each villager).
4. Recalculate safety for any villager who has woken up since the last safety recalc (safety recalculates per-villager on wake, not globally — but midnight is a natural point to ensure no one is stale).
5. Schedule next MIDNIGHT at `current_game_time + 1440`.

**CHECKPOINT:**
1. Serialize full simulation state (all VillagerState, WorldState, Memory System state, AutobalanceMultipliers, current event heap) to a `.json` file named by `current_game_time`.
2. Schedule next CHECKPOINT at `current_game_time + 180`.

---

## File Hierarchy

```
villmage/
    simulation_engine.py   — SimulationEngine class and event dispatch logic
    events.py              — EventType enum and ScheduledEvent dataclass
    autobalance.py         — AutobalanceMultipliers dataclass and adjustment logic
```

`events.py` and `autobalance.py` are leaves with no intra-project imports; `simulation_engine.py` imports both.

**Dependency direction:** `simulation_engine.py` imports from every other subsystem. No other subsystem imports from `simulation_engine.py` directly — Action System receives its `AutobalanceMultipliers` reference at construction time (passed in by the simulation entry point) rather than importing the engine.

---

## Step 1 — File Hierarchy and Object Assignments

### File Hierarchy

```
villmage/
    events.py              — EventType enum and ScheduledEvent dataclass
    autobalance.py         — AutobalanceMultipliers dataclass and midnight adjustment logic
    simulation_engine.py   — SimulationEngine class and all five event-dispatch handlers
```

#### `events.py`

Pure data definitions for the simulation heap. No logic, no intra-project imports. Defines the five scheduleable event categories and the heap-entry structure consumed by SimulationEngine to order and dispatch simulation transitions.

#### `autobalance.py`

Autobalance multipliers and the midnight adjustment algorithm. Multipliers scale exploration yield, satiation restoration, and hydration restoration toward design targets. The adjustment function accepts primitive aggregate values (per-villager stat averages, living villager count) passed in by SimulationEngine — it does not import Villager State or World State directly. No intra-project imports.

#### `simulation_engine.py`

Top-level simulation orchestrator. Owns the discrete-event heap, all VillagerState instances, and the WorldState. Advances game time by popping the next heap entry, applies stat decay to all villagers for the elapsed interval, and dispatches the appropriate handler. Holds references to every other subsystem at construction; nothing else holds a reference to it. The sole entry point for running the simulation.

---

### Core Object Assignments

#### `EventType` → `events.py`

Enumeration of the five scheduleable event categories. Each value maps to exactly one dispatch handler inside SimulationEngine. Knowing which enum value is set on a `ScheduledEvent` is sufficient to know which handler runs and which payload field is populated.

#### `ScheduledEvent` → `events.py`

A single entry on the simulation heap. Primary sort key is `timestamp`; secondary key is `sequence` (a monotone insertion counter) to guarantee deterministic FIFO ordering when two events share a timestamp. Carries at most one optional payload field — `villager_id` for `ACTION_COMPLETE`, `carcass_id` for `CARCASS_ROT`, neither for the three global events.

#### `AutobalanceMultipliers` → `autobalance.py`

Three scaling factors — exploration yield, satiation restoration, hydration restoration — adjusted multiplicatively at midnight based on deviation from design targets. All start at `1.0` and are unbounded. SimulationEngine holds the single instance and passes a reference to Action System at construction so Action System always reads current values without a per-call argument.

#### `SimulationEngine` → `simulation_engine.py`

The simulation loop and top-level state container. Owns the event heap (min-heap on `(timestamp, sequence)`), all `VillagerState` instances, `WorldState`, and `AutobalanceMultipliers`. Holds references to Action System, AI Coordinator, Conversation System, Memory System, and Character Canon. Nothing holds a reference back to it.

---

## Step 1 — Core Functions

### `events.py`

`EventType` and `ScheduledEvent` are pure data definitions; no core functions. `ScheduledEvent` should use `@dataclass(order=True)` with `compare=False` on `event_type`, `villager_id`, and `carcass_id` so heap ordering uses only `timestamp` then `sequence`.

---

### `autobalance.py`

#### `AutobalanceMultipliers`

```python
def adjust(
    self,
    avg_satiation_pct: float,
    avg_hydration_pct: float,
    avg_food_safety_days: float,
) -> None:
    """Multiplicatively nudge all three multipliers toward their design targets.

    Targets: satiation_pct=0.85, hydration_pct=0.50, food_safety_days=1.0. For each
    multiplier, if actual is x above target divide by (1 + x); if below, multiply by
    (1 + x), where x is the fractional deviation."""
```

---

### `simulation_engine.py`

#### `SimulationEngine`

```python
def __init__(
    self,
    character_canon: CharacterCanon,
    action_system: ActionSystem,
    ai_coordinator: AICoordinator,
    conversation_system: ConversationSystem,
    memory_system: MemorySystem,
) -> None:
    """Initialize simulation at Day 1 6:00 AM (t=360).

    Creates six VillagerState instances at starting values, an empty WorldState, and
    pre-populates the heap with one ACTION_COMPLETE per villager at t=360 (sequences
    0–5), a MIDNIGHT at t=1440, and a CHECKPOINT at t=540."""
```

```python
def run(self) -> None:
    """Main event loop. Runs until the heap is empty (all villagers dead).

    Each iteration: pop the lowest (timestamp, sequence) event, advance
    current_game_time, apply stat decay to all living villagers for the elapsed
    interval, process any threshold crossings (kill or force-sleep), then dispatch
    the event handler."""
```

```python
def _apply_decay_all(self, elapsed_hours: float) -> dict[str, list[CrossingType]]:
    """Call apply_decay(elapsed_hours) on every living villager.

    Returns {villager_id: [crossings]} for any HEALTH_ZERO or WAKEFULNESS_ZERO
    thresholds triggered. Callers handle all crossings before dispatching the event."""
```

```python
def _handle_action_complete(self, villager_id: str) -> None:
    """Handler for when a villager's scheduled action finishes.

    Returns immediately if the villager died or was force-slept in this event cycle's
    decay pass. Otherwise: completes the prior action via Action System; compacts
    short-term memory if the villager has been awake ≥4h since last compaction
    (BHVR-252) or if the next selected action is sleep (BHVR-251); recalculates safety
    on wake-from-sleep; then asks the AI for the next action and schedules its
    ACTION_COMPLETE. When the chosen action is 'Talk to someone', calls
    run_conversation synchronously — after it returns, cancels stale ACTION_COMPLETE
    events for every non-initiator participant and reschedules them at
    old_completion_timestamp + elapsed_conversation_minutes. Conversations block the
    simulation; if a villager's wakefulness would reach 0 during a conversation, they
    participate through the full conversation and are force-slept afterward (BHVR-192).
    Calls _sync_fire_event after any action that may modify fire state."""
```

```python
def _handle_fire_extinction(self) -> None:
    """Handler for fire fuel reaching zero.

    Marks fire extinguished in WorldState, then calls adjust_active_sleep on Action
    System for each sleeping villager to split their remaining sleep into a new segment
    computed under the updated (no-fire) wakefulness modifier."""
```

```python
def _handle_carcass_rot(self, carcass_id: int) -> None:
    """Handler for a carcass reaching its 24h rot deadline.

    Removes the carcass from WorldState (adding +30 dirtiness), then appends a rot
    event to Memory System for every villager currently at base and awake."""
```

```python
def _handle_midnight(self) -> None:
    """Handler for the daily midnight tick.

    Computes per-villager aggregate stats, adjusts AutobalanceMultipliers via
    adjust(), triggers medium-term memory compaction for all villagers (previous
    day's short-term memories), then schedules the next MIDNIGHT at
    current_game_time + 1440."""
```

```python
def _handle_checkpoint(self) -> None:
    """Serialize full simulation state to a timestamped JSON file.

    Snapshot includes all VillagerState instances, WorldState, Memory System state,
    AutobalanceMultipliers, and the event heap. Schedules the next CHECKPOINT at
    current_game_time + 180."""
```

```python
def _force_sleep(self, villager_id: str) -> None:
    """Pre-empt a villager's pending action and schedule a forced 4-hour sleep.

    Cancels their pending ACTION_COMPLETE from the heap if present (it may already
    be popped when force-sleep is triggered by the villager's own ACTION_COMPLETE;
    skip the cancellation in that case). Updates VillagerState to record forced sleep
    and schedules a new ACTION_COMPLETE at current_game_time + 240."""
```

```python
def _kill_villager(self, villager_id: str) -> None:
    """Remove a dead villager from the simulation.

    Cancels their pending ACTION_COMPLETE, clears their inventory, removes them from
    villager_states, and appends a death event to Memory System for all observers
    (villagers currently at base and awake)."""
```

```python
def _sync_fire_event(self) -> None:
    """Reconcile the heap's FIRE_EXTINCTION event with WorldState's current fire state.

    Cancels any existing FIRE_EXTINCTION event, then schedules a new one at
    WorldState's derived extinction timestamp if the fire is lit with remaining fuel;
    leaves it cancelled otherwise."""
```

---

## Flags and Issues

→ ISSUE: The numbered steps of ACTION_COMPLETE and its docstring describe different behavior. Step 3 covers only BHVR-252 (compact if ≥4h awake), but the docstring also describes BHVR-251 compaction ("if the next selected action is sleep") — which requires knowing the chosen action and therefore must happen after step 4, not at step 3. No such post-step-4 compaction step exists. The docstring also mentions "recalculates safety on wake-from-sleep" as a distinct behavior with no corresponding numbered step.

→ ISSUE: Step 2 of ACTION_COMPLETE calls `complete_action(villager_id)` unconditionally. At t=360, all six initial ACTION_COMPLETE events fire with no prior action to complete. No guard for this initial-state case is described, leaving `complete_action`'s behavior on a villager with no current action undefined here.

→ ISSUE: MIDNIGHT handler step 4 ("Recalculate safety for any villager who has woken up since the last safety recalc") contradicts the design resolution that safety recalculates per-villager on wake, not on a global clock. If wake-triggered recalculation is implemented correctly everywhere, this step is unreachable. The parenthetical justification ("midnight is a natural point to ensure no one is stale") directly contradicts the deliberate design choice.

→ ISSUE: `awake_minutes_since_compaction` is referenced in ACTION_COMPLETE step 3, and `reset_compaction_counter` is listed in the engine overview's call list against VillagerState — but neither field nor counter appears in any subsystem's defined data schema. VillagerState's owned data in both design.md and subsystem.md has no such field.

→ ISSUE: `run()` says it "runs until the heap is empty (all villagers dead)." MIDNIGHT and CHECKPOINT handlers each self-reschedule their next event unconditionally, so the heap never becomes empty regardless of villager count. The termination condition must be "all villagers dead," not heap emptiness.
