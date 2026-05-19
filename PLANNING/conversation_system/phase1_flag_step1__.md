Four flags and two issues added to `conversation_system.md`:

**Flags (dev input required):**
- **Trade transfer direction** — BHVR-63 defines *when* to accept but not *what* transfers; the doc picks unidirectional but bilateral may be intended.
- **Leavers and post-conversation updates** — BHVR-65/66/73 are silent on whether mid-conversation leavers receive social joy, connectedness, or relationship updates.
- **Turn priority order** — BHVR-50 references "the listed priority order" with no explicit source; the VRBTM-46 option numbers don't match the doc's ordering and would produce nonsensical results if taken literally.
- **BHVR-44 scope for voluntary joiners** — "pulled into a conversation" may only cover the original target, not bystanders who choose to join.

**Issues (implementation errors):**
- **Social joy clamping** — the doc clips the *delta* to [0, 100]; the spec requires clipping the *result*, which gives different outputs.
- **No task-pause mechanism in API** — `run_conversation` returns only elapsed minutes; Conversation System has no way to signal Simulation Engine to reschedule in-progress action events for conversation participants, making BHVR-44 unimplementable with the current interface.