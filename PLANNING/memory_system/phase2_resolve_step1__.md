All stylistic and design issues are resolved and removed. Summary of changes:

- **`VillagerId` newtype** added to `types.py` — catches speaker/subject/villager_id mixups under Pyre strict
- **`MemorySnapshot` dataclass** added to both Core Objects (with full struct) and types.py Object Assignments — replaces the `dict[str, object]` return type on `trigger_snapshot` / `from_snapshot`
- **Signature conflicts fixed** — `game_time: int` added to both `trigger_short_term_compaction` and `trigger_midnight_compaction` in the API Surface section
- **`trigger_midnight_compaction` decomposed** — `_compact_medium_term` and `_compact_long_term` private helpers added to Core Functions
- **`awake_minutes_since_compaction` ownership clarified** — explicitly assigned to Villager State with `reset_compaction_counter()` noted as its API
- **Checkpoint write ambiguity resolved** — `trigger_snapshot` returns a `MemorySnapshot`; Simulation Engine does the disk write
- **God-object flag dropped** — extraction would add abstraction without benefit at this scale; left as-is
- **`EventLogEntry.text` and `write_impressions` flags dropped** — both already sufficiently documented in their docstrings