# pyre-strict

"""Tests for action-system start and completion effects."""

from __future__ import annotations

from copy import deepcopy

import pytest

from action_system.effects import apply_completion_effect, apply_start_effect
from action_system.types import ActionContext, ActionType, AutobalanceMultipliers, SelectedAction
from character_canon.canon import CharacterCanon
from villmage.game_types import CraftableItem, ItemType, RestingSpotType
from villmage.villager_state import CraftingProgress, VillagerState
from villmage.world_state import FuelType, WorldState


def make_ctx(
    villager_id: str = "ivette",
    multipliers: AutobalanceMultipliers | None = None,
) -> ActionContext:
    """Build a minimal action context for one authored villager."""

    villager_state = VillagerState(villager_id)
    return ActionContext(
        villager_id=villager_id,
        canon=CharacterCanon(),
        vs=villager_state,
        all_states={villager_id: villager_state},
        ws=WorldState(),
        multipliers=(
            AutobalanceMultipliers() if multipliers is None else multipliers
        ),
    )


def make_action(action_type: ActionType, **args: object) -> SelectedAction:
    """Build one selected action with the provided authored args."""

    return SelectedAction(action_type=action_type, **args)


def test_craft_new_consumes_materials_from_inventory_only() -> None:
    """Crafting should spend inventory materials before touching base storage."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 2)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.PROCESSED_HIDE] == 1
    assert ctx.vs.crafting_in_progress == CraftingProgress(
        item=CraftableItem.SATCHEL,
        minutes_spent=0,
    )


def test_craft_new_consumes_materials_from_base_when_inventory_is_empty() -> None:
    """Crafting should fall back to base storage when inventory lacks materials."""

    ctx = make_ctx()
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 1)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    assert ctx.ws.base_storage[ItemType.PROCESSED_HIDE] == 0


def test_craft_new_splits_material_consumption_across_inventory_and_base() -> None:
    """Crafting should exhaust inventory first and then consume the remainder from base."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)
    ctx.ws.modify_base_item(ItemType.LOG, 5)
    ctx.ws.modify_base_item(ItemType.STICK, 25)
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 3)
    ctx.ws.modify_base_item(ItemType.LEAVES, 400)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.COT,
        ),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.PROCESSED_HIDE] == 0
    assert ctx.ws.base_storage[ItemType.PROCESSED_HIDE] == 0


def test_craft_new_raises_when_materials_are_insufficient() -> None:
    """Crafting should reject malformed starts that lack enough materials."""

    ctx = make_ctx()

    with pytest.raises(ValueError):
        apply_start_effect(
            make_action(
                ActionType.CRAFT_NEW,
                craftable_item=CraftableItem.SATCHEL,
            ),
            ctx,
        )


def test_craft_new_sets_crafting_in_progress() -> None:
    """Crafting should start a fresh progress snapshot at zero minutes."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 1)

    apply_start_effect(
        make_action(
            ActionType.CRAFT_NEW,
            craftable_item=CraftableItem.SATCHEL,
        ),
        ctx,
    )

    crafting = ctx.vs.crafting_in_progress
    assert crafting is not None
    assert crafting.item is CraftableItem.SATCHEL
    assert crafting.minutes_spent == 0


def test_continue_crafting_is_a_no_op() -> None:
    """Continuing a job should not spend materials or mutate progress."""

    ctx = make_ctx()
    ctx.vs.set_crafting_state(
        CraftingProgress(item=CraftableItem.SATCHEL, minutes_spent=60)
    )
    ctx.vs.modify_inventory(ItemType.PROCESSED_HIDE, 2)
    ctx.ws.modify_base_item(ItemType.PROCESSED_HIDE, 3)
    before_vs = deepcopy(ctx.vs)
    before_ws = deepcopy(ctx.ws)

    apply_start_effect(make_action(ActionType.CONTINUE_CRAFTING), ctx)

    assert ctx.vs.__dict__ == before_vs.__dict__
    assert ctx.ws.__dict__ == before_ws.__dict__


def test_add_sticks_prefers_inventory_over_base() -> None:
    """Adding sticks should consume carried sticks before stored sticks."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.STICK, 3)
    ctx.ws.modify_base_item(ItemType.STICK, 5)

    apply_start_effect(
        make_action(ActionType.ADD_STICKS, quantity=4),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.STICK] == 0
    assert ctx.ws.base_storage[ItemType.STICK] == 4
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.STICK
    assert ctx.ws.fire.fuel_queue[-1].quantity == 4


