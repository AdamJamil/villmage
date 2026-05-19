# Subsystems

## Character Canon

This subsystem defines who each villmager is in stable narrative terms. It owns the authored identity that should remain consistent across prompts, decisions, and social interpretation.

### Responsibilities
- Provide the immutable backstory, bios, personalities, desires, and profession tags for each villmager.
- Expose profession-based capability flags that other subsystems use to decide what actions or recipes are conceptually available, but not whether a specific action is currently legal.
- Own only authored character facts and capability metadata. Inventories, statuses, relationships, memories, and in-progress tasks live elsewhere and must not be duplicated here.
- Serve as the authoritative source for character-facing prompt context, without owning transient state, simulation logic, or prompt assembly.

### Dependencies
- None. This subsystem is pure source data that other subsystems read.

## World State Model

This subsystem defines the shared simulation state and static world data. It is the canonical representation of things that exist, where they are, and what persistent world facts are true right now.

### Responsibilities
- Define the core entities and constants for items, weights, storage, base water supply, fire capacity, fire fuel-unit values, dirtiness contributors, resting spots, and other persistent world objects.
- Track mutable ownership and location state for inventory, base storage, base water quantity, fire on/off state plus remaining placed fuel, claimed resting spots, carcass age or rot deadline, in-progress crafting, paused work, active sleep records, and other durable world records required by the spec.
- Organize shared state into explicit domains rather than one undifferentiated store. At minimum this includes world resources and objects, actor task or execution records, and other non-social durable records needed across the simulation.
- Own where data lives for the shared simulation. This includes durable facts such as item counts, object placement, task progress, and perishable timers, but not formulas for how those facts affect health, mood, legality, or balance.
- Provide the shared read/write surface used by action resolution, survival updates, social systems, replay persistence, and prompt construction, while remaining deliberately ignorant of why a caller wants the data.

### Dependencies
- None. This subsystem is the canonical store and should not call into rule subsystems to interpret its own records.

## Turn And Time Engine

This subsystem advances time and coordinates the order in which the rest of the game runs. It is a scheduler that decides what is due next, dispatches to the subsystem that owns that transition, and commits results in a consistent order.

### Responsibilities
- Decide which villmager or live social session is due next, when prompts are issued, how chosen actions advance the simulation clock, and when conversation flow temporarily takes over from normal single-actor turns.
- Advance elapsed time and trigger all time-based transitions required by the spec, including passive stat drains, fire burn-down, carcass rot expiry, conversation turn time, sleep progression, midnight or end-of-day triggers, and checkpoint cadence.
- Own sequencing and lifecycle only. It does not decide action legality, survival formulas, relationship text, checkpoint storage format, or replay UI behavior; it invokes the subsystems that own those rules.
- Advance the clock, dispatch elapsed time or action or session completions to the owning subsystem, and apply the returned mutations and events in a consistent order.
- Maintain the small shared event vocabulary that other subsystems consume, such as action started, action completed, conversation started, conversation turn appended, trade started, trade updated, conversation ended, sleep began, sleep ended, villmager died, and memory formed.

### Dependencies
- `World State Model`: Reads who is busy, awake, alive, and located where, and writes scheduling outcomes such as task start, task completion, interruption, resume, sleep records, and expiry or removal of timed world objects.
- `Action System`: Requests legal action sets for normal turns and asks it to resolve chosen non-social actions into time costs and state mutations.
- `Social Interaction`: Hands off control when a conversation or trade starts, lets it drive social turn order while active, then resumes normal scheduling when the social flow ends.
- `Survival State`: Advances passive drains, recomputes derived statuses after world changes, and asks for threshold outcomes such as forced sleep, death, and remedial warnings.
- `Memory And Relationships`: Triggers thought capture and memory-compaction moments on the required cadence.
- `Prompt And Model Interface`: Uses it as the only path for action-turn, join-turn, conversation-turn, trade-turn, and cognition-maintenance model exchanges.
- `Adaptive Balance Controller`: Invokes the end-of-day rebalance pass and applies the resulting tuning changes for future turns.
- `Replay And Observability`: Emits the ordered stream of events, deltas, and checkpoints that make the simulation inspectable and restartable.

## Action System

This subsystem is the high-level interaction surface between villmagers and the world. It owns what actions are currently legal, what arguments they require, and how chosen actions transform shared state.

### Responsibilities
- Build the currently available action list for a villmager based on location, inventory, profession, world state, claimed-object rules, and blocking conditions such as encumbrance or death.
- Resolve the full catalog of non-social actions, including base storage transfer, eating, drinking, placing and claiming resting spots, exploration, resting, fire tending, hauling water, butchering, camp cleaning, log splitting, hide scraping, crafting, continuing crafts, cooking, washing, and sleeping.
- Own action-local rules: argument ranges, visibility, action-specific wording, item transformations, fuel-consumption order, recipe progression, exploration-yield sampling, exploration stop conditions, and other per-action behaviors.
- Handle actions that consume from multiple locations according to spec rules, such as preferring inventory fuel before base fuel for fire tending while still allowing misc actions and crafting to draw from both inventory and base.
- Own long-running action progression records for actions that can span multiple turns, especially partial crafting, and return structured execution data for the scheduler to resume or complete later.
- Expose social initiation as a legal high-level action where appropriate, but hand off immediately to `Social Interaction` once that action is chosen rather than resolving conversation or trade protocol itself.
- Keep persistent world facts in the world model and survival ledgers in survival state. The action system decides that butchering costs cleanliness and calories, for example, but does not own the cleanliness or calorie state itself.

