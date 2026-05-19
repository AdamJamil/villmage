# ai_coordinator — Diff Plan

Six diffs. The subsystem splits across four files — types, prompt assembly, response parsing, and orchestration — with parsing further split between infrastructure and constraint-heavy parsers.

---

## DIFF 1 of 6

**TITLE:** `[ai_coordinator][1/6]` types module

**DESCRIPTION:**
Create `villmage/ai_coordinator/types.py`. Pure data leaf — no LLM or subsystem imports. Contains every type in the AI Coordinator's input/output contract.

Enums:

- `LLMCallType` — 6-member enum (`ACTION_SELECTION=1` through `TRADE_TURN=6`). Diagnostic classifier stored in `ParseFailureLog`; has no effect on routing.
- `ConvActionType` — 9-member enum (`LEAVE=1` through `TRADE=9`). Conversation action space; Conversation System imports this.
- `TradeActionType` — 4-member enum (`MAKE_OFFER=1` through `ACCEPT=4`). Trade sub-protocol action space.

Dataclasses (frozen unless noted):

- `ConversationTurn` — `villager_id: str`, `text: str`. One recorded turn; `text` is fully self-contained and carries speaker attribution.
- `ConversationSnapshot` — `participant_ids: list[str]`, `history: list[ConversationTurn]`, `elapsed_game_minutes: int`. Pre-filtered by caller; coordinator does not slice internally.
- `ConversationTurnResult` — `action: ConvActionType`, `resp: str | None`, `target_id: str | None`. Parser guarantees required fields before returning (resp for actions 3–8, target_id for TRADE).
- `TradeItemSpec` — `item: ItemType`, `quantity: int`. Item–quantity pair; item name resolved from raw LLM string before construction.
- `TradeTurnRecord` — `villager_id: str`, `action: TradeActionType`, `items: list[TradeItemSpec]`, `speech: str | None`. One trade turn in snapshot history; stores resolved types.
- `TradeSnapshot` — `other_villager_id: str`, `history: list[TradeTurnRecord]`, `turn_count: int`. Full trade negotiation context.
- `TradeTurnResult` — `action: TradeActionType`, `items: list[TradeItemSpec]`, `speech: str | None`. Validated trade turn output.
- `ActionSelectionResult` — `action: SelectedAction`, `thought: str | None`. Thought absent when LLM omits or empties the `thoughts` key (never None when key is present and non-empty).
- `RelationshipUpdateResult` — `impression: str`, `desc_update: str | None`. `desc_update` present only when LLM signals an opinion change.
- `RelationshipRecord` — `description: str`, `impressions: list[str]`. Two fields coordinator reads from Memory System for one ordered pair; grouped to prevent mismatched extraction.
- `PromptPackage` — `segments: list[PromptSegment]`, `breakpoints: list[int]`. Named return type for all `assemble_*` functions; prevents positional confusion at call sites.
- `ParseContext` — `villager_id: str`, `call_type: LLMCallType`, `game_time: GameTime`, `prompt: list[PromptSegment]`. Logging context passed into every parser function so failure records can be written without importing coordinator state.
- `ParseFailureLog` — `villager_id: str`, `call_type: LLMCallType`, `game_time: int`, `prompt: list[PromptSegment]`, `raw_response: str`, `parse_error: str`, `is_retry: bool`. Appended to `.jsonl` on every failure.

Imports: `llm_client.types` (PromptSegment), `action_system.types` (SelectedAction), `game_types` (ItemType, GameTime).

**TEST PLAN:**

*`tests/test_ai_coordinator_types.py`*

*Enum completeness and values.* Assert `len(LLMCallType) == 6`, `len(ConvActionType) == 9`, `len(TradeActionType) == 4`. Then assert each member's integer value exactly for all members of all three enums. Wrong values are silent until serialized or used in dispatch logic downstream.

*ConvActionType resp boundary.* Assert that members 3–8 inclusive are `INTERACT`, `INTERRUPT`, `CONTINUE`, `RESPOND`, `CHANGE_TOPIC`, `CASUAL` — the exact set that requires a `resp` field per CONST-48. This boundary is enforced in the parser; having the enum members at wrong indices silently shifts which actions get validated.

