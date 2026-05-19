# Villmage v1 — Design Document

## ARCHITECTURE

---

### CHARACTER CANON

Static authored identity for each villager.

**Data owned:**
- Per-villager: name, bio, personality, desires, profession tag

**APIs exposed:**
- Read-only access to all fields (no mutation ever).

**Logic:**
- Pure lookup. No computation.

**Ambiguities:**

- *Gatherer profession is undefined but referenced.* BHVR-38 applies a `4x` penalty to "non-gatherers" exploring for peaches. ATTR-37 lists professions as crafting, woodcutting, hunting, and cooking — gatherer is absent. Maren is titled "the Gatherer" but no formal profession is defined. Does Maren get a `gatherer` profession tag that waives the 4x penalty? Or does everyone take the penalty (making peach gathering uniformly slow)? This is a gating rule in Action System and must be resolved before any exploration logic is written.

**Resolution:** Maren receives a formal `gatherer` profession tag, exempting her from the 4x peach-exploration penalty. ATTR-37 expands to six professions: crafting, woodcutting, hunting, cooking, gathering, building.

- *Harren has no profession.* He is "the Builder" but builder maps to nothing in ATTR-37. Is Harren a generalist with no gated abilities? If so, he's the only one with no profession-specific advantage.

**Resolution:** Harren gets a `builder` profession tag with no mechanical effect. It is a real profession in the system (one of the six in ATTR-37), but has no bonuses or penalties. This is intentional.

---

### VILLAGER STATE

Per-villager mutable survival stats, inventory, and in-progress action tracking.

**Data owned:**
- `wakefulness` (0–100), `satiation` (calories, max 1800), `hydration` (mL, max 6000)
- `social_joy` (0–100), `connectedness` (0–100), `cleanliness` (0–100)
- `inventory`: list of (item, quantity), total weight, over-encumbered flag
- `sleep_spot_claim`: none / bed_roll / cot
- `crafting_in_progress`: (item, minutes_spent) or null
- `current_action`: (type, completion_timestamp)

**APIs exposed:**
- `apply_decay(elapsed_hours)` → list of threshold crossings
- `compute_stats(base_calories, base_firewood, villager_count)` → health, mood, well-being, safety; includes partial-derivative subcomponent selection
- `get_stat_descriptions()` → natural-language prompt strings per VRBTM guidelines
- Mutators: `modify_inventory`, `modify_stat`, `set_crafting_state`, `set_current_action`, `set_sleep_spot`

**Logic:**
- Applies passive decay rates on caller request and reports crossings.
- Computes derived stats (health, mood, well-being, safety) from raw values using spec formulas.
- Identifies which input has highest partial derivative for mood and health, used to select which sub-description to surface.

**Ambiguities:**

- *Starting stats are mostly unspecified.* CONST-176 gives `social_joy = 20`. No starting values are given for wakefulness, satiation, hydration, cleanliness, or connectedness. Also no starting inventory or base resources.

**Resolution:** All stats start at maximum — wakefulness 100, satiation 1800 cal, hydration 6000 mL, connectedness 100, cleanliness 100. social_joy starts at 20 per CONST-176. No starting inventory or base resources.

- *Base cleanliness has no normalization formula.* The mood formula uses `b` (base cleanliness) scaled 0–1. World State tracks raw dirtiness (e.g., +30 per carcass remains), but there is no conversion formula. What is the maximum possible dirtiness, and how does the raw number map to a 0–1 score? Without this, the mood formula cannot be evaluated.

**Resolution:** Dirtiness caps at 100. Cleanliness = `1 - (dirtiness / 100)`, floored at 0.

- *Does sleeping reset the rest buff?* BHVR-112 says "activate the rest buff after resting for one hour." The mood formula uses `r` = "time since last rest in hours," which gives a buff for up to 5 hours post-rest. If sleep does not reset `r`, a villager who sleeps but never uses the explicit "Sit and relax" action will permanently have a degraded mood through this channel. If sleep does reset it, `r` resets whenever the villager wakes up.

**Resolution:** Sleep does NOT reset the rest buff. Only the explicit "Sit and relax" action (BHVR-112) activates it.

---

### WORLD STATE

Shared mutable base: storage, fire, water, carcasses, placed objects, dirtiness.

