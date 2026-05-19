Done. Here's what was added to `observability.md`:

**`observability/types.py` — 3 module-level functions:**
- `append_delta` — writes a `DeltaRecord` line to `state_deltas.jsonl`; called by Simulation Engine on every mutation
- `save_checkpoint` — writes a `CheckpointRecord` to `checkpoints/{game_time:05d}.json`
- `load_checkpoint` — deserializes a checkpoint by game_time; the restart entry point for Simulation Engine

**`observability/viewer.html` — 6 JS functions:**
- `initSession` — loads all checkpoints, builds delta index, loads first villager's log; initializes the session
- `selectVillager` — swaps the active villager's event log without replaying deltas
- `scrollToEvent` — the main scroll handler; advances `current_game_time`, applies new deltas, and populates `changed_fields` for highlighting
- `reconstructStateAt` — core replay algorithm; finds nearest checkpoint ≤ target, applies all four delta kinds, marks `changed_fields` only at the exact target time
- `loadAllCheckpoints` — loads all checkpoint files in chronological order
- `loadDeltaIndex` — reads `state_deltas.jsonl` into a `Map<gameTime, DeltaRecord[]>` for O(1) lookup