*Dataclass construction — required fields.* Construct every dataclass with minimal valid data. Assert no exceptions. A construction failure means the type contract is broken before any logic runs.

*Optional fields default to None.* For `ConversationTurnResult`, `TradeTurnResult`, `ActionSelectionResult`, `RelationshipUpdateResult`, `TradeTurnRecord`: construct with only required fields and assert each optional field is `None`. These defaults are load-bearing — parsers omit optional fields when the LLM omits them.

*`RelationshipRecord` field ordering.* Construct `RelationshipRecord(description="d", impressions=["a"])`. Assert `description == "d"` and `impressions == ["a"]`. The impl doc explicitly flags that reversing speaker/subject is a semantic error; this type is the grouping mechanism that makes them unambiguous.

*`PromptPackage` named fields.* Construct `PromptPackage(segments=[...], breakpoints=[1, 2])`. Assert `breakpoints == [1, 2]`. The named-field contract exists specifically to prevent positional confusion; verify both fields are accessible by name.

*`ParseContext` carries all four fields.* Construct and assert `villager_id`, `call_type`, `game_time`, and `prompt` are all stored. This is the failure-log bundle; a missing field means failure records are incomplete.

---

## DIFF 2 of 6

**TITLE:** `[ai_coordinator][2/6]` action selection prompt

**DESCRIPTION:**
Create `villmage/ai_coordinator/prompts.py` with `assemble_action_selection`. This is the most architecturally constrained function in the module: REQ-224 mandates a strict static-to-dynamic segment order, and cache breakpoints must fall at exactly the right positions for prefix caching to work.

```python
def assemble_action_selection(
    own_canon: VillagerCanon,
    other_canons: list[VillagerCanon],
    memory_context: VillagerMemoryContext,
    base_summary: BaseSummary,
    computed_stats: ComputedStats,
    inventory_items: list[tuple[ItemType, int]],
    action_list: ActionList,
    game_time: GameTime,
) -> PromptPackage:
```

Ten segments in this order (REQ-224):

1. System prompt (VRBTM-225) — fully static
2. Backstory (VRBTM-226) — fully static
3. Own character bio/personality/desires (VRBTM-227) — static per villager
4. Other characters' bios + relationship records (VRBTM-229, STRCT-230) — semi-static; one block per other villager, each pairing `other_canons[i]` with `memory_context.relationships[other_id]`
5. Memories: long-term → medium-term → short-term → active context log (STRCT-231)
6. World state summary: base items, fire, water, cleanliness, carcasses, villager actions (STRCT-232–234)
7. Villager state: inventory + stat description strings (STRCT-235–236)
8. Valid action list (STRCT-239)
9. Thoughts instruction (VRBTM-240) — static
10. Timestamp (STRCT-241)

Cache breakpoints at: end of segment 4 (after other-character bios + relationships) and end of segment 5 (after memories). These mark the two longest stable prefixes likely to be shared across successive calls for the same villager.

`memory_context.relationships` supplies relationship data for each other character, paired with their bio from `other_canons`. This pairing is what makes segment 4 cohesive.

**TEST PLAN:**

*`tests/test_ai_coordinator_prompts.py`*

Build minimal mock objects for all parameters. Simplicity matters here: the tests verify structure and ordering, not prose quality.

*Segment count.* `assemble_action_selection(...)` returns a `PromptPackage` with exactly 10 segments. The spec lists exactly 10 positions; any deviation in count means a segment was merged, split, or dropped.

*Breakpoint count and positions.* `package.breakpoints` has exactly 2 elements. `breakpoints[0]` equals the index of the last segment in group 4 (after all other-character blocks). `breakpoints[1]` equals the index of the last segment in group 5 (after all memory tiers). These positions are the core caching invariant; wrong positions mean the static/dynamic boundary is mis-declared to the LLM client.

*Static content precedes dynamic content.* Find the segment index of the system prompt (VRBTM-225 literal text), backstory (VRBTM-226), and own-character description (VRBTM-227). Find the segment index of the game_time timestamp (STRCT-241) and action list (STRCT-239). Assert all static segment indices are strictly less than all dynamic segment indices. A transposed segment silently breaks prefix caching for all calls.

