# Suggestions On Proposed Subsystems

## Overall Assessment

The current subsystem split is thoughtful and already much better than a naive "game logic blob" architecture. It shows a real attempt to separate authored facts, mutable simulation state, rule evaluation, model I/O, social flow, cognition, balancing, and replay concerns. That is the right overall direction.

The strongest quality of the proposal is that most subsystems are defined by a clear kind of ownership:
- `Character Canon` owns stable authored identity.
- `World State Model` owns durable shared facts.
- `Action System` owns concrete non-social action rules.
- `Prompt And Model Interface` owns prompt/render/validation mechanics.
- `Replay And Observability` is explicitly downstream.

Those are clean joints. They support beautiful abstractions because each one has a narrow reason to change, and each one is easy to explain to another engineer in one sentence.

The weaker areas are:
- too much policy is concentrated in `Simulation Orchestrator`
- `Survival State` mixes "stored stats" with "derived interpretation" with "system-wide recalculation"
- `Social Interaction` currently combines conversation control flow, trade protocol, and some social effect application
- `Adaptive Balance Controller` is conceptually neat but risks becoming a cross-cutting modifier leak unless its interface is made extremely narrow
- some boundaries are described in terms of "does not own X" rather than in terms of a precise API contract for what it does own

So the architecture is promising, but several joints still need sharpening before they will stay clean under implementation pressure.

## What Already Has Clean Joints

### Character Canon

This is a very strong subsystem boundary.

Why it works:
- The spec has a genuine distinction between authored character identity and runtime state.
- Profession tags and static recipe/action unlocks belong naturally with canonical authored data.
- It creates a stable dependency root for prompting, legality checks, and social interpretation without letting those systems mutate it.

This subsystem lends itself to a beautiful abstraction because it can remain almost pure data plus typed accessors. It should stay boring forever, which is exactly what you want.

One improvement:
- Be explicit that `Character Canon` owns profession membership and static profession unlock metadata, but does not own the action catalog entries themselves. Right now that is implied, but making it explicit will prevent recipe duplication across canon and action code.

### World State Model

This is also a strong foundational split.

Why it works:
- The spec has a large amount of persistent state: inventories, base storage, fire fuel, water, placed sleep spots, carcass timers, ongoing crafting, logs, and so on.
- Having one canonical home for durable simulation facts is essential for replay, restart, prompt rendering, and legality checks.
- The definition correctly resists letting the world model interpret its own records.

This is a good joint because nearly every subsystem needs shared facts, but they should not each invent their own storage shape.

Main caution:
- The current definition risks turning `World State Model` into an enormous "everything persistent" bucket. That is survivable, but only if it is treated as a storage boundary rather than a conceptual subsystem that claims too much semantic territory.

Improvement:
- Define the world model as a set of state domains, not one undifferentiated store. At minimum:
  - world resources and objects
  - actor task/execution records
  - social session records
  - cognition records
- These can still live under one broad subsystem, but naming the domains will make the joints legible.

### Prompt And Model Interface

This is one of the best decisions in the document.

Why it works:
- The spec is unusually prompt-sensitive: exact field order, compact memory budgets, multiple specialized prompt types, and strict structured outputs.
- Treating prompt construction and output validation as a dedicated boundary will massively reduce accidental coupling between gameplay rules and prompt mechanics.
- It creates a natural seam for testing: prompt assembly tests and response validation tests can be isolated from simulation logic.

This subsystem supports delegation very well. Someone can work entirely on prompt schemas and model adapters without touching legality rules or stat formulas.

One improvement:
- State explicitly that this subsystem should not pull data from other subsystems on its own beyond read-only query interfaces. Callers should assemble a prompt input object as much as possible, with the interface owning rendering and validation rather than becoming a second orchestrator.

### Replay And Observability

Another strong boundary.

Why it works:
- The spec clearly wants inspectability from multiple perspectives, delta persistence, checkpoints, and restart.
- Making replay downstream avoids contaminating game logic with UI storage concerns.
- The split between canonical state and replay materialization is conceptually clean.

This is a good abstraction because it can be built and tested against emitted events/checkpoints without needing to own gameplay decisions.

The main improvement is interface shape:
- Prefer "subscribe to domain events + periodic snapshots/checkpoints" over ad hoc direct reads from many subsystems.
- If replay reads live subsystem state too freely, it will become tightly coupled to internal storage layouts.

## Where The Joints Are Still Blurry

### Simulation Orchestrator Is Too Powerful

This is the biggest architectural risk in the current design.

The definition says the orchestrator:
- decides who acts next
- advances time
- handles conversation takeover
- triggers passive stat drains
- triggers sleep collapse, death handling, memory formation, daily recalculations, checkpoints
- coordinates mutation, recomputation, balancing, and event emission

