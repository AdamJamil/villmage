Two flags and four issues appended to `world_state.md`.

**Flags** (need your input):
- Whether sticks count toward the firewood safety score (CONST-204 says "base firewood" but the implementation counts sticks)
- Whether fuel already loaded into the fire queue should count toward safety (currently excluded since it's no longer in base_storage)

**Issues** (implementation problems, no dev input needed):
- Water stored as integer liters can't represent the 500 mL washing cost (CONST-165)
- `WorldState` struct missing a carcass auto-increment counter field
- `extinguish_fire` docs don't explicitly clear `extinction_timestamp`
- `get_base_summary` has no `current_time` parameter but needs it to report remaining fire burn time