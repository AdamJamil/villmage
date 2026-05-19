# character_canon — Diff Plan

Two diffs. The subsystem has no logic to speak of — just type definitions, authored data, and three trivial accessors — so the only meaningful split is between the type layer and the data+API layer.

---

## DIFF 1 of 2

**TITLE:** `[character_canon][1/2]` Type definitions

**DESCRIPTION:**
Create `character_canon/types.py`. No `__init__.py` (per impl spec: callers import directly from `character_canon.types` or `character_canon.canon`).

The file contains:
- `VillagerId` — `NewType('VillagerId', str)`. The stable foreign key used across all subsystems. Pyre enforces that an arbitrary `str` cannot be passed where a `VillagerId` is expected.
- `Profession` — six-value `enum.Enum` with integer assignments exactly per ATTR-37 / design.md resolution: `CRAFTER=1, WOODCUTTER=2, HUNTER=3, COOK=4, GATHERER=5, BUILDER=6`.
- `VillagerCanon` — frozen `dataclass` with fields `id: VillagerId`, `name: str`, `bio: str`, `personality: str`, `desires: str`, `profession: Profession`. Frozen because canon is authored once and never mutated.
- `WorldBackstory` — frozen `dataclass` with field `text: str`. A typed wrapper rather than a bare `str` so prompt assembly code has an unambiguous handle.

No logic belongs here. `canon.py` imports from this file; nothing in this file imports from within the package.

**TEST PLAN:**

*`tests/character_canon/test_types.py`*

1. **Profession enum completeness and values.** Assert `len(Profession) == 6` and verify each member's integer value exactly: `CRAFTER=1, WOODCUTTER=2, HUNTER=3, COOK=4, GATHERER=5, BUILDER=6`. This is the tightest possible check against spec drift — a future addition or renumbering will break this test loudly.

2. **`VillagerCanon` is frozen.** Construct a `VillagerCanon` with valid field values and attempt `instance.name = "other"`. Assert `FrozenInstanceError` is raised. This proves the immutability guarantee that the entire subsystem relies on.

3. **`WorldBackstory` is frozen.** Same pattern — construct and attempt mutation, assert `FrozenInstanceError`.

These three tests cover the only behavioral properties of `types.py`. Type annotation correctness is enforced by Pyre at the static level, not by runtime tests.

---

## DIFF 2 of 2

**TITLE:** `[character_canon][2/2]` Canon data and API

**DESCRIPTION:**
Create `character_canon/canon.py`.

The file contains:
- `_VILLAGERS: tuple[VillagerCanon, ...]` — module-level constant holding all six hardcoded villager records in authoring order (Aldric, Sewalt, Harren, Maren, Ivette, Thessia), with full `bio`, `personality`, `desires`, and `profession` populated from VRBTM-3 through VRBTM-8.
- `_BACKSTORY: WorldBackstory` — module-level constant holding the world backstory prose from VRBTM-2.
- `CharacterCanon` — the subsystem's sole API surface. `__init__` builds a `dict[VillagerId, VillagerCanon]` from `_VILLAGERS` for O(1) lookup. Exposes three read-only methods: `get_villager`, `get_all_villagers`, `get_backstory`.

`get_villager` raises `KeyError` for unknown ids (no sentinel/None return — callers should never query an id they don't know is valid).

**TEST PLAN:**

*`tests/character_canon/test_canon.py`*

1. **`_VILLAGERS` has exactly 6 entries.** Assert `len(_VILLAGERS) == 6`. Catches accidental additions or deletions.

2. **Villager ids are unique.** Assert `len({v.id for v in _VILLAGERS}) == 6`. A duplicate id would silently corrupt the lookup dict.

3. **Each villager's id, name, and profession match the spec table.** Assert a complete expected mapping:
   ```
   "aldric"  → "Aldric the Woodsman",  WOODCUTTER
   "sewalt"  → "Sewalt the Hunter",    HUNTER
   "harren"  → "Harren the Builder",   BUILDER
   "maren"   → "Maren the Gatherer",   GATHERER
   "ivette"  → "Ivette the Crafter",   CRAFTER
   "thessia" → "Thessia the Cook",     COOK
   ```
   This is the most load-bearing test: profession tags gate Action System behavior (GATHERER waives the 4× peach penalty; CRAFTER and COOK gate their respective action categories). A wrong profession on any villager would cause silent behavioral errors downstream.

4. **Each villager's bio, personality, and desires are non-empty.** Assert all three fields are non-empty strings for every record. Prevents accidentally blank authored fields from silently producing empty prompt sections.

5. **`get_villager` returns the correct record for each valid id.** Iterate all six ids, call `get_villager`, assert the returned record is the expected `VillagerCanon` instance (identity or equality). Confirms the lookup dict was built correctly from `_VILLAGERS`.

6. **`get_villager` raises `KeyError` for an unknown id.** Call `get_villager(VillagerId("nobody"))` and assert `KeyError`. This is the documented error contract; callers must not receive a silent None.

7. **`get_all_villagers` returns all six in authoring order.** Assert the returned tuple equals `_VILLAGERS` element-by-element. Order is a stated guarantee (the impl spec says "authoring order") and downstream prompt assembly may depend on it.

8. **`get_backstory` returns a `WorldBackstory` with substantive text.** Assert the returned object is a `WorldBackstory` and its `text` field contains `"Grey Rot"` (the named plague from VRBTM-2). This verifies the right backstory was loaded without hard-coding the full multi-paragraph prose into the test.
