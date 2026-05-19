# memory_system — Diff Plan

Seven diffs across `memory_system/types.py` and `memory_system/memory.py`, covering the pure data layer, event log management, relationship updates, state serialization, and the three-tier compaction hierarchy.

---

## DIFF 1

**TITLE:** `[memory_system][1/7]` Types

**DESCRIPTION:**
Add `memory_system/types.py` with all pure data types. No logic; no imports from within the package or from LLM Client.

`VillagerId` is a `NewType` wrapper around `str`. This is the sole guard against silently mixing `villager_id`, `speaker_id`, and `subject_id` at call sites where all three are in scope simultaneously.

`EventType` is an enum with five members and exact integer values per the spec: `ACTION=1`, `THOUGHT=2`, `CONVO_TURN=3`, `TRADE=4`, `BASE_EVENT=5`. `CompactionReason` has two members: `SLEEP=1`, `AWAKE_THRESHOLD=2`. Both are routing enums — wrong integer values silently corrupt any code that serializes or pattern-matches on them.

`EventLogEntry` (frozen dataclass): `game_time: int`, `type: EventType`, `text: str`. The `text` field is fed verbatim into LLM compaction prompts; no content validation is performed here — callers own that responsibility. Frozen because entries are never modified after being appended.

`MemoryEntry` (frozen dataclass): `game_time: int`, `text: str`. No tier field; tier is determined entirely by which list the entry lives in inside `MemorySystem`. `game_time` is used to identify which calendar day a short-term entry belongs to (`game_time // 1440`), the key operation for midnight compaction's previous-day selection (BHVR-256).

`RelationshipRecord` (mutable dataclass): `description: str`, `recent_impressions: list[str]`. Mutable because `write_impressions` modifies both fields in place. The FIFO cap-3 invariant is enforced by `MemorySystem`, not by this struct.

`VillagerMemoryContext` (frozen dataclass): `long_term_memories: list[MemoryEntry]`, `medium_term_memories: list[MemoryEntry]`, `short_term_memories: list[MemoryEntry]`, `active_context_log: list[EventLogEntry]`, `relationships: dict[VillagerId, RelationshipRecord]`. Frozen because it is a read-only assembled view consumed by AI Coordinator.

`MemorySnapshot` (frozen dataclass): six fields mirroring `MemorySystem`'s in-memory layout exactly — `active_context_log: dict[VillagerId, list[EventLogEntry]]`, `short_term_memories: dict[VillagerId, list[MemoryEntry]]`, `medium_term_memories: dict[VillagerId, list[MemoryEntry]]`, `long_term_memories: dict[VillagerId, list[MemoryEntry]]`, `relationships: dict[VillagerId, dict[VillagerId, RelationshipRecord]]`, `last_long_term_compaction_day: int`. Frozen because it is a typed checkpoint artifact passed to Simulation Engine for disk serialization.

**TEST PLAN:**

*`tests/memory_system/test_types.py`*

*Enum values — EventType.* Assert all five `EventType` members and their exact integer values: `ACTION=1`, `THOUGHT=2`, `CONVO_TURN=3`, `TRADE=4`, `BASE_EVENT=5`. Assert `len(EventType) == 5`. A wrong integer value silently corrupts serialization and any code comparing event types.

*Enum values — CompactionReason.* Assert `SLEEP=1`, `AWAKE_THRESHOLD=2` exactly, and `len(CompactionReason) == 2`.

*EventLogEntry — construction and field access.* Instantiate with all three fields and assert each field returns the supplied value. Verify `type` field accepts an `EventType` enum member.

*EventLogEntry — frozen.* Assert that attempting to assign to any field raises `FrozenInstanceError` (or equivalent). Entries must be structurally immutable, not just conventionally so.

*MemoryEntry — construction and frozen.* Same pattern: instantiate, assert fields, assert mutation raises.

