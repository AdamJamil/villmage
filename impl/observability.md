# Observability — Implementation Details

## Overview

Observability is a read-only offline subsystem. At runtime, the Simulation Engine and
Memory System write structured files to disk. After the simulation runs (or while it runs),
the Observability viewer — a standalone HTML/CSS/JS page — reads those files and provides
a scrollable, per-villager replay surface with highlighted state deltas.

No Observability code executes during simulation. The viewer is standalone tooling that
reads persisted files only.

Three things are persisted to disk by other subsystems:
1. **Per-villager event logs** — written by Memory System as `events/{villager_id}.jsonl`
   (EventLogEntry records, perspective-filtered at write time). A villager sees their own actions always, conversations they participated in, and all base events while at base and awake. A "base event" is any event that occurs at base — everything except exploration and water-hauling activities.
2. **State deltas** — written by Simulation Engine as `state_deltas.jsonl` (DeltaRecord
   records, one per state change).
3. **Checkpoint snapshots** — written by Simulation Engine as `checkpoints/{game_time}.json`
   (CheckpointRecord, full machine-readable state every 3 in-game hours per BHVR-271).

The viewer reconstructs simulation state at any scroll position by loading the nearest
preceding checkpoint and replaying delta records forward.

---

## File Layout

```
data/
  events/
    aldric.jsonl        ← Memory System writes; EventLogEntry per line
    sewalt.jsonl
    ...
  state_deltas.jsonl    ← Simulation Engine writes; DeltaRecord per line
  checkpoints/
    00360.json          ← game_time=360, Day 1 6:00 AM
    00540.json          ← game_time=540, first 3h checkpoint
    ...
  llm_failures.jsonl    ← AI Coordinator writes; ParseFailureLog per line (existing)
```

---

## Core Objects

### DeltaKind

Discriminates which kind of state changed in a `DeltaRecord`. Determines which
optional payload fields are populated.

```thrift
enum DeltaKind {
    VILLAGER_STATS = 1,   // one or more of a villager's raw or derived stats changed
    VILLAGER_INV   = 2,   // a villager's inventory changed
    WORLD_STATE    = 3,   // world state changed (base storage, fire, water, dirtiness, etc.)
    MEMORY_UPDATE  = 4,   // a memory entry was formed or a relationship record was updated
}
```

---

### FieldChange

One field's old and new value, identified by a dot-path string. Used in `DeltaRecord`
to record exactly what changed without writing full snapshots (REQ-18). The viewer
uses `field` to target the right display element and `old_value`/`new_value` for
delta highlighting (ATTR-16).

```thrift
struct FieldChange {
    1: string field,       // dot-path into the owning record:
                           //   VILLAGER_STATS: "wakefulness", "satiation", "health", "mood", etc.
                           //   VILLAGER_INV:   "PEACH", "COOKED_MEAT", "LOG", etc. (ItemType name)
                           //   WORLD_STATE:    "base_storage.PEACH", "water_supply_liters",
                           //                   "fire.lit", "fire.remaining_minutes",
                           //                   "total_dirtiness", etc.
    2: string old_value,   // JSON-encoded previous value; "" if field did not exist before
    3: string new_value,   // JSON-encoded new value
}
```

---

### DeltaRecord

One line in `state_deltas.jsonl`. A tagged record; exactly one of the optional payload
groups is populated depending on `kind`. Written by any mutating subsystem via
`append_delta` — Villager State and World State setters write it directly; Simulation
Engine writes it for decay and event scheduling.

```thrift
struct DeltaRecord {
    1: i32 game_time,
    2: DeltaKind kind,

    // VILLAGER_STATS and VILLAGER_INV: identifies which villager changed
    3: optional string villager_id,

    // VILLAGER_STATS, VILLAGER_INV, WORLD_STATE:
    // list of (field, old_value, new_value) triples; non-empty for all kinds except MEMORY_UPDATE
    4: optional list<FieldChange> changes,

    // MEMORY_UPDATE only:
    5: optional string memory_kind,    // "short_term" | "medium_term" | "long_term"
                                       // | "relationship_desc" | "impression"
    6: optional string content,        // the new memory/impression text
    7: optional string subject_id,     // for "relationship_desc" and "impression": subject villager
}
```

