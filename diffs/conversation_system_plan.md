# Conversation System — Diff Plan

---

## TITLE: [conversation_system][1/9] Types: ConversationSession, ActiveTrade, snapshot_for

**DESCRIPTION:**
Create `conversation_system/` package (`__init__.py`, `types.py`). Define `ActiveTrade` and `ConversationSession` as dataclasses. Implement `ConversationSession.snapshot_for(villager_id)`, the only method on these structs — it slices `full_turn_log` from `join_turn_index[villager_id]` forward and returns a `ConversationSnapshot`. Imports `ConversationTurn`, `TradeTurnRecord`, `ConversationSnapshot` from `ai_coordinator.types` for annotations; no other external dependencies. No logic beyond the accessor.

**TEST PLAN:**
- `snapshot_for` for the initiator (`join_turn_index=0`) returns the full turn log.
- `snapshot_for` for a late joiner (`join_turn_index=k`) returns only turns from index `k` onward; earlier turns are excluded.
- `snapshot_for` on an empty `full_turn_log` returns a snapshot with empty history.
- Constructing `ConversationSession` with valid fields (including no `active_trade`) yields expected attribute values; `active_trade` defaults to `None`.
- Constructing `ActiveTrade` and deriving whose-turn from `turn_count % 2` matches spec: `turn_count=0` → initiator, `turn_count=1` → partner, `turn_count=2` → initiator again.

---

## TITLE: [conversation_system][2/9] format_turn_text pure function

**DESCRIPTION:**
Add `format_turn_text(result, villager_name, target_name?)` to `conversation.py`. Pure function; no imports beyond `ConversationTurnResult` and `ConvActionType`. Implements per-action-type text rules exactly:
- Speech actions (INTERRUPT, CONTINUE, RESPOND, CHANGE_TOPIC): `"{villager_name}: {resp}"`
- Action types (INTERACT, CASUAL): `"{resp}"` verbatim (LLM supplies third-person text)
- TRADE initiation: `"{villager_name} asks {target_name} if they want to trade."`
- LEAVE: `"{villager_name} leaves the conversation."`

`ConversationSystem` shell (class with no methods) added so the file compiles.

**TEST PLAN:**
- Each speech action type (INTERRUPT, CONTINUE, RESPOND, CHANGE_TOPIC) produces `"Name: resp"`.
- INTERACT and CASUAL both produce `"resp"` with no name prefix.
- TRADE produces `"Name asks Target if they want to trade."` — verify `target_name` is used.
- LEAVE produces `"Name leaves the conversation."` — `resp` is ignored.
- Calling with TRADE but `target_name=None` raises (or fails at type check); ensures callers provide target name.

---

## TITLE: [conversation_system][3/9] _select_winner priority and tiebreak

**DESCRIPTION:**
Add `ConversationSystem._select_winner(responses, session)` to `conversation.py`. Pure selection logic: given a `dict[str, ConversationTurnResult]` of non-LEAVE responses, returns the winning result by (1) priority order: INTERACT > TRADE > INTERRUPT > CONTINUE > RESPOND > CHANGE_TOPIC > CASUAL > SILENT; (2) recency tiebreak: absent `last_spoke_turn` beats any present value, lower present value beats higher; (3) `ConvActionType` enum declaration order as final fallback. Returns `None` if `responses` is empty or all chose SILENT.

**TEST PLAN:**
Priority:
- INTERACT beats every lower-priority action (test INTERACT vs TRADE, INTERACT vs CASUAL).
- TRADE beats INTERRUPT; INTERRUPT beats CONTINUE; a mid-priority action beats SILENT — spot-checking the chain is sufficient.
- Single participant returns that participant's action regardless of type (including SILENT → not None in isolation, but all-SILENT dict → None).

Tiebreak:
- Two RESPOND actions: the one with no `last_spoke_turn` entry wins over one that has spoken.
- Two RESPOND actions, both have `last_spoke_turn`: lower index wins.
- Two RESPOND actions, identical `last_spoke_turn` index: winner is the one with lower `ConvActionType` enum value (final fallback; covers true ties only possible in contrived scenarios).

