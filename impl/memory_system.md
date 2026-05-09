# Memory System — Implementation Details

## Overview

Memory System is the per-villager cognitive archive: event logs, compacted memory tiers,
thoughts, and relationship records. It is the only subsystem other than AI Coordinator that
drives LLM calls — compaction prompts and relationship-update prompts run through LLM Client.

Three subsystems write into it:
- **Simulation Engine** — appends villager action events and base events; triggers snapshots
- **Conversation System** — appends conversation/trade events; writes post-conversation impressions and relationship description updates
- **AI Coordinator** — reads assembled memory context for prompt construction

It calls one subsystem:
- **LLM Client** — for short-term, medium-term, and long-term compaction; for relationship description updates

---

## Core Objects

### EventType

Categories of log entries. Used by observability to filter and display events, and to
distinguish thoughts (which are formatted differently in prompts) from other entries.

```thrift
enum EventType {
    ACTION     = 1,   // villager's own action: start or completion
    THOUGHT    = 2,   // LLM-generated thought snippet (VRBTM-240, BHVR-249)
    CONVO_TURN = 3,   // a single turn within a conversation
    TRADE      = 4,   // a trade action within a conversation sub-protocol
    BASE_EVENT = 5,   // camp-level event visible to present awake villagers
                      // (fire out, carcass rotted, death notification, etc.)
}
```

---

### EventLogEntry

One timestamped entry in a villager's perspective-filtered log. Filtering is done by callers
before calling `append_event` — the Memory System stores whatever it receives without
re-checking visibility. Each entry is written to the persistent `event_log` on disk and
simultaneously added to the `active_context_log` (the in-context window fed into compaction).

```thrift
struct EventLogEntry {
    1: i32 game_time,    // game-minutes from epoch when the event occurred
    2: EventType type,
    3: string text,      // human-readable description; fed verbatim into compaction prompts
}
```

**Notes:**
- `text` must be self-contained: it is fed directly into compaction LLM calls without
  surrounding context. Callers (Simulation Engine, Conversation System) are responsible
  for writing complete, unambiguous text.
- Thoughts (`EventType.THOUGHT`) are `append_thought` calls internally converted to entries
  with this type before being appended to both logs.

---

### MemoryEntry

A single compacted memory summary at any tier. Short-term, medium-term, and long-term
memories all use this struct — the distinction is which list they reside in.

```thrift
struct MemoryEntry {
    1: i32 game_time,   // game-minutes when this compaction was performed
    2: string text,     // LLM-generated summary; ≤128 tokens (short-term) or ≤256 (medium/long)
}
```

**Notes:**
- `game_time` is used to identify which calendar day a short-term memory belongs to
  (`game_time // 1440`), which is needed by midnight compaction to select "previous day"
  entries (BHVR-256).
- No explicit `day` field needed: day is always derivable from `game_time`.

---

### RelationshipRecord

One ordered pair `(x, y)` — x's view of y. Initialized with the default description for all
pairs at startup (CONST-244). Updated after conversations by LLM-generated text (BHVR-67,
BHVR-70, BHVR-71).

```thrift
struct RelationshipRecord {
    1: string description,               // ≤128 tokens; initial: "I don't know anything about them."
    2: list<string> recent_impressions,  // FIFO, capped at 3 entries; each ≤32 tokens
}
```

**Notes:**
- `recent_impressions` is maintained as a bounded FIFO: when a 4th impression is added,
  the oldest is dropped. The list always contains 0–3 entries.
- `description` is replaced wholesale when Conversation System calls `write_impressions`
  with an optional `desc_update` string (BHVR-71). If no `desc_update` is provided,
  `description` is unchanged.
- The relationship map is keyed `relationships[speaker_id][subject_id]`. For 6 villagers
  there are 30 ordered pairs; all are initialized at startup.

---

### CompactionReason

Why a short-term compaction was triggered. Used for diagnostic logging; does not affect
the compaction prompt or behavior.

```thrift
enum CompactionReason {
    SLEEP           = 1,   // villager went to sleep (BHVR-251)
    AWAKE_THRESHOLD = 2,   // ≥4 awake hours since last compaction (BHVR-252)
}
```

Midnight medium-term compaction and long-term compaction have no `CompactionReason` because
they are not per-villager triggers — they fire globally and are not passed through this enum.

---

### VillagerMemoryContext

Assembled memory context returned to AI Coordinator by `get_memory_context`. Contains
everything the AI Coordinator needs to populate the memory and relationship sections of the
villager's action-selection prompt (STRCT-231, STRCT-230).

