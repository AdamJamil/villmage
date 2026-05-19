Two files:

- **`villmage/game_types.py`** — shared leaf for `ItemType`, `RestingSpotType`, and `ITEM_WEIGHT_G`. No project imports; imported by World State, Villager State, Action System, AI Coordinator.
- **`villmage/world_state.py`** — the subsystem proper: internal types (`FuelType`, `FuelUnit`, `DirtinessSource`, `Carcass`, `Fire`) plus the `WorldState` container with its full API surface.

The split keeps the shared/internal boundary explicit and avoids any import cycle — both World State and Villager State can import from `game_types` without needing to import from each other.