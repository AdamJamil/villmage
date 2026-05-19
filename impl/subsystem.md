# Villmage v1 — Subsystem Architecture

## Design Decisions

Nine subsystems plus a thin LLM Client leaf. Key calls:

- **Autobalancing is not a subsystem.** It's a daily scheduled event inside Simulation Engine that reads aggregate stats and writes multipliers. The interaction surface is two reads and one write — not enough to justify a boundary.
- **Character Canon is separate from Villager State.** Canon is static authored identity; Villager State is mutable per-character simulation data. They change for different reasons and are read by different callers.
- **Relationships live with Memory, not Villager State.** Relationship descriptions and impressions are cognitive artifacts updated from social outcomes. Keeping them with memories avoids Villager State doing double duty as both survival ledger and social record.
- **LLM Client exists to break a cycle.** Memory System needs the LLM for compaction; AI Coordinator needs memories for prompts. Without a shared leaf, one would depend on the other.
- **Prompt assembly lives inside AI Coordinator.** It's the coordinator's core job. Factoring it into its own subsystem adds a boundary without adding clarity — no other subsystem constructs prompts.

---

## Character Canon

> Static authored identity for each villager.

### Owns (mutable state)
- None. All data is immutable after authoring.

### Reads
- Nothing.

### Key rules
- Backstory, personality, desires, profession tags, and bios are authored once and never modified by simulation.
- Six professions: crafting, woodcutting, hunting, cooking, gathering, building. Builder has no mechanical effect — it gates nothing in Action System.
- Profession tags gate which exploration types, crafting recipes, and cooking actions are conceptually available. Canon says "can conceptually do X" — Action System decides if X is currently legal.

---

## Villager State

> Per-villager mutable survival stats, inventory, and action tracking.

### Owns (mutable state)
- wakefulness (0–100), satiation (calories), hydration (mL, max 6000), social_joy (0–100), connectedness (0–100), cleanliness (0–100)
- inventory: list of (item, quantity) with total weight; over-encumbered flag derived from weight vs carry capacity
- sleep_spot_claim: none / bedroll / cot
- crafting_in_progress: (item, minutes_spent) or null
- current_action: (action_type, completion_timestamp) — written at action start so other villagers' prompts can display it

### Reads
- World State: base calorie count, base firewood count, living villager count — passed in by caller for safety computation

### Called by
- Simulation Engine — to apply time-based decay and detect threshold crossings
- Action System — to check eligibility and apply stat/inventory mutations
- Conversation System — to update social_joy and apply trade transfers

### Calls
- Nothing. Passive data store with derived computations.

### Key rules
- Time-based decay rates: wakefulness −3/hr, cleanliness −2/hr, connectedness −100/48hr, hydration −120 mL/hr, satiation −1 unit/hr. Applied on caller request, returns list of threshold crossings.
- Derived stats: health from (wakefulness, satiation, hydration); mood from (social_joy, connectedness, cleanliness, base_cleanliness, rest_hours); well-being from (mood, health, safety).
- For health and mood, identifies which input has the highest partial derivative at current values — used to select which sub-description to surface in prompts.
- Safety requires cross-subsystem context (base calories, base firewood, living count), so the caller must pass these in.
- Starting values: wakefulness 100, satiation 1800, hydration 6000, social_joy 20, connectedness 100, cleanliness 100. No starting inventory.
- Cleanliness normalization: `1 - (total_dirtiness / 100)`, floored at 0. Max dirtiness = 100.
- Sleep does NOT reset the rest buff timer.
- Generates natural-language prompt text for each stat at the appropriate descriptive tier.

---

## World State

> Shared mutable base state: storage, resources, fire, placed objects, carcasses.

### Owns (mutable state)
- base_storage: item → quantity map
- water_supply: liters available
- fire: lit/unlit flag, ordered fuel queue (quantity, fuel_type), derived extinction timestamp
- cleanliness_contributors: list of (source_type, count) — carcass_remains, meat_scraps, cooking_scraps — with per-source dirtiness penalties; total_dirtiness is their weighted sum
- placed_resting_spots: villager_id → spot_type map (objects on the ground, distinct from inventory items)
- live_carcasses: carcass_id → arrival_timestamp

