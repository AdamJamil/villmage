The Core Functions section in `llm_client.md` now has:

- **`types.py`**: No logic functions — confirmed, only enum and frozen dataclasses.
- **`LLMClient.__init__`**: Tightened docstring: creates one `GenerativeModel` reused across all calls, key not stored after SDK init.
- **`LLMClient.complete`**: Tightened docstring covering SYSTEM extraction, USER/MODEL mapping, retry policy (429/5xx/network, 1s→2×→60s cap, indefinite), hard-raise on 400/403, and the debug-only purpose of `cache_breakpoint_indices`.

These are the only two core functions for this subsystem — everything else (backoff timing, segment assembly, log file writes) is internal implementation detail that two separate implementers can independently arrive at given the docstrings.