*RelationshipRecord — construction and mutability.* Instantiate with a description and an empty `recent_impressions` list. Assert both fields are accessible. Assert the list field can be appended to and popped from without error — this is the struct that `write_impressions` mutates in place, so mutability is required.

*VillagerMemoryContext — construction and frozen.* Construct with all five fields (using empty lists and an empty dict) and assert field access returns correct values. Assert `FrozenInstanceError` on field assignment.

*MemorySnapshot — construction and frozen.* Same pattern for all six fields, including `last_long_term_compaction_day: int`.

*VillagerId — newtype behavior.* Assert that `VillagerId("aldric")` equals the string `"aldric"` at runtime. Verify it can be used as a dict key interchangeably with the underlying string.

---

## DIFF 2

**TITLE:** `[memory_system][2/7]` Init and event log

**DESCRIPTION:**
Add `memory_system/memory.py` with `MemorySystem.__init__`, `append_event`, and `append_thought`. No compaction, no snapshot, no relationship logic — just the foundational event log.

`__init__(self, villager_ids: list[VillagerId], llm_client: LLMClient, event_log_path: Path)` initializes six per-villager dictionaries keyed by `VillagerId`: `_active_context_log`, `_short_term_memories`, `_medium_term_memories`, `_long_term_memories` (each mapping to an empty list), and `_relationships` (mapping to an empty inner dict). It also initializes all `n*(n-1)` ordered pairs in `_relationships[x][y]` with a `RelationshipRecord` whose `description` is `"I don't know anything about them."` (CONST-244) and `recent_impressions=[]`. For six villagers that is exactly 30 pairs. Finally it opens `event_log_path` for appending (creating if absent) to receive JSONL output. `_last_long_term_compaction_day` is initialized to `0`.

`append_event(self, villager_id: VillagerId, entry: EventLogEntry)` appends the entry to `_active_context_log[villager_id]` and immediately serializes the entry as one JSON line to the open file handle (flushing after each write so crash-safety holds). The JSONL file is the persistent full event log (BHVR-12); the in-memory `_active_context_log` is the subset of events not yet compacted. Both are updated by this single call.

`append_thought(self, villager_id: VillagerId, game_time: int, text: str)` constructs an `EventLogEntry` with `type=EventType.THOUGHT` and delegates to `append_event`. It exists as a named API to make the call site in Simulation Engine unambiguous (STRCT-248, BHVR-249).

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*Init — per-villager data structures.* Construct a `MemorySystem` with three villager IDs. Assert each villager's `_active_context_log` is initially an empty list, and likewise for the three memory tier lists.

*Init — relationship map completeness.* For three villagers, assert that `_relationships` contains exactly `3*2=6` ordered pairs, each with description `"I don't know anything about them."` and empty `recent_impressions`. Assert that self-pairs (`x == x`) are absent. This test encodes CONST-244 exactly.

*Init — event log file created.* Pass a path in a temp directory that does not yet exist. Assert the file is created after `__init__`. Assert it is empty (zero bytes) initially.

*`append_event` — in-memory accumulation.* Append two events for villager A and one for villager B. Assert `_active_context_log[A]` has exactly two entries in insertion order and `_active_context_log[B]` has one. Events must not bleed across villagers.

*`append_event` — JSONL flush.* Append one event and then read the log file. Assert it contains exactly one line, that the line is valid JSON, and that the parsed object has fields `game_time`, `type`, and `text` matching the appended entry. Append a second event; assert two lines.

*`append_event` — immediate flush.* Close the MemorySystem's underlying file handle externally (or read bytes directly) immediately after `append_event`. Assert the line is present — the write must not be buffered.

*`append_thought` — type field.* Call `append_thought` and assert the resulting `EventLogEntry` in `_active_context_log` has `type == EventType.THOUGHT` and that `text` matches the supplied argument. The `game_time` field must also match.

*`append_thought` — delegates to `append_event`.* Assert the thought entry appears in the JSONL file, proving `append_thought` goes through `append_event` and not a separate code path.

