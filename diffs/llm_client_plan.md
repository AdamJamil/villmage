# llm_client — Diff Plan

---

## DIFF 1

**TITLE:** `[llm_client][1/4]` Types

**DESCRIPTION:**
Add `llm_client/types.py` with all five pure data types: `MessageRole`, `CallType`, `PromptSegment`, `LLMResponse`, and `LLMConfig`. No logic; no imports from within the package or from the Gemini SDK. Every field matches the spec exactly: enum integer values per the thrift definitions in `llm_client.md`, dataclass defaults per `LLMConfig` (`model="gemini-2.5-flash"`, `max_output_tokens=2048`, `max_retries=10`), all dataclasses frozen.

This diff exists because `types.py` is a pure-data leaf that every other file in the package imports. Getting the types right and tested before any logic exists eliminates ambiguity in all subsequent diffs.

**TEST PLAN:**

*Enum values.* Assert each `MessageRole` and `CallType` member has its exact integer value from the spec. A wrong value would silently corrupt Gemini API calls; test every member, not just one.

*Dataclass construction.* Instantiate each dataclass with all fields; verify field access returns the supplied values. Cover `LLMConfig` with its defaults as well as overrides of all three fields.

*Frozen enforcement.* Attempt to assign to a field on a `PromptSegment`, `LLMResponse`, and `LLMConfig` instance and assert `FrozenInstanceError` (or equivalent) is raised. Mutation must be structurally impossible, not just discouraged.

*`LLMConfig` defaults.* Construct `LLMConfig()` with no arguments and assert all three defaults exactly. These values are load-bearing for every LLM call in the system.

---

## DIFF 2

**TITLE:** `[llm_client][2/4]` Content assembly

**DESCRIPTION:**
Add `llm_client/client.py` with the `LLMClient` class: `__init__` (constructs a single `GenerativeModel` instance using the provided API key and model name from config) and `_build_contents` (extracts and concatenates all `SYSTEM` segments into a single `system_instruction` string, maps remaining `USER`/`MODEL` segments to Gemini `Content` objects in order, and returns both as a tuple). `complete()` and `_submit_with_retry` are intentionally absent — they arrive in later diffs.

This diff isolates the prompt-shape transformation, which is pure and has no async or API surface. It is the most testable piece of logic in the client and the most likely to silently misbehave (wrong role mapping, wrong concatenation order) without dedicated coverage.

**TEST PLAN:**

*SYSTEM extraction and concatenation.* Build a segment list with two `SYSTEM` segments and assert `system_instruction` is their texts joined in order. Verify neither appears in the returned `contents` list.

*USER/MODEL ordering.* Build a segment list with alternating `USER` and `MODEL` segments (no `SYSTEM`). Assert the returned `contents` preserves order and maps each segment to the correct Gemini role string (`"user"` or `"model"`).

*Mixed realistic prompt.* Build a list that mirrors a real prompt: one `SYSTEM` (static system prompt), one `SYSTEM` (backstory), two `USER`/`MODEL` turns, one final `USER`. Assert `system_instruction` contains both SYSTEM texts (in order), and `contents` has exactly the three `USER`/`MODEL` segments in order. This is the shape every real call will use.

*No SYSTEM segments.* Build a list with only `USER` and `MODEL` segments. Assert `system_instruction` is an empty string (or whatever the Gemini SDK accepts for "no system instruction") and `contents` is fully populated.

*Single-segment list.* One `USER` segment only. Assert contents has one element, `system_instruction` is empty.

---

## DIFF 3

**TITLE:** `[llm_client][3/4]` Retry logic

**DESCRIPTION:**
Add `_submit_with_retry` to `LLMClient`. The method accepts a `GenerateContentRequest` and a `float` temperature, submits via the SDK, and on failure either retries (HTTP 429, HTTP 5xx, network errors) or re-raises immediately (HTTP 400, HTTP 403). Retries use exponential backoff starting at 1 s, doubling each attempt, capped at 60 s, up to `config.max_retries` attempts. Each failed attempt is logged (attempt number, error type, wait duration). After exhausting retries, raises. `complete()` still absent.

This diff addresses the only stateful, time-dependent logic in the package. The retry policy and error classification are safety-critical: getting them wrong could hang the simulation indefinitely or crash it on a recoverable error. Focused, mock-heavy tests are the only way to verify the policy without real API calls.

**TEST PLAN:**

*Transient error recovered.* Mock the SDK to fail with 429 twice, then succeed. Assert the method returns the successful response and that exactly two retries were attempted before success.

*Non-transient 400 raises immediately.* Mock the SDK to raise an HTTP 400. Assert the exception propagates without any retry and that no backoff was invoked.

*Non-transient 403 raises immediately.* Same as above for 403.

*Max retries exhausted.* Mock the SDK to always return 500. Assert that after exactly `max_retries` failed attempts the method raises, not loops forever.

*Backoff sequence.* With `max_retries=4` and a time mock, assert the wait durations follow the 1 s → 2 s → 4 s → 8 s progression. Also verify the cap: at high attempt counts the wait does not exceed 60 s regardless of the theoretical doubling.

*Network error is transient.* Mock the SDK to raise a connection-reset or timeout exception. Assert it is retried like a 5xx.

*Logging.* Capture log output across a two-failure scenario. Assert each failure entry contains the attempt number, a recognizable error indicator, and the wait duration. The log format is the sole observability path for API-level failures.

---

## DIFF 4

**TITLE:** `[llm_client][4/4]` complete()

**DESCRIPTION:**
Add `complete()` to `LLMClient` and the private `_TEMPERATURES: dict[CallType, float]` mapping. `complete()` looks up the temperature for the given `CallType`, calls `_build_contents` on the segment list, constructs a `GenerateContentRequest`, calls `_submit_with_retry`, unwraps the `GenerateContentResponse` into an `LLMResponse` (raw text verbatim, input/output token counts from usage metadata), and returns it. The method is `async def` (Trio coroutine). Callers supply segments; this method adds nothing to them.

This diff delivers the only public API surface of the package. It is intentionally thin: all substantive logic lives in `_build_contents` and `_submit_with_retry`, both already tested. The concerns here are temperature selection, response unwrapping, and the async boundary.

**TEST PLAN:**

*Temperature mapping — all four call types.* For each `CallType`, call `complete()` with a mock `_submit_with_retry` and assert the temperature passed to that mock matches the spec value (`ACTION_SELECTION=0.7`, `CONVERSATION_TURN=1.0`, `MEMORY_COMPACTION=0.2`, `RELATIONSHIP_UPDATE=0.4`). A wrong temperature is silent and would silently alter model behavior.

*Raw text returned verbatim.* Mock the SDK to return a response with leading/trailing whitespace in the text. Assert `LLMResponse.text` is identical to what the SDK returned — no stripping, no normalization.

*Token counts.* Mock a response with known `input_token_count` and `output_token_count` in usage metadata. Assert `LLMResponse.input_tokens` and `output_tokens` match exactly.

*End-to-end async smoke test.* Using `pytest-trio` (or equivalent), run a full `complete()` call against a fully mocked Gemini SDK — mock both the HTTP layer and the usage metadata. Assert the returned `LLMResponse` has the expected text and token counts. This test exercises the full call stack: segment list → `_build_contents` → request construction → `_submit_with_retry` → response unwrapping, all in one async execution, confirming the pieces compose correctly.
