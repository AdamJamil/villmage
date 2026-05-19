# Observability — Diff Plan

---

## TITLE: [observability][1/4] types.py schema and persistence

**DESCRIPTION:**
Define all on-disk schema types and persistence functions in `observability/types.py`. This includes `DeltaKind` (enum with values 1–4), `FieldChange` (dataclass with `field`, `old_value`, `new_value` as JSON strings), `DeltaRecord` (tagged record; exactly one optional payload group populated depending on `kind`), `VillagerMemoryCheckpoint` (per-villager memory snapshot embedded in checkpoints), and `CheckpointRecord` (complete serialized simulation state). Also includes three module-level functions: `append_delta` (appends a JSONL line to `state_deltas.jsonl`), `save_checkpoint` (writes to `checkpoints/{game_time:05d}.json`), and `load_checkpoint` (deserializes a checkpoint file for Simulation Engine restart per REQ-272).

The types import `VillagerState` and `WorldState` from their respective modules, plus `MemoryEntry`, `EventLogEntry`, `RelationshipRecord` from `memory_system.types`, `AutobalanceMultipliers` from `autobalance.py`, and `ScheduledEvent` from `events.py`.

The zero-padded filename format (`{game_time:05d}.json`) is load-bearing: it guarantees that lexicographic directory listing equals chronological order, which the viewer's "find nearest preceding checkpoint" scan depends on.

**TEST PLAN:**
- **Round-trip for each DeltaKind variant.** For each of VILLAGER_STATS, VILLAGER_INV, WORLD_STATE, MEMORY_UPDATE: construct a `DeltaRecord` with all relevant fields populated, call `append_delta`, read the resulting file, parse each line as JSON, reconstruct a `DeltaRecord`, and assert equality. This proves the serialization format is stable and no fields are silently dropped.
- **Optional-field exclusion.** After serializing a VILLAGER_STATS record, assert the JSON line does not contain `memory_kind`, `content`, or `subject_id` keys. After serializing a MEMORY_UPDATE record, assert it does not contain a `changes` key. The viewer and Simulation Engine rely on absent keys being truly absent.
- **append_delta accumulation.** Call `append_delta` three times with records of different `game_time`. Read the file; assert it contains exactly three newline-terminated JSON lines in call order. Proves JSONL append semantics.
- **save_checkpoint filename format.** Call `save_checkpoint` with `game_time=360`. Assert the file is created at `checkpoints/00360.json`. Call again with `game_time=1440`. Assert `checkpoints/01440.json`. The zero-padding is critical for sort correctness.
- **load_checkpoint round-trip.** Construct a `CheckpointRecord` with non-trivial nested data — at least two `VillagerState`s, a `WorldState` with items in storage and a running fire, at least one `VillagerMemoryCheckpoint` with entries in all three memory tiers and a relationship record, and an `event_heap` with two `ScheduledEvent`s. Save then load; assert deep equality across all nested fields. This is the primary correctness test for restart (REQ-272).
- **Lexicographic sort order.** Generate checkpoint files for `game_time` values `[360, 540, 1440, 10080]`. Collect filenames via `sorted(os.listdir(...))`. Assert the sort order matches chronological order. This validates the zero-padding invariant the viewer depends on.

---

## TITLE: [observability][2/4] viewer data loading and state reconstruction

**DESCRIPTION:**
Create `observability/viewer.html` as a minimal scaffold and implement its computational core: `loadAllCheckpoints`, `loadDeltaIndex`, and `reconstructStateAt`. No interactive UI yet — just the replay engine. `loadAllCheckpoints` fetches all files in `checkpoints/`, parses them, and returns them sorted chronologically. `loadDeltaIndex` reads `state_deltas.jsonl` line by line and returns a `Map<number, DeltaRecord[]>` keyed by `game_time`. `reconstructStateAt` finds the nearest checkpoint with `game_time <= targetTime`, applies all intervening delta records, and returns `{villager_states, world_state}`. All four `DeltaKind` values are handled. `changed_fields` is populated using only deltas at exactly `targetTime` (ATTR-16 requirement).

