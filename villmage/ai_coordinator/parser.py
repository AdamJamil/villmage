# pyre-strict

"""Response parsing and parse-failure logging for the AI coordinator."""

from dataclasses import asdict
import json
from pathlib import Path
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from action_system.types import ActionList, ActionType, ExploreResource, SelectedAction, ValidAction
from llm_client.types import PromptSegment
from villmage.ai_coordinator.types import (
    ActionSelectionResult,
    ConvActionType,
    ConversationTurnResult,
    ParseContext,
    ParseFailureLog,
    RelationshipUpdateResult,
    TradeActionType,
    TradeItemSpec,
    TradeTurnResult,
)
from villmage.game_types import CraftableItem, ItemType


_FAILURE_LOG_PATH = Path("data/llm_failures.jsonl")
_RETRY_LOGGING: ContextVar[bool] = ContextVar("_RETRY_LOGGING", default=False)
_NO_ARG_ACTION_TYPES: frozenset[ActionType] = frozenset(
    {
        ActionType.PLACE_BED_ROLL,
        ActionType.PLACE_COT,
        ActionType.REST,
        ActionType.LIGHT_FIRE,
        ActionType.EXTINGUISH_FIRE,
        ActionType.HAUL_WATER,
        ActionType.BUTCHER_CARCASS,
        ActionType.CLEAN_CAMP,
        ActionType.COOK_MEAT,
        ActionType.FINISH_COOKING,
        ActionType.WASH_UP,
    }
)
_RESP_REQUIRED_ACTIONS: frozenset[ConvActionType] = frozenset(
    {
        ConvActionType.INTERACT,
        ConvActionType.INTERRUPT,
        ConvActionType.CONTINUE,
        ConvActionType.RESPOND,
        ConvActionType.CHANGE_TOPIC,
        ConvActionType.CASUAL,
    }
)
_ITEM_NAME_MAP: dict[str, ItemType] = {
    item_type.name.lower().replace("_", " "): item_type for item_type in ItemType
}
_RESOURCE_NAME_MAP: dict[str, ExploreResource] = {
    resource.name.lower(): resource for resource in ExploreResource
}
_CRAFTABLE_NAME_MAP: dict[str, CraftableItem] = {
    craftable_item.name.lower().replace("_", " "): craftable_item
    for craftable_item in CraftableItem
}
_TARGET_VILLAGER_ID_PATTERN = re.compile(r'"target_villager_id": "([^"]+)"')


class ParseError(Exception):
    """Raised when one LLM response fails JSON or schema validation."""


@contextmanager
def retry_logging(is_retry: bool) -> Iterator[None]:
    """Temporarily mark parse failures within the block as retry attempts."""

    token = _RETRY_LOGGING.set(is_retry)
    try:
        yield
    finally:
        _RETRY_LOGGING.reset(token)


def _serialize_prompt(prompt: list[PromptSegment]) -> list[PromptSegment]:
    """Return a shallow prompt copy for stable failure-log serialization."""

    return list(prompt)


def _write_failure_log(
    ctx: ParseContext,
    raw_response: str,
    parse_error: str,
    is_retry: bool,
) -> None:
    """Append one parse-failure record to the shared JSONL diagnostics file."""

    failure_log = ParseFailureLog(
        villager_id=ctx.villager_id,
        call_type=ctx.call_type,
        game_time=ctx.game_time,
        prompt=_serialize_prompt(ctx.prompt),
        raw_response=raw_response,
        parse_error=parse_error,
        is_retry=is_retry,
    )
    _FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FAILURE_LOG_PATH.open("a", encoding="utf-8") as failure_log_file:
        failure_log_file.write(json.dumps(asdict(failure_log)) + "\n")


def _raise_parse_error(
    ctx: ParseContext,
    raw_response: str,
    message: str,
    is_retry: bool | None = None,
) -> None:
    """Write the failure record and then raise ParseError with the same message."""

    retry_flag = _RETRY_LOGGING.get() if is_retry is None else is_retry
    _write_failure_log(ctx, raw_response, message, retry_flag)
    raise ParseError(message)


def _parse_json_object(response: str, ctx: ParseContext) -> dict[str, object]:
    """Parse one response string into a JSON object or raise ParseError."""

    try:
        parsed: object = json.loads(response)
    except json.JSONDecodeError:
        _raise_parse_error(ctx, response, "Response was not valid JSON.")

    if not isinstance(parsed, dict):
        _raise_parse_error(ctx, response, "Response JSON must be an object.")

    result: dict[str, object] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            _raise_parse_error(ctx, response, "Response JSON keys must be strings.")
        result[key] = value
    return result


