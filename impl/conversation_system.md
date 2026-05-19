# Conversation System — Implementation Details

## Overview

Conversation System runs multi-villager conversations synchronously. It is called by
Simulation Engine via `run_conversation(initiator_id, target_id)` and blocks until the
conversation ends, returning elapsed game minutes and all participant IDs. Simulation
Engine uses the participant list to reschedule any interrupted base tasks (BHVR-44). It
manages the turn loop, the join pause after turn 2, the trade sub-protocol, and
post-conversation social updates.

Most conversation-related types (`ConversationSnapshot`, `TradeSnapshot`, `ConvActionType`,
`TradeActionType`, `ConversationTurn`, `TradeTurnRecord`, `ConversationTurnResult`,
`TradeTurnResult`) are defined in `ai_coordinator.types` because AI Coordinator is their
primary consumer. Conversation System constructs and passes them.

The two structs Conversation System genuinely owns are the in-flight session state
(`ConversationSession`) and the in-flight trade sub-protocol state (`ActiveTrade`). Both
exist only for the duration of one `run_conversation` call.

---

## Core Objects

### ActiveTrade

In-progress trade sub-protocol state. Constructed when a participant selects `TRADE`,
destroyed when the trade completes or cancels. Conversation System constructs
`TradeSnapshot` (from `ai_coordinator.types`) on demand from this struct.

```thrift
struct ActiveTrade {
    1: string initiator_id,            // the participant who selected TRADE; acts first (BHVR-58)
    2: string partner_id,              // the named trade target
    3: list<TradeTurnRecord> history,  // all trade turns in chronological order;
                                       // TradeTurnRecord is imported from ai_coordinator.types
    4: i32 turn_count,                 // total trade turns taken; cancel after 6 (BHVR-62)
}
```

**Notes:**

- **Whose turn:** `initiator_id` when `turn_count % 2 == 0`, `partner_id` otherwise.
  Derived; not stored.

- **ACCEPT validity (BHVR-63):** When a party returns `ACCEPT`, honor it only if the most
  recent `TradeTurnRecord` in `history` from the *other* party has `action == MAKE_OFFER`.
  If the condition is not met, treat the ACCEPT as a no-op (append nothing to history,
  increment `turn_count`, continue the trade).

- **Cancellation (BHVR-62):** When `turn_count == 6` and the trade has not completed,
  Conversation System cancels it, appends a cancellation `EventLogEntry` to each
  participant's Memory System log, clears `active_trade`, and resumes the conversation
  turn loop.

- **Completion:** When ACCEPT is validly honored, Conversation System calls
  `VillagerState.modify_inventory` on both parties to transfer items simultaneously
  (INVR-60, BHVR-63). Both parties' most recent `MAKE_OFFER` items are exchanged — the
  acceptor receives the counterpart's last offer, and the counterpart receives the
  acceptor's last offer.

- **Zero game time (BHVR-61):** Trade turns do not increment
  `ConversationSession.elapsed_game_minutes`.

- **Visibility:** All trade events are appended to the Memory System log of every
  conversation participant (BHVR-57) — all participants are present for the trade.

- **`TradeSnapshot` construction:** For prompting participant `v`, Conversation System
  builds `TradeSnapshot(other_villager_id=<their counterpart>, history=history, turn_count=turn_count)`.
  The `other_villager_id` is whichever of `initiator_id`/`partner_id` is not `v`.

---

### ConversationSession

Full mutable state of an in-progress conversation. Exists only while
`run_conversation` is executing. Conversation System constructs `ConversationSnapshot`
(from `ai_coordinator.types`) on demand via `snapshot_for(villager_id)`.

```thrift
struct ConversationSession {
    1: list<string> participant_ids,          // active participants in join order; shrinks as villagers leave
    2: list<string> all_participant_ids,      // append-only join-order roster; never shrinks; used for
                                              // post-conversation updates to cover early leavers
    3: list<ConversationTurn> full_turn_log,  // every resolved non-silent turn in chronological order,
                                              // unfiltered across all participants;
                                              // ConversationTurn is imported from ai_coordinator.types
    4: map<string, i32> join_turn_index,      // villager_id → index into full_turn_log where this
                                              // participant first entered the conversation;
                                              // 0 for initiator and original target
    5: i32 elapsed_game_minutes,             // total game minutes consumed; 0–60; increments by 5
                                              // per resolved turn (BHVR-54); NOT incremented by trade turns
    6: map<string, i32> last_spoke_turn,     // villager_id → full_turn_log index of the last turn
                                              // where this participant's action won priority resolution;
                                              // absent for participants who have never won a turn;
                                              // lower value means spoke less recently → wins tiebreak
    7: optional ActiveTrade active_trade,    // non-null while a trade sub-protocol is active
}
```

