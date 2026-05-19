Done. Here's a summary of what changed and why:

**Functional fixes (ISSUE items):**
- `ExploreResource` overview now correctly states LOGS is WOODCUTTER-only (the prose contradicted the enum comments)
- `AutobalanceMultipliers` formula comment fixed: removed `work_speed` (it belongs in the yield sampler, not the multiplier definition)
- `sample_exploration_yield` gains a `work_speed` parameter; `exploration_effective_mean` docstring clarifies work-speed is applied there separately
- `apply_start_effect` docstring explicitly distinguishes `CRAFT_NEW` (consumes materials) from `CONTINUE_CRAFTING` (does not)
- `apply_completion_effect` docstring now lists all calorie charges (exploration, hauling) and all dirtiness sources (butchering, eating meat, cooking meat)
- `cooking_actions` documents the `vs.cooking_paused` field dependency and where it's owned (VillagerState)
- `start_action` documents that `TALK_TO` returns 0 and Simulation Engine routes it to Conversation System; `complete_action` notes it's never called for `TALK_TO`
- `adjust_active_sleep` removes the undocumented `new_modifier` parameter (the caller already has it; this function only needs to process the completed segment) and documents that both `LIGHT_FIRE` completion and fire extinction trigger it

**Structural fixes (STYLE items):**
- Added `ActionContext` struct — all eligibility and effect function signatures now take `ctx: ActionContext` instead of the 5-argument cluster
- Added `ActiveSleepSegment` struct — `adjust_active_sleep` signature is now `(vs, segment)` instead of four bare numerics
- `effects.py` overview documents the per-type handler pattern so the dispatcher functions stay thin
- Resolved `SelectedAction` untagged union, `ValidAction.idx` optional invariant, and `prompt_text` opaque string as acceptable — no change needed, notes removed