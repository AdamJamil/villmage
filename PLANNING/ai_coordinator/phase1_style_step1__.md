Six style notes appended:

1. **Repeated assemble→invoke→parse→retry pattern** — needs a private `_call` helper; currently duplicated across all 6 public methods.
2. **`game_time: int` bare primitive** — a `GameTime` newtype prevents silent parameter-order bugs.
3. **`villager_id`/`speaker_id`/`subject_id` all `str`** — a `VillagerId` newtype catches transpositions of the ordered `(speaker, subject)` pair.
4. **Unnamed `tuple` return from `assemble_*`** — a `PromptPackage` dataclass eliminates positional guessing at call sites.
5. **Caller-side pre-filtering footgun** — both visibility-filtering and the 2-entry slice for join decisions are silent preconditions; a typed `JoinDecisionSnapshot` wrapper enforces them structurally.
6. **Flat primitives in `assemble_relationship_update`** — `existing_description` + `recent_impressions` should be one `RelationshipRecord` object to prevent passing mismatched data from different villager pairs.