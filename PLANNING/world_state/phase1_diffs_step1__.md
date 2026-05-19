`diffs/world_state_plan.md` is written. Eight diffs:

1. **game_types module** — `ItemType`, `RestingSpotType`, `ITEM_WEIGHT_G` (shared leaf, everything else depends on it)
2. **Internal types + shell** — `FuelType`, `FuelUnit`, `DirtinessSource`, `Carcass`, `Fire`, `item_type_to_fuel_type`, `WorldState.__init__`
3. **Storage + water** — `modify_base_item`, `get_base_item_count`, `modify_water`
4. **Fire state machine** — all six fire methods together (tightly coupled invariants; can't split)
5. **Dirtiness** — `update_cleanliness_source`, `clear_dirtiness`, `get_total_dirtiness`
6. **Resting spots** — `place_resting_spot`, `has_placed_spot`
7. **Carcass tracking** — `add_carcass`, `remove_carcass` (depends on diff 5; `remove_carcass` calls `update_cleanliness_source`)
8. **Aggregate queries** — `BaseSummary`, `get_total_edible_calories`, `get_total_fuel_minutes`, `get_base_summary`

Key test design choices: the fire diff tests the extinction_timestamp invariant after *every* transition (the most failure-prone part); the carcass diff tests sort order and dirtiness side-effects; the aggregate diff uses one comprehensive composite snapshot test for `get_base_summary` rather than testing each field in isolation.