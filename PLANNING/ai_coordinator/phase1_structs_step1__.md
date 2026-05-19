Here's a summary of the core objects defined:

**Classification/Logging:**
- `LLMCallType` — enum of the 6 prompt types, used only in failure logs
- `ParseFailureLog` — disk record written on every parse failure (BHVR-287), including prompt, raw response, error, and retry flag

**Conversation turn system:**
- `ConvActionType` — the 9 turn options from VRBTM-46 (LEAVE through TRADE)
- `ConversationTurn` — single turn entry with speaker id and self-contained text
- `ConversationSnapshot` — visibility-filtered history + participant list, constructed by Conversation System and passed to all conversation-related calls
- `ConversationTurnResult` — parsed turn output; validates `resp` is present for options 3–8

**Trade sub-protocol:**
- `TradeActionType` — 4 trade actions from VRBTM-59
- `TradeItemSpec` — item + quantity in a trade offer
- `TradeTurnRecord` — one resolved trade turn for the history
- `TradeSnapshot` — full trade history passed to `get_trade_turn`; sufficient to determine ACCEPT validity (BHVR-63)
- `TradeTurnResult` — parsed trade output with inventory validation for MAKE_OFFER

**Action selection:**
- `ActionSelectionResult` — wraps `SelectedAction` (from Action System) + optional thought string

**Relationship:**
- `RelationshipUpdateResult` — impression + optional description replacement

Key design decisions captured: `ConversationSnapshot` is owned here (not in Conversation System) since Conversation System → AI Coordinator is the dependency direction, not the reverse; trade turn handling is an implicit but necessary API not listed in design.md; memory compaction stays with Memory System calling LLM Client directly.