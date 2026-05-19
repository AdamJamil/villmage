The core functions are now appended to `simulation_engine.md`. Here's a summary of what was defined:

**`events.py`** — No functions; pure data. `ScheduledEvent` uses `order=True` with non-key fields marked `compare=False` so heap ordering uses only `(timestamp, sequence)`.

**`autobalance.py`** — One function on `AutobalanceMultipliers`:
- `adjust(avg_satiation_pct, avg_hydration_pct, avg_food_safety_days)` — multiplicative adjustment toward targets (0.85 / 0.50 / 1.0 day) by fractional deviation.

**`simulation_engine.py`** — Eleven functions on `SimulationEngine`:
- `__init__` — sets up six villagers, empty world, pre-seeded heap
- `run` — main pop/decay/dispatch loop until heap empty
- `_apply_decay_all` — decays all living villagers, returns per-villager threshold crossings
- `_handle_action_complete` — the most complex handler; covers early-exit on death/force-sleep, action completion, memory compaction (both triggers), safety recalc on wake, AI selection, and the synchronous conversation special case with participant rescheduling
- `_handle_fire_extinction` / `_handle_carcass_rot` / `_handle_midnight` / `_handle_checkpoint` — the four remaining event handlers
- `_force_sleep` — handles the "already popped" edge case explicitly
- `_kill_villager` — cancels events, clears inventory, notifies observers
- `_sync_fire_event` — reconciles heap fire event with WorldState after any fire-mutating action