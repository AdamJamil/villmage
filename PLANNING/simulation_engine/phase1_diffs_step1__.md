Written to `diffs/simulation_engine_plan.md`. Twelve diffs:

| # | File | Change |
|---|------|--------|
| 1 | `events.py` | Event dataclasses and type aliases |
| 2 | `autobalance.py` | AutobalanceMultipliers and adjust() |
| 3 | `simulation_engine.py` | Shell, `__init__`, heap helpers (`_push`, `_cancel`) |
| 4 | `simulation_engine.py` | `_apply_decay_all`, `_apply_thresholds`, `_force_sleep`, `_kill_villager` |
| 5 | `simulation_engine.py` | `_sync_fire_event` |
| 6 | `simulation_engine.py` | `_handle_midnight` (+ `_compute_autobalance_aggregates`) |
| 7 | `simulation_engine.py` | `_handle_checkpoint` (incl. round-trip load) |
| 8 | `simulation_engine.py` | `_handle_fire_extinction` |
| 9 | `simulation_engine.py` | `_handle_carcass_rot` |
| 10 | `simulation_engine.py` | `_handle_action_complete` |
| 11 | `simulation_engine.py` | `_handle_conversation_action` |
| 12 | `simulation_engine.py` | `run()` main loop |

Key test design choices: the heap ordering test (diff 1) uses the actual six-event startup configuration so it proves real-world correctness, not just abstract ordering. The `adjust()` test (diff 2) covers the compound-daily case since that's where sign errors compound silently. The `_handle_action_complete` tests (diff 10) cover both BHVR-251 and BHVR-252 compaction triggers including the "already-ran" guard. Diff 12 includes one integration test that drives a full simulated day — the only test that exercises handler coordination in a real time-advancing loop.