**`snapshot_for(villager_id: str) -> ConversationSnapshot`:** Returns a
`ConversationSnapshot` for the given participant, slicing `full_turn_log` from
`join_turn_index[villager_id]` forward. Defined on `ConversationSession`; callers use this
instead of open-coding the slice.

---

## Key Logic Notes

### Turn Loop

One turn resolves at a time. Per turn:

1. All current `participant_ids` are prompted in parallel via
   `ai_coordinator.get_conversation_turn(villager_id, snapshot, game_time)`.
2. **Process LEAVE first:** all participants who returned `LEAVE` are immediately removed
   from `participant_ids` (BHVR-51 exception). `all_participant_ids` is never modified.
   Their leave is appended to `full_turn_log`.
3. From the remaining results, call `_select_winner` to get the winning action by priority
   and recency tiebreak.
4. All non-winning non-LEAVE results are discarded (BHVR-51).
5. The winning turn is appended to `full_turn_log`; `elapsed_game_minutes += 5`;
   `last_spoke_turn[winner] = len(full_turn_log) - 1`.

**End condition (BHVR-55):** after each turn, check `len(participant_ids) <= 1` or
`elapsed_game_minutes >= 60`. If either is true, end the conversation.

**Priority order (highest to lowest):**
LEAVE → INTERACT → TRADE → INTERRUPT → CONTINUE → RESPOND → CHANGE_TOPIC → CASUAL → SILENT

LEAVE is processed separately (concurrent), not through this order. SILENT actions never
win: if all remaining (non-leaving) participants chose SILENT, no action wins, but
`elapsed_game_minutes` still increments by 5 and the loop continues — no `ConversationTurn`
is appended for silent turns.

**Tiebreak:** if two participants chose actions of the same `ConvActionType`, the one whose
`last_spoke_turn` entry is absent (never spoken) or lower wins. Ties broken by enum
declaration order of `ConvActionType` as a final fallback.

### Turn 1 Initiator-Only (BHVR-52)

Turn 0 (the first turn) queries only the initiator, not the original target. The result
wins by default — no priority resolution needed. Set `last_spoke_turn[initiator_id] = 0`
after appending.

### Join Pause After Turn 2 (BHVR-45)

After the second turn completes (`len(full_turn_log) == 2`), the conversation loop pauses.
Conversation System:

1. Queries World State for villagers who are at base, awake, not exploring, not hauling,
   and not already in `participant_ids`.
2. For each such villager, calls
   `ai_coordinator.get_join_decision(villager_id, current_action_description, snapshot)`
   where `snapshot.history` is `full_turn_log[:2]` (the opening excerpt, per VRBTM-42).
3. All join decisions are made in parallel, then results are applied atomically.
4. Each joiner: append `villager_id` to both `participant_ids` and `all_participant_ids`;
   set `join_turn_index[villager_id] = len(full_turn_log)`. `last_spoke_turn` entry
   remains absent (never spoken).
5. Resume the turn loop.

### ConversationSnapshot Construction

Use `session.snapshot_for(villager_id)` wherever a per-participant snapshot is needed —
in `_resolve_single_turn`, `_pause_for_joiners`, and `_apply_post_conversation_updates`.

### Trade Sub-Protocol Activation

When a winning `ConversationTurnResult` has `action == TRADE`:

1. Set `active_trade = ActiveTrade(initiator_id=winner, partner_id=result.target_id, history=[], turn_count=0)`.
2. Suspend the conversation turn loop.
3. Alternate trade turns between `initiator_id` and `partner_id` by calling
   `ai_coordinator.get_trade_turn` until the trade completes or cancels.
4. Append all trade events to each participant's Memory System log (BHVR-57).
5. Clear `active_trade`. Resume the conversation turn loop.

### Turn Text Format

`format_turn_text(result, villager_name, target_name?) -> str` builds the
`ConversationTurn.text` string from a resolved turn result. Convention:

- Speech actions (INTERRUPT, CONTINUE, RESPOND, CHANGE_TOPIC): `"{villager_name}: {resp}"`
- Action types (INTERACT, CASUAL): `"{resp}"` — LLM generates `resp` in third person
  (e.g., `"Aldric stands up and moves closer to the fire."`)
- TRADE initiation: `"{villager_name} asks {target_name} if they want to trade."`
- LEAVE: `"{villager_name} leaves the conversation."`
- SILENT: no `ConversationTurn` appended

### Post-Conversation Flow

After the turn loop ends:

1. For each villager in `all_participant_ids` (including early leavers, per BHVR-65): call
   `ai_coordinator.get_social_score(villager_id, snapshot, game_time)`. Apply
   `social_joy_delta = score - 5`; clip the result `social_joy + delta` to [0, 100] via
   `VillagerState.modify_stat` (BHVR-66).

