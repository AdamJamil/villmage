`impl/observability.md` is written. Here's a summary of the decisions made and why:

**Core objects:**

- **`DeltaKind` + `FieldChange` + `DeltaRecord`** — the JSONL delta format. One line per state change, using dot-path field names and JSON-encoded values. This satisfies REQ-18 (only deltas, not full snapshots) while giving the viewer everything it needs for ATTR-16 (delta highlighting). Derived stats (health, mood, etc.) are included in the same `VILLAGER_STATS` records so the viewer never has to re-run the formulas in JavaScript.

- **`VillagerMemoryCheckpoint` + `CheckpointRecord`** — the full-state checkpoint format. Checkpoint files serve double duty: Simulation Engine restart (needs the event heap) and viewer replay base (needs all villager/world/memory state). The file naming convention (`{game_time:05d}.json`) makes "find nearest preceding checkpoint" a simple lexicographic scan.

- **`VillagerViewerState` + `WorldViewerState` + `ViewerSession`** — the viewer's in-memory model at any scroll position. Defining these explicitly ensures both implementers agree on what the sidebar panels render and how `changed_fields` drives ATTR-16 highlighting.

**Key design choices logged in the file:** why `old_value`/`new_value` are JSON strings, why dead villagers stay in memory state but not in later checkpoints, and the viewer startup sequence (checkpoint → delta index → event log → scroll handling).