```thrift
struct VillagerMemoryContext {
    1: list<MemoryEntry> long_term_memories,       // all long-term entries in chronological order
    2: list<MemoryEntry> medium_term_memories,     // all medium-term entries not yet in long-term
    3: list<MemoryEntry> short_term_memories,      // current-day short-term entries (previous-day
                                                   // entries are compacted at midnight)
    4: list<EventLogEntry> active_context_log,     // events since last compaction, includes thoughts
    5: map<string, RelationshipRecord> relationships,  // keyed by other villager_id; always 5 entries
}
```

**Notes:**
- AI Coordinator renders these fields into the prompt in the order mandated by REQ-224
  (static-to-dynamic). Long-term memories are most-static; the active context log is
  least-static.
- `relationships` always has exactly 5 entries (one per other villager). Keys are stable
  villager IDs from Character Canon.
- The total memory budget across all tiers is ≤2k tokens (CONST-261). AI Coordinator is
  responsible for enforcing this at render time — Memory System does not truncate here.
- `active_context_log` entries are in chronological order. Thoughts are included inline
  (EventType.THOUGHT entries), appearing at the point in time they were generated.

---

## Key Logic Notes

### Compaction Triggers

**Short-term (BHVR-251, BHVR-252):**
1. Villager goes to sleep → trigger immediately
2. Villager completes any action AND `awake_minutes_since_compaction >= 240` → trigger

Both checks are driven by Simulation Engine. After triggering, Simulation Engine calls
`VillagerState.reset_compaction_counter()`. Memory System submits the `active_context_log`
to LLM Client as a compaction prompt, stores the resulting `MemoryEntry` in
`short_term_memories`, and clears `active_context_log`.

**Medium-term (BHVR-255, BHVR-256):**
At midnight (each time `game_time % 1440 == 0`), Simulation Engine triggers midnight
compaction. Memory System collects all `short_term_memories` with `game_time // 1440 ==
previous_day`, submits them to LLM Client, stores one `MemoryEntry` in
`medium_term_memories`, and removes those short-term entries.