**Write frequency:**
- VILLAGER_STATS: once after each `apply_decay` call and after any `modify_stat` call
  that changes a derived stat. Writing both raw and derived stats in one record keeps
  the viewer from having to re-run the health/mood formulas in JavaScript.
- VILLAGER_INV: once per `modify_inventory` call.
- WORLD_STATE: once per World State mutation (modify_base_item, modify_water, fire
  state changes, dirtiness changes).
- MEMORY_UPDATE: once per `trigger_short_term_compaction` completion, per midnight
  compaction, and per `write_impressions` call.

**Viewer correlation:** the viewer correlates delta records with event log entries by
`game_time`. For a given event at game_time T, the viewer applies all delta records
with `game_time == T` for the same `villager_id` to compute the post-event state.
Multiple events may share the same game_time (parallel villager completions); the
`villager_id` field disambiguates.

---

### VillagerMemoryCheckpoint

Per-villager memory state included in `CheckpointRecord`. Corresponds to the in-memory
state that `MemorySystem.trigger_snapshot()` returns; defined here to make the on-disk
format explicit and machine-readable by the Simulation Engine for restart (REQ-272).

```thrift
struct VillagerMemoryCheckpoint {
    1: string villager_id,
    2: list<MemoryEntry> short_term_memories,   // MemoryEntry from memory_system.types
    3: list<MemoryEntry> medium_term_memories,
    4: list<MemoryEntry> long_term_memories,
    5: list<EventLogEntry> active_context_log,  // EventLogEntry from memory_system.types;
                                                // cleared on compaction but preserved here
    6: map<string, RelationshipRecord> relationships,  // keyed by subject villager_id;
                                                       // RelationshipRecord from memory_system.types
    7: i32 last_long_term_compaction_day,   // day number (game_time // 1440) of last long-term fire
}
```

---

### CheckpointRecord

Complete machine-readable simulation state. Written to
`checkpoints/{game_time:05d}.json` every 3 in-game hours (BHVR-271). Serves two
purposes:
1. **Sim Engine restart** — Simulation Engine deserializes this and resumes from exactly
   this point (REQ-272). The `event_heap` is essential for this use case.
2. **Viewer replay base** — The viewer loads the nearest preceding checkpoint as the
   starting state, then replays `DeltaRecord`s forward to reach any target game_time.

```thrift
struct CheckpointRecord {
    1: i32 game_time,
    2: list<VillagerState> villager_states,              // all living villagers at checkpoint time;
                                                         // VillagerState from villager_state.py
    3: WorldState world_state,                           // WorldState from world_state.py
    4: list<VillagerMemoryCheckpoint> memory_state,      // one entry per villager (living and dead)
    5: AutobalanceMultipliers autobalance,               // from autobalance.py
    6: list<ScheduledEvent> event_heap,                  // from events.py; sorted (timestamp, sequence);
                                                         // required for sim restart; viewer ignores
}
```

**Notes:**
- `villager_states` includes only living villagers (dead ones are removed from
  `SimulationEngine.villager_states` on death per `_kill_villager`).
- `memory_state` retains all villagers, including dead ones, because Memory System
  stores their logs separately and they are needed for viewer replay of past events.
- The JSON file name uses zero-padded game_time to guarantee lexicographic sort order
  matches chronological order, simplifying "find nearest preceding checkpoint" queries.

---

### VillagerViewerState

Viewer-side in-memory state for one villager at the current scroll position. Computed
by the viewer by replaying checkpoint + delta records; never persisted. This struct
defines what the viewer renders in the character panel alongside the event log.

```thrift
struct VillagerViewerState {
    1: string villager_id,

    // Raw stats — displayed with their numeric value and VRBTM tier description
    2: f64 wakefulness,        // 0–100
    3: f64 satiation,          // 0–1800 cal
    4: f64 hydration,          // 0–6000 mL
    5: f64 social_joy,         // 0–100
    6: f64 connectedness,      // 0–100
    7: f64 cleanliness,        // 0–100

    // Derived — also persisted in DeltaRecords so viewer needn't re-run formulas
    8: f64 health,             // 0–1
    9: f64 mood,               // 0–1
    10: f64 well_being,        // 0–1
    11: f64 safety,            // 0–unbounded (clamped for display)

    // Inventory: item display name → quantity; omit zero-quantity entries
    12: map<string, i32> inventory,

    // Current action text, e.g. "Exploring for logs (completes at Day 2, 10:14 AM)"
    13: optional string current_action_text,

    // Fields changed since the previous displayed event; used by viewer for
    // ATTR-16 delta highlighting. Field names match FieldChange.field keys.
    14: set<string> changed_fields,

    // Latest memory text for display in the memory panel
    15: list<string> short_term_memory_texts,    // most recent first
    16: list<string> medium_term_memory_texts,
    17: list<string> long_term_memory_texts,

    // Relationship descriptions for display; keyed by other villager_id
    18: map<string, string> relationship_descriptions,

    // Recent impressions for display; keyed by other villager_id → list of ≤3 strings
    19: map<string, list<string>> recent_impressions,
}
```