def _coerce_json_object(
    value: object,
    field_name: str,
    response: str,
    ctx: ParseContext,
) -> dict[str, object]:
    """Return one string-keyed JSON object value."""

    if not isinstance(value, dict):
        _raise_parse_error(ctx, response, f"Field `{field_name}` must be an object.")

    result: dict[str, object] = {}
    for key, inner_value in value.items():
        if not isinstance(key, str):
            _raise_parse_error(
                ctx,
                response,
                f"Field `{field_name}` must use string keys.",
            )
        result[key] = inner_value
    return result


def _require_object_field(
    parsed: dict[str, object],
    field_name: str,
    response: str,
    ctx: ParseContext,
) -> dict[str, object]:
    """Return one required object field from the parsed payload."""

    if field_name not in parsed:
        _raise_parse_error(ctx, response, f"Field `{field_name}` is required.")
    return _coerce_json_object(parsed[field_name], field_name, response, ctx)


def _require_int_field(
    parsed: dict[str, object],
    field_name: str,
    response: str,
    ctx: ParseContext,
) -> int:
    """Return one required non-boolean integer field."""

    value = parsed.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_parse_error(ctx, response, f"Field `{field_name}` must be an integer.")
    return value


def _require_non_empty_string_field(
    parsed: dict[str, object],
    field_name: str,
    response: str,
    ctx: ParseContext,
) -> str:
    """Return one required non-empty string field."""

    value = parsed.get(field_name)
    if not isinstance(value, str) or value == "":
        _raise_parse_error(
            ctx,
            response,
            f"Field `{field_name}` must be a non-empty string.",
        )
    return value


def _parse_optional_string(
    parsed: dict[str, object],
    field_name: str,
    response: str,
    ctx: ParseContext,
) -> str | None:
    """Return one optional string field, preserving empty strings."""

    if field_name not in parsed:
        return None
    value = parsed[field_name]
    if not isinstance(value, str):
        _raise_parse_error(ctx, response, f"Field `{field_name}` must be a string.")
    return value


def _parse_item_type(
    item_name: str,
    response: str,
    ctx: ParseContext,
) -> ItemType:
    """Resolve one prompt-facing item label to its enum."""

    item_type = _ITEM_NAME_MAP.get(item_name)
    if item_type is None:
        _raise_parse_error(ctx, response, f"Unknown item `{item_name}`.")
    return item_type


def _resolve_action_by_idx(
    idx: int,
    action_list: ActionList,
    response: str,
    ctx: ParseContext,
) -> ValidAction:
    """Return the selected action entry for one authored menu index."""

    for action in (*action_list.main_actions, *action_list.crafter_recipes):
        if action.idx != idx:
            continue
        if not action.selectable:
            _raise_parse_error(
                ctx,
                response,
                f"Action index {idx} is not currently selectable.",
            )
        return action
    _raise_parse_error(ctx, response, f"Action index {idx} was not found.")


def _parse_resource_from_prompt_text(
    prompt_text: str,
    response: str,
    ctx: ParseContext,
) -> ExploreResource:
    """Resolve the authored exploration resource embedded in one menu line."""

    lowered_prompt = prompt_text.lower()
    for resource_name, resource in _RESOURCE_NAME_MAP.items():
        if lowered_prompt.startswith(f"explore for {resource_name} "):
            return resource
    _raise_parse_error(ctx, response, "Could not resolve exploration resource.")


def _parse_craftable_item_from_prompt_text(
    prompt_text: str,
    response: str,
    ctx: ParseContext,
) -> CraftableItem:
    """Resolve the authored craftable item embedded in one recipe line."""

    lowered_prompt = prompt_text.lower()
    for craftable_name, craftable_item in _CRAFTABLE_NAME_MAP.items():
        if lowered_prompt.startswith(f"craft {craftable_name} "):
            return craftable_item
    _raise_parse_error(ctx, response, "Could not resolve craftable item.")


def _parse_target_villager_id_from_prompt_text(
    prompt_text: str,
    response: str,
    ctx: ParseContext,
) -> str:
    """Resolve the authored fixed conversation target from one menu line."""

    match = _TARGET_VILLAGER_ID_PATTERN.search(prompt_text)
    if match is None:
        _raise_parse_error(ctx, response, "Could not resolve target villager id.")
    return match.group(1)


