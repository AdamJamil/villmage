# simulation_engine — Diff Plan

Twelve diffs. Three files: `events.py` (pure data), `autobalance.py` (daily math), and `simulation_engine.py` (orchestrator). The engine itself is split by concern: initialization + heap plumbing, the decay/threshold/kill cluster, five event handlers, and the main loop last.

---

## DIFF 1 of 12

**TITLE:** `[simulation_engine][1/12]` events.py — event dataclasses

**DESCRIPTION:**
Create `villmage/events.py`. Pure data leaf: no intra-project imports, no logic.

Objects added:

- `VillagerId: TypeAlias = str` — named alias preventing silent substitution of a carcass ID or log key where a villager ID is expected.
- Five event dataclasses — `ActionCompleteEvent`, `FireExtinctionEvent`, `CarcassRotEvent`, `MidnightEvent`, `CheckpointEvent` — each `@dataclass(order=True)` with `timestamp: int` and `sequence: int` as the only compared fields. `ActionCompleteEvent.villager_id` and `CarcassRotEvent.carcass_id` use `field(compare=False)` so heap ordering is defined solely by `(timestamp, sequence)`.
- `ScheduledEvent: TypeAlias = ActionCompleteEvent | FireExtinctionEvent | CarcassRotEvent | MidnightEvent | CheckpointEvent` — the heap's element type.

The ordering contract is load-bearing: every heap operation in `SimulationEngine` depends on events comparing only on `(timestamp, sequence)`. A wrong `compare=False` placement silently breaks min-heap ordering whenever two events share a timestamp.

**TEST PLAN:**

*`tests/test_events.py`*

*Ordering on `(timestamp, sequence)` only.* Push a mix of all five event types with deliberate timestamp and sequence collisions onto a `heapq` and pop in order. Assert that the extracted sequence is monotonically non-decreasing on `(timestamp, sequence)` regardless of event type. Specifically: two `ActionCompleteEvent`s with the same timestamp but different villager IDs must sort by sequence, not by villager ID.

*`field(compare=False)` on payload fields.* Directly assert `ActionCompleteEvent(360, 0, "aldric") == ActionCompleteEvent(360, 0, "sewalt")` (same timestamp + sequence, different villager) and `ActionCompleteEvent(360, 0, "aldric") < ActionCompleteEvent(360, 1, "aldric")` (same villager, different sequence). Same for `CarcassRotEvent` with different carcass IDs.

*Heap extraction order, mixed types.* Build a heap with: `MidnightEvent(1440, 6)`, `ActionCompleteEvent(360, 0, "aldric")`, `CheckpointEvent(540, 7)`, `CarcassRotEvent(500, 3, 1)`, `FireExtinctionEvent(400, 2)`. Assert pop order is exactly: `(360,0)`, `(400,2)`, `(500,3)`, `(540,7)`, `(1440,6)`. This is the canonical simulation startup heap; wrong ordering here means the first events in a real run execute in the wrong sequence.

---

## DIFF 2 of 12

**TITLE:** `[simulation_engine][2/12]` autobalance.py — AutobalanceMultipliers

**DESCRIPTION:**
Create `villmage/autobalance.py`. No intra-project imports.

- `AutobalanceMultipliers` — dataclass with three `float` fields: `exploration_yield`, `satiation_restore`, `hydration_restore`, all defaulting to `1.0`.
- `adjust(avg_satiation_pct, avg_hydration_pct, avg_food_safety_days) -> None` — multiplicatively nudges each multiplier toward its design target per BHVR-221. Targets: satiation `0.85`, hydration `0.50`, food safety `1.0` (CONST-216/217/218). If actual is `x` above target, divides multiplier by `(1 + x)`; if below, multiplies by `(1 + x)`, where `x` is the fractional deviation (`(actual - target) / target`). Multipliers are unbounded (design doc resolution).

The `adjust` formula has a subtle direction: above target means the game is too easy, so we reduce the multiplier; below means too hard, so we increase it. Getting the sign wrong produces a runaway positive-feedback loop instead of the intended self-regulating negative feedback.

**TEST PLAN:**

*`tests/test_autobalance.py`*