---

### WorldViewerState

Viewer-side in-memory world state at the current scroll position. Rendered in the
base-status panel alongside the selected villager's event log.

```thrift
struct WorldViewerState {
    1: map<string, i32> base_storage,           // item display name → quantity; zero-quantity omitted
    2: i32 water_supply_liters,
    3: bool fire_lit,
    4: i32 fire_remaining_minutes,
    5: i32 total_dirtiness,                     // 0–100
    6: map<string, string> placed_resting_spots, // villager_id → spot type display name
    7: i32 live_carcass_count,

    // Fields changed since the previous displayed event; for ATTR-16 highlighting
    8: set<string> changed_fields,
}
```

---

### ViewerSession

Top-level in-memory state the HTML/JS viewer maintains as the user scrolls. Not
persisted; reconstructed from files on page load or scroll.

```thrift
struct ViewerSession {
    1: string selected_villager_id,              // whose event log is displayed in the main pane
    2: i32 current_game_time,                    // game time at the current scroll position
    3: map<string, VillagerViewerState> villager_states,  // keyed by villager_id; all villagers
    4: WorldViewerState world_state,
    5: list<EventLogEntry> visible_events,       // the selected villager's perspective-filtered
                                                 // event log up to current_game_time;
                                                 // EventLogEntry from memory_system.types
}
```

**Scroll behavior (BHVR-15):** as the user scrolls, `current_game_time` advances to
the `game_time` of the newly visible event log entry. The viewer recomputes
`villager_states` and `world_state` by applying all `DeltaRecord`s between the nearest
checkpoint's `game_time` and `current_game_time`. Changed fields from delta records
applied at exactly `current_game_time` populate `changed_fields` for highlighting
(ATTR-16). Fields changed at earlier game times are not highlighted.

---

## Design Notes

**Why `FieldChange.old_value` and `new_value` are JSON strings:** stats and inventory
quantities are heterogeneous (int, float, bool, map). Using JSON strings avoids a
typed union at this layer. The viewer parses them with `JSON.parse` and formats them
with known display logic per field name.

**Derived stats in VILLAGER_STATS delta records:** the Simulation Engine writes
`health`, `mood`, `well_being`, and `safety` as fields in the same `DeltaRecord` as
the raw stats that caused them to change. This means the viewer never runs the
health/mood/well-being formulas in JavaScript — it only applies pre-computed values.
The cost is slightly larger delta records; the benefit is formula logic lives in one
place (Python) and is not duplicated in the viewer.

**`VillagerMemoryCheckpoint` vs. `MemorySystem.trigger_snapshot`:** Memory System's
`trigger_snapshot()` returns `dict[str, object]`. `VillagerMemoryCheckpoint` is the
typed schema that dict must conform to. The Simulation Engine's `_handle_checkpoint`
is responsible for calling `memory_system.trigger_snapshot()` and serializing it in
this format.

**Checkpoint file naming:** zero-padded game_time (`{game_time:05d}.json`) ensures
lexicographic `listdir` sort equals chronological order, so "find checkpoint before
target_time" is a linear scan from the back with no timestamp parsing.

**Viewer startup sequence:**
1. List `checkpoints/` and load the latest checkpoint for initial display.
2. Read `state_deltas.jsonl` in full (or stream it) and build a time-indexed index:
   `Map<game_time, List<DeltaRecord>>`.
3. Read `events/{selected_villager_id}.jsonl` in full.
4. Render the event log; on scroll, apply deltas up to the scrolled-to event's
   `game_time` to update the sidebar state panels.