That is dangerously close to "the real game logic lives here."

A top-level coordinator should decide order of operations, but not encode many named game policies itself. Otherwise every feature ends up requiring an orchestrator edit, and the subsystem boundaries below it stop mattering.

The clean joint would be:
- orchestrator owns sequencing and lifecycle
- domain subsystems own when their own transitions are due, given elapsed time or events

Example:
- `Survival State` should own "wakefulness reached zero, forced sleep occurs"
- `Memory And Relationships` should own "4 awake hours have elapsed since last compaction checkpoint"
- `Replay And Observability` should own "checkpoint every 3 in-game hours"
- `Social Interaction` should own "conversation expires after one hour or one participant remains"

The orchestrator should ask each subsystem something closer to:
- "advance from `t0` to `t1`"
- "apply completion of action X"
- "open/continue/close session Y"

Not:
- "I know all threshold rules and call everyone manually"

Suggestion:
- Narrow `Simulation Orchestrator` into a `Turn And Time Engine`.
- Make it responsible for:
  - selecting the next due actor/session
  - advancing the clock
  - dispatching to the owning subsystem
  - applying returned mutations/events in a consistent order
- Remove ownership of specific domain transitions from its prose.

### Survival State Is Doing Three Different Jobs

`Survival State` currently owns:
- the stored bodily/social stats
- the formulas and thresholds
- the prompt-facing interpretations/descriptions

That can work, but it is near the edge of becoming muddy.

Why this is risky:
- stored values and formula logic are tightly related
- prompt-facing descriptions are also related
- but whole-world recomputation like safety-from-stockpiles and derivative-based explanation selection is a different kind of responsibility

This subsystem is still viable as one unit because all of those pieces serve the same concept: "how a villmager is doing." But the API needs to be sharper.

What the joint should be:
- input: canonical world facts + direct action effects + elapsed time
- output: updated stats, derived statuses, threshold events, and explanation snippets

What should not leak:
- no other subsystem should compute health, mood, speed modifiers, or remedial-action logic itself
- no other subsystem should manually write survival-owned fields except through survival APIs

Specific improvement:
- Separate in the definition between:
  - persistent survival ledgers
  - derived metrics and thresholds
  - prompt-facing textual interpretations
- Keep them in one subsystem, but make the internal layering explicit.

### Social Interaction Combines Protocol And Consequence

The conversation/trade split is sensible, and keeping social flow outside the normal action system is likely the right call. The spec really does have a separate multi-actor protocol here.

Still, the joint is not fully clean.

Why:
- `Social Interaction` owns conversation/trade turn rules
- `Memory And Relationships` owns lasting interpretation
- `Survival State` owns direct social-joy/connectedness stat changes

That is fine in principle, but the current description leaves open whether `Social Interaction` is merely a session engine or whether it will also become the place where every social outcome rule gets encoded.

It should remain a session/protocol subsystem.

Beautiful joint:
- `Social Interaction` decides who is in the conversation, whose turn it is, what options are legal, what raw transcript/events occurred, and when the session ends
- it emits a compact session outcome object
- `Survival State` and `Memory And Relationships` consume that outcome and apply their own updates

Suggestion:
- Define `Social Interaction` primarily around "live social session state machines."
- Be explicit that it owns transcripts and visible turn flow, but not the longer-term semantic consequences of those transcripts.

### Action System Versus Social Interaction

This seam is mostly good, but it needs one explicit rule: social initiation belongs to one subsystem.

Right now:
- normal action prompts include "Talk to someone"
- `Action System` owns non-social actions
- `Social Interaction` owns conversations and trades

The cleanest boundary is:
- `Action System` may expose a high-level "initiate social session" action as a legal option
- but it should not resolve the session logic itself
- once selected, control transfers immediately to `Social Interaction`

That single sentence belongs in the definition. Without it, social actions will get awkwardly half-implemented in two places.

### Memory And Relationships Is Slightly Asymmetric

Conceptually this subsystem is strong. The spec clearly distinguishes:
- recent log
- current thought snippets
- per-pair relationship descriptions
- recent impressions
- short/medium/long-term memory compaction

That is a coherent ownership domain.

The issue is dependency asymmetry. The definition makes it depend only on `Prompt And Model Interface`, but in practice it also depends on structured event inputs from the rest of the game.

That matters because otherwise there is no clean answer to:
- who appends experience logs?
- who decides what a villmager "saw" from an action outcome?
- who emits memory-formation triggers?

Suggestion:
- State that `Memory And Relationships` consumes perspective-scoped experience events from the orchestrator/social/action domains.
- Keep prompt generation for thoughts and compaction in the prompt subsystem, but do not imply that cognition owns raw event production.

This is a case where the subsystem idea is good, but the input contract needs to be named.

