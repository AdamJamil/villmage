One FLAG and five ISSUEs appended to `simulation_engine.md`:

- **FLAG**: Whether force-sleep (BHVR-192) should interrupt an active conversation mid-flow, or only trigger post-hoc after the conversation ends. Needs your decision.

- **ISSUE 1**: The `_handle_action_complete` numbered steps and docstring are inconsistent — BHVR-251 sleep-start compaction and the safety-on-wake recalculation are described in the docstring but have no corresponding numbered steps.

- **ISSUE 2**: `complete_action` is called unconditionally at step 2, but the six initial events at t=360 have no prior action to complete. No initial-state guard is described.

- **ISSUE 3**: MIDNIGHT step 4 re-recalculates safety globally at midnight, directly contradicting the design resolution that safety only recalculates per-villager on wake.

- **ISSUE 4**: `awake_minutes_since_compaction` and `reset_compaction_counter` are referenced but assigned to no subsystem's data model.

- **ISSUE 5**: `run()` terminates "when the heap is empty," but MIDNIGHT and CHECKPOINT self-reschedule forever — the heap is never empty.