**Dead villager handling:** dead villagers are removed from `checkpoint.villager_states`
at the checkpoint following death. Their last known state is preserved in the preceding
checkpoint plus any `VILLAGER_STATS`/`VILLAGER_INV` delta records up to the death
event. The viewer can reconstruct and display their state up to death; afterwards
their panel shows "deceased" and stops updating.

---

## File Hierarchy

```
observability/
  types.py     ← Python on-disk schema types (imported by Simulation Engine + Memory System)
  viewer.html  ← Standalone HTML/CSS/JS replay viewer
```

### `observability/types.py`

On-disk data types for the observability layer. Defines the exact format of
`state_deltas.jsonl` lines and the `checkpoints/{game_time:05d}.json` files written
at runtime by Simulation Engine and Memory System. The Simulation Engine also
deserializes `CheckpointRecord` when restarting from a checkpoint. The JS viewer
reads these formats directly; this module is not imported by viewer code.

### `observability/viewer.html`

Standalone single-file HTML/CSS/JS replay viewer. Reads `data/state_deltas.jsonl`,
`data/checkpoints/`, and `data/events/` via `fetch()` relative to the page origin.
Serve from the project root with any static HTTP server (e.g. `python -m http.server`)
and open in a browser. Contains all CSS (dark theme) and JS (file loading,
delta replay, scroll handler, delta highlighting) inline. The JS viewer-state types
`VillagerViewerState`, `WorldViewerState`, and `ViewerSession` live here as
in-memory JS objects and are never persisted.

---

## Object Assignments

### `observability/types.py`

**`DeltaKind`**

Enum discriminant for `DeltaRecord`. Determines which optional payload group is
populated in the record and which display panel the viewer updates.

**`FieldChange`**

A single field's before/after values identified by a dot-path string. Both values
are JSON-encoded so the viewer can apply delta highlighting without re-running any
Python formulas in JavaScript. The dot-path is the key the viewer uses to target
the correct display element.

**`DeltaRecord`**

One line appended to `state_deltas.jsonl` after every state mutation. Tagged by
`DeltaKind`; the viewer applies records in `game_time` order on top of the nearest
checkpoint to reconstruct simulation state at any scroll position.

**`VillagerMemoryCheckpoint`**

Per-villager memory snapshot embedded inside a `CheckpointRecord`. Carries all
memory tiers, the active context log, and relationship data so the Memory System
can be fully restored from a checkpoint without replaying the event log.

**`CheckpointRecord`**

Complete serialized simulation state written to `checkpoints/{game_time:05d}.json`
every 3 in-game hours. Serves as the restart base for Simulation Engine (which
deserializes and resumes directly) and as the replay base for the viewer (which
applies `DeltaRecord`s forward from this snapshot to reach any target game time).

### `observability/viewer.html`

**`VillagerViewerState`** (JS object)

Viewer-internal in-memory state for one villager at the current scroll position.
Computed by replaying checkpoint + delta records; never persisted. Holds all raw
and derived stats, inventory, current action text, memory texts, relationship
descriptions, and the set of fields that changed at the current scroll position
(used for delta highlighting).

**`WorldViewerState`** (JS object)

Viewer-internal in-memory world state at the current scroll position. Computed
alongside `VillagerViewerState`; never persisted. Holds base storage, water,
fire state, dirtiness, placed resting spots, and carcass count, plus the set of
fields changed at the current scroll position.

**`ViewerSession`** (JS object)

Top-level viewer state maintained as the user scrolls. Tracks which villager's
log is displayed, the current game time derived from the scroll position, and the
current `VillagerViewerState` and `WorldViewerState` for every villager. Rebuilt
from files on page load; updated incrementally on scroll.

---

## Function Definitions

### `observability/types.py`

#### Module-level

```python
def append_delta(data_dir: Path, record: DeltaRecord) -> None:
    """Append record as a JSON line to `{data_dir}/state_deltas.jsonl`. Called by any subsystem that performs a state mutation — Villager State and World State setters call it directly; Simulation Engine calls it for decay and scheduling events."""

def save_checkpoint(data_dir: Path, record: CheckpointRecord) -> None:
    """Write record to `{data_dir}/checkpoints/{record.game_time:05d}.json`. Called by Simulation Engine every 3 in-game hours."""

def load_checkpoint(data_dir: Path, game_time: int) -> CheckpointRecord:
    """Deserialize `checkpoints/{game_time:05d}.json`. Used by Simulation Engine for checkpoint restart."""
```

---

### `observability/viewer.html`

