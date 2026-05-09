# AI Coordinator — Implementation Details

## Overview

AI Coordinator is stateless. It assembles prompts from inputs supplied by other subsystems,
invokes LLM Client, parses structured JSON responses, and returns validated domain objects.
It owns no mutable runtime state — it is a pure function layer over LLM Client.

Two subsystems call into it:
- **Simulation Engine** — `select_action` (action + thought at each decision point)
- **Conversation System** — `get_conversation_turn`, `get_trade_turn`, `get_join_decision`,
  `get_social_score`, `get_relationship_update`

It reads from five other subsystems to assemble prompts:
- **Character Canon** — backstory, per-character bio/personality/desires, profession text
- **Villager State** — stat descriptions, inventory, current action (for other villagers)
- **World State** — `BaseSummary` (items, fire, water, dirtiness, carcasses, placed spots)
- **Action System** — `ActionList` with fully-formatted VRBTM prompt text and selectability flags
- **Memory System** — `VillagerMemoryContext` (all memory tiers, active log, relationships)

`get_memory_compaction` is **not** an AI Coordinator API. Memory System calls LLM Client
directly for compaction, using LLM Client as the shared leaf that breaks the
Memory System ↔ AI Coordinator cycle.

---

## Core Objects

### LLMCallType

Classifier for every prompt type AI Coordinator sends to LLM Client. Used exclusively in
`ParseFailureLog` for diagnostics — has no effect on behavior.

```thrift
enum LLMCallType {
    ACTION_SELECTION    = 1,
    CONVERSATION_TURN   = 2,
    JOIN_DECISION       = 3,
    SOCIAL_SCORE        = 4,
    RELATIONSHIP_UPDATE = 5,
    TRADE_TURN          = 6,
}
```

---

### ConvActionType

The nine selectable actions a villager may take on their conversation turn (VRBTM-46).
Options 3–8 require a `resp` string in `ConversationTurnResult`; TRADE requires a
`target_id`. Owned here because it is an LLM output type — Conversation System imports it.

```thrift
enum ConvActionType {
    LEAVE        = 1,   // exit the conversation
    SILENT       = 2,   // do nothing this turn
    INTERACT     = 3,   // significant physical or social action
    INTERRUPT    = 4,   // sharp interjection
    CONTINUE     = 5,   // continue own previous statement
    RESPOND      = 6,   // reply to the last speaker
    CHANGE_TOPIC = 7,   // redirect the conversation
    CASUAL       = 8,   // light background action (fidget, look around, etc.)
    TRADE        = 9,   // initiate trade sub-protocol with a named participant
}
```

---

### ConversationTurn

One recorded turn in a conversation, as seen by a specific participant. The `text` field
is fully self-contained — a human-readable description of what was said or done — because
it is rendered verbatim into prompts without surrounding context.

```thrift
struct ConversationTurn {
    1: string villager_id,   // stable id of the villager who acted
    2: string text,          // human-readable; e.g. "Aldric: I wouldn't worry about it."
                             //                     "Sewalt stands up and walks to the fire."
}
```

---

### ConversationSnapshot

A snapshot of a conversation session, constructed by Conversation System and passed to AI
Coordinator for all conversation-related prompts. The `history` list is already filtered to
the perspective of the villager being prompted (per BHVR-53 — each villager only sees the
turns they witnessed). `elapsed_game_minutes` provides context for the 60-minute cap.

Used by: `get_conversation_turn`, `get_join_decision` (first 2 history entries as excerpt),
`get_social_score`, `get_relationship_update`.

```thrift
struct ConversationSnapshot {
    1: list<string> participant_ids,     // stable IDs of all current participants, in join order
    2: list<ConversationTurn> history,   // turns in chronological order, visibility-filtered
    3: i32 elapsed_game_minutes,         // 0–60; used for prompt context only
}
```

**Note:** For `get_join_decision`, the caller slices `history` to the first 2 entries and
passes the truncated snapshot. AI Coordinator does not slice internally.

---

### ConversationTurnResult

The parsed output of one `get_conversation_turn` call. Options 3–8 require `resp`; TRADE
requires `target_id`. Both fields are absent for LEAVE and SILENT. AI Coordinator validates
that required fields are present before returning — a missing `resp` on RESPOND is a parse
failure, not a valid SILENT.

```thrift
struct ConversationTurnResult {
    1: ConvActionType action,
    2: optional string resp,       // speech or action text; required for INTERACT through CASUAL
    3: optional string target_id,  // stable villager id of trade target; required for TRADE
}
```

