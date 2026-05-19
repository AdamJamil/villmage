# pyre-strict

"""Tests for AI coordinator response parsing and failure logging."""

import json
from pathlib import Path
from typing import Callable

import pytest
from llm_client.types import MessageRole, PromptSegment
from villmage.ai_coordinator import parser
from villmage.ai_coordinator.parser import (
    ParseError,
    _write_failure_log,
    parse_join_decision,
    parse_relationship_update,
    parse_social_score,
)
from villmage.ai_coordinator.types import (
    LLMCallType,
    ParseContext,
    RelationshipUpdateResult,
)


def _make_context(call_type: LLMCallType) -> ParseContext:
    """Return one stable parse context for parser tests."""

    return ParseContext(
        villager_id="aldric",
        call_type=call_type,
        game_time=321,
        prompt=[PromptSegment(role=MessageRole.USER, text="Prompt marker")],
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read one JSONL file into parsed line records."""

    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_parse_join_decision_accepts_only_yes_and_no() -> None:
    """Join decisions map `yes` to True and `no` to False."""

    context = _make_context(LLMCallType.JOIN_DECISION)

    assert parse_join_decision('{"response": "yes"}', context) is True
    assert parse_join_decision('{"response": "no"}', context) is False


@pytest.mark.parametrize(
    "response",
    ['{"response": "maybe"}', '{"response": ""}', "{}", "not json"],
)
def test_parse_join_decision_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Ambiguous or malformed join responses raise ParseError."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)

    with pytest.raises(ParseError):
        parse_join_decision(response, _make_context(LLMCallType.JOIN_DECISION))


@pytest.mark.parametrize("value", [0, 5, 10])
def test_parse_social_score_accepts_full_valid_range(value: int) -> None:
    """Boundary and middle social scores remain valid."""

    context = _make_context(LLMCallType.SOCIAL_SCORE)

    assert parse_social_score(f'{{"val": {value}}}', context) == value


@pytest.mark.parametrize("response", ['{"val": -1}', '{"val": 11}'])
def test_parse_social_score_rejects_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Raw social scores outside 0 through 10 are parse failures."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_social_score(response, _make_context(LLMCallType.SOCIAL_SCORE))


@pytest.mark.parametrize("response", ['{"val": "high"}', '{"val": 7.5}'])
def test_parse_social_score_rejects_non_integer_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Non-integer social scores are rejected instead of coerced."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_social_score(response, _make_context(LLMCallType.SOCIAL_SCORE))


def test_parse_relationship_update_parses_full_response() -> None:
    """Both relationship fields are forwarded when present."""

    context = _make_context(LLMCallType.RELATIONSHIP_UPDATE)

    assert parse_relationship_update(
        '{"impression": "wary", "desc": "Hid food."}',
        context,
    ) == RelationshipUpdateResult(impression="wary", desc_update="Hid food.")


def test_parse_relationship_update_uses_none_when_desc_is_absent() -> None:
    """Missing desc means keep the existing description unchanged."""

    context = _make_context(LLMCallType.RELATIONSHIP_UPDATE)

    assert parse_relationship_update('{"impression": "fine"}', context) == (
        RelationshipUpdateResult(impression="fine", desc_update=None)
    )


@pytest.mark.parametrize(
    "response",
    ['{"impression": ""}', '{"impression": null}', "{}"],
)
def test_parse_relationship_update_requires_non_empty_impression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response: str,
) -> None:
    """Missing or empty impressions are hard parse failures."""

    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", tmp_path / "llm_failures.jsonl")

    with pytest.raises(ParseError):
        parse_relationship_update(
            response,
            _make_context(LLMCallType.RELATIONSHIP_UPDATE),
        )


@pytest.mark.parametrize(
    ("call_type", "parse_fn", "response"),
    [
        (LLMCallType.JOIN_DECISION, parse_join_decision, '{"response": "maybe"}'),
        (LLMCallType.SOCIAL_SCORE, parse_social_score, '{"val": 11}'),
        (
            LLMCallType.RELATIONSHIP_UPDATE,
            parse_relationship_update,
            '{"impression": ""}',
        ),
    ],
)
def test_parse_error_writes_complete_failure_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    call_type: LLMCallType,
    parse_fn: Callable[[str, ParseContext], object],
    response: str,
) -> None:
    """Each parser failure appends one complete diagnostic record."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(call_type)

    with pytest.raises(ParseError):
        parse_fn(response, context)

    assert log_path.exists()
    records = _read_jsonl(log_path)
    assert len(records) == 1
    record = records[0]
    assert record["villager_id"] == context.villager_id
    assert record["call_type"] == context.call_type
    assert record["raw_response"] == response
    assert record["parse_error"] != ""
    assert record["is_retry"] is False


def test_failure_log_appends_instead_of_overwriting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Multiple parse failures preserve every JSONL line."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(LLMCallType.JOIN_DECISION)

    for response in ['{"response": "maybe"}', "{}"]:
        with pytest.raises(ParseError):
            parse_join_decision(response, context)

    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_write_failure_log_preserves_retry_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The retry marker is written verbatim to disk."""

    log_path = tmp_path / "llm_failures.jsonl"
    monkeypatch.setattr(parser, "_FAILURE_LOG_PATH", log_path)
    context = _make_context(LLMCallType.SOCIAL_SCORE)

    _write_failure_log(
        context,
        raw_response='{"val": 12}',
        parse_error="Field `val` must be between 0 and 10.",
        is_retry=True,
    )

    records = _read_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["is_retry"] is True
