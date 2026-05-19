The Step 1 section has been appended to `impl/memory_system.md`. Here's what was added:

**File hierarchy (confirmed two files, same as the sketch):**
- `types.py` — pure data types, no logic, no LLM dependency; imported by every external subsystem that touches memory
- `memory.py` — the single `MemorySystem` class; the only file that imports `LLMClient`

**Object docstrings** cover the key non-obvious points a new implementer needs:
- `EventLogEntry.text` must be self-contained (callers' responsibility, not Memory System's)
- `MemoryEntry` has no tier field — tier is determined by which list it lives in; `game_time // 1440` gives the calendar day
- `RelationshipRecord` is directional `(x, y)` and initialized for all 30 pairs at startup
- `CompactionReason` is diagnostic only — no behavioral effect
- `VillagerMemoryContext` is rendered static-to-dynamic (long-term → medium-term → short-term → active log)
- `MemorySystem` is instantiated once and also deserialized from checkpoints