---

### TradeActionType

The four actions available during the trade sub-protocol (VRBTM-59).

```thrift
enum TradeActionType {
    MAKE_OFFER    = 1,
    REQUEST_ITEMS = 2,
    CANCEL        = 3,
    ACCEPT        = 4,   // only valid when the other party's last action was MAKE_OFFER (BHVR-63)
}
```

---

### TradeItemSpec

One item and quantity in a trade offer or request. The LLM output uses item name strings
(VRBTM-59 format); AI Coordinator resolves those to `ItemType` before constructing
`TradeTurnResult`.

```thrift
struct TradeItemSpec {
    1: ItemType item,
    2: i32 quantity,   // always >= 1
}
```

---

### TradeTurnRecord

One trade turn as it appears in the trade history, used to build `TradeSnapshot`. Stores
the resolved types, not the raw LLM strings, so the snapshot is unambiguous.

```thrift
struct TradeTurnRecord {
    1: string villager_id,          // who acted
    2: TradeActionType action,
    3: list<TradeItemSpec> items,   // populated for MAKE_OFFER and REQUEST_ITEMS; empty otherwise
    4: optional string speech,      // ≤32 tokens of side-channel speech (VRBTM-59)
}
```

---

### TradeSnapshot

State of the trade sub-protocol at the moment a villager is prompted. Constructed and
owned by Conversation System; passed to `get_trade_turn`. Provides full history so the
LLM can assess the negotiation context and determine whether ACCEPT is valid (last record
was MAKE_OFFER from the other party per BHVR-63).

```thrift
struct TradeSnapshot {
    1: string other_villager_id,         // the trade partner's stable id
    2: list<TradeTurnRecord> history,    // all trade turns so far in chronological order
    3: i32 turn_count,                   // total trade turns elapsed (6-turn cancel rule, BHVR-62)
}
```

---

### TradeTurnResult

Parsed output of one `get_trade_turn` call. AI Coordinator validates that `items` is
non-empty for MAKE_OFFER and REQUEST_ITEMS, and that the acting villager has sufficient
inventory for MAKE_OFFER items (INVR-60) — failing either check is a parse failure.

```thrift
struct TradeTurnResult {
    1: TradeActionType action,
    2: list<TradeItemSpec> items,   // for MAKE_OFFER or REQUEST_ITEMS; empty otherwise
    3: optional string speech,      // ≤32 tokens; may be absent (VRBTM-59)
}
```

---

### ActionSelectionResult

Output of `select_action`. The thought is requested in the same LLM call as the action
(VRBTM-240, BHVR-249); the JSON response contains `idx`, `args`, and optionally
`thoughts`. AI Coordinator extracts `thoughts` here and returns it alongside the action so
Simulation Engine can write it to Memory System.

```thrift
struct ActionSelectionResult {
    1: SelectedAction action,        // fully validated; idx resolved to ActionType + args
    2: optional string thought,      // ≤32-token snippet; absent if LLM omitted "thoughts" key
}
```

**Thought absence rule:** If the LLM omits the `thoughts` key entirely, `thought` is None
and no entry is written to Memory System. If the key is present but empty, treat as None.

---

### RelationshipUpdateResult

Output of `get_relationship_update` for one ordered pair `(speaker, subject)` after a
conversation ends. `desc_update` is only present when the LLM includes the `"desc"` field,
signaling that the speaker's opinion of the subject has meaningfully changed (BHVR-71).
AI Coordinator validates `impression` is non-empty; an empty impression is a parse failure.

```thrift
struct RelationshipUpdateResult {
    1: string impression,           // ≤32 tokens; x's new impression of y (BHVR-70)
    2: optional string desc_update, // ≤128 tokens; replacement description; absent if opinion unchanged
}
```

---

### ParseFailureLog

Written to disk on every LLM parse failure (BHVR-287), including both the first attempt
and the retry. The file is append-only JSON Lines, one entry per failure. AI Coordinator
crashes (raises) after a failed retry, but still writes this record first.

```thrift
struct ParseFailureLog {
    1: string villager_id,              // villager being prompted; empty string for global calls
    2: LLMCallType call_type,
    3: i32 game_time,                   // game-minutes from epoch when the call was made
    4: list<PromptSegment> prompt,      // complete prompt sent, in segment order (BHVR-287)
    5: string raw_response,             // verbatim LLM output text
    6: string parse_error,              // exact exception message or structural validation error
    7: bool is_retry,                   // true iff this was the second attempt (BHVR-286)
}
```

