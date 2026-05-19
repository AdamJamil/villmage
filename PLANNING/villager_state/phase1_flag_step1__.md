Appended to `villager_state.md`:

**3 FLAGS** (require your input as the spec author):
1. **Safety tier descriptions** — spec has VRBTM tables for every stat except safety; the impl explicitly has a TODO here. What should the five description tiers be?
2. **REST-dominant prompt** — BHVR-268 says always include the dominant mood subcomponent description, but REST has none. The impl omits the line entirely, violating BHVR-268. What should appear when REST is dominant?
3. **Multiple satchels** — BHVR-266 doesn't say whether a second satchel stacks the +30 kg bonus. The impl caps it at one. Confirm or deny stacking.

**4 ISSUES** (implementation problems, no spec input needed):
1. `connectedness` is stored as `i32` but drains at the non-integer rate 100/48 ≈ 2.083/hr — integer truncation will accumulate drift.
2. REST's partial derivative is −0.06 (negative), but all other mood inputs have positive PDs. Using signed "highest" per the spec, REST could never win. The impl uses magnitude without documenting this departure.
3. Uncapped safety > 1.0 makes well-being > 1.0, which falls outside all VRBTM-170 tiers — `get_stat_descriptions` silently produces no match.
4. `compute_stats` takes `base_fuel_minutes` but WorldState's getter is `get_total_firewood`; the conversion from fuel pieces to burn minutes is unassigned.