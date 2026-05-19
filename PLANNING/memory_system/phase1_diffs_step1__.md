The plan is written to `diffs/memory_system_plan.md`. Here's a summary of the 7 diffs:

| # | Title | What it delivers |
|---|-------|-----------------|
| 1 | Types | All pure data types in `types.py` — enums, frozen/mutable dataclasses, `VillagerId` newtype |
| 2 | Init and event log | `__init__`, `append_event`, `append_thought` — JSONL persistence, per-villager structures, default relationships |
| 3 | Relationship management | `write_impressions` — FIFO impression queue (cap 3) and wholesale description replacement |
| 4 | Snapshot and context assembly | `trigger_snapshot`, `from_snapshot`, `get_memory_context` — pure state reads and checkpoint restore |
| 5 | Short-term compaction | `trigger_short_term_compaction` — first LLM call; skip-if-empty guard; clears active context log |
| 6 | Medium-term compaction | `_compact_medium_term`, partial `trigger_midnight_compaction` — previous-day filtering, forced short-term pass |
| 7 | Long-term compaction | `_compact_long_term`, complete `trigger_midnight_compaction` — every-third-day trigger, accumulation boundary, full chain integration test |

Each diff is ordered so its tests only depend on APIs introduced in that diff or earlier — no test reaches forward into unimplemented code.