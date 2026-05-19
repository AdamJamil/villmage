The Step 1 content is appended. Here's a summary of the decisions:

**File hierarchy:** Two files.
- `game_types.py` — `CraftableItem` and `ActionCategory` go here (mandated by the design doc to break circular imports with Action System).
- `villager_state.py` — everything else: the three VS-specific enums (`ThresholdCrossing`, `MoodSubcomponent`, `HealthSubcomponent`), two small structs (`CraftingProgress`, `CurrentAction`), the computed-stats bundle (`ComputedStats`), and `VillagerState` itself.

No third file was added. The one tempting split — pulling the VRBTM description tier strings into their own file — adds indirection without any architectural benefit, since the strings are consumed exclusively by `get_stat_descriptions` and nowhere else.