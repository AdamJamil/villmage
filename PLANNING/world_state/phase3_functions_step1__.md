Functions appended to `world_state.md`. Here's a summary of the decisions made:

**Fire split into four operations** instead of one `set_fire_fuel`: `add_fire_fuel`, `light_fire`, `extinguish_fire`, and `mark_fire_extinguished`. The distinction between voluntary extinguish (preserves queue) and natural burn-out (empties queue) is load-bearing — Simulation Engine calls `mark_fire_extinguished` when the scheduled event fires; Action System calls the others.

**Two fuel getters, not one**: `get_remaining_fuel_minutes(current_time)` reads the active fire queue (for the fire-tending UI's "X minutes of fuel left" and headroom calculation), while `get_total_stored_fuel_minutes()` reads only `base_storage` fuel items (for the firewood safety score per CONST-204, which explicitly uses "base firewood").

**`clear_dirtiness()` separate from `update_cleanliness_source()`**: cleaning zeroes all three source counts atomically; a delta-based call would require Action System to query each count first.

**`add_fire_fuel` and `light_fire` return `int | None`**: callers (Action System, ultimately Simulation Engine) need the new `extinction_timestamp` to reschedule the heap event. Returning it directly avoids a follow-up getter call.