*Other-character ordering.* Pass three `other_canons` with distinct names. Assert that all three names appear in the segments before `breakpoints[0]`, and that no other-character name appears after `breakpoints[0]`. The relationship data must co-locate with the bio, not float to a later position.

*Memory ordering.* Populate `memory_context` with distinct strings for long-term, medium-term, short-term, and active context log. Assert these appear in that order within the segment(s) comprising group 5, and that they all fall between `breakpoints[0]` and `breakpoints[1]`.

*Dynamic-only fields are after both breakpoints.* Supply a specific `game_time` value and a specific action list entry. Assert that the segment text containing the timestamp and the segment text containing the action list both appear at indices greater than `breakpoints[1]`. Changing these inputs must not affect any segment at or before `breakpoints[1]`.

*Thoughts instruction is static and late.* The VRBTM-240 instruction text (the `{"thoughts": str}` prompt) must appear in segments after `breakpoints[1]` and before the timestamp segment. It is always the same text regardless of inputs; assert the literal content matches VRBTM-240.

*Relationship data paired with bio.* Pass `other_canons` where one character has a non-default relationship description. Assert that the relationship description appears adjacent (in the same segment or an immediately adjacent segment) to that character's bio, and before `breakpoints[0]`. Relationship data must not leak to after the breakpoint.

---

## DIFF 3 of 6

**TITLE:** `[ai_coordinator][3/6]` conversation/social prompts

**DESCRIPTION:**
Add the remaining five `assemble_*` functions to `prompts.py`:

```python
def assemble_conversation_turn(
    own_canon, other_canons, memory_context, computed_stats,
    inventory_items, snapshot, game_time,
) -> PromptPackage

def assemble_trade_turn(
    own_canon, inventory_items, snapshot,
) -> PromptPackage

def assemble_join_decision(
    own_canon, current_action_description, snapshot,
) -> PromptPackage

def assemble_social_score(
    own_canon, snapshot,
) -> PromptPackage

def assemble_relationship_update(
    speaker_canon, subject_canon, relationship, snapshot,
) -> PromptPackage
```

Key constraints baked into these functions:

- `assemble_conversation_turn`: includes `computed_stats` and `inventory_items` so the villager can reference live condition when deciding what to say or offer. Snapshot history is already visibility-filtered; coordinator does not re-filter.
- `assemble_join_decision`: the caller pre-slices `snapshot.history` to the first two entries. The function uses the history as-is — it must not add internal slicing or the wrong excerpt reaches the LLM.
- `assemble_relationship_update`: `speaker_canon` comes before `subject_canon` in the parameter list. The prompt renders the speaker's perspective on the subject; reversing the parameters is a semantic error. The function must embed speaker and subject in positions that make this direction unambiguous.
- `assemble_social_score` and `assemble_trade_turn` are the simplest: minimal context, single-question or history-only prompts.

**TEST PLAN:**

*`tests/test_ai_coordinator_prompts.py`*

*`assemble_conversation_turn` — inventory and stats present.* Supply a specific inventory entry (e.g., 3 PEACH) and a specific stat description string. Assert both appear somewhere in the returned segments. The villager's live condition must be visible in the prompt for the LLM to make informed trade or food-related decisions.

*`assemble_conversation_turn` — snapshot history present.* Supply a `ConversationSnapshot` with two `ConversationTurn` entries. Assert both turn texts appear in the segments. History visibility filtering is the caller's responsibility; test that the function includes exactly the history it received.

*`assemble_trade_turn` — own inventory and negotiation history.* Supply inventory (2 COOKED_MEAT) and a `TradeSnapshot` with one prior turn. Assert the inventory entry and the prior turn both appear in segments.

*`assemble_join_decision` — uses provided history verbatim.* Supply a snapshot with exactly 2 turns (already sliced by caller). Assert both turn texts appear in segments. Supply a snapshot with 0 turns. Assert no crash — the function must not assume exactly 2 entries. The function's contract is pass-through; assert that the prompt contains exactly the history given.

