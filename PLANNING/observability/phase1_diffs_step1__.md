Written to `diffs/observability_plan.md`. Here's a summary of the plan:

**4 diffs, n=4:**

1. **`types.py` schema and persistence** — `DeltaKind`, `FieldChange`, `DeltaRecord`, `VillagerMemoryCheckpoint`, `CheckpointRecord`, plus `append_delta`/`save_checkpoint`/`load_checkpoint`. Tests cover round-trips for all 4 DeltaKind variants, optional-field exclusion (e.g. MEMORY_UPDATE records must not emit a `changes` key), JSONL accumulation, zero-padded filename format, and a deep-equality load_checkpoint round-trip proving restart correctness (REQ-272). The lexicographic-sort-equals-chronological invariant gets its own test.

2. **Viewer data loading and state reconstruction** — `loadAllCheckpoints`, `loadDeltaIndex`, `reconstructStateAt` with all 4 DeltaKind handlers. Playwright tests hit every DeltaKind independently, verify nearest-checkpoint selection, and — most critically — assert the `changed_fields` isolation invariant: a wakefulness delta at T=400 must NOT appear in `changed_fields` when the scroll target is T=500.

3. **Viewer session management and scroll** — `ViewerSession`, `initSession`, `selectVillager`, `scrollToEvent`. Tests verify forward incremental application vs. backward checkpoint-replay, that `selectVillager` doesn't trigger unnecessary delta replay, and that `changed_fields` is cleared on each scroll advance (not left stale).

4. **Viewer UI rendering and delta highlighting** — full HTML/CSS/JS UI. Tests cover dark theme, event log order and timestamps, stat panel values, highlight-add-on-scroll + highlight-remove-on-next-scroll (the core ATTR-16 behavior), deceased villager frozen panel, and memory/relationship panels updating correctly.