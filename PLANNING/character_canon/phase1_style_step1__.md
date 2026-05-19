Four style notes added to `impl/character_canon.md`:

1. **`villager_id: str` primitive** — bare string used as a foreign key across all four methods; a `NewType('VillagerId', str)` would catch cross-type confusion at pyre-check time.

2. **`get_profession` redundancy** — it's just `get_villager(id).profession`; two paths to the same datum cause inconsistent call-site patterns and should be collapsed.

3. **`get_all_villagers()` returns mutable `list`** — inconsistent with the immutable store; should be `tuple[VillagerCanon, ...]`.

4. **Hardcoded data in `__init__`** — six `VillagerCanon` instantiations in the constructor body make it a large data blob; a module-level constant separates data from initialization logic.