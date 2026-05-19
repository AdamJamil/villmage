Six style notes appended to `impl/simulation_engine.md`:

1. **`_handle_action_complete` complexity** — 8–10 concerns jammed into one function; needs decomposition into named helpers.
2. **`ScheduledEvent` implicit tagged-union** — optional fields keyed by `event_type` with no type enforcement; prefer explicit subtype classes with a `match` dispatch.
3. **`villager_id: str` bare primitive** — a `VillagerId` newtype would catch wrong-slot bugs across all subsystem boundaries.
4. **`_sync_fire_event` manual invariant** — caller must remember to call it after fire-touching actions; no enforcement. Consider centralizing the call in `run()` after every dispatch instead.
5. **Conversation branch inside `_handle_action_complete`** — large special-case block that should be `_handle_conversation_action(initiator_id)`.
6. **`adjust()` aggregation drift** — the midnight aggregation logic (especially food-safety) mirrors Villager State formulas and lives in two places that can diverge; extract a shared `compute_midnight_aggregates` function.