**Data owned:**
- `base_storage`: item → quantity
- `water_supply`: liters
- `fire`: lit flag, fuel queue (FIFO), derived extinction timestamp
- `cleanliness_contributors`: (source_type → count), total_dirtiness
- `placed_resting_spots`: villager_id → spot_type
- `live_carcasses`: carcass_id → arrival_timestamp

**APIs exposed:**
- Setters: `modify_base_item`, `set_fire_fuel`, `modify_water`, `update_cleanliness_source`, `place_resting_spot`, `add_carcass`, `remove_carcass`
- Getters: `get_base_summary`, `get_total_calories`, `get_total_firewood`, `get_total_dirtiness`

**Logic:**
- All mutations are explicit; all reads are side-effect-free.
- Fuel queue consumed FIFO.
- Carcass rot deadlines tracked by arrival timestamp; Simulation Engine fires the expiry event.

**Ambiguities:**

- *What happens when a carcass rots?* CONST-128 says it rots after 24h if not butchered. STRCT-131 includes "carcass remains" as a dirtiness source. Does a rotted carcass become remains (adding +30 dirtiness per CONST-132) and then disappear? Or does it just vanish silently? Or does it remain as an object?

**Resolution:** Both butchering and rotting produce carcass remains (+30 dirtiness each). Rotting also destroys the meat. Remains persist until cleaned.

---

### SIMULATION ENGINE

Discrete-event scheduler. Top-level entry point.

**Data owned:**
- `event_heap`: min-heap of future events by game timestamp
- `autobalance_multipliers`: yield scaling, satiation scaling, hydration scaling

**APIs exposed:**
- None (top-level, calls everything else).

**Logic:**
- Pops next event, advances game clock, applies stat decay to all villagers for elapsed duration, dispatches handler.
- Threshold crossings from decay: wakefulness 0 → force sleep; health 0 → death.
- Midnight: runs autobalancing — reads aggregate stats, computes deviation from targets, adjusts multipliers.
- Fire extinction mid-sleep: calls `adjust_active_sleep` on Action System for each sleeping villager, splitting remaining sleep into a new segment under the updated modifier.

**Ambiguities:**

- *Forced sleep has no defined duration.* BHVR-192 says wakefulness = 0 forces the villager to sleep. BHVR-152 says a villager chooses 4–12 hours when sleeping voluntarily. Forced sleep has no duration rule. Does the villager sleep until wakefulness hits some cap? Until a fixed default (e.g., 8 hours)? Until the player-equivalent of an AI decision?

**Resolution:** Forced sleep is always 4 hours.

- *Safety recalculation timing.* BHVR-201 says "Recalculate safety each day." Is this at midnight, or when the simulation first starts each calendar day? This affects whether eating your last food immediately tanks your safety score or only does so at the next recalculation.

**Resolution:** Per-villager, recalculated when they wake up — not on a global clock.

- *Autobalance multiplier bounds.* BHVR-221 compounds adjustments daily. No bound is specified. With sustained deviation in one direction, multipliers could diverge significantly over many days.

**Resolution:** Unbounded. The feedback loop self-regulates.

---

### ACTION SYSTEM

Action catalog: eligibility, cost, effect.

**Data owned:**
- None persistent. Reads autobalance multipliers from Simulation Engine at call time.

**APIs exposed:**
- `get_valid_actions(villager_id)` → list of eligible actions with formatted descriptions
- `start_action(villager_id, action)` → applies start effects, schedules completion
- `complete_action(villager_id, action)` → applies completion effects
- `adjust_active_sleep(villager_id, new_modifier)` → splits sleep on fire-state change

**Logic:**
- Eligibility: checks inventory, profession, encumbrance, fire state, location, and carry space.
- Time: raw time modified by profession factor and health work-speed modifier.
- Exploration yield: Erlang(k=5), truncated when inventory full.
- Fuel preference for fire-tending: inventory before base.
- Crafter recipes shown even when ineligible, with "Cannot perform" label.

**Ambiguities:**

- *What does "at base" mean for action eligibility?* BHVR-79 says eating/drinking requires being "at base." BHVR-43 limits conversations to villagers "at base." Exploration and hauling take villagers away. Is "at base" simply defined as "not currently on an away action (exploration, hauling)"? This needs a precise definition.