**Note:** `PromptSegment` is imported from `llm_client.types`. The prompt is logged at the
segment level so the static/dynamic boundary is visible in the failure record.

---

## Prompt Field Order and Cache Breakpoints

The action-selection prompt assembles segments in this static-to-dynamic order (REQ-224,
design.md), for maximum Gemini prefix-cache reuse across calls for the same villager:

1. System prompt (VRBTM-225) — fully static
2. Backstory (VRBTM-226) — fully static
3. Character's own bio/personality/desires (VRBTM-227) — static per villager
4. Other characters' bios + relationship records (VRBTM-229, STRCT-230) — semi-static;
   changes only when a relationship description is updated after a conversation
5. Long-term memories → medium-term → short-term → active context log (STRCT-231) —
   changes on compaction (minutes to hours cadence)
6. World state summary: base items, fire, water, cleanliness, carcasses, villager actions
   (STRCT-232–234) — changes every event
7. Villager state: inventory + stat description strings (STRCT-235–236) — changes every event
8. Valid action list (STRCT-239) — changes every event
9. Thoughts instruction (VRBTM-240) — static
10. Timestamp (STRCT-241) — changes every event

Cache breakpoints (passed to `LLMClient.complete()` as `cache_breakpoint_indices`) are
placed at the end of segment 4 (after other-character bios + relationships) and the end
of segment 5 (after memories). These mark the longest stable prefixes likely to be shared
across successive calls for the same villager.

---

## File Hierarchy (sketch)

```
ai_coordinator/
    types.py        — All structs and enums defined above. No LLM dependency.
                      Conversation System imports ConvActionType, ConversationTurnResult,
                      TradeActionType, TradeTurnResult, etc. from here.

    prompts.py      — One assembly function per call type. Takes fully-typed domain
                      objects (VillagerCanon, ComputedStats, ActionList, VillagerMemoryContext,
                      BaseSummary, ConversationSnapshot, etc.) and returns
                      list[PromptSegment] with cache_breakpoint_indices.

    parser.py       — One parse function per call type. Takes raw LLM response text,
                      validates structure and field constraints, returns the appropriate
                      result struct or raises ParseError. Writes ParseFailureLog to disk
                      on failure (both attempts).

    coordinator.py  — AICoordinator class. Stateless; initialized with references to all
                      subsystems it reads from (CharacterCanon, dict[str, VillagerState],
                      WorldState, ActionSystem, MemorySystem, LLMClient). Each public
                      method delegates to prompts.py (assembly), LLMClient.complete()
                      (invocation), and parser.py (parsing + retry logic).
```

**No `__init__.py` re-export layer.** Callers import directly from `ai_coordinator.types`
or `ai_coordinator.coordinator`.

**Dependency direction:** `coordinator.py` imports from `prompts.py`, `parser.py`,
`types.py`, and all subsystems it reads from. `prompts.py` and `parser.py` import from
`types.py`. `types.py` imports from `llm_client.types`, `action_system.types`, and
`game_types` (for `ItemType`). No cycles.

---

## File Hierarchy

Four files. No sub-packages.

```
ai_coordinator/
    types.py
    prompts.py
    parser.py
    coordinator.py
```

### `types.py`

```
Data structures and enumerations that define the AI Coordinator's input and output
contract. Contains all result structs, enums, and the ParseFailureLog record.

No LLM or subsystem dependencies — import freely. Conversation System in particular
imports ConvActionType, ConversationTurnResult, TradeActionType, and TradeTurnResult
from here.

Imports: llm_client.types (PromptSegment), action_system.types (ActionType), game_types (ItemType).
```

### `prompts.py`

```
Prompt assembly for every AI Coordinator call type. One function per call type;
each takes fully-typed domain objects and returns (list[PromptSegment], list[int])
where the second value is the cache_breakpoint_indices to pass to LLMClient.

No LLM calls, no mutable state. The only place in the codebase that knows how to
render domain state into model-ready segments.

Imports: types.py plus all domain types it renders
(VillagerCanon, VillagerState, WorldState, ActionList, VillagerMemoryContext,
ConversationSnapshot, TradeSnapshot).
```

### `parser.py`

```
Response parsing for every AI Coordinator call type. One function per call type;
each takes the raw completion string from LLMClient, validates the JSON structure
and field constraints, and returns the corresponding typed result struct from types.py.

Raises ParseError on invalid output. Writes a ParseFailureLog entry to the on-disk
.jsonl file on every failure — both the first attempt and the retry.

Imports: types.py, json, pathlib (for failure log path).
```

