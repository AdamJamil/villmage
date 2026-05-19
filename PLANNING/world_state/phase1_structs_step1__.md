The file is written. Here's a summary of the key decisions made:

**Shared types note** — `ItemType` and `RestingSpotType` can't live in either World State or Villager State since both are leaves; I've flagged them for a `game_types` module that both can safely import from, along with the item weight table.

**Fire model** — The fuel queue is a FIFO list of `FuelUnit` batches (type + quantity). The extinction timestamp is a derived cache valid only when lit; Action System must notify Simulation Engine to reschedule its heap event whenever fuel is added or the fire is relit.

**Carcass tracking** — `live_carcasses` mirrors all carcasses regardless of whether they're in inventory or base storage, to give Simulation Engine a single place to schedule rot events. The invariant (live count == physical count) is Action System's responsibility to maintain. Butcher always removes the oldest carcass (min arrival timestamp) to be deterministic.

**Dirtiness** — Stored as raw counts per source type; `total_dirtiness` is derived with a cap of 100. Cleaning zeroes all counts in one shot.

**`placed_resting_spots`** — Explicitly not in `base_storage`; placed objects leave inventory and enter this map, with Villager State's `sleep_spot_claim` tracking the claim side separately.