All nine issues resolved:

1. **Water in mL** — `water_supply_liters` → `water_supply_ml`; `modify_water` takes `delta_ml`. Haul adds `20000`, washing subtracts `500`.
2. **Missing carcass ID counter** — Added `next_carcass_id: i32` to `WorldState` struct, starting at 1.
3. **`extinguish_fire` contract** — Docstring now explicitly states `extinction_timestamp` is cleared to `None`.
4. **`get_base_summary` signature** — Now takes `current_time: int`; `BaseSummary` holds pre-computed remaining fuel minutes.
5. **`FuelType`/`ItemType` parallel enums** — Added `item_type_to_fuel_type` module-level helper; callers use it instead of raw mapping.
6. **Carcass creation two-step** — Left as two-step (location is caller's concern); improved `add_carcass` docstring to make the caller obligation explicit.
7. **Carcass removal three-step → two-step** — `remove_carcass` now always increments `CARCASS_REMAINS` dirtiness internally. Caller only needs to handle item removal. `update_cleanliness_source` docstring updated to exclude carcass remains.
8. **`clear_dirtiness` return** — Now returns `int` (total before clearing), eliminating the read-before-clear ordering hazard.
9. **`add_fire_fuel`/`light_fire` scheduling obligation** — Docstrings now explicitly name "schedule the fire-extinction heap event" as the caller's responsibility. Design left intact — the return value is the right mechanism here.