Written to `diffs/character_canon_plan.md`. Two diffs:

1. **`types.py`** — the four pure type definitions (NewType, enum, two frozen dataclasses), tested for enum value exactness and frozen immutability.
2. **`canon.py`** — the authored data (`_VILLAGERS`, `_BACKSTORY`) and `CharacterCanon` API, tested with 8 cases covering completeness, uniqueness, the full id/name/profession table (the mechanically critical one — wrong profession → wrong Action System behavior), non-empty prose fields, lookup correctness, KeyError contract, ordering, and backstory identity.

The table test in diff 2 is the one that matters most: it's the only thing standing between a typo in `maren`'s profession and the 4× peach penalty silently applying to everyone.