If no short-term memories exist for the previous day (e.g., villager was asleep all day and
short-term compaction hasn't fired yet), midnight compaction is a no-op for that villager.

**Long-term (BHVR-259):**
Fires every third day (day 3, 6, 9, …). Memory System collects all `medium_term_memories`
formed since the last long-term compaction, submits them to LLM Client, stores one
`MemoryEntry` in `long_term_memories`, and removes those medium-term entries. The timestamp
of the last long-term compaction is tracked internally (not in any exposed struct).

### Post-Conversation Relationship Updates

After each conversation, Conversation System calls `write_impressions` for every ordered
pair `(x, y)` where both participated. Memory System:
1. Appends the new impression to `relationships[x][y].recent_impressions`, dropping the
   oldest if the list already has 3 entries (BHVR-70).
2. If `desc_update` is provided, replaces `relationships[x][y].description` wholesale
   (BHVR-71). The LLM call that generates the impression and optional description update
   is made by AI Coordinator (via `get_relationship_update`) — Memory System only stores
   the result.

### Persistence and Snapshots

`event_log` (the full historical record) is appended to disk in JSON Lines format after
each `append_event` call. The `active_context_log` is in-memory only; its disk copy is
preserved as part of the event_log.

Checkpoints (BHVR-271, REQ-272): when Simulation Engine calls `trigger_snapshot`, Memory
System serializes its complete in-memory state — `short_term_memories`,
`medium_term_memories`, `long_term_memories`, `active_context_log`, `relationships`, and
`last_long_term_compaction_day` — to a single `.json` checkpoint file. Checkpoint format
is the same for all subsystems; Simulation Engine coordinates the combined write.

---

## API Surface

```python
def append_event(self, villager_id: str, entry: EventLogEntry) -> None:
    """Append one event to the villager's active_context_log and full event_log.
    Flushes the entry to disk immediately."""

def append_thought(self, villager_id: str, game_time: int, text: str) -> None:
    """Append a villager's thought as an EventLogEntry with type=THOUGHT.
    Wraps append_event; exists as a named API to make the call site in Simulation Engine
    unambiguous."""

def write_impressions(
    self,
    speaker_id: str,
    subject_id: str,
    impression: str,
    desc_update: str | None,
) -> None:
    """Append impression to the speaker's recent-impression queue for subject (FIFO, cap 3).
    If desc_update is provided, replace the relationship description wholesale."""

async def trigger_short_term_compaction(
    self, villager_id: str, reason: CompactionReason
) -> None:
    """Submit active_context_log to LLM for compaction; store result in short_term_memories;
    clear active_context_log. Called by Simulation Engine on sleep or 4h-awake threshold."""

async def trigger_midnight_compaction(self) -> None:
    """For each villager: compact previous-day short-term memories into one medium-term entry.
    Also runs long-term compaction if today is day 3, 6, 9, etc."""

def trigger_snapshot(self) -> dict[str, object]:
    """Return fully serializable snapshot of all in-memory memory state for checkpointing."""

def get_memory_context(self, villager_id: str) -> VillagerMemoryContext:
    """Assemble and return all memory tiers, active log, and relationships for the villager.
    Called by AI Coordinator immediately before prompt assembly."""
```

---

## File Hierarchy

```
memory_system/
    types.py        — EventType, EventLogEntry, MemoryEntry, RelationshipRecord,
                      CompactionReason, VillagerMemoryContext. No logic; no LLM dependency.

    memory.py       — MemorySystem class: all state and logic. Owns the in-memory data
                      structures and the async compaction paths. Imports LLMClient.
```

No `__init__.py` re-export layer. Callers import directly from `memory_system.types` or
`memory_system.memory`.

**Dependency direction:** `memory.py` imports from `types.py` and `llm_client`. `types.py`
imports nothing from within the package. No cycles.

---

## Step 1 — File Docstrings and Object Assignments

### File Docstrings

#### `memory_system/types.py`

```
Pure data types for the Memory System: enums, named structs (dataclasses), and the
assembled-context container returned to AI Coordinator. Contains no business logic
and carries no dependency on LLM Client or any other subsystem. All other subsystems
that touch memory (Simulation Engine, Conversation System, AI Coordinator) import
from here; memory.py imports from here as well.
```

#### `memory_system/memory.py`

```
The MemorySystem class — the single stateful object for this subsystem. Owns all
per-villager in-memory cognitive state: append-only event logs (flushed to disk as
JSON Lines), tiered compacted memories (short, medium, long-term), the active context
window, and relationship records. Exposes synchronous mutators (append_event,
append_thought, write_impressions, trigger_snapshot, get_memory_context) and async
compaction APIs (trigger_short_term_compaction, trigger_midnight_compaction). The
only file in this package that imports LLMClient.
```

---

### Object Assignments and Docstrings

#### `memory_system/types.py`

**`EventType`** *(enum)*
```
Categories of log entries written into a villager's perspective-filtered event log.
Used by observability to filter and display events, and by prompts to distinguish
thought snippets (THOUGHT) from action records and conversation turns.
```

**`EventLogEntry`** *(dataclass)*
```
One timestamped entry in a villager's event log. Carries a human-readable `text`
string that is fed verbatim into LLM compaction prompts, so callers are responsible
for making the text self-contained and unambiguous without additional context.
Thoughts are stored as THOUGHT-typed entries by append_thought.
```

**`MemoryEntry`** *(dataclass)*
```
A single LLM-generated compacted summary at any memory tier. The tier (short, medium,
long-term) is determined entirely by which list the entry lives in inside MemorySystem
— there is no tier field on the entry itself. game_time records when the compaction ran
and is used to identify which calendar day a short-term entry belongs to for midnight
compaction selection (day = game_time // 1440).
```

**`RelationshipRecord`** *(dataclass)*
```
One directed pair (x, y): x's current description of y (≤128 tokens) plus a FIFO
queue of x's three most recent impressions of y (each ≤32 tokens). Initialized at
startup for every ordered pair of the six villagers with the default description
"I don't know anything about them." Updated after each conversation by
MemorySystem.write_impressions.
```

**`CompactionReason`** *(enum)*
```
Why a short-term compaction was triggered: either the villager went to sleep (SLEEP)
or they completed an action after being awake for ≥4 hours since the last compaction
(AWAKE_THRESHOLD). Used only for diagnostic logging; has no effect on compaction
behavior or the LLM prompt.
```

**`VillagerMemoryContext`** *(dataclass)*
```
Read-only snapshot assembled by MemorySystem.get_memory_context and consumed by
AI Coordinator. Bundles all memory tiers, the active context log, and the full
relationship map for one villager in the order AI Coordinator needs to render
the action-selection prompt (static-to-dynamic: long-term → medium-term →
short-term → active log; relationships alongside character bios).
```

#### `memory_system/memory.py`

**`MemorySystem`** *(class)*
```
The single stateful object for the Memory System subsystem. Manages six per-villager
data structures (full event log on disk, active context log in memory, short/medium/
long-term memory lists, and the relationship map), drives async LLM compaction at
three tiers, and assembles memory context for AI Coordinator. Instantiated once by
Simulation Engine at startup (or deserialized from a checkpoint).
```

---

## Step 1 — Core Functions

### `memory_system/types.py`

Pure data declarations (enums and dataclasses). No core functions.

---

### `memory_system/memory.py` — `MemorySystem`

```python
def __init__(self, villager_ids: list[str], event_log_path: Path) -> None:
    """Initialize per-villager in-memory structures and open the event log file for appending.
    Sets default relationship descriptions for all 30 ordered pairs."""
```

```python
@classmethod
def from_snapshot(cls, snapshot: dict[str, object], event_log_path: Path) -> MemorySystem:
    """Reconstruct a MemorySystem from a checkpoint dict produced by trigger_snapshot."""
```

```python
def append_event(self, villager_id: str, entry: EventLogEntry) -> None:
    """Add entry to the villager's active_context_log and flush it to the JSONL event log on disk."""
```

```python
def append_thought(self, villager_id: str, game_time: int, text: str) -> None:
    """Wrap text as a THOUGHT-typed EventLogEntry and delegate to append_event."""
```

```python
def write_impressions(
    self,
    speaker_id: str,
    subject_id: str,
    impression: str,
    desc_update: str | None,
) -> None:
    """Append impression to speaker's FIFO impression queue for subject, dropping oldest if at cap 3.
    Replace the relationship description wholesale if desc_update is provided."""
```

```python
async def trigger_short_term_compaction(
    self, villager_id: str, game_time: int, reason: CompactionReason
) -> None:
    """Submit active_context_log to LLM, store the resulting MemoryEntry in short_term_memories,
    and clear active_context_log. game_time is recorded on the produced MemoryEntry."""
```

```python
async def trigger_midnight_compaction(self, current_game_time: int) -> None:
    """For each villager: compact previous-day short-term memories into one medium-term MemoryEntry,
    removing the source entries. Also runs long-term compaction if current day is a multiple of 3.
    current_game_time determines which entries are "previous day" and whether long-term fires."""
```

```python
def trigger_snapshot(self) -> dict[str, object]:
    """Return a fully JSON-serializable dict of all in-memory state for checkpointing.
    Includes all memory tiers, active_context_log, relationships, and last_long_term_compaction_day."""
```

```python
def get_memory_context(self, villager_id: str) -> VillagerMemoryContext:
    """Assemble and return all memory tiers, active log, and relationships for prompt construction.
    Called by AI Coordinator immediately before rendering the action-selection prompt."""
```

---

## Flags and Issues

→ FLAG: BHVR-251 triggers short-term compaction unconditionally when a villager goes to sleep, but `active_context_log` may be empty at that moment (e.g., forced sleep immediately after waking before any action or thought is recorded). The spec does not address this case.
    Should short-term compaction be skipped when `active_context_log` is empty, or should it always proceed?

→ FLAG: At midnight, medium-term compaction only collects already-formed short-term memories from the previous calendar day. Events still sitting in a villager's `active_context_log` that occurred on the previous day but haven't yet been short-term-compacted (e.g., from a hunting trip that completed after midnight) are excluded and would end up tagged to the current day when short-term compaction eventually fires. The spec does not address this.
    Should midnight first trigger short-term compaction for all villagers before running medium-term compaction, or is it acceptable for previous-day context-log events to carry over and be compacted under the current day?

→ FLAG: BHVR-67 says "each villmager updates their relationship with every other villmager" after a conversation, and BHVR-68 says this applies "for each ordered pair (x, y) where x ≠ y" — taken literally, all 30 pairs update regardless of who participated. VRBTM-69 scopes its prompt to "in this conversation," and the subsystem and design docs both say "per-other-participant impression," implying only participant pairs update.
    Does relationship updating after a conversation apply only to ordered pairs where both x and y were participants, or to all 30 pairs?

→ ISSUE: `trigger_short_term_compaction` and `trigger_midnight_compaction` have conflicting signatures between the two sections of this document. In "Step 1 — Core Functions," `trigger_short_term_compaction` includes `game_time: int` and `trigger_midnight_compaction` includes `current_game_time: int`; both parameters are absent from the "API Surface" section.

→ ISSUE: The "Key Logic Notes — Compaction Triggers" section states that after short-term compaction fires, Simulation Engine calls `VillagerState.reset_compaction_counter()`, and internally relies on an `awake_minutes_since_compaction` counter. Neither this method nor this field appears anywhere in the Villager State design or subsystem documentation. The ownership and API for this counter are undefined across subsystem boundaries.

→ ISSUE: The "Persistence and Snapshots" section states Memory System serializes state "to a single `.json` checkpoint file," implying it writes to disk directly. The `trigger_snapshot` API surface returns `dict[str, object]`, and the same paragraph states "Simulation Engine coordinates the combined write." All three statements cannot simultaneously be true.