### `coordinator.py`

```
AICoordinator: the stateless orchestrator. Initialized once with read-only references
to all subsystems it reads from. Each public method calls prompts.py for segment
assembly, LLMClient.complete() for model invocation, and parser.py for response
parsing — with exactly one retry on ParseError before crashing.

This is the only file that sequences those three steps and applies the retry rule.

Imports: prompts.py, parser.py, types.py, llm_client, and all subsystems.
```

---

## Object-to-File Assignments

All structs and enums live in `types.py`. `coordinator.py` contains the single
`AICoordinator` class. `prompts.py` and `parser.py` contain only module-level
functions, no classes.

---

### `types.py` objects

**`LLMCallType`** — Identifies which call type produced a parse failure. Stored in
`ParseFailureLog` for offline diagnostics only; has no effect on routing or behavior.

**`ConvActionType`** — The nine mutually exclusive actions a villager may select on a
conversation turn, listed in the priority order Conversation System uses for turn
resolution.

**`TradeActionType`** — The four actions available to a trade participant during the
trade sub-protocol.

**`ConversationTurn`** — One recorded turn in a conversation session. The `text` field
is a fully self-contained human-readable sentence rendered verbatim into prompts; it
carries its own speaker attribution so no surrounding context is needed.

**`ConversationSnapshot`** — A visibility-filtered snapshot of an in-progress
conversation, constructed and owned by Conversation System. Passed to every
conversation-related AI Coordinator method. History is pre-filtered to what the
prompted villager has witnessed; AI Coordinator does not filter internally.

**`ConversationTurnResult`** — Validated output of one `get_conversation_turn` call.
AI Coordinator guarantees required fields are present (`resp` for actions 3–8,
`target_id` for TRADE) before returning; a missing required field is a parse failure,
not a valid SILENT.

**`TradeItemSpec`** — One item–quantity pair in a trade offer or request. Parser
resolves the LLM's raw item-name string to `ItemType` before constructing this struct,
so callers never see unvalidated strings.

**`TradeTurnRecord`** — One trade turn stored in `TradeSnapshot.history`. Uses
resolved `ItemType` values (not raw LLM strings), so the snapshot is unambiguous when
fed back to the LLM as context.

**`TradeSnapshot`** — State of the trade sub-protocol at the moment a participant is
prompted. Constructed by Conversation System; passed to `get_trade_turn`. The full
history lets the LLM determine whether ACCEPT is currently valid (the other party's
last recorded action must be MAKE_OFFER).

**`TradeTurnResult`** — Validated output of one `get_trade_turn` call. Parser verifies
that `items` is non-empty for MAKE_OFFER/REQUEST_ITEMS and that the villager holds
sufficient inventory for any MAKE_OFFER items; either failure is a parse error.

**`ActionSelectionResult`** — Output of `select_action`. The optional `thought` is
extracted from the same LLM call as the action so Simulation Engine can write both to
Memory System in a single step. Absent `thoughts` key → `thought` is None; no log
entry is written.

**`RelationshipUpdateResult`** — Output of `get_relationship_update` for one ordered
pair after a conversation. `desc_update` is present only when the LLM signals a
meaningful opinion change; absence means the existing description is kept as-is.

**`ParseFailureLog`** — Appended to an on-disk `.jsonl` file on every parse failure,
including both the first attempt and the retry. Written before the crash so the record
is never lost. Captures the full segmented prompt, raw response, and exact error for
offline reproducibility.

---

## Functions

### `types.py`

No functions — pure data structures and enums.

One additional struct belongs here to support failure logging in `parser.py`:

```python
@dataclass
class ParseContext:
    villager_id: str             # empty string for non-villager calls
    call_type: LLMCallType
    game_time: int               # game-minutes from epoch at call time
    prompt: list[PromptSegment]  # full prompt sent, for the failure log
```

**`ParseContext`** — Logging context passed into every `parser.py` function so failure
records (BHVR-287) can be written without the parser importing coordinator state. The
`prompt` field is the same segment list passed to `LLMClient.complete()`.

---

### `prompts.py`

All functions return `tuple[list[PromptSegment], list[int]]` — the assembled segments
and the cache breakpoint indices to pass to `LLMClient.complete()`. No LLM calls, no
mutable state.

