The functions section has been appended to `impl/ai_coordinator.md`. Here's a summary of the key decisions:

**`types.py`** — Added `ParseContext` dataclass (villager_id, call_type, game_time, prompt). This is the only addition; all other types are pure data.

**`prompts.py`** — Six assembly functions, one per call type. All return `tuple[list[PromptSegment], list[int]]`. Key notes:
- `assemble_action_selection` gets `game_time` for the required timestamp (STRCT-241); `memory_context.relationships` paired with `other_canons` bios covers segment 4
- `assemble_join_decision` documents the contract that the caller pre-slices `snapshot.history` to 2 entries (the doc says so, but now it's on the function signature's docstring)

**`parser.py`** — Six parse functions, each taking a `ParseContext` so the parser itself can write the failure log (per the spec: "parser.py writes ParseFailureLog"). `parse_action_selection` takes `ActionList` to validate index range and selectability. `parse_trade_turn` takes `inventory_items` to enforce INVR-60.

**`coordinator.py` — `AICoordinator`** — `__init__` plus six public methods. All take `game_time: int` (needed to populate `ParseContext` for failure records). The retry-and-crash contract is described in the class-level docstring rather than repeated on each method.