Edge cases:
- Empty dict → `None`.
- All-SILENT dict → `None`.
- Single action → that action wins.

---

## TITLE: [conversation_system][4/9] _resolve_single_turn

**DESCRIPTION:**
Add `ConversationSystem._resolve_single_turn(session, game_time)` to `conversation.py`. Implements one full turn cycle: (1) Prompt all current `participant_ids` in parallel via `ai_coordinator.get_conversation_turn`; on turn 0 (`len(full_turn_log) == 0`), prompt only `initiator_id` (BHVR-52). (2) Process all LEAVE results first: remove leavers from `participant_ids`, append a LEAVE `ConversationTurn` to `full_turn_log` for each, write LEAVE event to each present participant's Memory System log (BHVR-53). (3) Call `_select_winner` on remaining responses. (4) If winner exists: build turn text via `format_turn_text`, append `ConversationTurn` to `full_turn_log`, update `last_spoke_turn[winner_id]`, write turn to every participant's Memory System log. (5) Return winning `ConversationTurnResult` or `None` if all silent/empty. `elapsed_game_minutes` is NOT updated here — that lives in `_run_turn_loop`.

**TEST PLAN:**
Turn-0 initiator-only (BHVR-52):
- Mock AI coordinator; verify `get_conversation_turn` called exactly once with `initiator_id`, not with target.
- Resulting turn appended to `full_turn_log`; `last_spoke_turn[initiator_id] = 0`.

Concurrent leaves (BHVR-51 exception):
- Two participants both return LEAVE; both removed from `participant_ids`; two LEAVE entries in `full_turn_log`; return `None`.
- Mix: one leaves, one acts; leaver removed, remaining participant's action wins normally.

Winner selection:
- Higher-priority action wins; lower-priority result is discarded with no trace in `full_turn_log`.
- `last_spoke_turn` updated for winner only.

Memory writes (BHVR-53):
- LEAVE turn written to memory of all participants present at that moment (including the leaver themselves).
- Winning turn written to memory of all participants in `participant_ids` after LEAVE removal.
- No memory write for discarded (non-winning, non-leaving) results.

All-SILENT:
- Returns `None`; no `ConversationTurn` appended.

---

## TITLE: [conversation_system][5/9] _pause_for_joiners

**DESCRIPTION:**
Add `ConversationSystem._pause_for_joiners(session, game_time)`. Called after the second resolved turn. Queries World State for villagers who are at base, awake, not exploring, not hauling, and not already in `participant_ids`. For each eligible villager, calls `ai_coordinator.get_join_decision(villager_id, current_action_description, snapshot)` where `snapshot.history = full_turn_log[:2]` — the opening excerpt (VRBTM-42). All decisions are issued in parallel (Trio nursery). Joiners are added atomically: appended to both `participant_ids` and `all_participant_ids`; `join_turn_index[villager_id] = len(full_turn_log)`. `last_spoke_turn` entry remains absent for joiners.

**TEST PLAN:**
Eligibility filtering:
- Villager already in `participant_ids` is not queried.
- Villager who is exploring or hauling is not queried.
- Villager who is asleep is not queried.
- Eligible villagers are queried; ineligible ones are not.

