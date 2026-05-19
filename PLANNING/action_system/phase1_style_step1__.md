Six style flags appended:

1. **`apply_start_effect` / `apply_completion_effect` complexity** — dispatching over 25 action types in a single function will produce enormous, unmaintainable bodies. Needs per-type handler functions with a thin dispatcher on top.

2. **`SelectedAction` untagged union** — 10 optional fields where validity depends on `action_type` with no type enforcement. A proper sum type (one dataclass per action variant) eliminates the footgun.

3. **`ValidAction.idx` optional invariant** — the "present only when selectable" rule is comment-only. Two subtypes or a required field on the selectable variant would make it structural.

4. **`adjust_active_sleep` primitive soup** — four bare numeric arguments in similar units; a small `ActiveSleepSegment` struct would name them at call sites and prevent ordering mistakes.

5. **Growing `(vs, ws, multipliers, canon, all_states)` context cluster** — already at five arguments on some functions; a `SimContext` value object would stabilize signatures as the system grows.

6. **`ValidAction.prompt_text` conflates data with presentation** — pre-baking the formatted string at eligibility time prevents AI Coordinator from reformatting or inspecting constraints; separating semantic fields from the rendered string would be cleaner.