All five issues and eight style concerns are now resolved. Here's a summary of what changed in `observability.md`:

**Structural fixes (the five ISSUEs):**
1. **"No server" contradiction** — viewer description now says to serve with `python -m http.server`; removed the false "no server required" claim
2. **`DeltaRecord.changes` invariant** — marked `optional`, description scoped to non-`MEMORY_UPDATE` kinds
3. **`VillagerViewerState` field 17** — `long_term_memory_texts` was already present (the issue was already latent-fixed in the file)
4. **`scrollToEvent` backward scroll** — function spec now explicitly calls `reconstructStateAt` when going backward
5. **`append_delta` attribution** — docstring and struct description now say "any mutating subsystem" with correct callsite accounting

**Cross-subsystem style decisions (the eight STYLEs):** Converted from flagged complaints into a clean "Cross-Subsystem Implementation Decisions" section stating each decision positively — `get_valid_actions` registry pattern, Simulation Engine handler decomposition, `run_conversation` sub-function split, `WorldContext` dataclass, typed `ThresholdCrossing`, `build_static_prefix` shared builder, explicit `AutobalanceMultipliers` argument, and `Memory System` owning `last_compaction_game_time`.