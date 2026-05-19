The document is updated. Here's what was resolved and what was left alone:

**Fixed:**
- `parse_trade_turn` now enforces BHVR-63 — added `last_other_action` parameter so the parser can reject out-of-sequence ACCEPT
- `assemble_conversation_turn` now includes `computed_stats` and `inventory_items` — villagers can reference their live condition during conversation
- `PromptPackage` dataclass replaces the unnamed tuple return type across all `assemble_*` functions
- `RelationshipRecord` groups description + impressions — prevents mismatched pair extraction at the `assemble_relationship_update` call site
- `_call` private method unifies the assemble → invoke → parse → retry-once → crash sequence; public methods delegate to it
- `GameTime` type alias used throughout coordinator signatures (imported from `game_types`)

**Left alone:**
- `assemble_social_score` still has no relationship data — the conversation history is sufficient context for a 0–10 score
- `VillagerId` stays as bare `str` — a newtype would require wrapping every villager ID at every call site across all subsystems
- Caller-side pre-filtering stays documented-in-docstring rather than wrapped in a separate type — `JoinDecisionSnapshot` adds a type boundary without adding any logic