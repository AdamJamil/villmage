# LLM Client — Implementation Details

## Overview

LLM Client is a thin, stateless async wrapper around the Gemini Flash 2.5 API. It accepts prompt segments and a call type, handles transient error retries with exponential backoff, and returns raw completion text. It has no domain knowledge — all JSON parsing, validation, and malformed-output retrying happen in callers.

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

### CallType

The purpose of an LLM call, used to select the appropriate temperature (CONST-290). Callers declare intent; the client maps to the right float internally.

```thrift
enum CallType {
    ACTION_SELECTION    = 1,   // temperature 0.7
    CONVERSATION_TURN   = 2,   // temperature 1.0
    MEMORY_COMPACTION   = 3,   // temperature 0.2
    RELATIONSHIP_UPDATE = 4,   // temperature 0.4
}
```

**Notes:**
- The temperature mapping is a private constant in `client.py`; `types.py` defines only the enum.
- Callers never supply a raw float — incorrect temperatures are not possible.

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

Construction-time configuration. Fixed for the lifetime of the client instance.

```thrift
struct LLMConfig {
    1: string model          = "gemini-2.5-flash",
    2: i32 max_output_tokens = 2048,
    3: i32 max_retries       = 10,
}
```

**Notes:**
- `max_output_tokens = 2048` is sufficient for all call types in this system: action selection JSON is ~100–200 tokens, compaction summaries are ≤256 tokens, conversation turns are short.
- CONST-261's "2k token budget" refers to the maximum prompt *input* size for memory context, not to `max_output_tokens`.
- `max_retries = 10` applies only to transient API errors (429, 5xx, network). With exponential backoff starting at 1 s and capping at 60 s, 10 retries allow up to ~5 minutes of retry window before a hard failure.

---

## API Surface

- `complete(segments: list[PromptSegment], call_type: CallType) -> LLMResponse`
  — Async Trio coroutine. Assembles the Gemini request at the temperature corresponding to `call_type`, submits it, retries on transient errors up to `max_retries` times, and returns the raw response.

Callers are responsible for ordering segments static-to-dynamic so the longest common prefix is cacheable across calls for the same villager within a session.

---

## Key Behaviors

### Retry on Transient Errors

Transient: HTTP 429 (rate limit), HTTP 5xx (server error), network timeouts and resets.

Retry policy: exponential backoff starting at 1 s, doubling each attempt, capped at 60 s, up to `config.max_retries` attempts. After exhausting retries, raises a hard exception.

Non-transient: HTTP 400 (invalid request), HTTP 403 (auth failure). Raised immediately as exceptions with no retry. Callers treat these as hard failures.

The client logs each failed attempt (attempt number, error type, wait duration) to a structured log file. This is separate from BHVR-287's parse-error log — the LLM Client only logs API-level failures; callers log content-level failures.

### Caching Strategy

Implicit prefix caching only. Gemini Flash 2.5 automatically caches common prompt prefixes across requests within a session. No `CachedContent` objects are created or managed. Callers must supply segments static-first; the client sends them in the order provided.

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
    types.py   — MessageRole enum, CallType enum, PromptSegment, LLMResponse,
                 LLMConfig. No logic. Import these types anywhere a type
                 annotation is needed without pulling in the Gemini SDK dependency.

    client.py  — LLMClient class. The only runtime API surface. Owns the
                 Gemini SDK client instance, the CallType→temperature mapping,
                 Gemini Content assembly, retry logic, and response unwrapping.
```

No `__init__.py` re-export layer. Callers import directly from `llm_client.types` or `llm_client.client`.

**Dependency direction:** `client.py` imports from `types.py` and the Gemini SDK. `types.py` imports nothing from within the package. No cycles.

---

## Object Assignments

### `llm_client/types.py`

#### `MessageRole`
Three-value enum mapping to Gemini's content roles. `SYSTEM` maps to Gemini's `system_instruction` field (extracted before submission by the client); `USER` and `MODEL` map to the `contents` list roles `"user"` and `"model"` respectively.

#### `CallType`
Four-value enum identifying the purpose of an LLM invocation. Members correspond directly to the four call types in CONST-290. The client maps each member to its temperature internally; callers never supply a raw float.

#### `PromptSegment`
Frozen dataclass pairing a `MessageRole` with a `text` string. The ordered list of these is the complete input to `complete()`. Callers are responsible for ordering (static first, dynamic last).

#### `LLMResponse`
Frozen dataclass carrying the model's raw text output and Gemini usage token counts. `text` is returned verbatim.

#### `LLMConfig`
Frozen dataclass holding the three construction-time API parameters. All fields have defaults; callers may override only when the simulation entry point constructs the client.

---

### `llm_client/client.py`

#### `LLMClient`
The subsystem's sole API surface. Constructed with an `LLMConfig` and a Gemini API key (passed in by the simulation entry point, which reads it from the environment). Holds one Gemini SDK `GenerativeModel` instance and a private `_TEMPERATURES: dict[CallType, float]` mapping. Exposes one async method, `complete()`.

Internally, `complete()` delegates to two private helpers:
- `_build_contents(segments)` — extracts and concatenates `SYSTEM` segments as `system_instruction`; maps remaining segments to Gemini `Content` objects in order.
- `_submit_with_retry(request, temperature)` — runs the exponential-backoff retry loop, classifies errors as transient or non-transient, logs each failed attempt, and raises after `max_retries` exhausted.

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
    call_type: CallType,
) -> LLMResponse:
    """Submit a prompt to Gemini and return the raw completion.

    Temperature is determined by call_type per CONST-290. SYSTEM segments are
    concatenated and sent as system_instruction. USER/MODEL segments become the
    contents list in order. Retries 429/5xx/network errors with exponential
    backoff (1s start, 2× each attempt, 60s cap) up to config.max_retries times,
    then raises. Raises immediately on 400/403.
    """

def _build_contents(
    self,
    segments: list[PromptSegment],
) -> tuple[str, list[Content]]:
    """Extract system instruction and build the Gemini contents list.

    Returns (system_instruction, contents). system_instruction is the
    concatenation of all SYSTEM segments; contents preserves the order of
    USER and MODEL segments.
    """

async def _submit_with_retry(
    self,
    request: GenerateContentRequest,
    temperature: float,
) -> GenerateContentResponse:
    """Submit request with exponential-backoff retry on transient errors.

    Transient: 429, 5xx, network errors. Non-transient (400, 403) raise
    immediately. Raises after config.max_retries failed attempts. Logs each
    failure with attempt number, error type, and wait duration.
    """
```

---

## File Docstrings

### `llm_client/types.py`

```python
"""Data types for the LLM client subsystem.

Defines MessageRole, CallType, PromptSegment, LLMResponse, and LLMConfig — the
complete set of types needed to call LLMClient.complete(). Import from here
whenever you need LLM-client type annotations without pulling in the Gemini SDK
as a dependency.
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

### `CallType` (`llm_client/types.py`)

```python
"""Purpose of an LLM invocation, used to select the correct temperature.

Members correspond to the four call types in CONST-290. The temperature
mapping lives in client.py; callers declare intent here rather than supplying
a raw float.
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
