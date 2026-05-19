Plan written to `diffs/llm_client_plan.md`. Four diffs, each atomic:

1. **Types** — pure data leaf, no dependencies, no logic. Tests lock down enum values, defaults, and frozen enforcement.
2. **Content assembly** (`_build_contents`) — pure transform from `PromptSegment` list to Gemini API shapes. Tests cover SYSTEM extraction/concatenation, role mapping, and realistic mixed-prompt shapes.
3. **Retry logic** (`_submit_with_retry`) — the only stateful, time-dependent piece. Tests cover transient/non-transient classification, backoff sequence (with time mocking), max-retries exhaustion, and log output.
4. **`complete()`** — thin integration that ties temperature selection, content assembly, and retry together. Tests lock down all four temperatures (silent if wrong), verbatim text return (no normalization), token count forwarding, and a full async end-to-end smoke test.