### Adaptive Balance Controller Is Intellectually Clean But Operationally Slippery

This subsystem is plausible because the spec explicitly calls for adaptive buffs/nerfs. So having a tuning layer is not architecture astronautics; it is justified by the domain.

But it will stay clean only if its knobs are extremely constrained.

Current risk:
- once a tuning subsystem exists, it is easy to let it mutate arbitrary yields, drains, thresholds, or formula constants
- then game behavior becomes hard to reason about because the source of truth for any number is no longer obvious

The clean joint should be:
- balance owns only a tiny set of named modifiers explicitly mentioned in the spec
- action/survival own all base formulas
- callers ask for "effective value = base rule plus named modifier"

Suggestion:
- List the exact modifier surface in the definition, likely only:
  - exploration yield modifier(s)
  - satiation restoration modifier
  - hydration restoration modifier
- Explicitly forbid balance from changing thresholds, action legality, or scheduling behavior.

## Structural Improvements To Consider

### 1. Split "State" From "Rules" More Systematically

The current architecture sometimes uses "subsystem" to mean a state domain, and other times to mean a rule engine.

Examples:
- `World State Model` is mostly storage
- `Survival State` is storage plus rules
- `Action System` is almost all rules
- `Social Interaction` is state machine plus rules

That is not wrong, but it means some boundaries are crisp and others are fuzzy.

A more legible framing would be:
- authored data: `Character Canon`
- canonical mutable state: `World State Model`, `Survival State`, `Memory And Relationships`
- rule engines: `Action System`, `Social Interaction`, `Adaptive Balance Controller`
- coordination boundary: `Simulation Orchestrator`
- external interfaces: `Prompt And Model Interface`, `Replay And Observability`

You do not need to rename everything, but writing the definitions with that pattern in mind would sharpen the architecture.

### 2. Consider Renaming `World State Model`

The current name sounds like it owns all simulation state, but in the definition it explicitly does not own survival data, relationship data, or some session-local state.

A name like `Shared World State` or `Physical World State` may be more honest if the goal is to emphasize resources, objects, placement, and task records rather than literally all mutable data.

This is optional, but it would reduce confusion.

### 3. Make "Session State" Explicit

The spec has at least two stateful session types:
- active work/action execution
- active conversation/trade execution

Right now these are spread across `World State Model`, `Simulation Orchestrator`, and `Social Interaction`.

That can still work, but you should clearly define where session records live.

My recommendation:
- active work records live with world/task state
- active social session records live in `Social Interaction`

That is a clean joint because social sessions have domain-specific protocol state that does not belong in a generic world store API.

### 4. Define Event Boundaries More Explicitly

Many subsystem joints would become cleaner if the architecture named a small event vocabulary.

Examples:
- action started
- action progressed
- action completed
- conversation started
- conversation turn appended
- conversation ended
- time advanced
- villmager died
- sleep began
- sleep ended

You do not need event sourcing everywhere. But defining domain events as the handoff objects between subsystems would make replay, cognition, and prompt updates much easier to reason about.

This is especially important because the spec includes perspective-specific logs and replay. Both want the same raw happenings, just rendered differently.

## Subsystems I Would Keep As-Is In Principle

I would keep the existence of these subsystems:
- `Character Canon`
- `World State Model`
- `Action System`
- `Social Interaction`
- `Memory And Relationships`
- `Prompt And Model Interface`
- `Replay And Observability`

These all correspond to genuine conceptual seams in the spec.

## Subsystems I Would Refine Most Aggressively

If only a few definitions are revised, I would focus on these:

### Simulation Orchestrator

Refine it into a thinner sequencing engine. This is the most important improvement because an overgrown orchestrator will silently erase all the other clean boundaries.

### Survival State

Clarify its internal layers and APIs so it does not become a mix of stat storage, formula dumping ground, and prompt-helper miscellany.

### Adaptive Balance Controller

Constrain it very tightly so it remains a small tuning shim rather than a second hidden rules engine.

## Final Recommendation

The architecture is already on a strong path. The proposed subsystems mostly point at the right joints, and several of them are already elegant:
- authored identity versus runtime state
- action legality/resolution versus prompt transport
- live social protocol versus long-term cognition
- simulation truth versus replay surface

The main thing to fix now is not "which major subsystems exist," but "how thin and explicit the joints are." In particular:
- make the orchestrator narrower
- define which subsystem owns session records
- define how experience events flow into cognition and replay
- constrain balance to a tiny explicit modifier surface
- make the `Action System` to `Social Interaction` handoff explicit

If those changes are made, the subsystem architecture should be both understandable and highly delegable: one engineer can work on prompts, another on action legality, another on survival math, another on replay, without all of them fighting over ambiguous ownership.
