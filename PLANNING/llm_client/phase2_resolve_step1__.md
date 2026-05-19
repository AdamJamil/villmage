The document is updated. Here's a summary of what changed and why:

- **Removed `cache_breakpoint_indices`** from the API entirely. No runtime effect, unimplementable validation promise — dead parameter. The ordering contract is now a caller doc concern only.
- **Replaced `temperature: float` with `call_type: CallType`**. Added a `CallType` enum to `types.py` with four members matching CONST-290. The client holds a private `_TEMPERATURES` dict; callers can no longer pass a wrong float.
- **Added `max_retries: int = 10` to `LLMConfig`**. 10 retries with the backoff schedule gives ~5 minutes of retry window — enough to ride out a brief outage, not enough to hang the process forever.
- **Extracted two private helpers** from `complete()`: `_build_contents` (segment assembly) and `_submit_with_retry` (retry loop). Each has a single clear responsibility.
- **Removed all `→ ISSUE` / `→ STYLE` annotations** — the document now reads as written in one shot.