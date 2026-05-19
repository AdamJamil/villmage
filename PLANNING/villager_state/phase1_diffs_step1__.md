Written to `diffs/villager_state_plan.md`. Five diffs:

1. **game_types additions** — `CraftableItem` (with `total_minutes`), `ActionCategory` (with `is_away`), `WorldContext`, `StatName`. Tests are exhaustive on enum values and properties since these are serialised and gate cross-subsystem behavior.

2. **Data types + simple mutators** — all dataclasses/enums, `VillagerState.__init__`, inventory/stat mutators, carry capacity logic. Tests cover starting values exactly, all six stat clamps, satchel non-stacking, and per-item `can_fit` boundaries.

3. **Health + decay** — `_compute_health` and `apply_decay`. Tests verify each drain rate numerically, that wakefulness doesn't drain during sleep, that social_joy is immune, floor-at-zero, the two crossing flags (including simultaneous), and that `awake_minutes_since_compaction` only accumulates while awake.

4. **Derived stat computation** — `compute_stats` and the two `_dominant_*` helpers. Tests construct explicit scenarios that force each of the 5 mood and 3 health subcomponents to be dominant, verify the REST magnitude goes to 0 at r≥5, check safety uncap + well-being reclamping, and validate the mood formula collapses correctly when any multiplicative term is 0.

5. **Stat descriptions + work speed** — `get_stat_descriptions` and `get_work_speed_modifier`. Tests cover always-included keys, conditional thresholds at their exact boundaries, the deduplication case (dominant subcomponent overlapping with a conditional include), tier text correctness for all 12 tables, and the work-speed boundary at exactly 0.5.