### Reads
- Nothing.

### Called by
- Simulation Engine — to advance fire, mark rotted carcasses, read aggregates for autobalancing
- Action System — to check eligibility and apply base mutations
- AI Coordinator — to read base summary for prompt context

### Calls
- Nothing. Passive data store.

### Key rules
- All mutations through explicit setters. All queries are side-effect-free.
- Fire fuel queue is ordered; consumption is FIFO.
- Carcass rot is tracked by arrival timestamp; Simulation Engine schedules the 24-hour deadline externally.
- Both butchering and rotting produce carcass remains (+30 dirtiness). Rotting destroys the meat; butchering yields it.

---

## Simulation Engine

> Discrete-event scheduler that advances time and dispatches all transitions.

### Owns (mutable state)
- event_heap: min-heap of future events timestamped in game time (action completions, fire extinction, carcass rot, midnight tick)
- autobalance_multipliers: exploration yield scaling, satiation restoration scaling, hydration restoration scaling — written at midnight, read by Action System and Villager State

### Reads
- Villager State: who is busy, asleep, alive, threshold crossings after decay
- World State: fire extinction time, carcass deadlines, base food/firewood totals for autobalancing

### Called by
- Nothing. Top-level entry point.

### Calls
- Villager State — apply_decay, compute_safety, set_current_action
- World State — advance_fire, mark_carcass_rotted, read aggregates
- Action System — get_valid_actions, start_action, complete_action, adjust_active_sleep
- AI Coordinator — select_action
- Conversation System — run_conversation (synchronous, blocks until done)
- Memory System — append_event, trigger snapshot

### Key rules
- On each event: advance game time to event timestamp, apply stat decay to all villagers for elapsed duration, then dispatch handler.
- Threshold crossings from decay: wakefulness zero → force sleep; health zero → death (remove villager, append death event).
- Fire extinction mid-sleep: calls adjust_active_sleep on Action System for each sleeping villager, splitting remaining sleep into a new segment under updated modifier.
- Midnight autobalancing: reads average wakefulness/satiation/hydration and base food/firewood supply, computes deviation from targets, writes adjusted multipliers. Targets and algorithm are owned here, not in Action System.
- Forced sleep duration is always 4 hours.
- Safety recalculates per-villager when they wake up.
- Autobalance multipliers are unbounded.
- Event heap invalidation: direct removal from heap on cancel/pause. No lazy invalidation scheme.
- Conversations are synchronous: calls run_conversation, which returns elapsed game time; resumes the initiating villager's event slot.

---

## Action System

> Action catalog: what's legal, what it costs, what it does.

### Owns (mutable state)
- None persistent. Reads autobalance multipliers from Simulation Engine.

### Reads
- Character Canon: profession tags for eligibility gating
- Villager State: inventory, encumbered flag, crafting_in_progress, profession, stat values for work-speed modifiers
- World State: base items, fire fuel, water level, placed objects, carcass state
- Simulation Engine: current autobalance multipliers for yield and restoration scaling

### Called by
- Simulation Engine — to get valid actions, start/complete actions, adjust active sleep
- AI Coordinator — to format the valid action list for prompt inclusion

### Calls
- Villager State — modify_inventory, modify_stat, set_crafting_state
- World State — modify_base_item, add_fire_fuel, modify_water, update_cleanliness_source

### Key rules
- Each action: eligibility predicate, time cost formula (modified by profession + health), calorie cost, start-effect, completion-effect.
- Valid action list: eligible actions get full descriptions with quantities and constraints; ineligible crafter recipes get "Cannot perform" labels rather than being omitted.
- Start effects apply immediately (e.g., consuming raw materials for crafting). Completion effects apply when Simulation Engine fires the scheduled event.
- "At base" = not on an away action (exploration, hauling). For active-participation actions (conversation), also requires awake.
- Fire out mid-cook: cooking pauses gracefully. Villager gets feedback "The fire went out; you cannot continue cooking." Once relit, menu shows "Finish cooking" instead of "Cook."
- Crafting draws from inventory first, then base storage.
- Fire tending fuel preference: inventory fuel before base fuel.
- Exploration yield: Erlang(k=5) sampling, truncated when inventory would be full.
- Profession gating: crafting, cooking, and woodcutting require matching profession; incompatible exploration types get 4× time penalty.
- Long-running crafting: start records (item, minutes_spent) in Villager State; completion step checks accumulated time.