def test_add_sticks_consumes_from_base_when_inventory_is_empty() -> None:
    """Adding sticks should fall back to base storage when needed."""

    ctx = make_ctx("harren")
    ctx.ws.modify_base_item(ItemType.STICK, 5)

    apply_start_effect(
        make_action(ActionType.ADD_STICKS, quantity=3),
        ctx,
    )

    assert ctx.ws.base_storage[ItemType.STICK] == 2
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.STICK
    assert ctx.ws.fire.fuel_queue[-1].quantity == 3


def test_add_firewood_uses_inventory_first() -> None:
    """Adding firewood should use the same inventory-first deduction rule."""

    ctx = make_ctx("harren")
    ctx.vs.modify_inventory(ItemType.FIREWOOD, 1)
    ctx.ws.modify_base_item(ItemType.FIREWOOD, 4)

    apply_start_effect(
        make_action(ActionType.ADD_FIREWOOD, quantity=3),
        ctx,
    )

    assert ctx.vs.inventory[ItemType.FIREWOOD] == 0
    assert ctx.ws.base_storage[ItemType.FIREWOOD] == 2
    assert ctx.ws.fire.fuel_queue[-1].fuel_type is FuelType.FIREWOOD
    assert ctx.ws.fire.fuel_queue[-1].quantity == 3


def test_other_action_types_have_no_start_effect() -> None:
    """Non-start-effect actions should leave villager and world state unchanged."""

    no_op_actions = (
        ActionType.EAT_PEACH,
        ActionType.EXPLORE,
        ActionType.REST,
        ActionType.GO_TO_SLEEP,
        ActionType.TALK_TO,
    )

    for action_type in no_op_actions:
        ctx = make_ctx("harren")
        ctx.vs.modify_inventory(ItemType.PEACH, 2)
        ctx.ws.modify_base_item(ItemType.STICK, 3)
        before_vs = deepcopy(ctx.vs)
        before_ws = deepcopy(ctx.ws)

        apply_start_effect(make_action(action_type), ctx)

        assert ctx.vs.__dict__ == before_vs.__dict__
        assert ctx.ws.__dict__ == before_ws.__dict__


def test_eat_peach_restores_satiation() -> None:
    """Eating peaches should restore 60 calories per peach."""

    ctx = make_ctx()
    ctx.vs.modify_stat("satiation", -1800)
    ctx.vs.modify_inventory(ItemType.PEACH, 2)

    apply_completion_effect(make_action(ActionType.EAT_PEACH, quantity=2), ctx)

    assert ctx.vs.satiation == 120.0
    assert ctx.vs.inventory[ItemType.PEACH] == 0


def test_eat_peach_uses_autobalance_scale() -> None:
    """Peach restoration should scale with the satiation autobalance multiplier."""

    ctx = make_ctx(
        multipliers=AutobalanceMultipliers(satiation_restore_scale=2.0)
    )
    ctx.vs.modify_stat("satiation", -1800)
    ctx.vs.modify_inventory(ItemType.PEACH, 1)

    apply_completion_effect(make_action(ActionType.EAT_PEACH, quantity=1), ctx)

    assert ctx.vs.satiation == 120.0


def test_eat_peach_caps_satiation() -> None:
    """Peach restoration should clamp satiation at the authored maximum."""

    ctx = make_ctx()
    ctx.vs.modify_stat("satiation", -100)
    ctx.vs.modify_inventory(ItemType.PEACH, 5)

    apply_completion_effect(make_action(ActionType.EAT_PEACH, quantity=5), ctx)

    assert ctx.vs.satiation == 1800.0


def test_eat_cooked_meat_restores_satiation() -> None:
    """Cooked meat should restore 800 calories per piece."""

    ctx = make_ctx()
    ctx.vs.modify_stat("satiation", -1800)
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 1)

    apply_completion_effect(
        make_action(ActionType.EAT_COOKED_MEAT, quantity=1),
        ctx,
    )

    assert ctx.vs.satiation == 800.0


def test_eat_cooked_meat_adds_dirtiness() -> None:
    """Cooked meat should add one meat-scraps dirtiness unit per piece eaten."""

    ctx = make_ctx()
    ctx.vs.modify_inventory(ItemType.COOKED_MEAT, 2)

    apply_completion_effect(
        make_action(ActionType.EAT_COOKED_MEAT, quantity=2),
        ctx,
    )

    assert ctx.ws.get_total_dirtiness() == 10


def test_drink_water_restores_hydration_and_consumes_supply() -> None:
    """Drinking water should restore hydration and deduct the consumed liters."""

    ctx = make_ctx()
    ctx.vs.modify_stat("hydration", -6000)
    ctx.ws.modify_water(2000)

    apply_completion_effect(make_action(ActionType.DRINK_WATER, liters=2), ctx)

    assert ctx.vs.hydration == 2000.0
    assert ctx.ws.water_supply_ml == 0