```python
def assemble_action_selection(
    own_canon: VillagerCanon,
    other_canons: list[VillagerCanon],
    memory_context: VillagerMemoryContext,
    base_summary: BaseSummary,
    computed_stats: ComputedStats,
    inventory_items: list[tuple[ItemType, int]],
    action_list: ActionList,
    game_time: int,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the action-selection prompt in static-to-dynamic segment order (REQ-224).
    Cache breakpoints fall after other-character data (segment 4) and after memories
    (segment 5). `memory_context.relationships` supplies each other character's
    relationship data to pair with their bio from `other_canons`."""
```

```python
def assemble_conversation_turn(
    own_canon: VillagerCanon,
    other_canons: list[VillagerCanon],
    memory_context: VillagerMemoryContext,
    snapshot: ConversationSnapshot,
    game_time: int,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the conversation-turn prompt for one participant given the filtered
    session history."""
```

```python
def assemble_trade_turn(
    own_canon: VillagerCanon,
    inventory_items: list[tuple[ItemType, int]],
    snapshot: TradeSnapshot,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the trade-turn prompt showing negotiation history and own inventory."""
```

```python
def assemble_join_decision(
    own_canon: VillagerCanon,
    current_action_description: str,
    snapshot: ConversationSnapshot,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the join-decision prompt (VRBTM-42). Caller must pre-slice
    `snapshot.history` to the first two entries before passing."""
```

```python
def assemble_social_score(
    own_canon: VillagerCanon,
    snapshot: ConversationSnapshot,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the post-conversation social satisfaction prompt (VRBTM-64)."""
```

```python
def assemble_relationship_update(
    speaker_canon: VillagerCanon,
    subject_canon: VillagerCanon,
    existing_description: str,
    recent_impressions: list[str],
    snapshot: ConversationSnapshot,
) -> tuple[list[PromptSegment], list[int]]:
    """Render the relationship-update prompt (VRBTM-69) for the ordered pair
    (speaker, subject). `existing_description` and `recent_impressions` come from
    `memory_context.relationships` for this pair and give the LLM context for whether
    its opinion has changed."""
```

---

### `parser.py`

All functions raise `ParseError` on invalid JSON, missing required fields, or violated
constraints. Each failure writes a `ParseFailureLog` entry to disk via `ctx` before
raising — covering both the first attempt and the retry.

```python
def parse_action_selection(
    response: str,
    action_list: ActionList,
    ctx: ParseContext,
) -> ActionSelectionResult:
    """Parse action-selection JSON. Resolves `idx` against `action_list` to a
    `SelectedAction`; raises `ParseError` if the index is out of range, targets a
    non-selectable action (e.g. a "Cannot perform" recipe), or `args` are malformed."""
```

```python
def parse_conversation_turn(
    response: str,
    ctx: ParseContext,
) -> ConversationTurnResult:
    """Parse conversation-turn JSON. Raises `ParseError` if `resp` is absent for
    actions 3–8 or `target_id` is absent for TRADE."""
```

```python
def parse_trade_turn(
    response: str,
    inventory_items: list[tuple[ItemType, int]],
    ctx: ParseContext,
) -> TradeTurnResult:
    """Parse trade-turn JSON. Raises `ParseError` if `items` is empty for
    MAKE_OFFER/REQUEST_ITEMS, or if MAKE_OFFER items exceed the villager's inventory
    (INVR-60)."""
```

```python
def parse_join_decision(response: str, ctx: ParseContext) -> bool:
    """Parse join-decision JSON. Returns True if the villager opts to join."""
```

```python
def parse_social_score(response: str, ctx: ParseContext) -> int:
    """Parse social-score JSON. Raises `ParseError` if the value is not an integer
    in [0, 10]."""
```

```python
def parse_relationship_update(
    response: str,
    ctx: ParseContext,
) -> RelationshipUpdateResult:
    """Parse relationship-update JSON. Raises `ParseError` if `impression` is absent
    or empty."""
```

---

### `coordinator.py` — `AICoordinator`

Every public method follows the same pattern: assemble prompt via `prompts.py`, invoke
`LLMClient.complete()`, parse via `parser.py`. On `ParseError`, retry once with the same
prompt; if the retry also fails, crash. Both failures are logged to disk via
`ParseContext` before the error propagates (BHVR-286, BHVR-287).

```python
def __init__(
    self,
    canon: CharacterCanon,
    villager_states: dict[str, VillagerState],
    world_state: WorldState,
    action_system: ActionSystem,
    memory_system: MemorySystem,
    llm_client: LLMClient,
) -> None:
    """Store read-only references to all subsystems needed for prompt assembly."""
```

