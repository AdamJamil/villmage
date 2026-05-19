Functions appended. The spec covers four files:

- **timing.py** — `work_speed_modifier`, `apply_duration_modifier`, `exploration_effective_mean`, `sample_exploration_yield`
- **eligibility.py** — one builder per action group (12 functions) plus `build_action_list` assembling them all
- **effects.py** — `apply_start_effect` (immediate mutations at action start) and `apply_completion_effect` (mutations at event completion)
- **api.py** — the four public API functions (`get_valid_actions`, `start_action`, `complete_action`, `adjust_active_sleep`)

A few design choices embedded in the signatures worth noting:
- `start_action` returns `int` (duration in minutes) — SimEngine uses this to schedule the completion event, since it owns the heap
- `adjust_active_sleep` takes both modifiers explicitly so Action System (not SimEngine) owns the wakefulness-rate math
- `exploration_effective_mean` takes a plain `yield_scale: float` rather than the full `AutobalanceMultipliers` struct to keep the coupling narrow