---

## DIFF 3

**TITLE:** `[memory_system][3/7]` Relationship management

**DESCRIPTION:**
Add `write_impressions` to `MemorySystem`. This is the only method that mutates the `_relationships` map.

`write_impressions(self, speaker_id: VillagerId, subject_id: VillagerId, impression: str, desc_update: str | None)` modifies `_relationships[speaker_id][subject_id]` in two steps. First, it appends `impression` to `recent_impressions`. If the list length now exceeds 3, it drops the oldest entry (index 0) so the list length stays at 3 — this is the FIFO cap defined by BHVR-70. Second, if `desc_update` is not `None`, it replaces `description` wholesale (BHVR-71). The impression is always appended; the description replacement is conditional and independent.

The FIFO invariant is the only non-trivial logic here. The description says "drop oldest when a 4th impression is added" — the representation is a plain Python list where index 0 is oldest. The implementation must preserve chronological insertion order so that "oldest" and "newest" are unambiguous.

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*First impression.* Call `write_impressions` once with `desc_update=None`. Assert `recent_impressions` has exactly one entry matching the supplied impression string. Assert `description` is still the default `"I don't know anything about them."`.

*Up to three impressions.* Call `write_impressions` three times with distinct impression strings. Assert the list contains all three, in insertion order (oldest at index 0, newest at index 2). Length must be exactly 3.

*Fourth impression drops oldest — FIFO.* Call `write_impressions` four times with strings `"A"`, `"B"`, `"C"`, `"D"`. Assert `recent_impressions == ["B", "C", "D"]`. The oldest (`"A"`) must have been dropped, not the newest. This is the tightest possible check of the FIFO semantics from BHVR-70.

*Fifth and sixth impressions — continued FIFO.* Continue from the above state: call with `"E"`, then `"F"`. Assert the list is `["D", "E", "F"]` then `["E", "F", "G"]`. Verifies the invariant holds on successive removals.

*`desc_update=None` — description unchanged.* Fill the impression queue to 3, then call with a new impression and `desc_update=None`. Assert `description` is still the original. The impression must still be added; only the description update is skipped.

*`desc_update` provided — description replaced.* Call with `desc_update="Shared food with party."`. Assert `description == "Shared food with party."`. The replacement is wholesale: no concatenation, no prefix.

*Both impression and desc_update in one call.* Call with a new impression and a new description simultaneously. Assert both the impression was appended to the queue and the description was replaced. These are independent operations; one must not gate the other.

*Ordered pair isolation.* Call `write_impressions(A, B, "imp1", None)` and `write_impressions(B, A, "imp2", None)`. Assert `_relationships[A][B].recent_impressions == ["imp1"]` and `_relationships[B][A].recent_impressions == ["imp2"]`. The directed pair `(A, B)` and `(B, A)` are independent records.

---

## DIFF 4

**TITLE:** `[memory_system][4/7]` Snapshot and context assembly

**DESCRIPTION:**
Add `trigger_snapshot`, `from_snapshot`, and `get_memory_context` to `MemorySystem`. No LLM calls; these are pure state reads and a reconstruction path.

`trigger_snapshot(self) -> MemorySnapshot` serializes the current in-memory state into a `MemorySnapshot`. It deep-copies all five per-villager maps (lists of entries and the nested relationship dicts) so that the snapshot is a stable point-in-time record that does not change if the live `MemorySystem` is subsequently mutated. It also copies `_last_long_term_compaction_day`. The full event log (JSONL on disk) is not included — it is already persisted (REQ-272).

`from_snapshot(cls, snapshot: MemorySnapshot, llm_client: LLMClient, event_log_path: Path) -> MemorySystem` is a `@classmethod` that reconstructs a `MemorySystem` without calling `__init__`. It restores all six fields from the snapshot and opens `event_log_path` in append mode (the file must already exist and contain all prior events). The `villager_ids` are derived from the snapshot's dict keys.

