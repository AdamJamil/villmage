The file is written. Here's a summary of the six core objects defined for action_system:

1. **`ExploreResource`** — Enum of the five things a villager can explore for, annotated with their base mean times and profession locks/penalties.

2. **`ActionType`** — Fine-grained discriminant for all 25 selectable action types. Lives in `action_system/types.py`; imported by AI Coordinator to map `idx` responses back to typed actions.

3. **`AutobalanceMultipliers`** — The three scaling factors (exploration yield, satiation restore, hydration restore) owned by Simulation Engine and passed into Action System at call time.

4. **`ValidAction`** — One entry in the rendered action menu: its type tag, fully-formatted VRBTM prompt text, and whether it's actually selectable (false for crafter recipes with missing materials or exploration with no inventory space).

5. **`ActionList`** — The full menu split into `main_actions` and `crafter_recipes` sections, with indices assigned only to selectable entries across both sections in one globally sequential space.

6. **`SelectedAction`** — The LLM's typed, parsed choice: an `ActionType` discriminant plus only the optional args relevant to that type (quantity, item, resource, hours, etc.).