**Resolution:** "At base" means not on an away action (exploration or hauling). For actions requiring active participation (e.g., conversation), also requires being awake.

- *Fire goes out during cooking.* CONST-147 requires a lit fire for cooking. If the fire extinguishes while a villager is mid-cook, the cooking action is now running without a valid precondition. Should it cancel? Complete as-is? Pause until relit?

**Resolution:** Cooking pauses gracefully. Villager receives feedback "The fire went out; you cannot continue cooking." Once relit, the action menu shows "Finish cooking" instead of "Cook."

- *Crafting resources drawn from base vs. inventory.* VRBTM-123 shows misc actions using "inventory and base." Crafting materials (e.g., processed hide for satchel) aren't explicitly called out the same way. Does crafting draw from base, or only from inventory?

**Resolution:** Crafting draws from inventory first, then base storage for the remainder.

---

### CONVERSATION SYSTEM

Multi-villager conversation and trade protocol.

**Data owned:**
- `active_session`: participants, turn log, per-participant seen log, elapsed game time
- `active_trade`: participants, current offers, turn count

**APIs exposed:**
- `run_conversation(initiator_id, target_id)` → blocks synchronously, returns elapsed game time

**Logic:**
- Turn loop: all participants prompted in parallel; winning action selected by priority (leave > significant > trade > interrupt > continue > respond > topic change > casual > silent), recency tiebreak. One action resolves per turn; others discarded (except concurrent leaves). 5 minutes per turn; ends at 60 minutes or one participant left. **Exception: turn 1 queries only the initiating villmager (BHVR-52).**
- After turn 2: non-participants at base get a join prompt with the opening excerpt.
- Trade sub-protocol: alternates between two participants; zero game time per trade turn; accepts when one party accepts and the other's last action was an offer; cancels after 6 turns without mutual acceptance.
- Post-conversation: each participant gives a 0–10 social score and per-other impression. Social joy update (`val − 5`, clipped 0–100) written to Villager State; impressions and relationship description updates written to Memory System. A flat **+20 connectedness** boost is also applied to all participants (BHVR-73).

**Ambiguities:**

- *Join prompt timing.* When the join prompt fires (after turn 2), does the conversation pause while non-participants decide, or does it proceed immediately and newcomers enter from the next available turn? This affects how many turns the original participants take before potential joiners arrive.

**Resolution:** Conversation pauses while non-participants decide whether to join.

- *Trade acceptance rule.* BHVR-63: "Accept a trade only when one party accepts and the other party was the last to make an offer." This was flagged as a potential ambiguity but is not one — the rule is clear. One party offers, the other accepts, trade completes. Accepting in response to a non-offer action does not trigger the trade.

---

### MEMORY SYSTEM

Per-villager event logs, thoughts, relationships, and tiered memory compaction.

**Data owned:**
- `event_log`: per-villager append-only timestamped events (persisted to disk)
- `active_context_log`: per-villager in-context window (cleared on compaction, disk copy preserved)
- `thoughts`: per-villager short snippets captured at action selection
- `short_term_memories`: per-villager ≤128-token summaries
- `medium_term_memories`: per-villager ≤256-token summaries
- `relationships`: per ordered pair (x, y) — description (≤128 tokens) + queue of 3 impressions (≤32 tokens each)

**APIs exposed:**
- `append_event(villager_id, event)`
- `append_thought(villager_id, thought)`
- `trigger_compaction(villager_id, reason)` → LLM call, clears context log
- `trigger_midnight_compaction()` → LLM calls for all villagers
- `write_impressions(speaker_id, subject_id, impression, desc_update?)`
- `get_memory_context(villager_id)` → assembled memories + relationships + context log for prompt

**Logic:**
- Short-term compaction: triggered by sleep or completing an action after ≥4 hours awake since last compaction. Submits context log to LLM, stores ≤128-token summary, clears context log.
- Medium-term compaction: midnight. Submits all previous-day short-term memories to LLM, stores ≤256-token summary.
- Long-term compaction: beyond day 3, compacts all medium-term memories.
- Total memory budget per villager: ≤2k tokens.

**Ambiguities:**