`get_memory_context(self, villager_id: VillagerId) -> VillagerMemoryContext` assembles the context consumed by AI Coordinator. It returns a `VillagerMemoryContext` where:
- Each memory tier list is the villager's current list in chronological order (as stored).
- `active_context_log` is the villager's current in-context log, including `THOUGHT` entries inline in chronological position (STRCT-247, STRCT-248).
- `relationships` is a dict keyed by every *other* villager's ID (exactly 5 entries for 6 villagers) mapping to that villager's `RelationshipRecord`. Self is excluded.

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*`trigger_snapshot` — captures active_context_log.* Append two events for villager A, one for villager B. Take a snapshot. Assert the snapshot's `active_context_log[A]` matches the two appended entries (by equality) and `active_context_log[B]` has one. Assert all other villagers' lists are empty.

*`trigger_snapshot` — captures empty memory tiers.* On a fresh `MemorySystem`, take a snapshot. Assert all four memory-tier dicts in the snapshot have their keys present but contain empty lists. The keys must exist (one per villager_id) — absence would indicate the snapshot is incomplete.

*`trigger_snapshot` — captures relationships with defaults.* Take a snapshot immediately after construction. Assert `relationships[A][B].description == "I don't know anything about them."` for a sample pair and that all `n*(n-1)` pairs are present.

*`trigger_snapshot` — captures populated relationships.* Call `write_impressions` on one pair, then snapshot. Assert the snapshot reflects the updated impression and that the mutation is visible in the snapshot.

*`trigger_snapshot` — snapshot is a deep copy.* Take a snapshot, then append another event to villager A. Assert the snapshot's `active_context_log[A]` has not grown. The snapshot must be frozen in time.

*`from_snapshot` — round-trip active_context_log.* Build a `MemorySystem`, append events, take a snapshot, reconstruct via `from_snapshot`. Assert the reconstructed system's `_active_context_log` matches the original's at snapshot time (entry-by-entry equality).

*`from_snapshot` — round-trip relationships.* Call `write_impressions` to modify several pairs, snapshot, reconstruct. Assert all modified relationship records match the original.

*`from_snapshot` — round-trip memory tiers.* Directly inject entries into `_short_term_memories[A]` and `_long_term_memories[B]` on the live system, snapshot, reconstruct. Assert the reconstructed system has the same entries in the same tiers. This exercises that snapshot captures all four memory-tier dicts, not just the ones populated through the public API.

*`from_snapshot` — `last_long_term_compaction_day`.* Set `_last_long_term_compaction_day = 6` directly, snapshot, reconstruct. Assert the reconstructed system has `_last_long_term_compaction_day == 6`.

*`get_memory_context` — relationships has exactly 5 entries.* For a 6-villager system, call `get_memory_context` for villager A. Assert `len(context.relationships) == 5` and that villager A's own ID is not a key.

*`get_memory_context` — relationship values match live state.* Modify a relationship via `write_impressions`, then call `get_memory_context`. Assert the context's `relationships` dict reflects the modification.

*`get_memory_context` — active_context_log matches live state.* Append events, call `get_memory_context`. Assert `context.active_context_log` is in chronological order and contains exactly the entries in `_active_context_log[villager_id]`.

*`get_memory_context` — all memory tiers initially empty.* On a fresh system, assert all three memory-tier lists in the context are empty.

---

## DIFF 5

**TITLE:** `[memory_system][5/7]` Short-term compaction

**DESCRIPTION:**
Add `trigger_short_term_compaction` to `MemorySystem`. This is the first diff that calls the LLM.