*`assemble_join_decision` — current action included.* Supply `current_action_description = "gathering sticks"`. Assert this string appears in the segments. Per VRBTM-42, the non-participant needs to know what they are currently doing.

*`assemble_social_score` — asks for 0–10 val.* Assert the segment text contains the string `"0-10"` or `"val"` matching the VRBTM-64 prompt format. This is the entire purpose of the function; a missing range makes the LLM's response uninterpretable.

*`assemble_relationship_update` — speaker and subject distinct.* Call with `speaker_canon` naming "Aldric" and `subject_canon` naming "Sewalt". Assert "Aldric" appears in a position (e.g., as the actor/perspective) that is semantically distinct from "Sewalt" (the subject of impression). Specifically: call again with speaker and subject swapped. Assert the two resulting prompt packages are not identical — a function that ignores the ordering would produce identical output for either argument order, which is the failure mode the impl doc explicitly warns against.

*`assemble_relationship_update` — relationship fields present.* Supply a `RelationshipRecord` with a specific `description` and three `impressions`. Assert all four strings appear in the segments. The LLM needs this context to determine if the opinion has changed.

---

## DIFF 4 of 6

**TITLE:** `[ai_coordinator][4/6]` parser infrastructure + simple parsers

**DESCRIPTION:**
Create `villmage/ai_coordinator/parser.py`. Establishes the parsing infrastructure (ParseError, failure log writing) and implements the three simpler parsers that don't require cross-field constraint validation.

Infrastructure:

- `ParseError(Exception)` — raised on invalid JSON, missing required fields, or violated constraints. Message is the exact error text written to the failure log.
- `_write_failure_log(ctx: ParseContext, raw_response: str, parse_error: str, is_retry: bool) -> None` — internal helper. Constructs a `ParseFailureLog`, serializes to JSON, appends to the `.jsonl` file at a path derived from `ctx`. Called by every parser before raising `ParseError`. This is the spec's BHVR-287 implementation.

Simple parsers:

```python
def parse_join_decision(response: str, ctx: ParseContext) -> bool
def parse_social_score(response: str, ctx: ParseContext) -> int
def parse_relationship_update(response: str, ctx: ParseContext) -> RelationshipUpdateResult
```

- `parse_join_decision`: parses `{"response": "yes"|"no"}`. Returns True for "yes", False for "no". Any other value or missing key → `ParseError`.
- `parse_social_score`: parses `{"val": int}`. Raises `ParseError` if `val` is not an integer or not in `[0, 10]`. Integer-outside-range is a constraint violation, not a type error — treat both as `ParseError`.
- `parse_relationship_update`: parses `{"impression": str, "desc": str}`. `impression` is required and must be non-empty (absent or empty → `ParseError`). `desc` is optional; absent means `desc_update=None`. Per BHVR-70/71.

Every `ParseError` raise is preceded by `_write_failure_log`.

**TEST PLAN:**

*`tests/test_ai_coordinator_parser.py`*

Use `tmp_path` (pytest fixture) for the failure log directory in all tests that trigger `ParseError`.

*`parse_join_decision` — yes/no.* `{"response": "yes"}` → True. `{"response": "no"}` → False. These are the only valid responses.

*`parse_join_decision` — invalid values.* `{"response": "maybe"}`, `{"response": ""}`, `{}` (missing key), and non-JSON input all raise `ParseError`. A liberal parser here would let ambiguous LLM output silently join conversations.

*`parse_social_score` — valid range.* Parse `{"val": 0}`, `{"val": 5}`, and `{"val": 10}`. Assert returns 0, 5, 10 respectively. Boundary values 0 and 10 are explicitly valid.

*`parse_social_score` — out of range.* `{"val": -1}` and `{"val": 11}` both raise `ParseError`. The score is clipped at `val - 5` before being applied (BHVR-66); an out-of-range raw score is a model failure.

*`parse_social_score` — non-integer.* `{"val": "high"}` and `{"val": 7.5}` both raise `ParseError`. The spec specifies an integer; accepting floats would produce fractional social_joy updates.