def test_drink_water_uses_autobalance_scale() -> None:
    """Hydration restoration should scale with the hydration multiplier."""

    ctx = make_ctx(
        multipliers=AutobalanceMultipliers(hydration_restore_scale=1.5)
    )
    ctx.vs.modify_stat("hydration", -6000)
    ctx.ws.modify_water(1000)

    apply_completion_effect(make_action(ActionType.DRINK_WATER, liters=1), ctx)

    assert ctx.vs.hydration == 1500.0


def test_drink_water_caps_hydration_but_still_spends_water() -> None:
    """Hydration should clamp at max even though the water is fully consumed."""

    ctx = make_ctx()
    ctx.vs.modify_stat("hydration", -500)
    ctx.ws.modify_water(2000)

    apply_completion_effect(make_action(ActionType.DRINK_WATER, liters=2), ctx)

    assert ctx.vs.hydration == 6000.0
    assert ctx.ws.water_supply_ml == 0


@pytest.mark.parametrize(
    ("sleep_spot", "fire_lit", "expected_modifier"),
    (
        (RestingSpotType.COT, False, 1.0),
        (RestingSpotType.BED_ROLL, True, 0.8),
        (RestingSpotType.BED_ROLL, False, 0.65),
        (None, True, 0.6),
        (None, False, 0.5),
    ),
)
def test_go_to_sleep_uses_authored_modifier_table(
    sleep_spot: RestingSpotType | None,
    fire_lit: bool,
    expected_modifier: float,
) -> None:
    """Sleeping should use the authored modifier table at completion time."""

    ctx = make_ctx()
    ctx.vs.modify_stat("wakefulness", -100)
    ctx.vs.set_sleep_spot(sleep_spot)
    if fire_lit:
        ctx.ws.add_fire_fuel(FuelType.STICK, 1, current_time=0)
        ctx.ws.light_fire(current_time=0)

    apply_completion_effect(make_action(ActionType.GO_TO_SLEEP, hours=7), ctx)

    assert ctx.vs.wakefulness == pytest.approx(51.0 * expected_modifier)


def test_go_to_sleep_caps_wakefulness() -> None:
    """Sleeping should clamp wakefulness at the authored maximum."""

    ctx = make_ctx()
    ctx.vs.modify_stat("wakefulness", -10)
    ctx.vs.set_sleep_spot(RestingSpotType.COT)

    apply_completion_effect(make_action(ActionType.GO_TO_SLEEP, hours=12), ctx)

    assert ctx.vs.wakefulness == 100.0


def test_place_bed_roll_deducts_inventory_and_claims_spot() -> None:
    """Placing a bed roll should move it from inventory into world placement state."""

    ctx = make_ctx("aldric")
    ctx.vs.modify_inventory(ItemType.BED_ROLL, 1)

    apply_completion_effect(make_action(ActionType.PLACE_BED_ROLL), ctx)

    assert ctx.vs.inventory[ItemType.BED_ROLL] == 0
    assert ctx.ws.placed_resting_spots["aldric"] is RestingSpotType.BED_ROLL
    assert ctx.vs.sleep_spot_claim is RestingSpotType.BED_ROLL


def test_place_cot_deducts_inventory_and_claims_spot() -> None:
    """Placing a cot should move it from inventory into world placement state."""

    ctx = make_ctx("aldric")
    ctx.vs.modify_inventory(ItemType.COT, 1)

    apply_completion_effect(make_action(ActionType.PLACE_COT), ctx)

    assert ctx.vs.inventory[ItemType.COT] == 0
    assert ctx.ws.placed_resting_spots["aldric"] is RestingSpotType.COT
    assert ctx.vs.sleep_spot_claim is RestingSpotType.COT


def test_wash_up_resets_cleanliness_and_consumes_water() -> None:
    """Washing should restore cleanliness to full and spend 500 mL."""

    ctx = make_ctx()
    ctx.vs.modify_stat("cleanliness", -80)
    ctx.ws.modify_water(500)

    apply_completion_effect(make_action(ActionType.WASH_UP), ctx)

    assert ctx.vs.cleanliness == 100.0
    assert ctx.ws.water_supply_ml == 0


def test_rest_completion_is_a_no_op() -> None:
    """Rest completion should not mutate explicit state on its own."""

    ctx = make_ctx()
    before_vs = deepcopy(ctx.vs)
    before_ws = deepcopy(ctx.ws)

    apply_completion_effect(make_action(ActionType.REST), ctx)

    assert ctx.vs.__dict__ == before_vs.__dict__
    assert ctx.ws.__dict__ == before_ws.__dict__