**TEST PLAN (Playwright, fixture data served via static HTTP):**

Fixture data: two checkpoint files (`00360.json`, `00720.json`) and a `state_deltas.jsonl` covering all four DeltaKind values at various `game_time` values.

- **loadAllCheckpoints returns sorted array.** Serve the two fixture checkpoints in reverse filename order on disk; assert the returned array is sorted chronologically by `game_time`. Confirms sorting, not just listing.
- **loadDeltaIndex grouping.** Fixture has three delta records: two at `game_time=400`, one at `game_time=600`. Assert `deltaIndex.get(400).length === 2` and `deltaIndex.get(600).length === 1`.
- **Checkpoint-only baseline.** `reconstructStateAt(checkpoints, emptyMap, 360)` must return state exactly matching the `00360.json` checkpoint — all villager stats, inventory, world state fields. No deltas means no changes.
- **VILLAGER_STATS delta applied.** At `game_time=400`, include a VILLAGER_STATS delta for `aldric` changing `wakefulness` from `100` to `85`. Call `reconstructStateAt` with `targetTime=400`. Assert `villager_states.get("aldric").wakefulness === 85`. Assert the pre-delta value is not present.
- **VILLAGER_INV delta applied.** At `game_time=420`, include a VILLAGER_INV delta for `sewalt` changing `PEACH` from `0` to `3`. Assert `villager_states.get("sewalt").inventory["PEACH"] === 3` at that target time.
- **WORLD_STATE delta applied.** At `game_time=450`, include a WORLD_STATE delta for `fire.lit` changing from `false` to `true`. Assert `world_state.fire_lit === true` at that target time.
- **MEMORY_UPDATE delta applied.** At `game_time=500`, include a MEMORY_UPDATE delta for `aldric` with `memory_kind="short_term"` and a content string. Assert that string appears in `villager_states.get("aldric").short_term_memory_texts`.
- **Nearest checkpoint selection.** Serve checkpoints at `game_time=360` and `game_time=720`. Call `reconstructStateAt` with `targetTime=600`. Assert the function applied deltas starting from the `game_time=360` checkpoint (not the 720 one). Detectable by confirming only deltas between 360 and 600 are applied — include a delta at `game_time=750` and assert it is absent from the result.
- **changed_fields isolation.** Include a delta for `aldric.wakefulness` at `game_time=400` and another for `aldric.satiation` at `game_time=500`. Call `reconstructStateAt` with `targetTime=500`. Assert `villager_states.get("aldric").changed_fields` contains `"satiation"` but NOT `"wakefulness"`. This is the core ATTR-16 invariant: only changes at exactly `targetTime` are highlighted.
- **Dead villager state frozen.** Fixture: checkpoint at 720 omits `aldric` from `villager_states` (dead). Delta at 800 references `aldric`. Assert that `reconstructStateAt(targetTime=800)` does not include `aldric` in `villager_states` (or marks them deceased), and the delta at 800 does not resurrect them.

---

## TITLE: [observability][3/4] viewer session management and scroll

**DESCRIPTION:**
Implement `ViewerSession`, `VillagerViewerState`, `WorldViewerState` as JS in-memory objects, and the three session functions: `initSession`, `selectVillager`, `scrollToEvent`. `initSession` loads all data and positions the session at the last event in the first villager's log. `selectVillager` swaps `visible_events` to the new villager's log without replaying deltas (state position unchanged). `scrollToEvent` is the scroll engine: forward scrolls apply deltas incrementally from the current position; backward scrolls call `reconstructStateAt` from the nearest preceding checkpoint (BHVR-15). `changed_fields` after a scroll reflects only deltas at exactly the newly-scrolled-to game_time.

**TEST PLAN (Playwright):**

Fixture: two villagers (`aldric`, `sewalt`), two checkpoints, `state_deltas.jsonl` with stat/inventory/world deltas at known game times, event log files with timestamped entries.