`async def trigger_short_term_compaction(self, villager_id: VillagerId, game_time: int, reason: CompactionReason) -> None` (BHVR-251, BHVR-252): If `_active_context_log[villager_id]` is empty, return immediately without making an LLM call or adding any entry — per BHVR-251, compaction is silently skipped when there is nothing to compact. Otherwise, it assembles the compaction prompt (VRBTM-253): the preamble `"Here is a log of everything you experienced recently: <log>. In 128 tokens (~90 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."`, with `<log>` replaced by the serialized entries in the active context log. It calls `LLMClient.complete()` with `CallType.MEMORY_COMPACTION`. The returned text is stored as a `MemoryEntry(game_time=game_time, text=response.text)` appended to `_short_term_memories[villager_id]`. Finally, `_active_context_log[villager_id]` is cleared. The `reason` parameter is for diagnostic logging only and has no effect on the prompt or outcome.

The skip-if-empty behavior is safety-critical: without it, a redundant LLM call generates an empty or nonsense summary and adds a spurious `MemoryEntry` that will pollute all future compaction tiers.

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*Empty log — no LLM call, no entry.* Construct a `MemorySystem` (villager A has empty log). Call `trigger_short_term_compaction(A, game_time=100, reason=SLEEP)` with a mock LLM client. Assert the mock was never called. Assert `_short_term_memories[A]` remains empty. This is the BHVR-251 skip guard.

*Non-empty log — LLM called.* Append two events to villager A's log, then call compaction. Assert the mock `LLMClient.complete` was called exactly once with `CallType.MEMORY_COMPACTION`.

*Prompt contains log content.* Capture the prompt segments passed to the mock. Assert the prompt contains the `text` fields of the two appended events. The log must be embedded verbatim into the compaction prompt (VRBTM-253).

*MemoryEntry stored with correct game_time.* Call compaction with `game_time=720`. Assert `_short_term_memories[A][-1].game_time == 720`. The `game_time` argument determines the entry's timestamp, not the game_time on the individual log entries.

*MemoryEntry text matches LLM response.* Configure the mock to return text `"Gathered wood, spoke to Sewalt."`. Assert `_short_term_memories[A][-1].text == "Gathered wood, spoke to Sewalt."`. No truncation or transformation.

*Active context log cleared after compaction.* After a successful compaction, assert `_active_context_log[A]` is empty.

*Subsequent events accumulate in cleared log.* Append an event after compaction and assert it is the only entry in `_active_context_log[A]`. Clearing must not permanently break appending.

*Multiple sequential compactions.* Run compaction three times (appending at least one event between each). Assert `_short_term_memories[A]` has exactly three entries in insertion order.

*Villager isolation.* Append events to A and B, compact A only. Assert B's `_active_context_log` is unchanged and `_short_term_memories[B]` is still empty.

*CompactionReason has no behavioral effect.* Call once with `reason=SLEEP` and once with `reason=AWAKE_THRESHOLD` (both after appending an event). Assert both produce a `MemoryEntry` and that the LLM call is identical in structure for both — reason is diagnostic only.

---

## DIFF 6

**TITLE:** `[memory_system][6/7]` Medium-term compaction

**DESCRIPTION:**
Add `_compact_medium_term` and a partial `trigger_midnight_compaction` (without long-term). Long-term is deferred to diff 7.

`async def _compact_medium_term(self, villager_id: VillagerId, current_game_time: int) -> None` (BHVR-255, BHVR-256): First, if `_active_context_log[villager_id]` is non-empty, call `trigger_short_term_compaction(villager_id, current_game_time, reason=CompactionReason.AWAKE_THRESHOLD)` — this is the forced short-term pass that ensures no events are lost before medium-term runs. Then compute `previous_day = (current_game_time // 1440) - 1` and collect all entries in `_short_term_memories[villager_id]` where `entry.game_time // 1440 == previous_day`. If no such entries exist after the short-term pass, return without making an LLM call (no-op for this villager). Otherwise, assemble the medium-term prompt (VRBTM-257): `"Here are your memories from yesterday: <short-term memories>. In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."`. Call `LLMClient.complete()` with `CallType.MEMORY_COMPACTION`. Store the result as a `MemoryEntry(game_time=current_game_time, text=response.text)` in `_medium_term_memories[villager_id]`. Remove the selected previous-day entries from `_short_term_memories[villager_id]`.

