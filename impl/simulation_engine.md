# Simulation Engine — Implementation Details

## Overview

The Simulation Engine is the top-level orchestrator. It owns the discrete-event heap and the autobalance multipliers. It calls into every other subsystem; nothing calls into it. It is the only entry point for running the simulation.

Subsystems called by it:
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

### VillagerId

```python
VillagerId: TypeAlias = str
```

A typed alias for villager identity strings. Using a named alias prevents silently passing a carcass ID, character name, or log key where a villager ID is expected.

---

### Event Types

Each event category is its own dataclass. Dispatch in `run()` is via `match` / `isinstance`; each handler receives the exact event type it needs with no optional-field inspection. All classes are ordered on `(timestamp, sequence)` only — payload fields are excluded from comparison so heap ordering is well-defined.

```python
@dataclass(order=True)
class ActionCompleteEvent:
    timestamp: int
    sequence: int
    villager_id: VillagerId = field(compare=False)

@dataclass(order=True)
class FireExtinctionEvent:
    timestamp: int
    sequence: int

@dataclass(order=True)
class CarcassRotEvent:
    timestamp: int
    sequence: int
    carcass_id: int = field(compare=False)

@dataclass(order=True)
class MidnightEvent:
    timestamp: int
    sequence: int

@dataclass(order=True)
class CheckpointEvent:
    timestamp: int
    sequence: int

ScheduledEvent: TypeAlias = (
    ActionCompleteEvent
    | FireExtinctionEvent
    | CarcassRotEvent
    | MidnightEvent
    | CheckpointEvent
)
```

**Heap invariant:** min-heap on `(timestamp, sequence)`. Direct removal is O(n) via linear scan + `heapify`; acceptable given the small event count (≤ ~15 concurrent events: 6 action completions + fire + active carcasses + midnight + checkpoint).

---

### AutobalanceMultipliers

Scaling factors adjusted daily at midnight (BHVR-221). All three start at `1.0` and are unbounded (design doc resolution: self-regulating feedback loop). Action System reads these when computing exploration yield and calorie/hydration restoration amounts.

```thrift
struct AutobalanceMultipliers {
    1: f64 exploration_yield = 1.0,   // scales yield from all exploration actions
    2: f64 satiation_restore = 1.0,   // scales caloric gain from eating
    3: f64 hydration_restore = 1.0,   // scales hydration gain from drinking water
}
```

**Autobalance adjustment (BHVR-221):** at each MidnightEvent, compare aggregate stats to targets:
- `satiation_restore`: average `satiation_pct` vs target `0.85` (CONST-216)
- `hydration_restore`: average `hydration_pct` vs target `0.50` (CONST-217)
- `exploration_yield`: average `food_safety_days` vs target `1.0` (CONST-218)

For each: if actual is `x%` above target, divide multiplier by `(1 + x/100)`; if below, multiply by `(1 + x/100)`.

Firewood safety (CONST-219) is logged at midnight but has no corresponding multiplier to adjust.

**Access pattern:** SimulationEngine holds the single instance and passes a reference to Action System at construction — Action System reads current values without a per-call argument.

---

### SimulationEngine (owned data)

```thrift
struct SimulationEngine {
    1: i32 current_game_time,
    2: list<ScheduledEvent> event_heap,                   // min-heap by (timestamp, sequence)
    3: i32 next_sequence,                                 // monotone counter; incremented on every heap insertion
    4: AutobalanceMultipliers autobalance,
    5: map<VillagerId, VillagerState> villager_states,    // dead villagers removed
    6: WorldState world_state,
    // subsystem references (not serialized in checkpoints):
    //   action_system, ai_coordinator, conversation_system, memory_system, character_canon
}
```

**Starting conditions:**
- `current_game_time = 360` (Day 1, 6:00 AM)
- `event_heap` pre-populated with:
  - One `ActionCompleteEvent` per villager at `t = 360` with `sequence = 0..5` — triggers first action selection
  - One `MidnightEvent` at `t = 1440`
  - One `CheckpointEvent` at `t = 360 + 180 = 540`
- `next_sequence = 6` (after the six initial insertions)
- `autobalance` all multipliers = `1.0`
- `villager_states`: six VillagerState instances at starting values
- `world_state`: empty WorldState

