1 flag and 5 issues appended to `impl/observability.md`:

**FLAG** — `base event` is undefined. BHVR-11's perspective filter says villagers see "all base events" while present and awake, but never defines what qualifies. The write-time filter in Memory System can't be implemented without a precise list of event types that count.

**ISSUEs:**
1. "No server required; open directly in a browser" contradicts the file-loading design — browsers block local filesystem access without a server.
2. `DeltaRecord.changes` is non-optional and "always non-empty," but `MEMORY_UPDATE` records have no `FieldChange` entries, only `memory_kind`/`content`/`subject_id`.
3. `VillagerViewerState` skips field 17, omitting `long_term_memory_texts` from the viewer display despite it being stored in `VillagerMemoryCheckpoint`.
4. `scrollToEvent` only applies deltas forward; backward scrolling would produce wrong state — it needs to delegate to `reconstructStateAt` when `new_game_time < old_game_time`.
5. `append_delta` is attributed solely to Simulation Engine, but Action System directly mutates World State and Villager State via their setters, bypassing Simulation Engine entirely.