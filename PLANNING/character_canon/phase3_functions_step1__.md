Done. I appended a "Core Functions" section to `character_canon.md` with:

- **`types.py`** — explicitly noted as having no logic functions (pure data types only).
- **`canon.py` / `CharacterCanon`** — five functions:
  - `__init__`: builds the internal lookup dict from hardcoded data
  - `get_villager`: O(1) id lookup, KeyError on unknown id
  - `get_all_villagers`: returns all six in authoring order
  - `get_backstory`: returns the world backstory
  - `get_profession`: convenience shorthand used by Action System for eligibility gating