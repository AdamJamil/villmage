Two flags and three issues added to `ai_coordinator.md`:

**FLAGS** (need your input):
1. **Thought capture in conversation turns** — BHVR-249 says thoughts are captured "each time villmagers are prompted for their next action." Conversation turns also prompt for action choices. Should `ConversationTurnResult` include thoughts?
2. **Post-conversation updates for early leavers** — BHVR-65's "ask each villmager" is ambiguous about whether villagers who chose LEAVE mid-conversation still get the social score / relationship update prompts at the end.

**ISSUEs** (implementation problems, no dev input needed):
1. **ACCEPT validation gap** — `parse_trade_turn` doesn't enforce BHVR-63 (ACCEPT only valid when other party's last action was MAKE_OFFER), even though `TradeSnapshot.history` is available.
2. **No live state in conversation prompt** — `assemble_conversation_turn` has no current stats or inventory, only memory logs. Villagers making social decisions (trade offers, requesting food) can't see their actual live state.
3. **Social score lacks relationship context** — `assemble_social_score` omits prior relationship data, so the LLM can't rate a conversation in character (e.g., despising the other person should affect the score).