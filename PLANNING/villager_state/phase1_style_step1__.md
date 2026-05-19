Five style issues added to `impl/villager_state.md`:

1. **`get_stat_descriptions` tier explosion** — 12 stats × up to 6 tiers each will become an enormous if/elif chain; should be a data table with a shared lookup helper.

2. **`compute_stats` does too much** — four formulas plus two rounds of partial-derivative perturbation all in one function; the PD logic should be a private helper.

3. **Five loose primitives to `compute_stats`** — `base_calories`, `base_fuel_minutes`, `villager_count`, `total_dirtiness`, `current_game_time` are transposable and unself-documenting; a `WorldContext` dataclass would fix this.

4. **`apply_decay` ordering footgun** — returns an unordered list where the caller must know to handle `HEALTH_ZERO` before `WAKEFULNESS_ZERO`; nothing in the type enforces this.

5. **`modify_stat` is stringly-typed dispatch** — the `Literal` alias doesn't prevent a branch-per-stat `if/elif` chain in the body, and Pyre can't verify exhaustiveness; individual mutators or an enum key would be safer.