The Step 1 content has been appended to `impl/conversation_system.md`. Here's a summary of what was added:

**Files (2 total, matching the existing skeleton):**
- `types.py` — pure data structures, no logic, no LLM dependency; only imports from `ai_coordinator.types`
- `conversation.py` — all orchestration logic in `ConversationSystem`; imports from `types.py` and every subsystem it calls

**Objects (3 total):**
- `ActiveTrade` (in `types.py`) — in-flight trade state; `turn_count % 2` derives whose turn it is rather than storing it
- `ConversationSession` (in `types.py`) — in-flight conversation state; the `join_turn_index` map is called out specifically as what enables per-participant history slicing before prompting
- `ConversationSystem` (in `conversation.py`) — stateless between calls; single entry point `run_conversation`

The two-file structure is already minimal and correct — splitting further (e.g., separating trade logic) would add indirection without adding clarity, since both `ActiveTrade` and `ConversationSession` are consumed exclusively by `ConversationSystem`.