JavaScript functions; TypeScript-style signatures for precision.

#### `ViewerSession`

```typescript
async function initSession(dataDir: string): Promise<ViewerSession>
// Load all checkpoints, build the delta index, and load the first villager's event log.
// Return a fully initialized ViewerSession positioned at the end of the log.

async function selectVillager(session: ViewerSession, villagerId: string): Promise<ViewerSession>
// Load the given villager's event log and return a session with visible_events refreshed.
// State stays at session.current_game_time; no delta replay needed.

function scrollToEvent(session: ViewerSession, eventIndex: number): ViewerSession
// Move current_game_time to the game_time of the event at eventIndex. When scrolling
// forward, applies deltas between old and new game_time incrementally. When scrolling
// backward, calls reconstructStateAt from the nearest preceding checkpoint. Returns the
// updated session. changed_fields reflects only deltas at exactly the new game_time (ATTR-16).
```

#### Standalone — State Reconstruction

```typescript
function reconstructStateAt(
  checkpoints: CheckpointRecord[],
  deltaIndex: Map<number, DeltaRecord[]>,
  targetTime: number
): { villager_states: Map<string, VillagerViewerState>; world_state: WorldViewerState }
// Find the nearest checkpoint with game_time <= targetTime; apply all delta records from
// that checkpoint through targetTime. Handles all four DeltaKind values. Populates
// changed_fields using only deltas at exactly targetTime (ATTR-16 highlighting).
```

#### Standalone — Data Loading

```typescript
async function loadAllCheckpoints(dataDir: string): Promise<CheckpointRecord[]>
// Parse all files in checkpoints/ and return them sorted chronologically.

async function loadDeltaIndex(dataDir: string): Promise<Map<number, DeltaRecord[]>>
// Read state_deltas.jsonl and return records grouped by game_time for O(1) replay lookup.
```

---

## Cross-Subsystem Implementation Decisions

Style decisions that emerged from designing the observability layer but apply to the broader codebase.

**`get_valid_actions` decomposition.** Implement as a registry of per-action-type `(predicate, formatter)` pairs rather than a monolithic function. Each action type defines its own eligibility predicate and description formatter; `get_valid_actions` iterates over the registry. Keeps cyclomatic complexity flat regardless of how many action types exist.

**Simulation Engine dispatch decomposition.** Each event type handled by a dedicated named function — `_handle_action_completion`, `_handle_fire_extinction`, `_handle_carcass_rot`, `_handle_forced_sleep`, `_handle_death`, `_handle_midnight`, `_handle_checkpoint`. The dispatch loop is a short `match` on event type; all logic lives in the handlers.

**`run_conversation` decomposition.** Decompose into `_run_turn_loop`, `_run_bystander_join`, `_run_trade`, and `_score_post_conversation`. `run_conversation` is an orchestrator that calls these in sequence. Each concern is independently readable and testable.

**`compute_stats` safety context.** Pass world context as a `WorldContext` dataclass (`base_calories: int`, `base_firewood_minutes: int`, `living_villager_count: int`) rather than three positional primitives. Prevents silent argument transposition.

**`apply_decay` return type.** Returns `list[ThresholdCrossing]` where `ThresholdCrossing` is a typed dataclass with a `kind: CrossingKind` field (`WAKEFULNESS_ZERO` | `HEALTH_ZERO`). Simulation Engine pattern-matches on `kind`; unhandled crossing kinds are a type error, not a silent no-op.

**AI Coordinator shared prompt prefix.** A `build_static_prefix(villager_id: str) -> list[PromptSegment]` function assembles the shared segment (system prompt, backstory, bios, relationship data). All seven prompt templates call it. Prevents silent divergence when any shared field changes.

**Autobalance multipliers as explicit argument.** `AutobalanceMultipliers` is passed as an explicit argument to `get_valid_actions`, `start_action`, and `complete_action`. Simulation Engine holds the authoritative copy and passes it at each call site. Action System has no implicit dependency on Simulation Engine internals.

**Memory compaction trigger ownership.** `last_compaction_game_time` is owned by Memory System, stored per villager alongside the rest of the memory state. Memory System exposes `should_compact(villager_id: str, current_game_time: int) -> bool` which encapsulates the 4-hour trigger logic. Simulation Engine calls `should_compact` at action completion; no other subsystem tracks this timestamp.
