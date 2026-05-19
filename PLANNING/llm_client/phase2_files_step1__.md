Appended two new sections to `impl/llm_client.md`:

**File Docstrings** — module-level triple-quote docstrings for `types.py` and `client.py`, written from a "new dev" perspective: what lives there, when to import from it, and what the file's one responsibility is.

**Object Docstrings** — class-level docstrings for `MessageRole`, `PromptSegment`, `LLMResponse`, `LLMConfig`, and `LLMClient`. Each one explains what the object *is* and how to use it without restating logic that belongs in method docstrings. Key details surfaced: the static-to-dynamic ordering requirement on `PromptSegment`, the verbatim-text contract on `LLMResponse`, and the "construct once, share widely" usage pattern for `LLMClient`.