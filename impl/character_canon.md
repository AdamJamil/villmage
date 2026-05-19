# Character Canon — Implementation Details

## Overview

Character Canon is a static, immutable data store. It is authored once at startup and never mutated during simulation. It is a leaf subsystem: no runtime dependencies, no calls to other subsystems.

Two subsystems read from it:
- **Action System** — reads `profession` to gate crafting recipes and cooking actions, and to determine whether the 4× peach-exploration time penalty applies.
- **AI Coordinator** — reads `backstory`, `bio`, `personality`, `desires`, and `profession` for prompt assembly.

---

## Core Objects

### Profession

An enum covering exactly six values per ATTR-37 / design.md resolutions. `BUILDER` has no mechanical effect. `GATHERER` exists as a formal tag waiving the 4× peach-exploration time penalty for Maren; all villagers can explore for peaches, but non-gatherers take four times as long.

```thrift
enum Profession {
    CRAFTER    = 1,
    WOODCUTTER = 2,
    HUNTER     = 3,
    COOK       = 4,
    GATHERER   = 5,
    BUILDER    = 6,
}
```

---

### VillagerId

A `NewType` wrapping `str`, defined in `types.py`. Used as the stable foreign key for a villager across all subsystems. Pyre enforces that callers cannot accidentally pass an item name or other arbitrary string where a villager id is expected.

```python
VillagerId = NewType('VillagerId', str)
```

---

### VillagerCanon

The complete static identity record for one villager. All fields are set at authoring time and are read-only thereafter.

```thrift
struct VillagerCanon {
    1: VillagerId id,    // stable lowercase key, e.g. "aldric" — used as foreign key everywhere
    2: string name,      // display name, e.g. "Aldric the Woodsman"
    3: string bio,       // one short paragraph, injected into other-character sections of prompts
    4: string personality, // one short paragraph, injected into the villager's own character prompt
    5: string desires,   // one short paragraph, injected into the villager's own character prompt
    6: Profession profession,
}
```

**Notes:**
- `id` is the stable key used as a foreign key in Villager State, Memory System, World State, etc. It must never change after authoring.
- `bio` is the only field exposed to *other* villagers' prompts (per VRBTM-229: `"<character name>'s info: <character bio only>"`). `personality` and `desires` are exposed only to the villager's own prompt (VRBTM-227).
- All six villagers are hardcoded: Aldric, Sewalt, Harren, Maren, Ivette, Thessia.

---

### WorldBackstory

A single global record holding the shared world context. Injected once per prompt via VRBTM-226.

```thrift
struct WorldBackstory {
    1: string text,   // the full backstory prose block (VRBTM-2)
}
```

---

### CharacterCanon

The top-level container returned by the subsystem. Callers hold a reference to this and read from it; nothing mutates it after construction.

```thrift
struct CharacterCanon {
    1: WorldBackstory backstory,
    2: list<VillagerCanon> villagers,   // exactly 6 entries, order is authoring order
}
```

---

## API Surface

All access is read-only. No setters exist.

- `get_villager(id: VillagerId) -> VillagerCanon` — O(1) lookup by stable id.
- `get_all_villagers() -> tuple[VillagerCanon, ...]` — returns all six in authoring order.
- `get_backstory() -> WorldBackstory` — returns the global backstory.

The internal implementation is a dict keyed by `VillagerId` built at construction time. The six `VillagerCanon` records are defined as a module-level `_VILLAGERS: tuple[VillagerCanon, ...]` constant so the authored data is readable without constructing the class.

---

## Data Values

The six villagers and their professions, exactly as authored in VRBTM-3 through VRBTM-8:

| id       | name                  | profession  |
|----------|-----------------------|-------------|
| aldric   | Aldric the Woodsman   | WOODCUTTER  |
| sewalt   | Sewalt the Hunter     | HUNTER      |
| harren   | Harren the Builder    | BUILDER     |
| maren    | Maren the Gatherer    | GATHERER    |
| ivette   | Ivette the Crafter    | CRAFTER     |
| thessia  | Thessia the Cook      | COOK        |

---

## What This Subsystem Does NOT Own

- Villager runtime stats (Villager State)
- Relationship descriptions and impressions (Memory System)
- Any derived or computed values — pure authored text only

---

## File Hierarchy

```
character_canon/
    types.py   — Immutable data types: VillagerId NewType, the Profession enum, and the
                 two record structs (VillagerCanon, WorldBackstory). No logic, no
                 dependencies. Import these types anywhere a type annotation is needed
                 without pulling in the populated data store.

    canon.py   — The CharacterCanon class: the subsystem's only API surface. Contains
                 the hardcoded authored data for all six villagers and the world
                 backstory as a module-level _VILLAGERS constant, constructs the lookup
                 dict at startup, and exposes the three read-only accessors called by
                 Action System and AI Coordinator.
```

**No `__init__.py` re-export layer.** Callers import directly from `character_canon.types` or `character_canon.canon`. There is no runtime logic at package level.

**Dependency direction:** `canon.py` imports from `types.py`. `types.py` imports nothing from within the package. No cycles.

---

## Object Assignments

### `character_canon/types.py`

#### `VillagerId`
A `NewType` wrapping `str`. Used as the stable foreign key for a villager across all subsystems. Prevents callers from accidentally passing an item name or other arbitrary string where a villager id is expected.

#### `Profession`
Six-value enum covering every profession tag in the system. Action System uses these tags to gate crafting recipes and cooking actions, and to apply the 4× peach-exploration time penalty to non-gatherers. `BUILDER` has no mechanical effect. `GATHERER` waives the timing penalty; it does not gate access (any villager can explore for peaches).

#### `VillagerCanon`
Frozen dataclass holding the complete static identity of one villager: stable `id` key, display `name`, `bio` (exposed to other villagers' prompts), `personality` and `desires` (exposed only to the villager's own prompt), and `profession` tag. All fields are set at authoring time; nothing in the simulation mutates them.

#### `WorldBackstory`
Single-field frozen dataclass holding the shared world-context prose. Injected once into every villager prompt (VRBTM-226). Exists as its own type rather than a bare string so callers have a typed handle and the prompt assembly code is unambiguous about what it is receiving.

---

### `character_canon/canon.py`

#### `_VILLAGERS`
Module-level `tuple[VillagerCanon, ...]` constant holding all six hardcoded villager records in authoring order. Defined at module level so the authored data is independently readable without constructing `CharacterCanon`.

#### `CharacterCanon`
The subsystem's sole API surface. Built once at module load from `_VILLAGERS` and the world backstory. Internally maintains a `dict[VillagerId, VillagerCanon]` for O(1) lookups. Callers receive a single shared instance and call its read-only accessors; nothing modifies the instance after construction.

---

## Core Functions

### `character_canon/types.py`

`types.py` contains only the `VillagerId` NewType, enum, and frozen dataclass definitions. No logic functions belong here — all computation lives in `canon.py`.

---

### `character_canon/canon.py`

#### `CharacterCanon`

```python
def __init__(self) -> None:
    """Build the id-keyed lookup dict from _VILLAGERS and the world backstory."""

def get_villager(self, villager_id: VillagerId) -> VillagerCanon:
    """Return the canon record for villager_id. Raises KeyError for unknown ids."""

def get_all_villagers(self) -> tuple[VillagerCanon, ...]:
    """Return all six villager records in authoring order."""

def get_backstory(self) -> WorldBackstory:
    """Return the shared world backstory."""
```