`async def trigger_midnight_compaction(self, current_game_time: int) -> None` (partial, BHVR-255): Calls `_compact_medium_term` for every villager. Long-term logic is absent in this diff.

The previous-day selection (`game_time // 1440 == previous_day`) is the exact operation specified in BHVR-256. Same-day short-term entries (from the just-forced short-term compaction) must NOT be included — they belong to the current day and will be picked up at the next midnight.

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*Previous-day filtering — only correct day selected.* Manually inject three `MemoryEntry` objects into `_short_term_memories[A]`: one with `game_time=1000` (day 0), one with `game_time=1440` (day 1), one with `game_time=2900` (day 2). Call `_compact_medium_term(A, current_game_time=2880)` (midnight of day 2; previous_day=1). Assert the LLM was called with only the day-1 entry (`game_time=1440`), and that the day-0 and day-2 entries survive in `_short_term_memories[A]`.

*Previous-day entries removed after compaction.* After the above, assert that `_short_term_memories[A]` no longer contains the day-1 entry.

*No previous-day entries — no LLM call.* Inject only a same-day entry. Call `_compact_medium_term`. Assert the mock LLM was not called and `_medium_term_memories[A]` is empty.

*Forced short-term compaction fires first.* Append an event to `_active_context_log[A]` (simulating an event that occurred before midnight but was not yet compacted). Call `_compact_medium_term`. Assert the mock LLM was called at least once for short-term compaction before medium-term. Also assert `_active_context_log[A]` is empty afterwards.

*Forced short-term produces same-day entry — not picked up by medium-term.* Set `current_game_time=2880`. Append an event and call `_compact_medium_term`. The forced short-term compaction creates a `MemoryEntry` with `game_time=2880` (day 2). Assert the medium-term LLM call only includes prior-day entries (not day 2), and that the just-created short-term entry remains in `_short_term_memories[A]`.

*Medium-term MemoryEntry stored with current_game_time.* Call `_compact_medium_term(A, current_game_time=2880)` with one previous-day entry present. Assert `_medium_term_memories[A][-1].game_time == 2880`.

*Medium-term entry text matches LLM response.* Configure mock to return `"Day 1: Hunted boar, argued with Harren."`. Assert `_medium_term_memories[A][-1].text` equals that string exactly.

*`trigger_midnight_compaction` — runs for all villagers.* Construct a system with three villagers, inject previous-day short-term entries for each. Call `trigger_midnight_compaction`. Assert each villager has a new entry in `_medium_term_memories` and their previous-day short-term entries are gone.

*`trigger_midnight_compaction` — villager with no entries is no-op.* One villager has no events and no short-term memories. Call `trigger_midnight_compaction`. Assert no LLM call is made for that villager and their memory state is unchanged.

---

## DIFF 7

**TITLE:** `[memory_system][7/7]` Long-term compaction

**DESCRIPTION:**
Add `_compact_long_term` and complete `trigger_midnight_compaction` by calling it on every third day.

`async def _compact_long_term(self, current_game_time: int) -> None` (BHVR-259): Collects, for each villager, all `MemoryEntry` objects in `_medium_term_memories[villager_id]` whose `game_time // 1440 > _last_long_term_compaction_day`. For each villager that has such entries, assembles the long-term prompt (VRBTM-270): `"Here are your accumulated memories from prior days: <medium-term memories>. In 256 tokens (~180 words), form an EXTREMELY CONCISE summary of the salient memories you experienced. This will be recorded in the future and the rest will be thrown out. Prioritize information you will use to inform later actions or opinions on others. Prioritize information density and accuracy."`. Calls `LLMClient.complete()` with `CallType.MEMORY_COMPACTION`. Stores the result as a `MemoryEntry(game_time=current_game_time, text=response.text)` in `_long_term_memories[villager_id]`. Removes the collected medium-term entries. After processing all villagers, sets `_last_long_term_compaction_day = current_game_time // 1440`.