---

## Conversation System

> Multi-villager conversation and trade protocol.

### Owns (mutable state)
- active_session: participants, turn log, per-participant seen log, session elapsed time
- active_trade: (villager_a, villager_b), current offers, turn count

### Reads
- World State: who is at base, awake, not exploring or hauling — for join eligibility
- Villager State: conspicuous uncleanliness (prompt-relevant visibility flag)

### Called by
- Simulation Engine — run_conversation, blocks until complete

### Calls
- AI Coordinator — turn decisions, join decisions, social score queries, relationship update queries
- Villager State — update social_joy, transfer_item on accepted trade
- Memory System — append turn events, conversation outcomes, trade events

### Key rules
- Runs synchronously until all participants leave or 60 game-minutes elapse. Each turn = 5 game-minutes.
- Turn priority: leave > significant interaction > trade > interrupt > continue > respond > topic change > casual action > silent. All participants prompted in parallel; winning action chosen by priority, then recency tiebreak.
- Conversation pauses after turn 2 while non-participants decide whether to join. Each non-participant at base gets a join prompt with the opening excerpt.
- Trade sub-protocol: alternates offer/request/accept/cancel between two villagers. Zero game-time per trade turn. Accepts when one party has accepted and the other's last action was an offer. Cancels after 6 turns without mutual acceptance. Inventory transfers applied immediately.
- Post-conversation: each participant gives a social score delta (0–10) and per-other-participant impression. Social_joy delta and impressions written to Memory System.
- Concurrent leaves are all honored even when only one action "wins" per turn.

---

## Memory System

> Per-villager event logs, thoughts, relationships, and tiered memory compaction.

### Owns (mutable state)
- event_log: per-villager append-only timestamped events (also flushed to disk)
- active_context_log: per-villager current in-context log (cleared on compaction, disk copy preserved)
- thoughts: per-villager short thought snippets captured alongside action selection
- short_term_memories: per-villager ≤128-token summaries
- medium_term_memories: per-villager ≤256-token summaries
- relationships: per ordered villager pair — description string (≤128 tokens) + queue of 3 most recent impression strings (≤32 tokens each)

### Reads
- Nothing.

### Called by
- Simulation Engine — append_event, trigger snapshot
- Conversation System — append turn/trade events, write impressions and relationship updates
- AI Coordinator — retrieve memories, relationships, and logs for prompt assembly

### Calls
- LLM Client — compaction prompts and relationship-update prompts

### Key rules
- Short-term compaction trigger: villager goes to sleep, OR villager completes an action and has been awake ≥4 hours since last compaction. Submits raw log to LLM; stores ≤128-token summary; clears in-context log.
- Medium-term compaction trigger: midnight. Submits all short-term memories from previous calendar day; stores ≤256-token summary; clears those short-term entries.
- Long-term compaction fires every third day (day 3, 6, 9, etc.), compacting all medium-term memories since the last long-term compaction.
- Total memory budget per villager across all tiers: ≤2k tokens.
- Relationship descriptions updated after conversations via LLM-generated text. Impression queue is FIFO capped at 3.
- Full state snapshots flushed to disk when Simulation Engine requests.

---

## AI Coordinator

> Assembles prompts, invokes the model, parses structured responses.

### Owns (mutable state)
- None. Stateless request-response.