*`parse_relationship_update` — full response.* `{"impression": "wary", "desc": "Hid food."}` → `RelationshipUpdateResult(impression="wary", desc_update="Hid food.")`. Both fields present and forwarded.

*`parse_relationship_update` — no desc.* `{"impression": "fine"}` → `RelationshipUpdateResult(impression="fine", desc_update=None)`. Absent desc means no opinion change (BHVR-71); `desc_update` must be None, not an empty string.

*`parse_relationship_update` — empty impression raises.* `{"impression": ""}` and `{"impression": None}` and `{}` all raise `ParseError`. An empty impression is explicitly a parse failure per the impl doc — it may not be silently treated as a no-op.

*Failure log written on every ParseError.* For one failure case of each of the three parsers: after the `ParseError` is raised, assert the `.jsonl` file exists and contains exactly one line. Parse that line as JSON and assert: `villager_id` matches `ctx.villager_id`, `call_type` matches `ctx.call_type`, `raw_response` is the verbatim string that was passed in, `parse_error` is non-empty, `is_retry` is False. The failure log is the primary diagnostic artifact for offline debugging; its contents must be complete and faithful.

*Failure log appends, not overwrites.* Trigger two `ParseError`s against the same log path. Assert the file contains exactly two lines. Append semantics are required so that both the first attempt and the retry are preserved (BHVR-287).

*`is_retry` flag is forwarded.* Call `_write_failure_log` with `is_retry=True`. Assert the written record has `is_retry == True`.

---

## DIFF 5 of 6

**TITLE:** `[ai_coordinator][5/6]` complex parsers

**DESCRIPTION:**
Add the three constraint-heavy parsers to `parser.py`:

```python
def parse_action_selection(
    response: str, action_list: ActionList, ctx: ParseContext,
) -> ActionSelectionResult

def parse_conversation_turn(
    response: str, ctx: ParseContext,
) -> ConversationTurnResult

def parse_trade_turn(
    response: str,
    inventory_items: list[tuple[ItemType, int]],
    last_other_action: TradeActionType | None,
    ctx: ParseContext,
) -> TradeTurnResult
```

`parse_action_selection`: parses `{"idx": int, "args": {...}, "thoughts": str}`. Resolves `idx` against `action_list` to a `SelectedAction`; raises `ParseError` if idx is out of range or the target action is non-selectable (e.g., "Cannot perform" recipe). Extracts `thoughts`; absent or empty `thoughts` key → `thought=None` in result (thought absence rule — no memory entry written).

`parse_conversation_turn`: parses `{"idx": int, "args": {...}}`. Resolves idx to `ConvActionType`. For actions 3–8 (INTERACT through CASUAL), `args.resp` must be present and non-empty — absence is a `ParseError`, not a silent downgrade to SILENT (CONST-48). For TRADE (idx 9), `args.target_id` must be present.

`parse_trade_turn`: parses `{"idx": int, "args": {...}, "speech": str}`. Raises `ParseError` if:
- `items` is empty for MAKE_OFFER or REQUEST_ITEMS
- MAKE_OFFER items exceed the acting villager's inventory (INVR-60: can only offer what you hold)
- ACCEPT is returned when `last_other_action` is not MAKE_OFFER (BHVR-63)

`last_other_action=None` means no offer has been made yet; ACCEPT in this state is always a `ParseError`.

All three parsers write a `ParseFailureLog` entry before every raise.

**TEST PLAN:**

*`tests/test_ai_coordinator_parser.py`*

*`parse_action_selection` — happy path.* Construct an `ActionList` with two selectable actions at indices 0 and 1. Parse `{"idx": 0, "args": {}}`. Assert the returned `SelectedAction` corresponds to index 0. Parse `{"idx": 1, "args": {}}`. Assert index 1 resolves correctly.

*`parse_action_selection` — out-of-range idx.* `{"idx": 99, "args": {}}` against a 2-action list raises `ParseError`. The LLM hallucinating an index beyond the list must not silently select an arbitrary action.

