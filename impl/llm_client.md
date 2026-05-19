# LLM Client — Implementation Details

## Overview

LLM Client is a thin, stateless async wrapper around the Gemini Flash 2.5 API. It accepts prompt segments and cache breakpoint hints, handles transient error retries with exponential backoff, and returns raw completion text. It has no domain knowledge — all JSON parsing, validation, and malformed-output retrying happen in callers.

Two subsystems call into it:
- **AI Coordinator** — action selection, conversation turns, join decisions, social scores, relationship updates
- **Memory System** — short-term, medium-term, and long-term compaction prompts; relationship-update prompts

---

## Core Objects

### MessageRole

Role of a message segment as understood by the Gemini API. `SYSTEM` segments are extracted by the client and passed as Gemini's `system_instruction`; `USER` and `MODEL` segments become conversation turn contents.

```thrift
enum MessageRole {
    SYSTEM = 1,
    USER   = 2,
    MODEL  = 3,
}
```

---

### PromptSegment

One segment of a complete prompt. Callers construct an ordered list of these and pass it to `complete()`. Order must be static-to-dynamic for prefix caching to be effective.

```thrift
struct PromptSegment {
    1: MessageRole role,
    2: string text,
}
```

**Notes:**
- Multiple `SYSTEM` segments are concatenated in order and passed as a single `system_instruction` to Gemini.
- `USER` and `MODEL` segments become the `contents` list in order.
- The final segment before the model responds must have role `USER`.

---

### LLMResponse

The raw completion returned to callers. Includes token counts for diagnostic purposes.

```thrift
struct LLMResponse {
    1: string text,
    2: i32 input_tokens,
    3: i32 output_tokens,
}
```

**Notes:**
- `text` is the raw model output, completely unmodified — no stripping, no normalization.
- `input_tokens` and `output_tokens` are taken from Gemini usage metadata.

---

### LLMConfig

Construction-time configuration. Fixed for the lifetime of the client instance; all calls from a single `LLMClient` share these parameters.

```thrift
struct LLMConfig {
    1: string model = "gemini-2.5-flash",
    2: double temperature = 1.0,
    3: i32 max_output_tokens = 2048,
}
```

**Notes:**
- `max_output_tokens = 2048` is sufficient for all call types in this system: action selection JSON is ~100–200 tokens, compaction summaries are ≤256 tokens, conversation turns are short.
- CONST-261's "2k token budget" refers to the maximum prompt *input* size for memory context, not to `max_output_tokens`.
- Callers that need short outputs enforce this at the prompt level ("be extremely concise"), not by adjusting `max_output_tokens`.

---

## API Surface

- `complete(segments: list[PromptSegment], cache_breakpoint_indices: list[int]) -> LLMResponse`
  — Async Trio coroutine. Assembles the Gemini request, submits it, retries on transient errors, and returns the raw response.

**`cache_breakpoint_indices`:** Indices into `segments` marking the end of static/cacheable prefixes (e.g., `[3]` means segments 0–3 are the static prefix). The design decision is **implicit prefix caching only** — no explicit Gemini `CachedContent` API calls are made. These indices do not change runtime behavior; they document the static/dynamic boundary so callers declare their caching intent and so the ordering contract is machine-checkable. Callers must place static segments before dynamic ones; the client asserts this in debug builds.

---

## Key Behaviors

### Retry on Transient Errors

Transient: HTTP 429 (rate limit), HTTP 5xx (server error), network timeouts and resets.

Retry policy: exponential backoff starting at 1 s, doubling each attempt, capped at 60 s, indefinite retries until success or a non-transient error.

Non-transient: HTTP 400 (invalid request), HTTP 403 (auth failure). Raised immediately as exceptions with no retry. Callers treat these as hard failures.

The client logs each failed attempt (attempt number, error type, wait duration) to a structured log file. This is separate from BHVR-287's parse-error log — the LLM Client only logs API-level failures; callers log content-level failures.

### Caching Strategy

Implicit prefix caching only. Gemini Flash 2.5 automatically caches common prompt prefixes across requests within a session. No `CachedContent` objects are created or managed. The client's sole responsibility is to send segments in the order provided; the caller's responsibility is to provide them static-first.

### Async Concurrency (Trio)

`complete()` is an `async def` Trio coroutine. The client holds no mutable state between calls — each `complete()` call is fully independent. Callers that fan out across multiple villagers (e.g., parallel conversation turns) open a Trio nursery and launch one `complete()` task per call. The nursery ensures all tasks complete before the parent scope continues.

---

## What This Subsystem Does NOT Own

- JSON parsing or structural validation of model responses (AI Coordinator, Memory System)
- Retry logic for malformed model outputs — that is "one retry then crash" (AI Coordinator)
- Logging of parse errors and raw model responses on malformed output (AI Coordinator)
- Prompt construction (AI Coordinator, Memory System)
- Explicit Gemini context caching (not used)

---

## File Hierarchy

```
llm_client/
    types.py   — MessageRole enum, PromptSegment, LLMResponse, LLMConfig.
                 No logic. Import these types anywhere a type annotation is
                 needed without pulling in the Gemini SDK dependency.

    client.py  — LLMClient class. The only runtime API surface. Owns the
                 Gemini SDK client instance, handles Gemini Content assembly,
                 executes retry logic, and returns LLMResponse.
```

No `__init__.py` re-export layer. Callers import directly from `llm_client.types` or `llm_client.client`.

**Dependency direction:** `client.py` imports from `types.py` and the Gemini SDK. `types.py` imports nothing from within the package. No cycles.

