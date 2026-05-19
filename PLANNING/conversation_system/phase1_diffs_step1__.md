9 diffs written to `diffs/conversation_system_plan.md`. Here's the structure:

| # | Title | What it adds |
|---|-------|-------------|
| 1/9 | Types | `ConversationSession`, `ActiveTrade`, `snapshot_for` — pure data |
| 2/9 | format_turn_text | Pure string formatter for all action types |
| 3/9 | _select_winner | Priority + recency tiebreak algorithm |
| 4/9 | _resolve_single_turn | One full turn: parallel prompts, LEAVE processing, winner dispatch, memory writes |
| 5/9 | _pause_for_joiners | Post-turn-2 join pause with opening-excerpt snapshot |
| 6/9 | _run_trade_subprotocol | Full trade sub-protocol: ACCEPT validity, cancellation at 6 turns, inventory transfer |
| 7/9 | _run_turn_loop | Loop driver: end conditions, 5-min increments, join pause timing, trade suspension |
| 8/9 | _apply_post_conversation_updates | Social score delta, +20 connectedness, ordered-pair relationship writes |
| 9/9 | run_conversation | Entry point + integration test |

The test plans are weighted toward the tricky behavioral invariants: the ACCEPT validity rule (BHVR-63 — invalid ACCEPTs are no-ops that still consume a turn), the exactly-one join-pause timing, the per-participant snapshot slicing for early leavers, and trade event visibility to all conversation participants (not just the two traders).