2. Apply `+20 connectedness` to all villagers in `all_participant_ids`, including early
   leavers, via `VillagerState.modify_stat("connectedness", 20)` (BHVR-73).

3. For every ordered pair `(speaker, subject)` where `speaker != subject` and both are in
   `all_participant_ids`: call
   `ai_coordinator.get_relationship_update(speaker, subject, snapshot, game_time)`.
   Call `memory_system.write_impressions(speaker, subject, impression, desc_update)` with
   the result (BHVR-67–71).

All social-score and relationship queries for the same participant are issued in parallel.

### Memory System Event Appending (BHVR-53)

After each resolved turn (including trade turns), Conversation System appends the
`ConversationTurn` text as an `EventLogEntry` with `type=CONVO_TURN` to every participant
who was present for that turn — i.e., every villager in `participant_ids` at the time of
the turn. Trade events use `type=TRADE`. This is done immediately after each turn, not
batched at conversation end.

### Cleanliness Flag in Conversation Prompts (BHVR-184)

AI Coordinator reads `VillagerState.cleanliness` for each participant when assembling the
conversation-turn prompt. Conversation System does not pass cleanliness data separately —
AI Coordinator accesses VillagerState directly for this check. No struct field needed.

---

## File Hierarchy

```
conversation_system/
    types.py        — ConversationSession, ActiveTrade. No LLM dependency.
                      Imports ConversationTurn, TradeTurnRecord, ConversationSnapshot
                      from ai_coordinator.types. ConversationSession.snapshot_for is
                      defined here.

    conversation.py — ConversationSystem class: run_conversation and all turn-loop logic.
                      Also contains format_turn_text (pure function, no dependencies).
                      Imports from types.py, ai_coordinator, villager_state, world_state,
                      memory_system.
```

**Dependency direction:** `conversation.py` imports from `types.py` and all subsystems it
calls. `types.py` imports from `ai_coordinator.types` only. No cycles.

---

## Step 1 — File Hierarchy and Object Docstrings

### Files

#### `conversation_system/types.py`

```
Pure data structures for the conversation and trade sub-protocols.

Owns ConversationSession and ActiveTrade — the two mutable structs that track
in-flight conversation and trade state respectively. ConversationSession exposes
snapshot_for(villager_id) as a thin accessor for per-participant history slices;
all other mutation is performed by ConversationSystem in conversation.py.
Imports ConversationTurn, TradeTurnRecord, and ConversationSnapshot from
ai_coordinator.types for type annotations; no other subsystem dependencies.
```

#### `conversation_system/conversation.py`

```
Conversation orchestration: the ConversationSystem class and its turn-loop logic.

Implements run_conversation, the single entry point called by Simulation Engine.
Manages the main turn loop, the join-pause after turn 2, the trade sub-protocol,
and all post-conversation social updates. Coordinates calls to AI Coordinator,
Villager State, World State, and Memory System. Also contains format_turn_text,
a pure function that builds ConversationTurn.text from a resolved turn result.
Imports types from types.py and all subsystems it calls.
```

---

### Objects

#### `ActiveTrade` → `conversation_system/types.py`

```
Mutable state for one in-progress trade sub-protocol.

Created when a participant selects TRADE during a conversation turn; destroyed
when the trade completes (accepted) or cancels (6 turns without acceptance).
ConversationSystem reads this struct to determine whose turn it is and whether
an ACCEPT is valid, and mutates it after each trade turn. Whose turn it is is
derived from turn_count % 2 rather than stored explicitly.
```

#### `ConversationSession` → `conversation_system/types.py`

```
Mutable state for one in-progress conversation, from first turn to final exit.

Holds the active participant roster (participant_ids, shrinks on LEAVE) and the
append-only full roster (all_participant_ids, used for post-conversation updates
covering early leavers). Also holds the full ordered turn log, per-participant
join indices (for history slicing via snapshot_for), elapsed game minutes,
last-spoke tracking (for priority tiebreak; absent means never won a turn), and
the optional active trade sub-protocol. Created at the start of run_conversation
and discarded when it returns.
```

#### `ConversationSystem` → `conversation_system/conversation.py`

```
Orchestrates multi-villager conversations from initiation to post-conversation
social updates.

Exposes a single entry point: run_conversation(initiator_id, target_id), which
blocks synchronously until the conversation ends and returns (elapsed_minutes,
all_participant_ids) so Simulation Engine can reschedule any interrupted tasks
(BHVR-44). All turn-loop decisions, join-pause handling, trade sub-protocol
activation, and Memory System writes happen inside this class. Stateless between
calls — no fields persist across separate conversations.
```

