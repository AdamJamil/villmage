The file looks good. Here's a summary of what I wrote:

**Two core objects owned by Conversation System:**

1. **`ActiveTrade`** — in-flight trade sub-protocol state: `initiator_id`, `partner_id`, `history: list[TradeTurnRecord]`, `turn_count`. Everything else (whose turn, accept validity, cancel trigger) is derivable.

2. **`ConversationSession`** — in-flight conversation state: `participant_ids` (in join order), `full_turn_log` (unfiltered), `join_turn_index` (maps each participant to the turn index where they first entered — 0 for original pair, `len(full_turn_log)` at join time for latecomers), `elapsed_game_minutes`, `last_spoke_turn` (for recency tiebreak, initialized to -1), and `active_trade`.

The key implementation decisions hammered out in the logic notes:
- `ConversationSnapshot.history` is constructed by slicing `full_turn_log[join_turn_index[v]:]` — no separate per-participant logs maintained
- LEAVE is processed concurrently (all leavers always honored) before priority resolution on the remaining actions
- SILENT turns don't generate a `ConversationTurn` entry but still advance time
- Post-conversation queries (social score, relationship updates) go only to participants still present at the end — mid-conversation leavers are excluded
- Turn text format convention is specified since it's verbatim in prompts and Memory System