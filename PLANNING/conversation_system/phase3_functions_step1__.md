The core functions are appended to `conversation_system.md`. Here's a summary of what was defined:

**`types.py`** — no methods; both structs are pure data.

**`ConversationSystem`** — six core functions:

| Function | Role |
|---|---|
| `run_conversation` | Public entry point; initializes session, runs loop, applies post-conv updates, returns elapsed minutes |
| `_run_turn_loop` | Iteration driver; handles join-pause after turn 2, triggers trade sub-protocol on TRADE wins |
| `_resolve_single_turn` | Single turn: parallel prompting (turn-0 initiator-only), LEAVE processing, priority+recency resolution, memory writes |
| `_pause_for_joiners` | Queries bystanders in parallel after turn 2, adds joiners atomically |
| `_run_trade_subprotocol` | Full trade protocol: alternates turns, validates ACCEPT per BHVR-63, cancels after 6 turns, transfers items, writes trade events to all participant logs |
| `_apply_post_conversation_updates` | Social scores → `social_joy` delta, `+20 connectedness`, relationship impression writes for all non-leavers |