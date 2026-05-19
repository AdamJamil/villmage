Two findings appended:

**FLAG — Temperature**: `spec.md` never specifies a temperature. `llm_client.md` picks `1.0` for all call types uniformly. Since temperature affects how creatively/consistently the LLM plays characters and summarizes memories (and the tradeoffs differ per call type), this is a creative-vision decision that needs your input.

**ISSUE — Unimplementable debug assertion**: The doc claims `cache_breakpoint_indices` is validated in debug builds to check "static segments must precede dynamic," but the client has no way to make that semantic distinction — it only sees opaque `PromptSegment` text. The assertion as written cannot be implemented; at best the client can bounds-check the indices.