*Starting values.* Assert `AutobalanceMultipliers()` produces all three multipliers equal to exactly `1.0`.

*At-target: no change.* Call `adjust(0.85, 0.50, 1.0)` on a fresh instance. Assert all three multipliers remain `1.0`. This is the fixed point of the system.

*Above target: multiplier decreases.* Call `adjust(1.0, 0.50, 1.0)` (satiation 17.6% above target: `(1.0 - 0.85) / 0.85`). Assert `satiation_restore` is approximately `1.0 / (1 + (1.0 - 0.85) / 0.85)`. Assert `hydration_restore` and `exploration_yield` remain `1.0`. Verify the direction is a decrease (multiplier < 1.0).

*Below target: multiplier increases.* Call `adjust(0.85, 0.10, 1.0)` (hydration 80% below target). Assert `hydration_restore ≈ 1.0 * (1 + (0.50 - 0.10) / 0.50)`. Assert satiation and yield unchanged. Verify the direction is an increase (multiplier > 1.0).

*All three adjust independently.* Call `adjust(0.68, 0.75, 0.5)` — satiation below, hydration above, food safety below. Assert all three multipliers adjusted in their respective correct directions, and that their values match the formula independently (none of the three interferes with the others).

*Cumulative adjustment compounds.* Call `adjust(1.0, 0.50, 1.0)` twice on the same instance. Assert `satiation_restore` after two calls equals `1.0 / (1 + x)^2` where `x = (1.0 - 0.85) / 0.85`. Autobalancing compounds daily; testing one call only would miss a class of off-by-one bugs where the previous day's multiplier is not threaded through correctly.

---

## DIFF 3 of 12

**TITLE:** `[simulation_engine][3/12]` SimulationEngine shell and __init__

**DESCRIPTION:**
Create `villmage/simulation_engine.py`. Adds the `SimulationEngine` class with its owned data, two internal heap helpers, and `__init__`.

Heap helpers (private):

- `_push(event: ScheduledEvent) -> None` — pushes the event onto the heap using the current `next_sequence`, stamps the sequence field, then increments `next_sequence`. All heap insertions go through this method so sequence monotonicity is guaranteed.
- `_cancel(predicate: Callable[[ScheduledEvent], bool]) -> None` — removes all heap entries matching the predicate via linear scan + `heapify`. Acceptable at the small event counts described in the impl doc (≤~15 concurrent). Used to cancel a specific villager's `ActionCompleteEvent`, a `FireExtinctionEvent`, etc.

`__init__` per the spec:

- `current_game_time = 360`
- Creates six `VillagerState` instances at starting values, keyed by villager ID strings from `CharacterCanon`.
- Creates an empty `WorldState`.
- Pre-populates the heap: one `ActionCompleteEvent` per villager at `t=360` (sequences 0–5), one `MidnightEvent` at `t=1440`, one `CheckpointEvent` at `t=540`. Calls `_push` for each so sequences are assigned monotonically.
- `next_sequence = 6` after the six initial insertions (midnight and checkpoint get sequences 6 and 7, but the villager events get 0–5 because `_push` stamps and increments).

Wait — re-reading: the impl doc says `next_sequence = 6` *after the six initial insertions*, implying only the six `ActionCompleteEvent`s use sequences 0–5, then midnight and checkpoint use 6 and 7, leaving `next_sequence = 8`. But the doc says "next_sequence = 6 (after the six initial insertions)" which is slightly ambiguous. The canonical reading is that after all eight initial events, `next_sequence` equals however many pushes occurred (8). This is clarified in tests by asserting the exact heap size and sequence values.

- Stores references to `action_system`, `ai_coordinator`, `conversation_system`, `memory_system`, `character_canon` — not serialized in checkpoints.
- `autobalance = AutobalanceMultipliers()`.

**TEST PLAN:**

*`tests/test_simulation_engine_init.py`*

*Heap pre-population — count and types.* Assert the heap has exactly 8 events after `__init__`: 6 `ActionCompleteEvent`, 1 `MidnightEvent`, 1 `CheckpointEvent`. No `FireExtinctionEvent` or `CarcassRotEvent` should be present (fire starts unlit, no carcasses).