```python
def select_action(self, villager_id: str, game_time: int) -> ActionSelectionResult:
    """Fetch all subsystem inputs, assemble the action-selection prompt, invoke the
    LLM, and return the validated action and optional thought."""
```

```python
def get_conversation_turn(
    self,
    villager_id: str,
    snapshot: ConversationSnapshot,
    game_time: int,
) -> ConversationTurnResult:
    """Get the villager's next conversation action given the filtered session
    history."""
```

```python
def get_trade_turn(
    self,
    villager_id: str,
    snapshot: TradeSnapshot,
    game_time: int,
) -> TradeTurnResult:
    """Get the villager's next trade action given the current negotiation state."""
```

```python
def get_join_decision(
    self,
    villager_id: str,
    current_action_description: str,
    snapshot: ConversationSnapshot,
    game_time: int,
) -> bool:
    """Decide whether the villager wants to join an in-progress conversation. Caller
    must pre-slice `snapshot.history` to the opening two turns before passing."""
```

```python
def get_social_score(
    self,
    villager_id: str,
    snapshot: ConversationSnapshot,
    game_time: int,
) -> int:
    """Get the villager's 0–10 social satisfaction score for the just-ended
    conversation."""
```

```python
def get_relationship_update(
    self,
    speaker_id: str,
    subject_id: str,
    snapshot: ConversationSnapshot,
    game_time: int,
) -> RelationshipUpdateResult:
    """Get the speaker's updated impression of the subject after a conversation.
    Reads existing relationship data from `memory_system` to populate the prompt."""
```

---

## Flags and Issues

→ ISSUE: `parse_trade_turn` documents validation of item presence and inventory sufficiency, but does not mention enforcing BHVR-63 — that ACCEPT is only valid when the other party's last recorded action is MAKE_OFFER. The full trade history is available in `TradeSnapshot`, but the parser description omits this check. If the LLM returns ACCEPT out of sequence, it passes through undetected.

→ ISSUE: `assemble_conversation_turn` includes `memory_context` but no current stat values or inventory. During conversation, a villager deciding whether to offer items, request food, or comment on their own condition has only indirect access through whatever recent events appear in their log — not their actual live state. This creates a gap between what the character would know and what the prompt tells them.

→ ISSUE: `assemble_social_score` takes only `own_canon` and `snapshot`, with no access to the villager's prior relationship data for the participants. A villager's satisfaction with a conversation is shaped by their history with those people (e.g., a deeply distrusted participant makes even a neutral exchange feel sour). The existing relationship descriptions and impressions are available in Memory System but are not passed to this prompt.

→ STYLE: Every public method on `AICoordinator` follows the identical assemble → invoke → parse → retry-once → crash sequence. This pattern is repeated six times with no shared helper. A private `_call(assemble_fn, parse_fn, ctx)` would unify the retry/crash/log logic and make each public method a one-liner delegation.

→ STYLE: `game_time: int` is passed as a bare `int` to every public method. A `GameTime` newtype (or even a module-level alias) would prevent silent parameter-order bugs and make call sites self-documenting.

→ STYLE: `villager_id`, `speaker_id`, and `subject_id` are all bare `str`. The ordered pair `(speaker_id, subject_id)` in `get_relationship_update` is easy to swap; swapping is a silent semantic error. A `VillagerId` newtype would make the compiler catch transpositions.

→ STYLE: `assemble_*` functions return an unnamed `tuple[list[PromptSegment], list[int]]`. Callers must remember that index 0 is segments and index 1 is breakpoints. A two-field dataclass (e.g. `PromptPackage`) eliminates positional confusion at every call site with zero extra logic.

→ STYLE: Caller-side pre-filtering is a footgun in two places: (1) `ConversationSnapshot.history` must already be visibility-filtered to the prompted villager's perspective before passing to any `assemble_*` function — AI Coordinator never filters internally; (2) `assemble_join_decision` additionally requires the caller to pre-slice history to the first two entries. Both violations produce silent misbehavior (LLM sees turns it shouldn't). Encoding the slice/filter as a typed wrapper (e.g. `JoinDecisionSnapshot`) would make the constraint impossible to forget.

→ STYLE: `assemble_relationship_update` receives `existing_description: str` and `recent_impressions: list[str]` as separate primitives that the caller must extract from `MemorySystem` and pass correctly for the right ordered pair. This is better expressed as a single `RelationshipRecord` value object so the caller cannot accidentally pass mismatched fields from different villager pairs.