`trigger_midnight_compaction` is extended: after calling `_compact_medium_term` for every villager, it checks whether `current_day % 3 == 0` (where `current_day = current_game_time // 1440`). If so, it calls `_compact_long_term(current_game_time)`. The check fires on day 3, 6, 9, etc. (BHVR-259). Days 1, 2, 4, 5, 7, 8, … are not multiples of 3 and skip long-term.

The `_last_long_term_compaction_day` boundary ensures that medium-term memories from previous long-term cycles are not re-compacted. This is the only internal counter that distinguishes "new medium-term since last long-term compaction" from older entries.

**TEST PLAN:**

*`tests/memory_system/test_memory.py`*

*Fires on day 3 — LLM called.* Inject a medium-term entry with `game_time=1000` (day 0). Call `trigger_midnight_compaction(current_game_time=3*1440)`. Assert the long-term LLM call is made and `_long_term_memories[A]` has one entry.

*Does not fire on day 1 or day 2.* Call `trigger_midnight_compaction(current_game_time=1440)` (day 1) and then `(current_game_time=2880)` (day 2). Assert no long-term LLM call occurs and `_long_term_memories[A]` remains empty.

*Fires on day 6 after already firing on day 3.* Simulate day 3 compaction (set `_last_long_term_compaction_day=3`). Inject a medium-term entry created after day 3 (e.g., `game_time=5000`). Call `trigger_midnight_compaction(current_game_time=6*1440)`. Assert long-term LLM called and the day-3 entry is NOT re-included (it was already compacted).

*Accumulation since last long-term — boundary filtering.* Set `_last_long_term_compaction_day=3`. Inject two medium-term entries: one with `game_time=3*1440+100` (day 3, just after last compaction — game_time // 1440 == 3, which is NOT greater than 3) and one with `game_time=4*1440+100` (day 4). Call `_compact_long_term(current_game_time=6*1440)`. Assert only the day-4 entry is included in the prompt; the day-3 entry is excluded because `3 > 3` is false.

*Medium-term entries removed after long-term compaction.* Inject two medium-term entries (past the boundary), call `_compact_long_term`. Assert both entries are removed from `_medium_term_memories[A]`.

*`_last_long_term_compaction_day` updated.* Call `_compact_long_term(current_game_time=4320)` (day 3). Assert `_last_long_term_compaction_day == 3` afterward.

*Long-term MemoryEntry stored.* Assert `_long_term_memories[A][-1].game_time == current_game_time` and `.text` matches the mock LLM response.

*No medium-term entries — no LLM call.* Call `_compact_long_term` on a day-3 midnight with no medium-term entries for any villager. Assert no LLM call and `_long_term_memories` remains empty.

*Villager with no new medium-term entries skipped.* Two villagers: A has a qualifying medium-term entry, B does not. Call `_compact_long_term`. Assert the LLM is called only for A and B's `_long_term_memories` remains empty.

*Full midnight chain on day 3.* Call `trigger_midnight_compaction` on a day-3 midnight with: an uncompacted event in `_active_context_log[A]`, a previous-day short-term entry, and a qualifying medium-term entry. Assert: (1) forced short-term fires for A, (2) medium-term compaction runs for A, (3) long-term compaction runs for A. All three tiers are exercised in the correct order by a single `trigger_midnight_compaction` call. This is the integration test for the full compaction chain.

*Snapshot round-trip after long-term compaction.* After running long-term compaction, take a snapshot and reconstruct via `from_snapshot`. Assert `_long_term_memories`, `_last_long_term_compaction_day`, and the remaining `_medium_term_memories` all survive the round-trip. This validates that the snapshot schema is complete for fully compacted state.