*`parse_action_selection` — non-selectable action.* Mark one action in the list as non-selectable (e.g., a "Cannot perform" recipe). Parse that action's idx. Assert `ParseError`. The LLM must not be able to select actions that are displayed as unavailable.

*`parse_action_selection` — thoughts present.* `{"idx": 0, "args": {}, "thoughts": "need food"}` → `thought == "need food"` in result.

*`parse_action_selection` — thoughts absent.* `{"idx": 0, "args": {}}` → `thought is None`. This is the thought absence rule per the impl doc; no memory entry should be written for None thoughts.

*`parse_action_selection` — thoughts empty string.* `{"idx": 0, "args": {}, "thoughts": ""}` → `thought is None`. Empty is treated as absent.

*`parse_conversation_turn` — all 9 action types.* For each `ConvActionType` value 1–9, construct valid JSON and assert the returned `action` field matches. For actions 3–8, include `{"resp": "something"}`. For TRADE (9), include `{"target_id": "sewalt"}`. Cover every branch.

*`parse_conversation_turn` — missing resp for actions 3–8.* For each of INTERACT (3), INTERRUPT (4), CONTINUE (5), RESPOND (6), CHANGE_TOPIC (7), CASUAL (8): supply valid JSON with action idx but no `args.resp`. Assert `ParseError` is raised for each, not `ConvActionType.SILENT`. This is the critical constraint: a missing resp is a model failure, not a silent action.

*`parse_conversation_turn` — missing target_id for TRADE.* `{"idx": 9, "args": {}}` (no `target_id`) raises `ParseError`.

*`parse_trade_turn` — MAKE_OFFER happy path.* Supply inventory with 3 PEACH. Parse `{"idx": 1, "args": {"1": {"name": "peach", "quantity": 2}}}`. Assert MAKE_OFFER returned with `items=[TradeItemSpec(PEACH, 2)]`.

*`parse_trade_turn` — MAKE_OFFER empty items.* `{"idx": 1, "args": {}}` raises `ParseError`. MAKE_OFFER without items is always invalid.

*`parse_trade_turn` — MAKE_OFFER exceeds inventory (INVR-60).* Inventory has 2 PEACH. Offer 3 PEACH. Assert `ParseError`. The constraint is: you can only offer what you hold. This is the spec's INVR-60 enforcement.

*`parse_trade_turn` — ACCEPT valid.* `last_other_action=MAKE_OFFER`. Parse ACCEPT (idx 4). Assert returns `TradeTurnResult(action=ACCEPT, items=[], speech=None)`. ACCEPT is valid only in this case.

*`parse_trade_turn` — ACCEPT invalid when last action is not MAKE_OFFER.* Test `last_other_action=REQUEST_ITEMS`, `last_other_action=CANCEL`, and `last_other_action=None`. All three must raise `ParseError` when the LLM outputs ACCEPT. This is BHVR-63; a miscoded check silently transfers inventory items in an invalid trade state.

*`parse_trade_turn` — CANCEL and optional speech.* Parse CANCEL with `"speech": "not interested"`. Assert `speech == "not interested"`. Parse CANCEL without speech field. Assert `speech is None`.

*Failure log written for each parse failure.* Pick one failure case per parser (3 total). After each `ParseError`, assert the `.jsonl` log has a new line with the correct `call_type` for that parser.

---

## DIFF 6 of 6

**TITLE:** `[ai_coordinator][6/6]` AICoordinator class

**DESCRIPTION:**
Create `villmage/ai_coordinator/coordinator.py`. The `AICoordinator` class is a stateless orchestrator: initialized once with read-only subsystem references, each public method assembles a `PromptPackage`, builds a `ParseContext`, and delegates to `_call`.

```python
class AICoordinator:
    def __init__(
        self, canon, villager_states, world_state, action_system,
        memory_system, llm_client,
    ) -> None

    def _call(
        self,
        package: PromptPackage,
        parse_fn: Callable[[str, ParseContext], T],
        ctx: ParseContext,
    ) -> T

    def select_action(self, villager_id, game_time) -> ActionSelectionResult
    def get_conversation_turn(self, villager_id, snapshot, game_time) -> ConversationTurnResult
    def get_trade_turn(self, villager_id, snapshot, game_time) -> TradeTurnResult
    def get_join_decision(self, villager_id, current_action_description, snapshot, game_time) -> bool
    def get_social_score(self, villager_id, snapshot, game_time) -> int
    def get_relationship_update(self, speaker_id, subject_id, snapshot, game_time) -> RelationshipUpdateResult
```