*Heap pre-population — timestamps and villager coverage.* Extract all events. Assert all 6 `ActionCompleteEvent`s have `timestamp=360`. Assert their `villager_id` fields are exactly the six canon villager IDs (as a set). Assert `MidnightEvent.timestamp == 1440`. Assert `CheckpointEvent.timestamp == 540`.

*Heap pre-population — sequence assignment.* Assert sequences on the 6 `ActionCompleteEvent`s are `{0,1,2,3,4,5}`. Assert `MidnightEvent` and `CheckpointEvent` have sequences 6 and 7 (or 7 and 6 depending on push order — assert the set `{6,7}`). Assert `next_sequence == 8` after init.

*`current_game_time`.* Assert `engine.current_game_time == 360`.

*`autobalance`.* Assert all three multipliers are `1.0`.

*VillagerState starting values.* Assert `len(engine.villager_states) == 6`. For each, assert `wakefulness=100, satiation=1800, hydration=6000, connectedness=100, cleanliness=100, social_joy=20` and empty inventory. (These starting values come from Villager State's spec; this test confirms the engine initializes them correctly, not that Villager State computes them correctly.)

*`_push` increments sequence.* Call `_push` with a dummy event; assert `next_sequence` incremented by 1 and the event is on the heap with the correct sequence stamped.

*`_cancel` removes matching events.* Push two `ActionCompleteEvent`s for different villagers. Cancel by `villager_id` predicate for one. Assert only the other remains. Assert heap invariant is preserved (re-heapify worked) by popping and verifying order.

---

## DIFF 4 of 12

**TITLE:** `[simulation_engine][4/12]` Decay, thresholds, force-sleep, kill

**DESCRIPTION:**
Add four private methods that form the decay/threshold cluster. These are always called together in a fixed sequence and must all be present for any handler to be correct.

- `_apply_decay_all(elapsed_hours: float) -> dict[VillagerId, list[CrossingType]]` — calls `apply_decay(elapsed_hours)` on every living villager in `villager_states`. Returns a dict of only the villagers who crossed a threshold (HEALTH_ZERO or WAKEFULNESS_ZERO). Villagers with no crossings are omitted from the returned dict.

- `_apply_thresholds(villager_id: VillagerId, crossings: list[CrossingType]) -> bool` — inspects crossings. HEALTH_ZERO → calls `_kill_villager`; WAKEFULNESS_ZERO (only if villager still alive after kill check) → calls `_force_sleep`. Returns `True` if the villager is now dead or sleeping (caller must return early). If both crossings appear, HEALTH_ZERO takes precedence — a dead villager is not also force-slept.

- `_force_sleep(villager_id: VillagerId) -> None` — cancels any pending `ActionCompleteEvent` for this villager (if one exists on the heap; it may already have been popped if this is being called from within that villager's own handler). Sets the villager's `current_action` to forced sleep via Villager State. Pushes a new `ActionCompleteEvent` at `current_game_time + 240` (CONST-283: forced sleep is always 4 hours).

- `_kill_villager(villager_id: VillagerId) -> None` — cancels any pending `ActionCompleteEvent` for the villager. Calls `VillagerState.clear_inventory()` (or equivalent). Removes the villager from `villager_states`. Appends a death event to Memory System for all villagers currently at base and awake (per BHVR-210 and the subsystem visibility rule: base events are visible to those present and awake).

**TEST PLAN:**

*`tests/test_simulation_engine_decay.py`*

*`_apply_decay_all` — all living villagers decayed.* Mock `VillagerState.apply_decay` for each of 6 villagers. Call `_apply_decay_all(2.0)`. Assert `apply_decay(2.0)` was called exactly once per living villager. Assert the return dict contains only the villagers whose mocked `apply_decay` returned threshold crossings.

*`_apply_decay_all` — only living villagers.* Simulate a dead villager by removing one from `villager_states`. Assert `apply_decay` is not called for the removed villager.

*`_apply_thresholds` — HEALTH_ZERO kills.* Mock `_kill_villager`. Call `_apply_thresholds("aldric", [CrossingType.HEALTH_ZERO])`. Assert `_kill_villager` called with "aldric". Assert return is `True`.

*`_apply_thresholds` — WAKEFULNESS_ZERO force-sleeps.* Mock `_force_sleep`. Call `_apply_thresholds("aldric", [CrossingType.WAKEFULNESS_ZERO])`. Assert `_force_sleep("aldric")` called. Assert return is `True`.

*`_apply_thresholds` — both crossings: HEALTH_ZERO wins.* Mock both `_kill_villager` and `_force_sleep`. Call with `[CrossingType.HEALTH_ZERO, CrossingType.WAKEFULNESS_ZERO]`. Assert `_kill_villager` called, `_force_sleep` not called.

*`_apply_thresholds` — no crossings returns False.* Call with empty list. Assert return is `False`, neither kill nor force-sleep invoked.

*`_force_sleep` — cancels existing event, schedules new one.* Push an `ActionCompleteEvent` for "aldric". Call `_force_sleep("aldric")`. Assert no `ActionCompleteEvent` for "aldric" exists on the heap with the old timestamp. Assert a new `ActionCompleteEvent` for "aldric" exists at `current_game_time + 240`.

*`_force_sleep` — no existing event (already popped).* With no `ActionCompleteEvent` for "aldric" on the heap, call `_force_sleep("aldric")`. Assert it does not raise and does schedule the new sleep event.

*`_kill_villager` — removes from villager_states.* Call `_kill_villager("aldric")`. Assert "aldric" is not in `villager_states`.

*`_kill_villager` — cancels pending event.* Push an `ActionCompleteEvent` for "aldric". Kill them. Assert no `ActionCompleteEvent` for "aldric" remains.

*`_kill_villager` — death event appended to memory for base+awake observers.* Set up two villagers at base and awake, one exploring. Kill "aldric". Assert Memory System's `append_event` was called for the two base+awake villagers, not for the exploring villager. Assert the event describes a death.

---

## DIFF 5 of 12

**TITLE:** `[simulation_engine][5/12]` _sync_fire_event

**DESCRIPTION:**
Add `_sync_fire_event(self) -> None`. Called unconditionally after every event dispatch in `run()`. Reconciles the heap's `FireExtinctionEvent` with WorldState's current fire state:

1. Cancel any existing `FireExtinctionEvent` on the heap (via `_cancel`).
2. If the fire is lit and WorldState reports a non-None `extinction_timestamp`: push a new `FireExtinctionEvent` at that timestamp.
3. If the fire is unlit or has no fuel, leave it cancelled.

This is called after every event — not just fire-related ones — because any action (e.g., adding fuel, hauling water) can indirectly change the extinction timestamp. Centralizing the reconciliation in one unconditional call avoids scattered fire-event management throughout every handler.

**TEST PLAN:**

*`tests/test_simulation_engine_sync_fire.py`*

*Fire lit with fuel → event scheduled.* Configure WorldState mock to report `fire.lit=True`, `extinction_timestamp=720`. Call `_sync_fire_event()`. Assert exactly one `FireExtinctionEvent` on the heap with `timestamp=720`.

*Fire unlit → no event.* Configure `fire.lit=False`. Call `_sync_fire_event()`. Assert no `FireExtinctionEvent` on heap.

*Fire lit but no extinction timestamp (no fuel loaded).* Configure `fire.lit=True`, `extinction_timestamp=None`. Call `_sync_fire_event()`. Assert no `FireExtinctionEvent` on heap.

*Idempotency — called twice without state change.* Call `_sync_fire_event()` twice with `lit=True, timestamp=720`. Assert exactly one `FireExtinctionEvent` with `timestamp=720` (no duplicates). The cancel-then-reschedule pattern must not accumulate entries.

*Fuel change → event timestamp updates.* First call with `extinction_timestamp=600`, assert event at 600. Update mock to return `extinction_timestamp=800`, call again. Assert the 600 event is gone and a new event at 800 is present.

*Extinguished fire after having been lit → event removed.* Place a `FireExtinctionEvent(600, seq)` on the heap directly. Then call `_sync_fire_event()` with `fire.lit=False`. Assert the heap has no `FireExtinctionEvent`.

---

## DIFF 6 of 12

**TITLE:** `[simulation_engine][6/12]` _handle_midnight

**DESCRIPTION:**
Add `_compute_autobalance_aggregates(self) -> tuple[float, float, float]` and `_handle_midnight(self) -> None`.

`_compute_autobalance_aggregates` averages three values across all living villagers:
- `avg_satiation_pct`: each villager's `satiation / 1800`.
- `avg_hydration_pct`: each villager's `hydration / 6000`.
- `avg_food_safety_days`: each villager's food safety score — per CONST-202 corrected formula: `((calories_in_inventory / 2200) + (1 / n_living) * (calories_in_base / 2200)) / 5` — then averaged over all living villagers. Base calories are read from WorldState once and shared.

`_handle_midnight` per the impl doc:
1. Call `_apply_decay_all` for elapsed hours; process threshold crossings on all villagers.
2. Call `_compute_autobalance_aggregates()` and pass results to `autobalance.adjust()`.
3. Call `memory_system.trigger_midnight_compaction()`.
4. Push a new `MidnightEvent` at `current_game_time + 1440`.

**TEST PLAN:**

*`tests/test_simulation_engine_midnight.py`*

*`_compute_autobalance_aggregates` — formula correctness with multiple villagers.* Set up 3 villagers with known satiation/hydration. Set WorldState base calories to a known value. Call the function. Assert `avg_satiation_pct` is the arithmetic mean of each villager's `satiation / 1800`. Assert `avg_hydration_pct` similarly. Assert `avg_food_safety_days` uses the corrected CONST-202 formula: `((inv_cal / 2200) + (base_cal / n / 2200)) / 5` averaged over villagers.

*`_compute_autobalance_aggregates` — single villager edge case.* One living villager. Assert the `1/n` term is `1.0` (not zero, not divide-by-zero).

*`_handle_midnight` — adjust called with correct args.* Mock `_compute_autobalance_aggregates` to return `(0.9, 0.4, 0.8)`. Call `_handle_midnight`. Assert `autobalance.adjust(0.9, 0.4, 0.8)` was called.

*`_handle_midnight` — midnight compaction triggered.* Assert `memory_system.trigger_midnight_compaction()` was called exactly once.

*`_handle_midnight` — next midnight scheduled.* Set `current_game_time = 1440`. Call `_handle_midnight`. Assert exactly one `MidnightEvent` on the heap with `timestamp = 2880`.

*`_handle_midnight` — decay applied before aggregates.* Use a spy on `_apply_decay_all`. Assert it is called before `_compute_autobalance_aggregates`. (Order matters: aggregates must reflect post-decay state.)

---

## DIFF 7 of 12

**TITLE:** `[simulation_engine][7/12]` _handle_checkpoint

**DESCRIPTION:**
Add `_handle_checkpoint(self) -> None`. Per the impl doc:

1. Serialize full simulation state to a `.json` file named `{current_game_time}.json`. Serialized state includes: all `VillagerState` instances, `WorldState`, Memory System state (retrieved via `memory_system.get_full_state()`), `AutobalanceMultipliers`, and the current event heap (as a list of dicts, one per event with type tag, timestamp, sequence, and any payload).
2. Push a new `CheckpointEvent` at `current_game_time + 180`.

The checkpoint file must be machine-readable by `SimulationEngine` (design doc resolution for REQ-272). The serialization schema is defined here; deserialization (for restart) is handled in the same method via a companion `@classmethod load_checkpoint(path)` that reconstructs the engine from the file.

**TEST PLAN:**

*`tests/test_simulation_engine_checkpoint.py`*

*File naming.* Set `current_game_time = 540`. Call `_handle_checkpoint`. Assert a file named `540.json` was written in the checkpoint directory (use `tmp_path` fixture).

*File is valid JSON.* Assert the written file parses as JSON without error.

*File contains all required top-level keys.* Assert the JSON object has keys `villager_states`, `world_state`, `memory_state`, `autobalance`, `event_heap`, `current_game_time`.

*Event heap serialization preserves all events.* Pre-populate the heap with one of each event type. Call `_handle_checkpoint`. Parse the file. Assert `event_heap` has 5 entries. Assert each entry has a `type` field matching the event class name and matching `timestamp`, `sequence`, and payload fields.

*Next checkpoint scheduled.* Set `current_game_time = 540`. Call `_handle_checkpoint`. Assert exactly one `CheckpointEvent` on the heap with `timestamp = 720`.

*Round-trip: save and reload.* Call `_handle_checkpoint`. Call `SimulationEngine.load_checkpoint(path)`. Assert the reloaded engine's `current_game_time`, `autobalance` multipliers, and event heap contents match the original engine.

---

## DIFF 8 of 12

**TITLE:** `[simulation_engine][8/12]` _handle_fire_extinction

**DESCRIPTION:**
Add `_handle_fire_extinction(self) -> None`. Per the impl doc:

1. Call `world_state.mark_fire_extinguished()`.
2. For each villager in `villager_states` whose `current_action.category == ActionCategory.SLEEPING`: call `action_system.adjust_active_sleep(villager_id)` to split their remaining sleep into a new segment computed under the updated (no-fire) wakefulness modifier.

Exploring villagers (who are away from base) may also be sleeping — specifically, a forced sleep can fire anywhere. The handler must iterate all living villagers, not just those at base.

**TEST PLAN:**

*`tests/test_simulation_engine_fire_extinction.py`*

*WorldState marked extinguished.* Call `_handle_fire_extinction`. Assert `world_state.mark_fire_extinguished()` called exactly once.

*Sleeping villagers get adjust_active_sleep.* Set up two villagers with `current_action.category == SLEEPING` and one with a non-sleeping action. Call `_handle_fire_extinction`. Assert `action_system.adjust_active_sleep` called for the two sleeping villagers only.

*No sleeping villagers — no adjust calls.* All villagers have non-sleep actions. Call `_handle_fire_extinction`. Assert `adjust_active_sleep` not called at all.

*All sleeping — all adjusted.* All 6 villagers sleeping. Assert `adjust_active_sleep` called 6 times, once per villager ID.

---

## DIFF 9 of 12

**TITLE:** `[simulation_engine][9/12]` _handle_carcass_rot

**DESCRIPTION:**
Add `_handle_carcass_rot(self, event: CarcassRotEvent) -> None`. Per the impl doc:

1. Call `world_state.mark_carcass_rotted(event.carcass_id)` — adds +30 dirtiness (CONST-132), destroys the carcass.
2. For each villager currently at base AND awake: call `memory_system.append_event(villager_id, rot_event)` with an event describing the rot. "At base" means `current_action.category` is not an away action (not `EXPLORING` and not `HAULING_WATER`). "Awake" means `current_action.category != SLEEPING`.

**TEST PLAN:**

*`tests/test_simulation_engine_carcass_rot.py`*

*WorldState mutation called.* Call `_handle_carcass_rot(CarcassRotEvent(500, 3, carcass_id=2))`. Assert `world_state.mark_carcass_rotted(2)` called exactly once.

*Memory appended for base+awake villagers only.* Set up: villager A at base and awake, villager B sleeping at base, villager C exploring (away). Call `_handle_carcass_rot`. Assert `memory_system.append_event` called for villager A only. Villager B is at base but asleep (invisible). Villager C is away (invisible).

*Memory not appended when no villagers at base and awake.* All villagers either exploring or sleeping. Assert `memory_system.append_event` not called.

*Correct carcass_id threaded through.* Assert the carcass_id passed to `mark_carcass_rotted` matches the event's `carcass_id` field.

---

## DIFF 10 of 12

**TITLE:** `[simulation_engine][10/12]` _handle_action_complete

**DESCRIPTION:**
Add `_handle_action_complete(self, event: ActionCompleteEvent) -> None`. This is the core villager action-cycle handler. Sequence per the impl doc:

1. Call `apply_decay` on this villager for elapsed hours (already done globally in `run()` before dispatch; this step is therefore a no-op here — decay is applied at event pop time, not per-villager). *(Clarification: the impl doc lists decay as step 1, but per `run()` doc, decay is applied to ALL villagers before dispatch. So step 1 is already handled by the time this is called. The handler starts at step 2.)*
2. If the villager has a `current_action` set (i.e., not the initial `t=360` event where `current_action` is None): call `action_system.complete_action(villager_id)`.
3. Call `_apply_thresholds(villager_id, crossings)` where `crossings` were returned by the prior `_apply_decay_all` call and passed in. If `True`, return early.
4. If `villager_state.awake_minutes_since_compaction >= 240` (BHVR-252): call `memory_system.trigger_compaction(villager_id)`; call `villager_state.reset_compaction_counter(villager_id)`. Set a local flag `compaction_ran = True`.
5. Call `ai_coordinator.select_action(villager_id)` → returns `(action, thought)`. Call `memory_system.append_thought(villager_id, thought)`.
6. If chosen action is sleep and `compaction_ran` is `False` (BHVR-251): call `memory_system.trigger_compaction(villager_id)`.
7. If chosen action is "Talk to someone": call `_handle_conversation_action(villager_id, target_id)` and return. Otherwise: call `action_system.start_action(villager_id, action)` → returns `completion_timestamp`. Push a new `ActionCompleteEvent` for this villager at `completion_timestamp`.

`_handle_conversation_action` is a stub in this diff (raises `NotImplementedError`); it is fully implemented in the next diff.

**TEST PLAN:**

*`tests/test_simulation_engine_action_complete.py`*

*Initial t=360 event — complete_action skipped.* Set villager's `current_action` to `None`. Call `_handle_action_complete`. Assert `action_system.complete_action` not called. Assert `action_system.start_action` called (action selection proceeds normally).

*Normal flow — full sequence.* Set villager with an existing action, `awake_minutes_since_compaction=100` (below 240). Mock `ai_coordinator.select_action` to return a non-sleep, non-conversation action. Assert in order: `complete_action` called, `select_action` called, thought appended, `start_action` called, new `ActionCompleteEvent` pushed at returned `completion_timestamp`. Assert `trigger_compaction` not called (not enough awake time, not sleeping).

*BHVR-252: compaction at 4h awake.* Set `awake_minutes_since_compaction=240`. Mock action as non-sleep. Assert `trigger_compaction` called, `reset_compaction_counter` called. Assert new action started normally afterward.

*BHVR-251: compaction on sleep choice, not previously compacted.* Set `awake_minutes_since_compaction=100` (below 240). Mock `select_action` to return a sleep action. Assert `trigger_compaction` called (sleep-triggered compaction). Assert `start_action` called with sleep action.

*BHVR-251 skipped if BHVR-252 already ran.* Set `awake_minutes_since_compaction=240`. Mock action as sleep. Assert `trigger_compaction` called exactly once (BHVR-252 path), not twice.

*Threshold early return.* Pass a `HEALTH_ZERO` crossing. Assert `_apply_thresholds` returns `True`. Assert `select_action` not called, `start_action` not called.

*Conversation action routes to _handle_conversation_action.* Mock `select_action` to return a "Talk to someone" action with `target_id="sewalt"`. Assert `_handle_conversation_action("aldric", "sewalt")` called. Assert `start_action` not called directly (the conversation handler owns scheduling).

---

## DIFF 11 of 12

**TITLE:** `[simulation_engine][11/12]` _handle_conversation_action

**DESCRIPTION:**
Replace the `NotImplementedError` stub with the full implementation of `_handle_conversation_action(self, initiator_id: VillagerId, target_id: VillagerId) -> None`.

Per the impl doc:
1. Call `conversation_system.run_conversation(initiator_id, target_id)` → returns `elapsed_minutes: int`.
2. For each non-initiator participant that `run_conversation` reports (the target and any bystanders who joined): find their current `ActionCompleteEvent` on the heap and record its `timestamp`. Cancel it via `_cancel`. Push a new `ActionCompleteEvent` for that participant at `old_completion_timestamp + elapsed_minutes`.
3. The initiating villager's new `ActionCompleteEvent` is scheduled by `_handle_action_complete` step 7 (the caller handles it). This function does not re-schedule the initiator.

The rescheduling logic is subtle: participants' tasks were paused when they joined the conversation. Their in-progress action's completion deadline shifts forward by the conversation duration. If a participant had no pending `ActionCompleteEvent` (e.g., they were force-slept mid-conversation), they are skipped.

**TEST PLAN:**

*`tests/test_simulation_engine_conversation_action.py`*

*Single target rescheduled.* Push `ActionCompleteEvent("sewalt", timestamp=600)`. Mock `run_conversation` to return `elapsed_minutes=30` with participants `["sewalt"]`. Call `_handle_conversation_action("aldric", "sewalt")`. Assert no `ActionCompleteEvent` for "sewalt" at 600. Assert a new one at 630.

*Multiple bystanders rescheduled.* Push events for "sewalt" at 600, "harren" at 700, "maren" at 500. Mock `run_conversation` → `elapsed=45`, participants = `["sewalt", "harren"]` (maren did not join). Assert "sewalt" rescheduled to 645, "harren" to 745. Assert "maren"'s event at 500 unchanged.

*Initiator not rescheduled here.* Assert no `ActionCompleteEvent` for "aldric" is pushed by `_handle_conversation_action`. The caller handles the initiator.

*Participant with no pending event (was force-slept mid-conversation).* "sewalt" has no `ActionCompleteEvent` on the heap (force-slept earlier). Mock `run_conversation` → participants include "sewalt". Assert no error is raised and no event is pushed for "sewalt" (skip gracefully).

*`run_conversation` called with correct args.* Assert `conversation_system.run_conversation("aldric", "sewalt")` called exactly once.

---

## DIFF 12 of 12

**TITLE:** `[simulation_engine][12/12]` run() main loop

**DESCRIPTION:**
Add `run(self) -> None`. The main event loop. Per the impl doc:

Each iteration:
1. Pop the lowest `(timestamp, sequence)` event from the heap.
2. Compute `elapsed_hours = (event.timestamp - current_game_time) / 60`. Set `current_game_time = event.timestamp`.
3. Call `_apply_decay_all(elapsed_hours)` → `crossings` dict.
4. Dispatch by event type using `match` / `isinstance`:
   - `ActionCompleteEvent` → `_handle_action_complete(event, crossings[event.villager_id])` *(crossings may be empty list if no threshold crossed)*
   - `FireExtinctionEvent` → `_handle_fire_extinction()`
   - `CarcassRotEvent` → `_handle_carcass_rot(event)`
   - `MidnightEvent` → `_handle_midnight()`
   - `CheckpointEvent` → `_handle_checkpoint()`
5. Call `_sync_fire_event()` unconditionally.
6. Continue until the heap has no `ActionCompleteEvent`s remaining (all villagers dead). `MidnightEvent` and `CheckpointEvent` self-reschedule; the loop must not exit just because those are on the heap.

Termination condition: the loop ends when there are no living villagers (`villager_states` is empty) and no `ActionCompleteEvent` remains on the heap.

**TEST PLAN:**

*`tests/test_simulation_engine_run.py`*

*Termination when all villagers die.* Set up a mock engine where killing villager A (the only villager) leaves the heap with only a `MidnightEvent` and a `CheckpointEvent`. Assert `run()` exits without looping forever.

*Event dispatch — each type reaches its handler.* Push one of each event type into the heap. Mock all five handlers. Call `run()` (which will exit quickly because no `ActionCompleteEvent`s remain after they're dispatched). Assert each handler was called exactly once with the correct event.

*`_sync_fire_event` called after every dispatch.* With 3 events on the heap, assert `_sync_fire_event` is called 3 times (once per event popped). Use a call counter.

*Game time advances monotonically.* Intercept `current_game_time` at each handler call. Assert it only ever increases.

*`_apply_decay_all` called with correct elapsed_hours.* Push two events: one at t=360, one at t=480. Assert first call to `_apply_decay_all` uses `(360-360)/60 = 0.0` hours (initial step), second uses `(480-360)/60 = 2.0` hours.

*Integration: one full day with mocked subsystems.* Set up a minimal 1-villager engine with all subsystems mocked. Mock `select_action` to always return "rest" (non-conversation, non-sleep), `start_action` to return `current_time + 60`. Run until `current_game_time >= 1440` (midnight). Assert `MidnightEvent` was dispatched, `trigger_midnight_compaction` was called, a second `MidnightEvent` was pushed. Assert `CheckpointEvent` was dispatched multiple times (every 180 minutes). Assert `_sync_fire_event` was called at least once per event. This integration test is the only test that exercises the full coordination path across all five handlers within a real-time-advancing loop.
