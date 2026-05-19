All seven issues resolved and the Flags section removed. Summary of changes:

- **Clamping** — post-conversation flow now says "clip the result `social_joy + delta` to [0, 100]" (not the delta)
- **BHVR-44** — `run_conversation` returns `tuple[int, list[str]]`; Simulation Engine uses the participant list to reschedule interrupted tasks
- **`all_participant_ids`** — added as an append-only field on `ConversationSession` alongside the shrinking `participant_ids`; post-conversation flow iterates over it
- **`last_spoke_turn` sentinel** — absent map entry replaces `-1`; tiebreak description updated accordingly
- **`snapshot_for`** — method on `ConversationSession`; all snapshot construction sites reference it; `types.py` now imports `ConversationSnapshot`
- **`format_turn_text`** — extracted to a standalone pure function in `conversation.py`; `_resolve_single_turn` calls it
- **`_select_winner`** — new helper carrying all priority/tiebreak logic out of `_resolve_single_turn`