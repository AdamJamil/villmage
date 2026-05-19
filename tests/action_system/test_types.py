# pyre-strict

"""Tests for action-system shared data types."""

from dataclasses import FrozenInstanceError

import pytest

from action_system.types import (
    ActionContext,
    ActionList,
    ActionType,
    ActiveSleepSegment,
    AutobalanceMultipliers,
    CraftableItem,
    ExploreResource,
    SelectedAction,
    ValidAction,
)
from character_canon.canon import CharacterCanon
from villmage.villager_state import VillagerState
from villmage.world_state import WorldState


def _assert_reassignment_is_frozen(instance: object, field_name: str) -> None:
    """Assert that assigning to one field raises FrozenInstanceError."""

    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, None)


def test_action_type_enum_is_complete_and_values_match_spec() -> None:
    """ActionType contains the authored member count and representative values."""

    assert len(ActionType) == 25
    assert ActionType.EAT_PEACH.value == 1
    assert ActionType.TALK_TO.value == 25


def test_explore_resource_enum_is_complete_and_values_match_spec() -> None:
    """ExploreResource contains the authored member count and representative values."""

    assert len(ExploreResource) == 5
    assert ExploreResource.BOAR.value == 5


def test_craftable_item_enum_is_complete_and_values_match_spec() -> None:
    """CraftableItem contains the authored member count and representative values."""

    assert len(CraftableItem) == 3
    assert CraftableItem.COT.value == 3


def test_autobalance_multipliers_defaults_are_identity() -> None:
    """Autobalance multipliers default to identity scaling."""

    multipliers = AutobalanceMultipliers()

    assert multipliers.exploration_yield_scale == 1.0
    assert multipliers.satiation_restore_scale == 1.0
    assert multipliers.hydration_restore_scale == 1.0


def test_active_sleep_segment_stores_fields() -> None:
    """ActiveSleepSegment stores constructor values unchanged."""

    segment = ActiveSleepSegment(
        total_minutes=480,
        elapsed_minutes=60,
        modifier=0.8,
    )

    assert segment.total_minutes == 480
    assert segment.elapsed_minutes == 60
    assert segment.modifier == 0.8


def test_valid_action_selectable_keeps_idx() -> None:
    """Selectable valid actions preserve their assigned menu index."""

    action = ValidAction(
        action_type=ActionType.EAT_PEACH,
        prompt_text="Eat peach {…}",
        selectable=True,
        idx=3,
    )

    assert action.idx == 3


def test_valid_action_non_selectable_defaults_to_none_idx() -> None:
    """Non-selectable valid actions default to an absent menu index."""

    action = ValidAction(
        action_type=ActionType.REST,
        prompt_text="Rest",
        selectable=False,
    )

    assert action.idx is None


def test_autobalance_multipliers_is_frozen() -> None:
    """AutobalanceMultipliers rejects field reassignment."""

    _assert_reassignment_is_frozen(AutobalanceMultipliers(), "exploration_yield_scale")


def test_action_context_is_frozen() -> None:
    """ActionContext rejects field reassignment."""

    context = ActionContext(
        villager_id="aldric",
        canon=CharacterCanon(),
        vs=VillagerState("aldric"),
        all_states={"aldric": VillagerState("aldric")},
        ws=WorldState(),
        multipliers=AutobalanceMultipliers(),
    )

    _assert_reassignment_is_frozen(context, "villager_id")


def test_active_sleep_segment_is_frozen() -> None:
    """ActiveSleepSegment rejects field reassignment."""

    _assert_reassignment_is_frozen(
        ActiveSleepSegment(total_minutes=480, elapsed_minutes=60, modifier=0.8),
        "modifier",
    )


def test_valid_action_is_frozen() -> None:
    """ValidAction rejects field reassignment."""

    _assert_reassignment_is_frozen(
        ValidAction(
            action_type=ActionType.EAT_PEACH,
            prompt_text="Eat peach {…}",
            selectable=True,
            idx=1,
        ),
        "idx",
    )


def test_action_list_is_frozen() -> None:
    """ActionList rejects field reassignment."""

    action = ValidAction(
        action_type=ActionType.REST,
        prompt_text="Rest",
        selectable=True,
        idx=1,
    )

    _assert_reassignment_is_frozen(
        ActionList(main_actions=(action,), crafter_recipes=()),
        "main_actions",
    )


def test_selected_action_is_frozen() -> None:
    """SelectedAction rejects field reassignment."""

    _assert_reassignment_is_frozen(
        SelectedAction(action_type=ActionType.TALK_TO, target_villager_id="maren"),
        "target_villager_id",
    )
