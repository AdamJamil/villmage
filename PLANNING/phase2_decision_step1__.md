Done. I've appended a `## DECISIONS` section to `design/DESIGN.md` with six entries:

**Already decided (documenting the commitment):**
- Discrete-event simulation — correctly chosen, sticky
- Conversations block the simulation — correct per spec, non-obvious cost

**Unresolved (needs your input):**
- **Python concurrency model** — highest blast radius; affects every LLM call site. Proposing `asyncio` throughout.
- **Game time representation** — affects every timestamp. Proposing plain `int` minutes from epoch.
- **Persistence format** — affects Observability replay and checkpoint restart. Proposing `.jsonl` event log + `.json` checkpoint files.
- **LLM model scope + caching mechanism** — the riskiest assumption. CONST-261 names Gemini Flash 2.5 but caching semantics (implicit vs. explicit Cache API) are unverified. Recommend prototyping one full prompt before finalizing LLM Client design.
- **Event heap invalidation** — needed for conversation pause/resume. Proposing lazy invalidation via per-villager generation tokens.