def _parse_trade_items(
    args: dict[str, object],
    response: str,
    ctx: ParseContext,
) -> list[TradeItemSpec]:
    """Parse one trade item mapping into stable item specs."""

    items: list[TradeItemSpec] = []
    for item_spec_value in args.values():
        item_spec = _coerce_json_object(item_spec_value, "args", response, ctx)
        item_name = _require_non_empty_string_field(item_spec, "name", response, ctx)
        quantity = _require_int_field(item_spec, "quantity", response, ctx)
        if quantity <= 0:
            _raise_parse_error(
                ctx,
                response,
                "Trade item quantity must be greater than zero.",
            )
        items.append(
            TradeItemSpec(
                item=_parse_item_type(item_name, response, ctx),
                quantity=quantity,
            )
        )
    return items


def _build_selected_action(
    action: ValidAction,
    args: dict[str, object],
    response: str,
    ctx: ParseContext,
) -> SelectedAction:
    """Build one typed selected action from the chosen menu entry and args."""

    action_type = action.action_type
    if action_type in {
        ActionType.EAT_PEACH,
        ActionType.EAT_COOKED_MEAT,
        ActionType.ADD_STICKS,
        ActionType.ADD_FIREWOOD,
        ActionType.SCRAPE_HIDE,
        ActionType.SPLIT_LOGS,
    }:
        return SelectedAction(
            action_type=action_type,
            quantity=_require_int_field(args, "quantity", response, ctx),
        )
    if action_type is ActionType.DRINK_WATER:
        return SelectedAction(
            action_type=action_type,
            liters=_require_int_field(args, "liters", response, ctx),
        )
    if action_type in {ActionType.TAKE_FROM_BASE, ActionType.STORE_IN_BASE}:
        return SelectedAction(
            action_type=action_type,
            item=_parse_item_type(
                _require_non_empty_string_field(args, "item", response, ctx),
                response,
                ctx,
            ),
            quantity=_require_int_field(args, "quantity", response, ctx),
        )
    if action_type in _NO_ARG_ACTION_TYPES:
        return SelectedAction(action_type=action_type)
    if action_type is ActionType.EXPLORE:
        return SelectedAction(
            action_type=action_type,
            resource=_parse_resource_from_prompt_text(action.prompt_text, response, ctx),
            duration_minutes=_require_int_field(args, "duration_minutes", response, ctx),
        )
    if action_type is ActionType.CRAFT_NEW:
        return SelectedAction(
            action_type=action_type,
            craftable_item=_parse_craftable_item_from_prompt_text(
                action.prompt_text,
                response,
                ctx,
            ),
        )
    if action_type is ActionType.CONTINUE_CRAFTING:
        return SelectedAction(
            action_type=action_type,
            minutes_to_spend=_require_int_field(
                args,
                "minutes_to_spend_now",
                response,
                ctx,
            ),
        )
    if action_type is ActionType.GO_TO_SLEEP:
        return SelectedAction(
            action_type=action_type,
            hours=_require_int_field(args, "hours", response, ctx),
        )
    if action_type is ActionType.TALK_TO:
        target_villager_id = _require_non_empty_string_field(
            args,
            "target_villager_id",
            response,
            ctx,
        )
        expected_target_id = _parse_target_villager_id_from_prompt_text(
            action.prompt_text,
            response,
            ctx,
        )
        if target_villager_id != expected_target_id:
            _raise_parse_error(
                ctx,
                response,
                "Field `target_villager_id` did not match the selected action.",
            )
        return SelectedAction(
            action_type=action_type,
            target_villager_id=target_villager_id,
        )
    _raise_parse_error(ctx, response, f"Unsupported action type `{action_type}`.")


def parse_action_selection(
    response: str,
    action_list: ActionList,
    ctx: ParseContext,
) -> ActionSelectionResult:
    """Parse action-selection JSON into one validated selected action."""

    parsed = _parse_json_object(response, ctx)
    idx = _require_int_field(parsed, "idx", response, ctx)
    args = _require_object_field(parsed, "args", response, ctx)
    selected_action = _build_selected_action(
        _resolve_action_by_idx(idx, action_list, response, ctx),
        args,
        response,
        ctx,
    )
    thoughts = _parse_optional_string(parsed, "thoughts", response, ctx)
    thought = None if thoughts in {None, ""} else thoughts
    return ActionSelectionResult(action=selected_action, thought=thought)