---

## Step 2 — Core Functions

### `conversation_system/types.py`

`ActiveTrade` is a pure data structure with no methods.

`ConversationSession` exposes one method:

```python
def snapshot_for(self, villager_id: str) -> ConversationSnapshot:
```
> Returns a `ConversationSnapshot` for `villager_id`, with history sliced from
> `join_turn_index[villager_id]` forward. Call this wherever a per-participant snapshot
> is needed instead of open-coding the slice.

---

### `conversation_system/conversation.py`

#### `format_turn_text`

```python
def format_turn_text(
    result: ConversationTurnResult,
    villager_name: str,
    target_name: Optional[str] = None,
) -> str:
```
> Pure function. Builds the `ConversationTurn.text` string from a resolved turn result
> using the per-action-type format rules. `target_name` is required only for TRADE
> initiation. LEAVE and speech actions use only `villager_name`.

---

#### `ConversationSystem`

```python
async def run_conversation(
    self,
    initiator_id: str,
    target_id: str,
    game_time: int,
) -> tuple[int, list[str]]:
```
> Entry point called by Simulation Engine. Initializes a `ConversationSession`,
> runs the turn loop to completion, applies post-conversation updates, and returns
> `(elapsed_game_minutes, all_participant_ids)`. Simulation Engine uses the participant
> list to reschedule any interrupted tasks (BHVR-44).

---

```python
async def _run_turn_loop(
    self,
    session: ConversationSession,
    game_time: int,
) -> None:
```
> Drives turns until ≤1 participant remains or 60 game-minutes have elapsed. After
> the second resolved turn, calls `_pause_for_joiners`. After each turn where the
> winning action is TRADE, suspends the loop and calls `_run_trade_subprotocol`
> before resuming.

---

```python
async def _resolve_single_turn(
    self,
    session: ConversationSession,
    game_time: int,
) -> Optional[ConversationTurnResult]:
```
> Prompts all current participants in parallel (turn 0: initiator only, per
> BHVR-52). Removes all concurrent LEAVEs from the session first. Calls
> `_select_winner` on the remaining responses to get the winning action. Builds
> turn text via `format_turn_text`, appends the winning turn to
> `session.full_turn_log`, updates `last_spoke_turn`, and writes the turn to each
> participant's Memory System log. Returns the winning result, or `None` if all
> participants left or all chose SILENT.

---

```python
def _select_winner(
    self,
    responses: dict[str, ConversationTurnResult],
    session: ConversationSession,
) -> Optional[ConversationTurnResult]:
```
> Pure selection logic. Given non-LEAVE responses keyed by villager ID, returns the
> winning result by priority order (INTERACT > TRADE > INTERRUPT > CONTINUE > RESPOND >
> CHANGE_TOPIC > CASUAL > SILENT), then recency tiebreak (absent `last_spoke_turn` beats
> any present value; lower present value wins), then `ConvActionType` enum order as a
> final fallback. Returns `None` if `responses` is empty or all chose SILENT.

---

```python
async def _pause_for_joiners(
    self,
    session: ConversationSession,
    game_time: int,
) -> None:
```
> Queries all eligible bystanders (at base, awake, not exploring or hauling, not
> already in the session) in parallel via `ai_coordinator.get_join_decision`,
> passing the first two turns as the excerpt. Adds all joiners to both
> `participant_ids` and `all_participant_ids` atomically before the turn loop resumes.

---

```python
async def _run_trade_subprotocol(
    self,
    session: ConversationSession,
    trade_initiator_id: str,
    trade_partner_id: str,
    game_time: int,
) -> None:
```
> Constructs an `ActiveTrade` and alternates trade turns between the two
> participants via `ai_coordinator.get_trade_turn` until: one party accepts a
> standing offer (BHVR-63), or 6 turns elapse without acceptance (BHVR-62).
> On acceptance, transfers items via `VillagerState.modify_inventory` for both
> parties. Appends all trade events to every conversation participant's Memory
> System log (BHVR-57). Does not advance `session.elapsed_game_minutes` (BHVR-61).

---

```python
async def _apply_post_conversation_updates(
    self,
    session: ConversationSession,
    game_time: int,
) -> None:
```
> Iterates over `session.all_participant_ids` (covering early leavers). Queries
> social score (0–10) via `ai_coordinator.get_social_score` and applies `score − 5`
> as a `social_joy` delta, clipping the result to [0, 100] (BHVR-66). Applies
> `+20 connectedness` to all participants (BHVR-73). Queries relationship impressions
> for every ordered pair via `ai_coordinator.get_relationship_update` and writes
> results to Memory System (BHVR-67–71). All queries for the same participant are
> issued in parallel.