`_call` owns the retry-once crash sequence: on `ParseError`, retry once with the same prompt; write a `ParseFailureLog` entry for each failure; crash (re-raise) after the second failure. The `ParseContext` carries the full prompt so failure records are complete at both the first failure and the retry.

`select_action` assembles inputs from all five subsystems — canon, villager_states, world_state, action_system, memory_system — then returns the validated `ActionSelectionResult` including the optional `thought`.

`get_relationship_update` reads `memory_system.get_relationship_record(speaker_id, subject_id)` to populate the `RelationshipRecord`. The (speaker, subject) ordering matches the prompt semantics from diff 3: speaker's perspective on subject.

**TEST PLAN:**

*`tests/test_ai_coordinator_coordinator.py`*

Use mock objects for all six subsystem dependencies. Mock `llm_client.complete` to return canned JSON strings.

*`_call` — success path.* Wire a mock LLM that returns valid JSON and a matching parse function. Call `_call`. Assert the parsed result is returned and `llm_client.complete` was called exactly once.

*`_call` — first failure, retry succeeds.* Wire a mock LLM that returns invalid JSON on call 1 and valid JSON on call 2. Call `_call`. Assert the result is returned successfully (from the retry). Assert `llm_client.complete` was called exactly twice — the retry used the same prompt.

*`_call` — both failures, crashes.* Wire a mock LLM that always returns invalid JSON. Call `_call`. Assert `ParseError` propagates out. Assert `llm_client.complete` was called exactly twice (first attempt + retry).

*`_call` — failure log written for both failures.* In the both-failures case, assert the `.jsonl` log has exactly two entries. The first entry has `is_retry=False`; the second has `is_retry=True`. Per BHVR-287, every failure is logged — including the retry — before the crash.

*`_call` — failure log written for first failure when retry succeeds.* In the first-failure-retry-succeeds case, assert one `.jsonl` entry is written (for the first failure), with `is_retry=False`.

*`select_action` — reads all subsystems.* Assert that `llm_client.complete` was called with a prompt that contains content from: own canon bio, other canons' bios, memory context, base summary, computed stats, inventory, action list. Use mock objects whose string representations are distinct and verifiable in the prompt text. This confirms all five subsystem reads are wired up.

*`select_action` — returns thought.* Wire the mock LLM to return `{"idx": 0, "args": {}, "thoughts": "need sleep"}`. Assert the returned `ActionSelectionResult.thought == "need sleep"`.

*`select_action` — thought absent.* Wire the mock LLM to return `{"idx": 0, "args": {}}`. Assert `ActionSelectionResult.thought is None`. The Simulation Engine checks for None before writing to Memory System; a wrong value here leaks empty thoughts.

*`get_relationship_update` — reads correct ordered pair from memory.* Call `get_relationship_update(speaker_id="aldric", subject_id="sewalt", ...)`. Assert `memory_system.get_relationship_record` was called with `("aldric", "sewalt")` — not the reverse. The impl doc flags reversed arguments as a semantic error; this test catches a transposed call.

*Public methods return correct types.* For each of the six public methods, wire the mock LLM with a valid response and assert the return type matches the declared return type (`ActionSelectionResult`, `ConversationTurnResult`, `TradeTurnResult`, `bool`, `int`, `RelationshipUpdateResult`). Type-checking alone catches this at analysis time, but a runtime smoke test catches cases where the parser returns the right structure but coordinator wraps it incorrectly.

*`get_join_decision` — caller pre-slices snapshot.* Pass a `ConversationSnapshot` whose `history` has exactly 2 entries. Assert `llm_client.complete` was called with prompt content that includes both turns. The coordinator must not slice internally — the caller is responsible (per impl doc). A function that silently re-slices would truncate join context; a function that silently extends it would violate the spec contract.