---

## Object Assignments

### `llm_client/types.py`

#### `MessageRole`
Three-value enum mapping to Gemini's content roles. `SYSTEM` maps to Gemini's `system_instruction` field (extracted before submission by the client); `USER` and `MODEL` map to the `contents` list roles `"user"` and `"model"` respectively.

#### `PromptSegment`
Frozen dataclass pairing a `MessageRole` with a `text` string. The ordered list of these is the complete input to `complete()`. Callers are responsible for ordering (static first, dynamic last). No validation of ordering at construction time — validation is the client's responsibility.

#### `LLMResponse`
Frozen dataclass carrying the model's raw text output and Gemini usage token counts. `text` is returned verbatim.

#### `LLMConfig`
Frozen dataclass holding the three construction-time API parameters. All fields have defaults; callers may override only when the simulation entry point constructs the client.

---

### `llm_client/client.py`

#### `LLMClient`
The subsystem's sole API surface. Constructed with an `LLMConfig` and a Gemini API key (passed in by the simulation entry point, which reads it from the environment). Holds one Gemini SDK `GenerativeModel` instance. Exposes one async method, `complete()`.

Internally: extracts `SYSTEM` segments and concatenates them as `system_instruction`; maps remaining segments to Gemini `Content` objects preserving order; submits the request; applies the exponential backoff retry loop on transient errors; wraps the response in `LLMResponse`.

---

## Core Functions

### `llm_client/types.py`

`types.py` contains only enum and frozen dataclass definitions. No logic functions belong here.

---

### `llm_client/client.py`

#### `LLMClient`

```python
def __init__(self, config: LLMConfig, api_key: str) -> None:
    """Create one GenerativeModel instance reused for all complete() calls.
    api_key is passed to the SDK and not stored after initialization.
    """

async def complete(
    self,
    segments: list[PromptSegment],
    cache_breakpoint_indices: list[int],
) -> LLMResponse:
    """Submit a prompt to Gemini and return the raw completion.

    SYSTEM segments are concatenated and sent as system_instruction.
    USER/MODEL segments become the contents list in order.
    Retries 429/5xx/network errors with exponential backoff (1s start,
    2× each attempt, 60s cap, indefinite). Raises immediately on 400/403.
    cache_breakpoint_indices is validated in debug builds (static segments
    must precede dynamic) but does not affect the Gemini request.
    """
```

---

## File Docstrings

### `llm_client/types.py`

```python
"""Data types for the LLM client subsystem.

Defines MessageRole, PromptSegment, LLMResponse, and LLMConfig — the complete
set of types needed to call LLMClient.complete(). Import from here whenever you
need LLM-client type annotations without pulling in the Gemini SDK as a
dependency.
"""
```

### `llm_client/client.py`

```python
"""Async Gemini API wrapper.

The only runtime entry point for the llm_client subsystem. Construct one
LLMClient at simulation startup and share it across AI Coordinator and Memory
System. Handles Gemini request assembly, exponential-backoff retry on transient
API errors, and response unwrapping. Returns raw text; all JSON parsing and
malformed-output retry logic are the caller's responsibility.
"""
```

---

## Object Docstrings

### `MessageRole` (`llm_client/types.py`)

```python
"""Role of one prompt segment as understood by the Gemini API.

SYSTEM segments are concatenated and passed as system_instruction. USER and
MODEL segments form the interleaved contents list. The final segment before
the model responds must be USER.
"""
```

### `PromptSegment` (`llm_client/types.py`)

```python
"""A single segment of a complete prompt, pairing a MessageRole with text.

Build an ordered list of PromptSegments and pass it to LLMClient.complete().
Order must be static-to-dynamic so the longest common prefix is cacheable across
calls for the same villager. Frozen after construction.
"""
```

### `LLMResponse` (`llm_client/types.py`)

```python
"""Raw completion returned by LLMClient.complete().

text is the model output verbatim — no stripping or normalization. Callers are
responsible for JSON parsing and structural validation. Token counts are provided
for diagnostic logging only.
"""
```

### `LLMConfig` (`llm_client/types.py`)

```python
"""Construction-time API parameters for LLMClient, fixed for the client lifetime.

All fields have defaults matching the simulation's requirements. Override only at
the simulation entry point; never modify per-call.
"""
```

### `LLMClient` (`llm_client/client.py`)

```python
"""Thin async wrapper around the Gemini Flash 2.5 API.

Construct once with an LLMConfig and API key (read from the environment at the
simulation entry point). Call complete() to submit a prompt and receive raw
completion text. Domain concerns — JSON parsing, malformed-output retry, prompt
construction — belong to callers (AI Coordinator, Memory System).
"""
```

---

→ FLAG: `spec.md` never specifies a temperature for LLM calls. `llm_client.md` sets `temperature = 1.0` for all call types — action selection, conversation turns, memory compaction, and relationship updates all share this single value. Temperature meaningfully shapes character behavior: higher values produce more varied and surprising decisions; lower values produce more consistent, predictable ones. Additionally, different call types have different stakes — a memory compaction summary benefits from low-temperature accuracy, while a conversation turn might benefit from higher-temperature spontaneity.
    What temperature should LLM calls use?

→ ISSUE: The `complete()` docstring and API surface section both state that `cache_breakpoint_indices` is "validated in debug builds" to enforce "static segments must precede dynamic." The client receives a list of `PromptSegment` objects whose content it does not interpret — it has no semantic basis for determining which segments are static and which are dynamic. The claimed assertion cannot be implemented as described; the client can at most check that the supplied indices are in-bounds integers.
