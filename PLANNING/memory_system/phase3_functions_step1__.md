The core functions are now appended to `impl/memory_system.md`. Here's a summary of decisions made:

- **`types.py`** has no functions — pure data declarations only.
- **`MemorySystem`** has 8 core functions covering the full API surface:
  - `__init__` + `from_snapshot` for construction and checkpoint restart
  - `append_event` / `append_thought` for log writes (synchronous, disk-flushing)
  - `write_impressions` for post-conversation relationship updates
  - `trigger_short_term_compaction` / `trigger_midnight_compaction` (async LLM calls) — notably, both take `game_time` as an explicit parameter since callers know the current time and the compaction logic needs it to identify which day's entries to compact
  - `trigger_snapshot` / `get_memory_context` for checkpointing and prompt assembly