Snapshot excerpt (VRBTM-42):
- Snapshot passed to `get_join_decision` has `history == full_turn_log[:2]`, regardless of how many total turns have been appended by the time this fires. (In the normal case it's always exactly 2 since the pause happens right after turn 2, but the slice must be explicit.)

Join atomicity and state updates:
- Joiner added to both `participant_ids` and `all_participant_ids`.
- `join_turn_index[joiner_id] == len(full_turn_log)` at the moment of joining.
- `last_spoke_turn` has no entry for the joiner.
- Non-joiner not added to either list.

Multiple concurrent joiners:
- All joiners in the parallel batch are added; none are lost due to ordering.

---

## TITLE: [conversation_system][6/9] _run_trade_subprotocol

**DESCRIPTION:**
Add `ConversationSystem._run_trade_subprotocol(session, trade_initiator_id, trade_partner_id, game_time)`. Constructs `ActiveTrade`; alternates calls to `ai_coordinator.get_trade_turn` between `initiator_id` (acts first, BHVR-58) and `partner_id` based on `turn_count % 2`.

**ACCEPT validity (BHVR-63):** Honor ACCEPT only if the other party's most recent `TradeTurnRecord` in `history` has `action == MAKE_OFFER`. If not, treat as no-op: do not append to `history`, increment `turn_count`, continue.

**Cancellation (BHVR-62):** When `turn_count == 6` with no completed trade, append a cancellation `EventLogEntry` to each participant's Memory System log, clear `active_trade`, return.

**Completion:** On valid ACCEPT, call `VillagerState.modify_inventory` on both parties to transfer items simultaneously — acceptor receives counterpart's last offer items, counterpart receives acceptor's last offer items. Append completion events to memory.

**Zero game time (BHVR-61):** `session.elapsed_game_minutes` unchanged throughout.

**Visibility (BHVR-57):** All trade events appended to every conversation participant's (`participant_ids`) Memory System log — not only the two traders.

**TEST PLAN:**
ACCEPT validity (BHVR-63):
- Initiator offers → partner accepts: trade completes; both inventories updated with each other's last-offered items.
- Partner offers → initiator accepts: same result in opposite roles.
- Initiator cancels → partner immediately accepts: ACCEPT is no-op (partner's last action was CANCEL, not MAKE_OFFER); `turn_count` increments; trade continues.
- Initiator accepts with no prior offer from partner (empty history): no-op; trade continues.

Cancellation (BHVR-62):
- Exactly 6 turns without acceptance: cancellation event written to memory of all participants; `active_trade` cleared; function returns without transferring items.
- An invalid ACCEPT on turn 5 (no-op) means turn_count reaches 6 and triggers cancellation.

Inventory transfer:
- Items from each party's most recent MAKE_OFFER are transferred correctly (A gets B's last offer; B gets A's last offer).
- `VillagerState.modify_inventory` called for both parties.

Zero game time (BHVR-61):
- `session.elapsed_game_minutes` is the same before and after the entire sub-protocol, regardless of how many trade turns occurred.

Event visibility (BHVR-57):
- A third participant (bystander who joined) receives memory writes for every trade event, not just the two traders.

CANCEL action:
- Either party issues CANCEL: trade ends without inventory transfer; cancellation logged.

---

## TITLE: [conversation_system][7/9] _run_turn_loop

**DESCRIPTION:**
Add `ConversationSystem._run_turn_loop(session, game_time)`. Drives the turn loop: call `_resolve_single_turn`; increment `session.elapsed_game_minutes += 5` (always, even for silent turns per BHVR-54); check end conditions after each turn; after the second resolved turn (`len(full_turn_log) == 2`), call `_pause_for_joiners` once; when the winning result has `action == TRADE`, suspend the loop and call `_run_trade_subprotocol` before resuming.

End conditions (BHVR-55): `len(participant_ids) <= 1` or `elapsed_game_minutes >= 60`.

**TEST PLAN:**
End conditions:
- Loop exits when `participant_ids` drops to 1 (last standing participant leaves; check returns before further turns).
- Loop exits when `elapsed_game_minutes` reaches exactly 60 (12 turns × 5 min); does not run turn 13.
- Both conditions true simultaneously: still exits cleanly.

Elapsed time:
- After N turns (including a silent turn), `elapsed_game_minutes == 5 * N`.
- Trade turns do not contribute (trade sub-protocol must not touch `elapsed_game_minutes`; verified by inspecting session after a trade).

Join pause timing:
- `_pause_for_joiners` called exactly once, after `len(full_turn_log) == 2` — not after turn 1, not after turn 3.
- If there are no eligible joiners, the loop resumes correctly.

Trade suspension and resumption:
- When `_resolve_single_turn` returns a result with `action == TRADE`, `_run_trade_subprotocol` is invoked with `trade_initiator_id=winner` and `trade_partner_id=result.target_id`.
- After the sub-protocol returns, the turn loop resumes and continues to resolve subsequent turns.
- `elapsed_game_minutes` reflects only conversation turns, not the trade turns.

---

## TITLE: [conversation_system][8/9] _apply_post_conversation_updates

**DESCRIPTION:**
Add `ConversationSystem._apply_post_conversation_updates(session, game_time)`. Iterates over `session.all_participant_ids` (covering early leavers, BHVR-65). For each: calls `ai_coordinator.get_social_score(villager_id, snapshot, game_time)` → applies `score - 5` delta to `social_joy`, clipped to [0, 100] via `VillagerState.modify_stat` (BHVR-66). Applies `+20 connectedness` to all via `VillagerState.modify_stat` (BHVR-73). For every ordered pair `(speaker, subject)` where `speaker != subject` and both are in `all_participant_ids`: calls `ai_coordinator.get_relationship_update`, then `memory_system.write_impressions(speaker, subject, impression, desc_update)` (BHVR-67–71). All queries for the same participant issued in parallel.

**TEST PLAN:**
Early leaver coverage:
- A villager who left mid-conversation is still in `all_participant_ids`; social score query and connectedness update are applied to them.

Social joy delta (BHVR-66):
- Score 10 → delta +5; score 0 → delta −5; score 5 → delta 0.
- Social joy at 98 with delta +5 → clipped to 100, not 103.
- Social joy at 2 with delta −5 → clipped to 0, not −3.

Connectedness (BHVR-73):
- Every villager in `all_participant_ids` receives exactly `+20` connectedness.

Relationship pairs (BHVR-67–68):
- For a 3-person conversation (A, B, C), `get_relationship_update` called for all 6 ordered pairs: (A,B), (A,C), (B,A), (B,C), (C,A), (C,B). No self-pairs. Verify count and identity of calls.
- `write_impressions` called once per ordered pair with the result.

Snapshot for early leaver:
- `session.snapshot_for(early_leaver_id)` used (not a full snapshot) when querying social score; snapshot history ends at the turn they left, since `join_turn_index` slicing picks up from their join.

---

## TITLE: [conversation_system][9/9] run_conversation + integration

**DESCRIPTION:**
Add `ConversationSystem.run_conversation(initiator_id, target_id, game_time)`. Initializes `ConversationSession`: `participant_ids = [initiator_id, target_id]`, `all_participant_ids = [initiator_id, target_id]`, `join_turn_index = {initiator_id: 0, target_id: 0}`, all other fields at defaults. Calls `_run_turn_loop`, then `_apply_post_conversation_updates`. Returns `(session.elapsed_game_minutes, session.all_participant_ids)`. Simulation Engine uses the participant list to reschedule interrupted tasks (BHVR-44).

**TEST PLAN:**
Session initialization:
- Both initiator and target present in `participant_ids` and `all_participant_ids`.
- `join_turn_index` is `{initiator_id: 0, target_id: 0}` — both see the full history.
- `elapsed_game_minutes` starts at 0; `active_trade` is `None`.

Return value:
- Returns `(elapsed_game_minutes, all_participant_ids)` — verify tuple shape and that `all_participant_ids` reflects any joiners or early leavers accumulated during the loop.

Integration scenario (mock all subsystems):
- Scripted 3-turn conversation: turn 0 initiator speaks, turn 1 target responds, turn 2 both silent (loop continues), turn 3 target leaves → participant count drops to 1 → loop exits. Verify: `elapsed_game_minutes == 20` (4 turns × 5 min), `all_participant_ids` contains both original participants, memory writes occurred for each turn, post-conversation updates applied to both. Asserts the full call graph: AI coordinator, Memory System, Villager State each received expected calls in expected order.

Statelessness:
- Call `run_conversation` twice on the same `ConversationSystem` instance with different participants; verify no state leaks between calls (second call's session is independent of the first's).
