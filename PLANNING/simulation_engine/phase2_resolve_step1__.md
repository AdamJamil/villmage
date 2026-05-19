The file is updated. Here's a summary of every change made:

**Logic fixes:**
- `run()` termination condition changed from "heap empty" to "all villagers dead" (MidnightEvent/CheckpointEvent self-reschedule forever)
- `complete_action` in ACTION_COMPLETE step 2 now guards against the initial t=360 fire (no prior action exists)
- BHVR-251 and BHVR-252 compaction separated into correct sequence: BHVR-252 fires *before* action selection (step 4), BHVR-251 fires *after* (step 6) only if BHVR-252 didn't already run
- MIDNIGHT step 4 ("recalculate safety at midnight") removed — contradicted the design resolution that safety recalculates per-villager on wake

**Structural fixes:**
- `EventType` enum + `ScheduledEvent` with optionals replaced by 5 explicit dataclasses + `ScheduledEvent` union alias — dispatch now uses `match`/`isinstance`, pyre gets full type info at each handler
- `VillagerId: TypeAlias = str` added to `events.py` — prevents passing any stray string in a villager ID position
- `_sync_fire_event()` moved to run unconditionally in `run()` after every dispatch — eliminates the manual per-handler invariant
- `_handle_action_complete` decomposed into `_apply_thresholds` and `_handle_conversation_action` helpers
- `_compute_autobalance_aggregates()` added — isolates the aggregation logic so `adjust()` and `_handle_midnight` don't independently reimplement the food-safety formula
- Duplicate "Step 1" sections merged into the main document; "Flags and Issues" section removed entirely