- *Long-term compaction trigger.* BHVR-259 says "beyond three days, compact all medium-term memories into long-term memories." Does this fire once at midnight of day 3, compacting everything accumulated, and then again at each subsequent midnight? Or is it a one-time operation? The spec says "compact all medium-term memories" which implies it runs on a schedule.

**Resolution:** Fires every third day (day 3, 6, 9, etc.), compacting all medium-term memories accumulated since the last long-term compaction.

---

### AI COORDINATOR

Prompt assembly, LLM invocation, response parsing.

**Data owned:**
- None. Stateless.

**APIs exposed:**
- `select_action(villager_id)` → validated action + args + thought
- `get_conversation_turn(villager_id, session)` → conversation action + speech
- `get_join_decision(villager_id, excerpt)` → yes/no
- `get_social_score(villager_id)` → 0–10
- `get_relationship_update(speaker_id, subject_id, session)` → impression + optional desc update
- `get_memory_compaction(villager_id, log)` → compacted summary string

**Logic:**
- Assembles prompts in spec-defined field order (most-static to least-static) for cache optimization.
- Parses JSON responses; retries on malformed output.
- Returns validated data structures, never raw JSON.

**Ambiguities:**

- *Which model?* CONST-261 references "gemini flash 2.5" with a 2k token budget as the only model mentioned. This is the only place in the spec where a model is named. Is Gemini Flash 2.5 the chosen model for all calls, including the action-selection prompt? Confirm before writing API client code.

**Resolution:** Gemini Flash 2.5 for all LLM calls in the system.

- *Retry limit.* The subsystems doc says "retries on malformed output" but no max retry count is specified. Infinite retries would hang the simulation.

**Resolution:** One retry on malformed output, then crash hard. Every failure logs the full prompt, raw response, and exact parsing error to a file.

---

### LLM CLIENT

Thin API wrapper.

**Data owned:**
- None. Model, temperature, and token limits fixed at construction.

**APIs exposed:**
- `complete(prompt_segments, cache_breakpoint_indices)` → raw completion string

**Logic:**
- Applies cache-control headers at specified positions.
- Retries transient API errors with exponential backoff.

**Ambiguities:** None beyond the model question noted in AI Coordinator.

---

### OBSERVABILITY

Replay surface and persistence.

**Data owned:**
- `event_log`: ordered events and state deltas on disk
- `checkpoints`: full state snapshots every 3 in-game hours

**APIs exposed:**
- None at runtime. Reads persisted files offline.

