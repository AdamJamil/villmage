Design doc written to `design/DESIGN.md`. Summary of what was flagged:

**Per-subsystem ambiguities** (13 total):
- **Character Canon**: `gatherer` is referenced in BHVR-38 but not listed as a profession in ATTR-37 — affects all exploration gating. Harren's "builder" profession maps to nothing mechanical.
- **Villager State**: Starting stats unspecified for most fields. Base cleanliness has no normalization formula (raw dirtiness → 0–1 score). Whether sleep resets the rest buff (`r` in the mood formula) is undefined — if it doesn't, villagers who never explicitly rest take a permanent mood penalty.
- **World State**: Carcass rot outcome undefined — does it become "remains" (adding dirtiness) or just vanish?
- **Simulation Engine**: Forced sleep has no duration rule. Safety recalculation timing is vague. Autobalance multipliers have no bounds and could diverge.
- **Action System**: "At base" has no precise definition. Cooking action behavior if fire extinguishes mid-cook. Whether crafting draws from base inventory or personal inventory only.
- **Conversation System**: Join prompt timing (pause vs. proceed). Trade acceptance edge case (both parties accepting directly doesn't resolve a trade — only accepting in response to an offer does).
- **Memory System**: Long-term compaction trigger frequency unclear.
- **AI Coordinator / LLM Client**: Model is only named once (Gemini Flash 2.5) — needs confirmation.
- **Observability**: Checkpoint-restart format not designed. Perspective filter definition needed before event log schema can be locked.

**Cross-cutting concerns raised**:
- The food safety score formula in CONST-202 multiplies calories × (cal/day) instead of dividing — dimensional error, likely a typo.
- Firewood safety references "the night" but no day/night cycle is defined anywhere.