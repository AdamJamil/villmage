Written to `impl/character_canon.md`. Here's a summary of the decisions made:

**Core structs:**
- `Profession` — enum of 6 values (CRAFTER, WOODCUTTER, HUNTER, COOK, GATHERER, BUILDER). Gatherer is formal per the design.md resolution; Builder has no mechanical effect.
- `VillagerCanon` — the per-villager static record with `id` (stable FK used everywhere), `name`, `bio`, `personality`, `desires`, and `profession`. Key distinction: `bio` goes into *other* villagers' prompts; `personality`/`desires` go only into the villager's own prompt.
- `WorldBackstory` — thin wrapper around the prose text block.
- `CharacterCanon` — top-level container, holds backstory + list of 6 villagers.

**Key design choices:**
- `id` is a lowercase stable string key (e.g. `"aldric"`) that every other subsystem uses as a foreign key — this is the linchpin since nothing should embed VillagerCanon by value.
- No setters exist anywhere; construction is the only mutation point.
- The hardcoded profession-to-villager table is explicit in the doc so both implementers match exactly.