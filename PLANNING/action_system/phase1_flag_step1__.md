2 FLAGS and 9 ISSUEs appended to `impl/action_system.md`.

**FLAGs** (need your input):
1. **Work speed + exploration duration** — does work speed change the actual scheduled duration of exploration, or only the displayed mean time per item?
2. **Exploration calorie costs** — do CONST-106/107 costs stack with passive satiation decay, or substitute for it during exploration?

**ISSUEs** (implementation gaps to fix without your input):
1. `ExploreResource` overview says "all professions can explore for others" — false for `LOGS` (WOODCUTTER-locked)
2. No `cooking_in_progress` state field exists anywhere for paused cooking / `FINISH_COOKING`
3. `adjust_active_sleep` takes `new_modifier` but its purpose is undocumented
4. Fire *relighting* mid-sleep not addressed as a trigger for `adjust_active_sleep` (BHVR-161 requires splits on any modifier change)
5. `AutobalanceMultipliers` formula includes `work_speed` but no exploration function accepts it
6. Calorie costs for exploration (CONST-106/107) and hauling (CONST-126) have no documented application site in `effects.py`
7. Dirtiness from eating cooked meat (+5) and cooking meat (+3) not mentioned in `apply_completion_effect`
8. `apply_start_effect` doesn't distinguish `CRAFT_NEW` (consumes materials) from `CONTINUE_CRAFTING` (must not)
9. `TALK_TO` in `ActionType` with no documented behaviour in `start_action`/`complete_action`