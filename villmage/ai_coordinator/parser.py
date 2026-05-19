# pyre-strict

"""Response parsing and parse-failure logging for the AI coordinator."""

from dataclasses import asdict
import json
from pathlib import Path

from llm_client.types import PromptSegment
from villmage.ai_coordinator.types import (
    ParseContext,
    ParseFailureLog,
    RelationshipUpdateResult,
)


_FAILURE_LOG_PATH = Path("data/llm_failures.jsonl")


class ParseError(Exception):
    """Raised when one LLM response fails JSON or schema validation."""


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
    is_retry: bool = False,
) -> None:
    """Write the failure record and then raise ParseError with the same message."""

    _write_failure_log(ctx, raw_response, message, is_retry)
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
