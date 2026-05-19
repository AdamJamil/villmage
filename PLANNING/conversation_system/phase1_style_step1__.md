Five style issues appended:

1. **`_resolve_single_turn` cyclomatic complexity** — seven distinct responsibilities in one function; the priority/tiebreak selection and Memory System write should each be separate helpers.

2. **Early-leaver tracking footgun** — `participant_ids` shrinks on LEAVE but post-conversation updates need the full historical roster; no `all_participant_ids` field exists in `ConversationSession`, making it easy to silently drop leavers.

3. **`last_spoke_turn` sentinel `-1`** — implicit integer convention that every consumer must know; should be `Optional[int]` so the type system enforces the check.

4. **`ConversationSnapshot` construction repeated inline** — the `full_turn_log[join_turn_index[v]:]` slice appears in at least three functions; should be a `snapshot_for(villager_id)` method on `ConversationSession`.

5. **Turn text formatting has no home** — the per-`ConvActionType` string templates are assigned to Conversation System but will end up embedded in `_resolve_single_turn`; should be a standalone pure function.