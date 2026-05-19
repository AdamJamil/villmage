Three flags and three issues appended to `impl/memory_system.md`:

**Flags (need your input):**
1. **Empty context log on sleep** — BHVR-251 says compaction fires unconditionally on sleep; spec is silent on whether to skip or proceed with an empty log.
2. **Context log events spanning midnight** — Previous-day events still in `active_context_log` at midnight are excluded from medium-term compaction and would be tagged to the next day. Should midnight first flush short-term compaction?
3. **Relationship update scope** — BHVR-67/68 implies all 30 ordered pairs update after every conversation; VRBTM-69 and both impl docs scope this to participant pairs only. Contradiction needs resolution.

**Issues (implementation problems to fix):**
1. `trigger_short_term_compaction` and `trigger_midnight_compaction` have `game_time` parameters in Core Functions that are missing from the API Surface section.
2. `VillagerState.reset_compaction_counter()` is called in the compaction logic but exists nowhere in Villager State's documented interface.
3. `trigger_snapshot` simultaneously says it writes to a `.json` file and returns a `dict` for Simulation Engine to write — contradictory.