### Dependencies
- `Character Canon`: Reads profession tags and static unlocks to decide which exploration options, crafting recipes, and cooking actions are conceptually available.
- `World State Model`: Reads inventories, base resources, base water, fire status, placed objects, carcass timers, and in-progress work, then writes the resulting item, location, and task mutations when an action resolves.
- `Survival State`: Requests work-speed modifiers for displayed times and applies action-driven stat changes such as calories, hydration, wakefulness effects from starting sleep, cleanliness, and direct mood or social updates explicitly caused by an action.
- `Adaptive Balance Controller`: Reads the currently tuned exploration-yield and restoration modifiers so legal actions and their outcomes reflect the latest balance settings without embedding tuning logic here.

## Survival State

This subsystem turns raw world and character state into survival outcomes. It owns the formulas, passive drains, thresholds, and status interpretations that describe how well each villmager is doing.

### Responsibilities
- Maintain the persistent survival ledgers for wakefulness, satiation, hydration, cleanliness, social joy, connectedness, mood, health, safety, and overall well-being.
- Own the formulas and thresholds for those values, including passive drains, work-speed modifiers, daily safety recomputation, death, forced sleep, and remedial warnings.
- Own sleep restoration math, including segmented overnight restoration when bed or fire conditions change during the same sleep interval and the corresponding feedback text derived from those segments.
- Produce the derived metrics and prompt-facing interpretations built from those ledgers, including status descriptions, remedial-action overrides, and explanation snippets chosen by the specified partial-derivative logic.
- Recalculate state from shared world facts where needed, including safety from stockpiles and mood or health explanations from their subcomponents.
- Keep only survival data and derived interpretations here. Item counts, fire fuel, base dirt sources, and conversation transcripts live elsewhere and are read as inputs rather than mirrored.

### Dependencies
- `World State Model`: Reads canonical world facts such as inventories, stockpiles, firewood, dirtiness contributors, sleeping setup, and alive or dead membership, and writes only the survival-owned stat fields that change over time.
- `Adaptive Balance Controller`: Reads the currently tuned satiation and hydration restoration modifiers when food and water intake are converted into stat gains.

## Social Interaction

This subsystem manages the multi-actor flow of conversations and trades. It owns the rules for who can join, who acts next, what happens during a turn, and when a social exchange begins or ends.

### Responsibilities
- Start, run, and end conversations, including initiator-only first turns, join prompts after two turns, pause-and-resume behavior for interrupted work, turn sequencing, and elapsed conversation time.
- Resolve conversation-turn protocol as a social state machine: collect candidate responses, choose the next actor by the specified priority order and recency tiebreak, discard non-winning turn inputs except concurrent leaves, append visible content to each participant's seen log, and stop after one hour or when only one participant remains.
- Run trading as a conversation-scoped interaction with its own turn rules, offer or request lifecycle, acceptance constraints, six-turn cancellation rule, zero-time trade turns, and inventory-transfer legality checks.
- Own the live social session state machines, including whose turn it is, who has joined, what each participant has seen, current offers, session transcripts, and session end conditions.
- Emit compact session outcome records that downstream systems can consume.
- Leave long-term social interpretation to memory and relationships and direct stat math to survival. This subsystem decides that a conversation ended and who participated; other subsystems own what lasting relationship text or social score changes are written.

### Dependencies
- `World State Model`: Reads who is at base, awake, exploring, or hauling water, pauses and resumes interrupted work, and applies the inventory transfers caused by accepted trades.
- `Prompt And Model Interface`: Uses specialized conversation, join, trade, and post-conversation reflection prompts to collect structured model outputs.
- `Survival State`: Applies the direct social-joy and connectedness updates from finished conversations and reads visibility-relevant status such as conspicuous uncleanliness.
- `Memory And Relationships`: Appends participant-visible conversation events to recent logs and requests per-pair impression and relationship updates after each conversation.

## Memory And Relationships

This subsystem converts lived experience into compact personal context. It owns what each villmager remembers, what they currently think, and how they internally model the other members of the group.

### Responsibilities
- Consume perspective-scoped experience events from the rest of the simulation and record recent event logs and short thought snippets from each villmager's perspective.
- Maintain relationship descriptions and recent impressions for every ordered villmager pair, updating them from social outcomes and keeping only the required rolling impression window.
- Form short-term memories from recent logs when a villmager sleeps or completes an action after the minimum awake interval, then clear the active log while keeping the historical record elsewhere.
- Run the scheduled compaction pipeline from short-term to medium-term at midnight, then from older medium-term memories into long-term memories after the configured day horizon, using aggressive summarization to preserve prompt budget.
- Own only private cognitive artifacts: logs, thoughts, memories, and relationship text. It does not own the authoritative action or event timeline, conversation control flow, or prompt transport.

