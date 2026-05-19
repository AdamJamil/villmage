Eight style issues appended to `impl/observability.md`:

1. **`get_valid_actions` cyclomatic complexity** — ~15 action types × per-action eligibility/quantity/format logic; needs decomposition into per-action predicate+formatter pairs from the start.

2. **Simulation Engine dispatch God function** — fire extinction, carcass rot, forced sleep, death, midnight, checkpoint, action completions all landing in one dispatcher body.

3. **`run_conversation` mixed concerns** — turn loop, bystander join, trade sub-protocol, and post-conversation scoring should be separate functions.

4. **`compute_stats` positional primitive args** — `(base_calories, base_firewood, villager_count)` transposition is silently wrong; needs a typed `WorldContext` dataclass.

5. **`apply_decay` untyped crossing list** — callers must interpret crossing semantics manually; a typed enum/dataclass per crossing kind would enforce correct handling.

6. **AI Coordinator prompt prefix duplication** — the static prefix is shared across 7 prompt types with no builder abstraction to keep them in sync.

7. **Autobalance multipliers as implicit Simulation Engine state** — Action System reads them as hidden globals; should be explicit arguments.

8. **Last-compaction timestamp ownership gap** — the 4-hour trigger condition requires state nobody is explicitly assigned to own.