Four style issues appended:

1. **`temperature: float` footgun** — callers must memorize which float maps to which call type; a `CallType` enum that owns the mapping internally is the fix.
2. **`cache_breakpoint_indices` is dead weight** — implicit caching means these indices have no runtime effect, the promised debug validation can't be implemented (per the existing ISSUE), and every caller still has to construct the list. Should be deleted.
3. **`complete()` will be a large mixed-concern function** — segment assembly, error classification, retry loop, and response unwrapping all in one place; needs private helpers.
4. **Indefinite retry is a footgun** — a sustained 429 hangs the simulation forever; a max-attempts cap is needed.