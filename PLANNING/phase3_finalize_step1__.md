Three issues found and fixed:

1. **BHVR-52 missing (conversation turn 1)** — the design doc said "all participants prompted in parallel" with no exception. The spec is explicit that turn 1 only queries the initiating villmager. Easy implementation mistake.

2. **BHVR-73 missing (connectedness update)** — the +20 flat connectedness boost applied to all participants after a conversation was entirely absent from the design doc. It would have been silently skipped.

3. **Post-conversation social_joy destination** — the design doc said "results written to Memory System" but social_joy updates go to Villager State; Memory System only gets impressions and relationship description updates. Also clarified this in the same fix.

4. **Memory System compaction trigger phrasing** — "≥4 hours awake" is the condition, but the trigger event is specifically completing an action (not just the passage of time). Corrected to match BHVR-252.

No fundamental architectural problems found. The ambiguities already documented (gatherer profession, forced sleep duration, carcass rot outcome, safety formula dimensional error, etc.) are all genuine and worth resolving before implementation.