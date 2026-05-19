The Step 1 section is appended. Here's a summary of the decisions:

**Files (3 total):**
- `events.py` — pure data, no intra-project imports; EventType enum + ScheduledEvent dataclass
- `autobalance.py` — no intra-project imports; AutobalanceMultipliers + midnight adjustment function that takes primitive aggregates (averages, counts) rather than importing Villager/World State
- `simulation_engine.py` — imports everything; owns the main loop, all five dispatch handlers, and top-level state

**Key architectural note captured:** The autobalance adjustment logic is isolated in `autobalance.py` as a function that takes primitive aggregates, not subsystem references — this keeps the file import-free and the logic unit-testable without mocking.

**Objects assigned:**
- `EventType`, `ScheduledEvent` → `events.py`
- `AutobalanceMultipliers` → `autobalance.py`
- `SimulationEngine` → `simulation_engine.py`