---

## Event Handlers

**ActionCompleteEvent(villager_id):**
1. Call `apply_decay` on the villager for elapsed hours since last event; collect threshold crossings.
2. If villager has a current action (i.e., not the initial t=360 events): call `complete_action(villager_id)` on Action System.
3. Process threshold crossings via `_apply_thresholds`: HEALTH_ZERO → `_kill_villager`; WAKEFULNESS_ZERO → `_force_sleep`. Return early if either triggered.
4. If `awake_minutes_since_compaction >= 240` (BHVR-252): call `trigger_compaction(villager_id)` on Memory System; call `reset_compaction_counter(villager_id)` on Villager State.
5. Call `select_action(villager_id)` on AI Coordinator; append the returned thought to Memory System.
6. If chosen action is sleep and compaction did not run in step 4 (BHVR-251): call `trigger_compaction(villager_id)`.
7. Call `start_action(villager_id, chosen_action)` on Action System; schedule new `ActionCompleteEvent` at the returned completion timestamp.
8. If chosen action is "Talk to someone": call `_handle_conversation_action(villager_id, target_id)` instead of the normal schedule in step 7.

**FireExtinctionEvent:**
1. Call `mark_fire_extinguished()` on WorldState.
2. For each villager whose `current_action.category == SLEEPING`: call `adjust_active_sleep(villager_id)` on Action System to split remaining sleep under the updated (no-fire) modifier.

**CarcassRotEvent(carcass_id):**
1. Call `mark_carcass_rotted(carcass_id)` on WorldState (adds +30 dirtiness, destroys the carcass).
2. Append rot event to Memory System for every villager currently at base and awake.

