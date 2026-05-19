`/home/tack/code/villmage/impl/villager_state.md` is written. Here's what it covers:

**Additions to `game_types.py`:**
- `CraftableItem` enum (SATCHEL, BED_ROLL, COT) — shared with Action System
- `ActionCategory` enum (18 values: SLEEPING, RESTING, EXPLORING, HAULING, ...) — the key semantic distinction is EXPLORING/HAULING as "away" actions, SLEEPING as blocking conversation participation

**Owned types in `villager_state.py`:**
- `ThresholdCrossing` — WAKEFULNESS_ZERO / HEALTH_ZERO, returned by `apply_decay`
- `MoodSubcomponent` / `HealthSubcomponent` — for partial-derivative selection in BHVR-174/191
- `CraftingProgress` — (item, minutes_spent); materials already consumed when this exists
- `CurrentAction` — (category, optional detail, completion_timestamp)
- `ComputedStats` — all derived scores + dominant subcomponent selection; consumed by AI Coordinator
- `VillagerState` — all 7 raw stats, inventory dict, sleep claim, crafting state, current action, rest timer, compaction counter, alive flag

**Key logic nailed down:**
- `apply_decay` drain rules: wakefulness only when awake, everything else always (including sleep)
- Health formula edge cases (satiation=0 → health=0, wakefulness=0 doesn't alone zero health)
- Partial derivatives computed numerically via finite differences (ε=1e-4)
- Carry capacity: 40kg base + 30kg if satchel in inventory; derived on the fly
- Safety formula with the CONST-202 dimensional correction from design.md
- REST subcomponent has no dedicated VRBTM description tier — flagged as a gap