def parse_conversation_turn(
    response: str,
    ctx: ParseContext,
) -> ConversationTurnResult:
    """Parse one conversation-turn response into a validated action result."""

    parsed = _parse_json_object(response, ctx)
    idx = _require_int_field(parsed, "idx", response, ctx)
    args = _require_object_field(parsed, "args", response, ctx)

    try:
        action = ConvActionType(idx)
    except ValueError:
        _raise_parse_error(ctx, response, f"Unknown conversation action index {idx}.")

    if action in _RESP_REQUIRED_ACTIONS:
        return ConversationTurnResult(
            action=action,
            resp=_require_non_empty_string_field(args, "resp", response, ctx),
        )
    if action is ConvActionType.TRADE:
        return ConversationTurnResult(
            action=action,
            target_id=_require_non_empty_string_field(args, "target_id", response, ctx),
        )
    return ConversationTurnResult(action=action)


def parse_trade_turn(
    response: str,
    inventory_items: list[tuple[ItemType, int]],
    last_other_action: TradeActionType | None,
    ctx: ParseContext,
) -> TradeTurnResult:
    """Parse one trade-turn response and enforce authored trade constraints."""

    parsed = _parse_json_object(response, ctx)
    idx = _require_int_field(parsed, "idx", response, ctx)
    args = _require_object_field(parsed, "args", response, ctx)
    speech = _parse_optional_string(parsed, "speech", response, ctx)

    try:
        action = TradeActionType(idx)
    except ValueError:
        _raise_parse_error(ctx, response, f"Unknown trade action index {idx}.")

    if action in {
        TradeActionType.MAKE_OFFER,
        TradeActionType.REQUEST_ITEMS,
    }:
        items = _parse_trade_items(args, response, ctx)
        if len(items) == 0:
            _raise_parse_error(
                ctx,
                response,
                "Trade items must be non-empty for offers and requests.",
            )
        if action is TradeActionType.MAKE_OFFER:
            available_inventory = dict(inventory_items)
            offered_counts: dict[ItemType, int] = {}
            for item in items:
                offered_counts[item.item] = offered_counts.get(item.item, 0) + item.quantity
            for item_type, quantity in offered_counts.items():
                if quantity > available_inventory.get(item_type, 0):
                    _raise_parse_error(
                        ctx,
                        response,
                        f"Cannot offer more {item_type.name} than the villager holds.",
                    )
        return TradeTurnResult(action=action, items=items, speech=speech)

    if action is TradeActionType.ACCEPT:
        if last_other_action is not TradeActionType.MAKE_OFFER:
            _raise_parse_error(
                ctx,
                response,
                "ACCEPT is only valid after the other villager makes an offer.",
            )
        return TradeTurnResult(action=action, items=[], speech=speech)

    return TradeTurnResult(action=action, items=[], speech=speech)


def parse_join_decision(response: str, ctx: ParseContext) -> bool:
    """Parse `{\"response\": \"yes\"|\"no\"}` into a join boolean."""

    parsed = _parse_json_object(response, ctx)
    value = parsed.get("response")
    if value == "yes":
        return True
    if value == "no":
        return False
    _raise_parse_error(
        ctx,
        response,
        "Field `response` must be exactly `yes` or `no`.",
    )


def parse_social_score(response: str, ctx: ParseContext) -> int:
    """Parse `{\"val\": int}` and enforce the inclusive 0 through 10 range."""

    parsed = _parse_json_object(response, ctx)
    value = parsed.get("val")
    if not isinstance(value, int) or isinstance(value, bool):
        _raise_parse_error(ctx, response, "Field `val` must be an integer.")
    if value < 0 or value > 10:
        _raise_parse_error(ctx, response, "Field `val` must be between 0 and 10.")
    return value


def parse_relationship_update(
    response: str,
    ctx: ParseContext,
) -> RelationshipUpdateResult:
    """Parse relationship output and require a non-empty impression string."""

    parsed = _parse_json_object(response, ctx)
    impression = parsed.get("impression")
    if not isinstance(impression, str) or impression == "":
        _raise_parse_error(
            ctx,
            response,
            "Field `impression` must be a non-empty string.",
        )

    desc_value = parsed.get("desc")
    if "desc" not in parsed:
        return RelationshipUpdateResult(impression=impression, desc_update=None)
    if not isinstance(desc_value, str):
        _raise_parse_error(ctx, response, "Field `desc` must be a string.")
    return RelationshipUpdateResult(impression=impression, desc_update=desc_value)
