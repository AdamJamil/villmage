Updated [subsystems/DEFINITION.md](/home/tack/code/villmage/subsystems/DEFINITION.md) to add `### Dependencies` for each outward-calling subsystem and to tighten `### Responsibilities` around ownership boundaries.

The main changes were:
- Made data ownership explicit: authored identity in `Character Canon`, canonical persistent facts in `World State Model`, derived survival math in `Survival State`, live conversation/trade state in `Social Interaction`, private cognition in `Memory And Relationships`, and prompt transport/validation in `Prompt And Model Interface`.
- Grouped cross-subsystem calls at the right level instead of repeating spec behaviors one by one.
- Clarified the highest-risk boundaries: action rules vs. world storage, social flow vs. long-term relationship state, orchestration vs. domain logic, and observability vs. source-of-truth state.

I did not run code checks since this was a documentation edit only.