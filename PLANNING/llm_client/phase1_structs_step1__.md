`impl/llm_client.md` is written. The four core objects are:

- **`MessageRole`** — enum with `SYSTEM/USER/MODEL`; `SYSTEM` segments get extracted and passed as Gemini's `system_instruction`, the rest become `contents` turns
- **`PromptSegment`** — frozen (role, text) pair; the ordered list is the complete input to `complete()`
- **`LLMResponse`** — frozen (text, input_tokens, output_tokens); text is verbatim unmodified
- **`LLMConfig`** — construction-time config (model, temperature, max_output_tokens); shared across all calls from one instance; defaults to `gemini-2.5-flash`, temp 1.0, 2048 output tokens

Key decisions captured: implicit prefix caching only (`cache_breakpoint_indices` is advisory/debug-checkable, not behavior-changing), Trio async with independent per-call state, exponential backoff for transient errors (1s→60s cap, indefinite), hard raise on non-transient errors, API key passed in at construction.