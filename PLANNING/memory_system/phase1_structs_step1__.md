The core objects for Memory System are defined. Here's the summary:

**6 core types:**

- **`EventType`** — enum categorizing log entries (ACTION, THOUGHT, CONVO_TURN, TRADE, BASE_EVENT). Needed so observability can filter and display correctly, and so thoughts can be identified inline in the log.

- **`EventLogEntry`** — a timestamped, typed, text entry appended to a villager's perspective-filtered log. Filtering happens at the caller (Sim Engine / Conversation System), not here.

- **`MemoryEntry`** — a single LLM-compacted summary at any tier (short/medium/long-term). All three tiers share the same struct — the distinction is which list they live in. `game_time` is the only metadata needed since day can be derived from it (`// 1440`).

- **`RelationshipRecord`** — one ordered pair (x, y): a ≤128-token description plus a FIFO-3 impressions queue. Initialized for all 30 pairs at startup.

- **`CompactionReason`** — SLEEP or AWAKE_THRESHOLD, for diagnostic logging on short-term compaction. Midnight and long-term compactions don't use this since they're global triggers.

- **`VillagerMemoryContext`** — the assembled return value of `get_memory_context()`, containing all four tiers (long/medium/short-term + active context log) and the relationships map. This is what AI Coordinator uses to build the memory sections of the villager prompt.