**MidnightEvent:**
1. Apply decay to all villagers for elapsed hours.
2. Compute aggregate stats via `_compute_autobalance_aggregates()` and pass to `autobalance.adjust()`.
3. Call `trigger_midnight_compaction()` on Memory System (compacts prior day's short-term memories for each villager).
4. Schedule next `MidnightEvent` at `current_game_time + 1440`.

**CheckpointEvent:**
1. Serialize full simulation state (all VillagerState, WorldState, Memory System state, AutobalanceMultipliers, event heap) to a `.json` file named by `current_game_time`.
2. Schedule next `CheckpointEvent` at `current_game_time + 180`.

---

## File Hierarchy

```
villmage/
    events.py              — event dataclasses, ScheduledEvent union alias, VillagerId alias
    autobalance.py         — AutobalanceMultipliers dataclass and adjustment logic
    simulation_engine.py   — SimulationEngine class and all five event-dispatch handlers
```

#### `events.py`

Pure data definitions for the simulation heap. No logic, no intra-project imports. Defines the five event types as individual ordered dataclasses, the `ScheduledEvent` union alias, and the `VillagerId` type alias.

#### `autobalance.py`

Autobalance multipliers and the midnight adjustment algorithm. The `adjust()` method accepts pre-aggregated primitive values passed in by SimulationEngine — it does not import Villager State or World State. No intra-project imports.

#### `simulation_engine.py`

Top-level simulation orchestrator. Owns the event heap, all VillagerState instances, and WorldState. Advances game time by popping the next heap entry, applies stat decay, dispatches the appropriate handler, then calls `_sync_fire_event()` unconditionally to reconcile the fire extinction event. Holds references to every other subsystem at construction; nothing else holds a reference to it.

---

## Core Functions

### `events.py`

All classes are pure data definitions; no functions. `ActionCompleteEvent` and `CarcassRotEvent` use `field(compare=False)` on their payload fields so heap ordering uses only `timestamp` then `sequence`.

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
    pre-populates the heap with one ActionCompleteEvent per villager at t=360
    (sequences 0–5), a MidnightEvent at t=1440, and a CheckpointEvent at t=540."""
```

```python
def run(self) -> None:
    """Main event loop. Runs until all villagers are dead.

    Each iteration: pop the lowest (timestamp, sequence) event, advance
    current_game_time, apply stat decay to all living villagers for the elapsed
    interval, process any threshold crossings, dispatch the event handler, then
    call _sync_fire_event() to reconcile the fire extinction event. MidnightEvent
    and CheckpointEvent self-reschedule indefinitely; the loop ends only when all
    villagers are dead and no ActionCompleteEvents remain on the heap."""
```

```python
def _apply_decay_all(self, elapsed_hours: float) -> dict[VillagerId, list[CrossingType]]:
    """Call apply_decay(elapsed_hours) on every living villager.

    Returns {villager_id: [crossings]} for any HEALTH_ZERO or WAKEFULNESS_ZERO
    thresholds triggered. Callers handle all crossings before dispatching the event."""
```

```python
def _handle_action_complete(self, event: ActionCompleteEvent) -> None:
    """Dispatch an action-completion event for one villager.

    Sequences: decay → prior-action completion → threshold handling → memory
    compaction (BHVR-252) → action selection → memory compaction (BHVR-251) →
    action start. Delegates threshold handling to _apply_thresholds and conversation
    routing to _handle_conversation_action to keep this function a flat dispatcher."""
```

```python
def _apply_thresholds(
    self, villager_id: VillagerId, crossings: list[CrossingType]
) -> bool:
    """Handle HEALTH_ZERO (kill) and WAKEFULNESS_ZERO (force-sleep) crossings.

    Returns True if the villager is now dead or sleeping, signalling the caller to
    skip further processing for this event cycle."""
```

```python
def _handle_conversation_action(
    self, initiator_id: VillagerId, target_id: VillagerId
) -> None:
    """Run a conversation synchronously and reschedule all participants afterward.

    Calls run_conversation(), which returns elapsed game time. Cancels stale
    ActionCompleteEvents for every non-initiator participant and reschedules them
    at old_completion_timestamp + elapsed_conversation_minutes."""
```

```python
def _handle_fire_extinction(self) -> None:
    """Handle fire fuel reaching zero.

    Marks fire extinguished in WorldState, then calls adjust_active_sleep on Action
    System for each sleeping villager to split remaining sleep under the updated
    (no-fire) wakefulness modifier."""
```

```python
def _handle_carcass_rot(self, event: CarcassRotEvent) -> None:
    """Handle a carcass reaching its 24h rot deadline.

    Removes the carcass from WorldState (+30 dirtiness), then appends a rot event
    to Memory System for every villager currently at base and awake."""
```

```python
def _handle_midnight(self) -> None:
    """Daily midnight tick: autobalancing and medium-term memory compaction.

    Computes per-villager aggregate stats via _compute_autobalance_aggregates,
    adjusts AutobalanceMultipliers, triggers medium-term memory compaction for all
    villagers, then schedules the next MidnightEvent."""
```

```python
def _handle_checkpoint(self) -> None:
    """Serialize full simulation state to a timestamped JSON file.

    Snapshot includes all VillagerState instances, WorldState, Memory System state,
    AutobalanceMultipliers, and the event heap. Schedules the next CheckpointEvent."""
```

```python
def _force_sleep(self, villager_id: VillagerId) -> None:
    """Pre-empt a villager's pending action and schedule a forced 4-hour sleep.

    Cancels their pending ActionCompleteEvent if present (it may already be popped
    when force-sleep is triggered by the villager's own event; skip if so). Updates
    VillagerState to record forced sleep and schedules a new ActionCompleteEvent at
    current_game_time + 240."""
```

```python
def _kill_villager(self, villager_id: VillagerId) -> None:
    """Remove a dead villager from the simulation.

    Cancels their pending ActionCompleteEvent, clears their inventory, removes them
    from villager_states, and appends a death event to Memory System for all observers
    (villagers currently at base and awake)."""
```

```python
def _sync_fire_event(self) -> None:
    """Reconcile the heap's FireExtinctionEvent with WorldState's current fire state.

    Called unconditionally after every event dispatch in run(). Cancels any existing
    FireExtinctionEvent, then schedules a new one at WorldState's derived extinction
    timestamp if the fire is lit with remaining fuel; leaves it cancelled otherwise."""
```

```python
def _compute_autobalance_aggregates(self) -> tuple[float, float, float]:
    """Compute (avg_satiation_pct, avg_hydration_pct, avg_food_safety_days) for midnight.

    Averages each value across all living villagers. Food safety days uses the food
    component of the safety score formula — personal calories plus a share of base
    calories, divided by 2200 — then averages over all living villagers."""
```