### Dependencies
- `Prompt And Model Interface`: Uses dedicated prompts to capture thoughts, summarize recent logs into memories, and generate post-conversation impressions and relationship-description changes.

## Prompt And Model Interface

This subsystem is the boundary between simulation code and model I/O. It packages the current world into the exact prompt contract the model expects, then validates and interprets the model's structured outputs.

### Responsibilities
- Construct villmager prompts in the required stable order, combining canon, per-other-character bio plus relationship info, memories, current log, local world state, base status, villmager status, timestamp, and legal actions.
- Build the smaller specialized prompts used for conversation turns, join decisions, trade turns, social reflection, relationship updates, thought capture, and memory compaction.
- Own prompt templates, exact field ordering, serialization, model invocation, and response validation only. It does not decide which facts are true or which actions are legal; it renders caller-owned data into the required contract.
- Enforce the structured-output contracts for each prompt family, including action selection, optional thought capture, join responses, conversation actions with required `resp` fields, trade actions with offer or request payloads, feeling scores, and relationship-update payloads.
- Stay read-only against domain state. Callers should provide prompt input objects or query through narrow read interfaces rather than letting this subsystem become a second orchestrator.
- Normalize model outputs into typed results for the caller, while leaving downstream state mutation and rule enforcement to the subsystem that requested the prompt.

### Dependencies
- `Character Canon`: Reads backstory, villmager bios, personalities, desires, and profession-facing identity text for stable prompt context.
- `World State Model`: Reads local world facts such as inventories, base status, ongoing actions, fire state, dirtiness, carcass info, and timestamps that must be surfaced in prompts.
- `Action System`: Requests the current legal action list, argument schemas, displayed times, unavailable-crafter-recipe section, and action-specific wording for normal action-choice prompts.
- `Survival State`: Reads the current status descriptions, highest-salience subcomponent feedback, sleep feedback, and remedial-warning override signals to decide what state feedback to include.
- `Memory And Relationships`: Reads relationship descriptions, recent impressions, current logs, thoughts, and compacted memories to populate both main prompts and cognition-maintenance prompts.

## Adaptive Balance Controller

This subsystem is a narrow tuning layer that pushes the simulation back toward target discomfort levels. It should stay small and data-driven rather than leaking balancing rules into the action or survival codepaths.

### Responsibilities
- Measure end-of-day aggregate outcomes against target satiation, hydration, food safety, and fuel safety values.
- Adjust only the explicit named modifier surface in the opposite direction of observed drift: exploration yield, satiation restoration, and hydration restoration.
- Own only the tuned modifier values and rebalance algorithm. Base action formulas, survival formulas, and world data remain owned by their respective subsystems.
- Expose the current tuned modifiers to the action and survival subsystems without taking ownership of their core formulas.
- Never change thresholds, action legality, scheduling behavior, or untargeted formula constants.

### Dependencies
- `World State Model`: Reads canonical resource and population state for balance signals that depend on stockpiles and living-villmager counts.
- `Survival State`: Reads the end-of-day aggregate satiation, hydration, and safety outcomes that the rebalance pass compares against targets.

## Replay And Observability

This subsystem turns the simulation into an inspectable historical record. It owns persistence of incremental updates and the UI logic that reconstructs what each villmager knew and what changed over time.

### Responsibilities
- Persist domain events, state deltas, memories, relationship changes, thoughts, and periodic checkpoints.
- Reconstruct simulation state from checkpoints plus updates so the run can be replayed or restarted from an earlier point.
- Reconstruct perspective-specific event logs and shown state so the observability surface can display what each villmager saw and knew at a given time, not just omniscient state.
- Own storage format, replay reconstruction, checkpoint materialization, and the HTML, CSS, and JavaScript observability surface.
- Keep observability downstream of the simulation. It stores and replays canonical data from other subsystems, but it must not become a second source of truth for world state, survival rules, or memory contents.

### Dependencies
- `Turn And Time Engine`: Consumes the ordered event stream and checkpoint triggers that define what happened and when.
- `World State Model`: Reads canonical world snapshots and deltas for inventories, base state, fire state, object placement, task progress, and other shared simulation facts.
- `Survival State`: Reads per-villmager stat changes and derived-status outputs so replay can show why condition changed over time.
- `Memory And Relationships`: Reads thought, memory, and relationship updates for persistence and perspective-specific reconstruction.

## Explicit Ownership Friction

- `Resting` touches mood through a one-hour action and also through the mood formula's rest input. This document assigns action completion to `Action System` and the actual mood-input state plus formula interpretation to `Survival State`.
- Sleep quality depends on world facts that can change while sleeping, especially fire state and resting-spot availability. This document assigns elapsed-time progression to `Turn And Time Engine`, source facts to `World State Model`, and segmented restoration math to `Survival State`.
- Thoughts are requested together with action choice, but thoughts become part of the villmager's cognitive record rather than action resolution. This document assigns prompt transport to `Prompt And Model Interface`, scheduling of thought-capture moments to `Turn And Time Engine`, and storage of the resulting thoughts to `Memory And Relationships`.