- **initSession positions at end.** After `initSession`, assert `session.current_game_time` equals the `game_time` of the last event in the first villager's event log. Assert `session.villager_states` contains entries for all villagers in the checkpoints.
- **selectVillager swaps visible_events.** Call `selectVillager(session, "sewalt")`. Assert `session.visible_events` contains Sewalt's events (not Aldric's). Assert `session.current_game_time` is unchanged. Assert `session.villager_states` is unchanged (no delta replay).
- **scrollToEvent forward applies deltas incrementally.** Start at event index 0 (game_time=370, past a checkpoint at 360). Scroll to event index 1 (game_time=400, where an `aldric.wakefulness` delta exists). Assert `session.villager_states.get("aldric").wakefulness` reflects the delta value without reloading the checkpoint.
- **scrollToEvent backward reconstructs from checkpoint.** Scroll forward to game_time=600, then backward to game_time=400. Assert the final state equals what `reconstructStateAt(targetTime=400)` would return — i.e., the backward scroll correctly identified and replayed from the checkpoint at 360.
- **scrollToEvent changed_fields after forward scroll.** Scroll forward to an event at game_time=450 where `world_state.water_supply_liters` changed. Assert `session.world_state.changed_fields` contains `"water_supply_liters"`. Then scroll forward again to game_time=500 where only an inventory delta fired. Assert `changed_fields` no longer contains `"water_supply_liters"` — it was cleared on the next scroll.
- **Idempotent scroll to same game_time.** Two events at the same game_time. Scrolling from one to the other must not double-apply deltas. Assert wakefulness does not change twice.

---

## TITLE: [observability][4/4] viewer UI rendering and delta highlighting

**DESCRIPTION:**
Implement the full interactive UI in `viewer.html`: dark-theme CSS (ATTR-10), scrollable event log pane with per-event timestamps (ATTR-17), character stat panel rendering VRBTM-tier descriptions for all raw and derived stats, inventory display, base-status panel (`WorldViewerState`), memory panel (all three tiers), and relationship/impression panels. Wire DOM scroll events to `scrollToEvent` and villager-select controls to `selectVillager`. Implement ATTR-16 delta highlighting: elements corresponding to fields in `changed_fields` receive a visible highlight CSS class on scroll; the highlight is removed on the next scroll. Villager death is displayed as "deceased" with a frozen stat panel after the death event.

**TEST PLAN (Playwright):**

Fixture: same fixture data as diff 3, plus a VRBTM-tier-spanning range of stat values and one dead villager.

- **Dark theme applied.** Assert `document.body` has a computed background-color that is not white or near-white (RGB values all below 60).
- **Event log renders in order.** After `initSession`, assert the event log pane contains the correct number of event entries in chronological order. Assert the first and last entries match the fixture event texts.
- **Timestamps visible.** Assert each rendered event entry contains a readable timestamp string (e.g., "Day 1, 6:00 AM") per ATTR-17.
- **Stat panel renders correct values.** After loading, assert the stat panel for the selected villager displays numeric values for wakefulness, satiation, hydration, social_joy, connectedness, cleanliness that match the session state.
- **Delta highlighting on scroll.** Scroll to an event where `aldric.wakefulness` changed. Assert the wakefulness display element has the highlight CSS class. Scroll to the next event where wakefulness did not change. Assert the wakefulness element no longer has the highlight class (no stale highlight).
- **World panel updates on scroll.** Scroll to an event where `base_storage.PEACH` changed. Assert the base storage panel shows the updated quantity. Assert the PEACH entry has the highlight class. Scroll forward; assert the highlight is gone.
- **Villager selector switches log.** Click the selector for `sewalt`. Assert the event log pane now shows Sewalt's events. Assert the character panel updates to Sewalt's stats.
- **Memory panel populates.** Assert the short-term, medium-term, and long-term memory sections are present. Scroll to a point where a MEMORY_UPDATE delta fired. Assert the relevant memory section reflects the new text.
- **Deceased villager display.** Scroll past the death event for the fixture's dead villager. Assert their panel shows "deceased" and their stat values are no longer updated by subsequent deltas.
- **Relationship panel renders.** Assert that for the selected villager, the relationship section shows an entry for each other villager with the description text from the fixture checkpoint.
