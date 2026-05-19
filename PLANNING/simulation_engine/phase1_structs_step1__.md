The file is written. Here's a summary of the core objects defined:

**`EventType`** — Five-value enum: `ACTION_COMPLETE`, `FIRE_EXTINCTION`, `CARCASS_ROT`, `MIDNIGHT`, `CHECKPOINT`. Each maps to a dispatch handler in the engine.

**`ScheduledEvent`** — Heap entry with `(timestamp, sequence)` as ordering key. Sequence is a monotone insertion counter for deterministic tie-breaking. Carries `villager_id` (for action completions) or `carcass_id` (for rot events); both null for fire/midnight/checkpoint.

**`AutobalanceMultipliers`** — Three floats (`exploration_yield`, `satiation_restore`, `hydration_restore`), all starting at 1.0, unbounded. Written at midnight; passed to Action System at construction so it reads current values without per-call threading.

**`SimulationEngine` (owned data)** — Holds `current_game_time`, the event heap, `next_sequence` counter, `AutobalanceMultipliers`, a `dict[str, VillagerState]` (dead villagers removed), and `WorldState`. Pre-populated at `t=360` with one ACTION_COMPLETE per villager plus MIDNIGHT at `t=1440` and CHECKPOINT at `t=540`.

The event handlers section summarizes the dispatch contracts for each event type, including the tricky cases (FIRE_EXTINCTION triggering `adjust_active_sleep`, MIDNIGHT running autobalancing and memory compaction).