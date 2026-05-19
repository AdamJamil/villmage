Five style notes added to `impl/world_state.md`:

1. **FuelType/ItemType duality** — `STICK` and `FIREWOOD` appear in both enums with no mapping; Action System must manually translate between them on every fire-tending call with no enforcement.

2. **Carcass creation footgun** — `add_carcass` registers the rot timer but the caller must separately add the item to storage; omitting either half silently breaks the invariant.

3. **Carcass removal footgun** — three independent calls must always co-occur (remove tracker, remove item, add dirtiness); any omission corrupts state silently.

4. **Dirtiness read-before-clear** — `clear_dirtiness` gives no return value, but Action System must read dirtiness before clearing to compute the cleanliness penalty; the API imposes no ordering, making it easy to silently drop the penalty.

5. **Fire scheduling footgun** — `add_fire_fuel` and `light_fire` return a timestamp that the caller must use to reschedule a heap event; the obligation is invisible in the type signature and easy to silently ignore.