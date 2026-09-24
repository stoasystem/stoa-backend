"""The AI call is bounded by the time the Lambda actually has left (#18, E10).

The conversation route gave the model a fixed 90 seconds, counted from just
before the call, inside an API Lambda that is stopped at 29. The allowance
wrapper also built its Bedrock client without the transport limits the direct
path uses, and nothing stopped a generation from starting after admission had
already used the time up. This is the interim fix; answers that need more than
the Lambda's lifetime are E11's.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from stoa.routers import conversations
from stoa.services import ai_service, runtime_budget_service
from test_conversation_token_finalization import NOW, _command, _patch_allowance_table
from test_token_allowances import AtomicAllowanceTable


ANSWER = {"steps": ["Count the four equal parts."], "answer": "One half.", "hints": []}


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Provider:
    """CountTokens and a streamed answer, moving an injected clock."""

    def __init__(self, clock: _Clock, *, count_at: float = 0.0, answer_at: float = 1.0,
                 first_event_at: float | None = None) -> None:
        self.clock = clock
        self.count_at = count_at
        self.answer_at = answer_at
        self.first_event_at = first_event_at
        self.invocations: list[float] = []

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        self.clock.now = self.count_at
        return {"inputTokens": 10, "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "c-1"}}

    def invoke_model_with_response_stream(self, **_kwargs: object) -> dict[str, object]:
        self.invocations.append(self.clock.now)
        if self.first_event_at is not None:
            self.clock.now = self.first_event_at

        def events():
            yield {"chunk": {"bytes": json.dumps({"type": "message_start", "message": {
                "id": "msg-1", "model": "anthropic.claude-sonnet-4-6",
                "usage": {"input_tokens": 10}}}).encode()}}
            self.clock.now = self.answer_at
            yield {"chunk": {"bytes": json.dumps({"type": "content_block_delta",
                                                  "delta": {"text": json.dumps(ANSWER)}}).encode()}}
            yield {"chunk": {"bytes": json.dumps({"type": "message_delta",
                                                  "usage": {"output_tokens": 20},
                                                  "delta": {"stop_reason": "end_turn"}}).encode()}}

        return {"body": events(), "ResponseMetadata": {"RequestId": "invoke-1"}}


def _factory(monkeypatch: pytest.MonkeyPatch, provider: _Provider) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []

    def factory(*_args: Any, **kwargs: Any) -> _Provider:
        built.append(kwargs)
        return provider

    monkeypatch.setattr(ai_service.boto3, "client", factory)
    return built


def _answer(client: Any, clock: _Clock, deadline: float) -> Any:
    return ai_service.get_ai_answer(
        "What is a half?", "math", "Grade 4", language="en",
        deadline_monotonic=deadline, clock=clock, client=client,
        effect_id=getattr(client, "allowance_effect_id", "effect-1"),
        observed_at=NOW, on_step=lambda *_: None,
    )


# ── The deadline: from the request's start, never past the Lambda's end ─────


def test_the_deadline_is_capped_by_the_lambdas_remaining_time() -> None:
    runtime_budget_service.begin_request(started_monotonic=100.0, remaining_seconds=20.0)
    try:
        deadline = runtime_budget_service.ai_deadline(
            fixed_seconds=90, reserve_seconds=4, clock=lambda: 103.0
        )
    finally:
        runtime_budget_service.begin_request(started_monotonic=None, remaining_seconds=None)
    assert deadline == 100.0 + 16.0


def test_the_deadline_counts_from_the_start_of_the_request() -> None:
    runtime_budget_service.begin_request(started_monotonic=50.0, remaining_seconds=None)
    try:
        deadline = runtime_budget_service.ai_deadline(
            fixed_seconds=90, reserve_seconds=4, clock=lambda: 58.0
        )
    finally:
        runtime_budget_service.begin_request(started_monotonic=None, remaining_seconds=None)
    assert deadline == 50.0 + 90.0


def test_without_a_lambda_context_the_fixed_budget_applies_from_now() -> None:
    runtime_budget_service.begin_request(started_monotonic=None, remaining_seconds=None)
    deadline = runtime_budget_service.ai_deadline(
        fixed_seconds=90, reserve_seconds=4, clock=lambda: 7.0
    )
    assert deadline == 97.0


def test_the_middleware_binds_the_remaining_time_from_the_lambda_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stoa import main

    seen: list[float] = []

    class _Context:
        def get_remaining_time_in_millis(self) -> int:
            return 20_000

    async def endpoint(_scope, _receive, _send) -> None:
        seen.append(runtime_budget_service.ai_deadline(
            fixed_seconds=90, reserve_seconds=4, clock=lambda: 1_000.0))

    monkeypatch.setattr(main.runtime_budget_service.time, "monotonic", lambda: 1_000.0)
    middleware = main.RequestBudgetMiddleware(endpoint)
    asyncio.run(middleware({"type": "http", "aws.context": _Context()}, None, None))

    assert seen == [1_000.0 + 16.0]


# ── The wrapper builds the same bounded client as the direct path ───────────


@pytest.mark.parametrize("through_allowance", [False, True], ids=["direct", "allowance-wrapper"])
def test_the_allowance_wrapper_uses_the_same_transport_limits(
    monkeypatch: pytest.MonkeyPatch, through_allowance: bool
) -> None:
    clock = _Clock()
    provider = _Provider(clock)
    built = _factory(monkeypatch, provider)
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    client = (
        conversations._ConversationAllowanceBedrockClient(_command())
        if through_allowance
        else None
    )

    result = _answer(client, clock, deadline=20.0)

    assert result.content == ANSWER
    assert len(built) == 1
    config = built[0]["config"]
    assert config.connect_timeout == 5
    assert config.read_timeout == 15  # 20 seconds left, less the 5-second margin
    assert config.retries["total_max_attempts"] == 1


# ── Admission that used the time up does not start a generation ────────────


def test_no_generation_starts_once_admission_has_used_up_the_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = _Provider(clock, count_at=21.0)
    _factory(monkeypatch, provider)
    table = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, table)
    command = _command()
    client = conversations._ConversationAllowanceBedrockClient(command)

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _answer(client, clock, deadline=20.0)

    assert failure.value.category == "deadline_exceeded"
    assert provider.invocations == []
    effect = next(i for i in table.items.values() if i.get("entity_type") == "allowance_effect")
    # Kept, not released: the retry of the same message reuses this reservation.
    assert effect["state"] == "reserved"

    clock.now = 0.0
    retry_provider = _Provider(clock)
    _factory(monkeypatch, retry_provider)
    retry = conversations._ConversationAllowanceBedrockClient(command)
    assert _answer(retry, clock, deadline=20.0).content == ANSWER
    assert len(retry_provider.invocations) == 1
    effects = [i for i in table.items.values() if i.get("entity_type") == "allowance_effect"]
    assert len(effects) == 1


def test_a_deadline_passed_before_the_first_stream_event_stops_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = _Provider(clock, first_event_at=21.0, answer_at=22.0)
    _factory(monkeypatch, provider)

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _answer(None, clock, deadline=20.0)

    assert failure.value.category == "deadline_exceeded"


def test_an_answer_that_takes_ten_seconds_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = _Provider(clock, count_at=1.0, answer_at=10.0)
    _factory(monkeypatch, provider)
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    client = conversations._ConversationAllowanceBedrockClient(_command())

    assert _answer(client, clock, deadline=20.0).content == ANSWER
    assert provider.invocations == [1.0]


def test_the_message_route_gives_the_answer_the_requests_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[float | None] = []
    real = ai_service.get_ai_answer

    def spy(**kwargs: Any) -> Any:
        seen.append(kwargs.get("deadline_monotonic"))
        return real(**kwargs)

    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", spy)
    monkeypatch.setattr(
        conversations.runtime_budget_service,
        "ai_deadline",
        lambda **kwargs: 12_345.0 if kwargs == {
            "fixed_seconds": conversations._AI_INVOCATION_DEADLINE_SECONDS,
            "reserve_seconds": conversations._AI_PERSIST_RESERVE_SECONDS,
        } else pytest.fail(f"unexpected budget arguments {kwargs}"),
    )
    from test_truncated_ai_output import _COMPLETE, _run_message_command

    _run_message_command(monkeypatch, text=_COMPLETE, stop_reason="end_turn")

    assert seen == [12_345.0]