**Logic:**
- Reconstructs simulation state by replaying deltas forward from nearest preceding checkpoint.
- Supports perspective-specific reconstruction (each villager's view of events).
- Renders HTML/CSS/JS viewer with per-character log navigation, highlighted deltas, and timestamp display.

**Ambiguities:**

- *Checkpoint restart format.* REQ-272 says "support restarting the simulation from any checkpoint." For this to work, checkpoints must be machine-readable by the Simulation Engine (not just human-readable for the viewer). The subsystems doc treats Observability as read-only offline with no runtime coupling. If restart is a hard requirement, either Simulation Engine reads checkpoint files directly, or there's a deserialization path that isn't yet designed.

**Resolution:** In scope for v1. Checkpoints must be fully machine-readable by the Simulation Engine — complete serialized simulation state.

- *Perspective-specific visibility definition.* BHVR-11 allows viewing each character's perspective. What exactly can each character observe? Presumably: their own actions and stats, any events at base while they are at base, any conversation they participated in, and explicitly nothing from when they were away. This needs a precise filter definition before the event log schema can be locked in.

**Resolution:** A villager sees their own actions always, conversations they participated in, and all base events while they were both present and awake. Sleeping at base or being away = invisible.

---

## CROSS-CUTTING CONCERNS

These don't belong to a single subsystem but affect multiple.

**Safety score formula has a dimensional error.** CONST-202 writes the food safety score as:

```
((calories in inventory) * (2200 cal/day) + (1/villagers) * (calories in base) * (2200 cal/day)) / 5
```

Multiplying calories by calories/day gives cal²/day, not a dimensionless score. The intent is clearly to divide by 2200 to convert calories → days of food, then normalize over 5 days. The formula should read:

```
((calories_in_inventory / 2200) + (1/villagers) * (calories_in_base / 2200)) / 5
```

Confirm the intent before implementing.

**Resolution:** Confirmed corrected — divide by 2200, not multiply. The formula to implement is `((calories_in_inventory / 2200) + (1/villagers) * (calories_in_base / 2200)) / 5`.

**Firewood safety has no "night" definition.** CONST-204 says firewood safety measures "firewood needed only for the night." The spec never defines what "night" is — no day/night cycle or fire schedule is specified. Sleep modifiers reference fire state but not time-of-day. Unless "night" is defined, firewood safety cannot be computed.

**Resolution:** Convert base firewood to total burn minutes, assume one night = 8 hours (480 minutes). Firewood safety = `(total_burn_minutes / 480) / 5`. No per-villager split since fire is shared.

---

## DECISIONS

### [Already Decided] Discrete-Event Simulation

The Simulation Engine uses a min-heap event queue. Game time advances by popping the next scheduled event, computing elapsed wall-time, decaying all villager stats for that interval, then dispatching the handler. No fixed tick rate.

Criterion: (1) Sticky — switching to a fixed-tick model restructures Simulation Engine and Action System completely.

This is correct for the problem: most events are hours apart. A 1-minute tick would run ~10,000 iterations per game day.

---

### [Already Decided] Conversations Block the Simulation

`run_conversation` is synchronous and runs to completion before any other event fires. During a 60-minute conversation (up to 12 turns × 6 participants), the rest of the simulation is frozen.

Criterion: (1) Sticky, (4) Risky.

This is the correct reading of the spec ("synchronous, blocks until done"). The cost is non-obvious: a full 60-minute conversation with 6 participants could require up to 72 sequential-or-parallel LLM calls before time advances. Flag if this becomes a latency concern in practice.

---

### [Decided] Python Concurrency Model for LLM Fan-Outs

Trio with structured concurrency. Nurseries for LLM fan-outs. No asyncio, no threads. Trio's nurseries enforce that all child tasks complete or error before the parent scope exits, preventing orphaned LLM calls. This affects LLM Client, AI Coordinator, Conversation System, and Memory System call sites.

Criterion: (2) Large blast radius, (5) Most technically complex.

---

### [Decided] Game Time Representation

Plain `int` — elapsed minutes from game start (epoch = 0, "Day 1, 6:00 AM" = 360). Midnight detection is `t % 1440 == 0`. The spec uses integer minutes and hours throughout; a plain int avoids datetime parsing, DST hazards, and float drift. Conversion utilities for human-readable formatting in logs.

Criterion: (1) Sticky, (2) Large blast radius.

---

### [Decided] Persistence Format

JSON Lines (`.jsonl`) for the append-only event log. Individual `.json` files for checkpoint snapshots, named by in-game timestamp. Human-readable format is essential for debugging emergent behavior. JSONlines requires no schema management and is trivially appendable. Checkpoint files being separate from the event log keeps restart logic simple: load the `.json` snapshot, then replay `.jsonl` entries after its timestamp. SQLite can be added later if replay performance becomes an issue.

Criterion: (1) Sticky — the format is baked into Observability reconstruction logic and Simulation Engine restart.

---

### [Decided] LLM Model and Caching Mechanism

Gemini Flash 2.5 for all call types (action selection, conversation turns, memory compaction, relationship updates). Implicit prefix caching only — order prompt segments static-to-dynamic per REQ-224, and rely on the model's automatic prefix-based caching. No explicit Cache API or cache object management. This keeps LLM Client simple (no cache lifecycle) while still benefiting from prefix reuse across calls for the same villager within a session.

Criterion: (3) Requires technical prototyping, (4) Risky, (6) Directly affects prompt design (creative vision).

---

### [Decided] Event Heap Invalidation Strategy

Direct removal from heap on cancel/pause. No lazy invalidation. When a villager's task is paused (e.g., pulled into a conversation), the scheduled completion event is removed directly from the heap and a new event for the remainder is scheduled after the interruption ends. This avoids the complexity of generation counters and stale-event checks at the cost of O(n) removal, which is acceptable given the small event count (handful of villagers).

Criterion: (4) Risky — getting this wrong causes silent task-resume bugs that only surface in specific conversation timing scenarios.