### Reads
- Character Canon: backstory, bios, personalities, desires, profession text
- Villager State: stat descriptions, inventory, current action, sleep spot
- World State: base summary (items, fire, water, cleanliness, other villagers' actions)
- Action System: formatted valid action list with quantities, constraints, wording
- Memory System: current log, thoughts, short-term memories, medium-term memories, relationships

### Called by
- Simulation Engine — select_action
- Conversation System — turn decisions, join decisions, social scores, relationship updates

### Calls
- LLM Client — all model invocations

### Key rules
- Action-selection prompt field order (most-static to least-static for cache optimization): system prompt → backstory → character description → other characters' bios + relationship data → memories → world state summary → villager state descriptions → valid action list → thoughts request → timestamp.
- Cache breakpoints placed at static/dynamic boundaries.
- Uses Gemini Flash 2.5 for all LLM calls.
- Parses JSON responses to extract action index, args, thoughts. One retry on malformed output, then crash. Full diagnostic log (prompt, response, exact parsing error) on every failure. Returns validated action references, never raw JSON.
- Separate prompt templates for: action selection, conversation turn, join decision, social score, relationship update, thought capture, memory compaction.
- Read-only against all domain state. Callers provide input; coordinator renders and parses.

---

## LLM Client

> Thin API wrapper.

### Owns (mutable state)
- None. Model, temperature, and token limit fixed at construction.

### Reads
- Nothing.

### Called by
- AI Coordinator — all prompted interactions
- Memory System — compaction and relationship-update prompts

### Calls
- External LLM API.

### Key rules
- Implicit prefix caching — no explicit Cache API management.
- Accepts prompt segments + caller-specified cache breakpoint indices. Applies cache-control headers at those positions.
- Uses Trio for async (structured concurrency with nurseries for fan-outs).
- Retries transient API errors with exponential backoff.
- Returns raw completion text. No parsing or interpretation.

---

## Observability

> Replay, persistence, and inspection viewer.

### Owns (mutable state)
- persisted_event_log: ordered events and state deltas written to disk
- checkpoints: periodic full state snapshots

### Reads
- Persisted files only at replay time. No runtime reads from other subsystems.

### Called by
- Nothing at runtime. Reads persisted data offline.

### Calls
- Nothing.

### Key rules
- Checkpoint restart is in scope for v1. Checkpoints must be machine-readable by Simulation Engine.
- Reconstructs simulation state by replaying deltas forward from nearest preceding checkpoint.
- Perspective filter: own actions always visible, own conversations, base events while present AND awake. Sleep or away = invisible.
- Renders HTML/CSS/JS viewer with per-villager event log navigation, timestamp display, and highlighted state deltas.

---

## Dependency Graph

```
Simulation Engine
├── Villager State
├── World State
├── Action System
│   ├── Villager State
│   └── World State
├── AI Coordinator
│   └── LLM Client
├── Conversation System
│   ├── AI Coordinator
│   ├── Villager State
│   └── Memory System
│       └── LLM Client
└── Memory System

Observability
└── [persisted files only]
```

No cycles. Leaves: Character Canon, Villager State, World State, LLM Client, Observability.

---

## Ownership Friction

Four spots where ownership is non-obvious and must be explicitly assigned:

1. **Placed resting spots vs sleep claims.** The physical object on the ground is World State (placed_resting_spots, keyed by villager). Whether the villager "has a sleep spot" is Villager State (sleep_spot_claim). Two subsystems, two facts, one invariant they must agree on — Action System is responsible for keeping them consistent when placing or picking up.

2. **Safety score.** Requires per-villager inventory calories (Villager State) AND base calories + firewood (World State). Simulation Engine reads both and passes aggregates into Villager State's compute_safety. Safety is a Villager State computation that cannot run without cross-subsystem context from the caller.

3. **Fire mid-sleep.** Simulation Engine schedules fire-extinction from World State's extinction timestamp. When it fires, Simulation Engine calls Action System's adjust_active_sleep for each sleeping villager, splitting remaining sleep into a new segment under the updated wakefulness modifier. State touched: World State (fire), Action System (sleep math), Villager State (wakefulness).

4. **Thoughts with action selection.** Thoughts are requested in the same prompt as action choice (AI Coordinator), but stored as cognitive artifacts (Memory System). AI Coordinator returns them to Simulation Engine, which writes them to Memory System. The thought is never an Action System concern.