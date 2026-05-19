Written to `diffs/action_system_plan.md` — 13 diffs total:

| # | Title |
|---|-------|
| 1 | types module (enums + frozen dataclasses, no logic) |
| 2 | timing module (work speed, duration math, Erlang sampling) |
| 3 | eligibility: eating, drinking, storage, resting spots |
| 4 | eligibility: exploration (profession gating, inventory-space checks) |
| 5 | eligibility: fire tending, misc actions |
| 6 | eligibility: crafting, cooking |
| 7 | eligibility: sleeping, washing, conversation + `build_action_list` |
| 8 | effects: start effects (CRAFT_NEW materials, fire fuel deduction) |
| 9 | effects: stat restoration completions (eat/drink/sleep/wash/place) |
| 10 | effects: exploration completion (Erlang yield, calorie charges, carcass tracking) |
| 11 | effects: misc completions (scrape, haul, butcher, clean, split) |
| 12 | effects: crafting and cooking completions |
| 13 | public api (`get_valid_actions`, `start_action`, `complete_action`, `adjust_active_sleep`) |

The key test philosophy across all diffs: stochastic functions (Erlang sampler) get boundary-condition tests plus statistical mean checks over many trials; mutation functions get before/after assertions on the actual state objects; cross-cutting constraints (inventory-first ordering, 4-hour fuel cap, profession gates, index uniqueness) each get their own dedicated test so a wrong implementation can't hide behind a passing integration test.