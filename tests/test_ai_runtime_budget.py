"""The AI call is bounded by the time the Lambda actually has left (#18, E10).

The conversation route gave the model a fixed 90 seconds, counted from just
before the call, inside an API Lambda that is stopped at 29. The allowance
wrapper also built its Bedrock client without the transport limits the direct
path uses, and nothing stopped a generation from starting after admission had
already used the time up. The model call (#436) now opens one connection per
call, bounded by the time left, and checks the deadline after admission. This is the interim fix; answers that need more than
the Lambda's lifetime are E11's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from fakes.ask_question import (
    _COMPLETE,
    _command,
    _patch_allowance_table,
    _run_message_command,
)
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.model import FakeModel, Reply, install
from stoa.services import ai_service, model_call, runtime_budget_service
from stoa.services import ask_answer
from stoa.services.ask_question import _admission, _answering
from stoa.services.model_call import bedrock
from stoa.services.model_call.adapter import Stream
from fakes.ask_question import AtomicAllowanceTable


ANSWER = {"steps": ["Count the four equal parts."], "answer": "One half.", "hints": []}


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Provider(FakeModel):
    """The model counting and streaming its answer, moving an injected clock."""

    def __init__(self, clock: _Clock, *, count_at: float = 0.0, answer_at: float = 1.0,
                 first_event_at: float | None = None) -> None:
        super().__init__(
            answer=Reply(input=ANSWER, stop_reason="end_turn",
                         usage={"input_tokens": 10, "output_tokens": 20}),
        )
        self.clock = clock
        self.count_at = count_at
        self.answer_at = answer_at
        self.first_event_at = first_event_at
        self.invocations: list[float] = []

    def count_tokens(self, model_id: str, body: Mapping[str, Any]) -> int:
        self.clock.now = self.count_at
        return super().count_tokens(model_id, body)

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Stream:
        self.invocations.append(self.clock.now)
        sent = super().stream(model_id, body)
        if self.first_event_at is not None:
            self.clock.now = self.first_event_at

        def events() -> Iterator[Mapping[str, Any]]:
            for index, event in enumerate(sent.events):
                if index == 1:
                    self.clock.now = self.answer_at
                yield event

        return Stream(request_id=sent.request_id, events=events())


def _answer(
    admission: _admission.Admission | None, clock: _Clock, deadline: float
) -> ai_service.AIProviderResult[dict]:
    result = model_call.call(
        system="Answer the question.",
        messages=[{"role": "user", "content": "What is a half?"}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=ask_answer.ANSWER_TEMPERATURE,
        deadline=deadline,
        admission=admission,
        on_partial=lambda _partial: None,
        clock=clock,
    )
    return ask_answer.provider_result(
        result, effect_id=admission.effect_id if admission is not None else "effect-1"
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


# ── One connection, bounded by the time left, with or without admission ────


@pytest.mark.parametrize("through_allowance", [False, True], ids=["direct", "admitted"])
def test_the_call_is_bounded_by_the_time_left_with_or_without_admission(
    monkeypatch: pytest.MonkeyPatch, through_allowance: bool
) -> None:
    clock = _Clock()
    provider = install(_Provider(clock))
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    admission = _admission.meter(_command()).admission() if through_allowance else None

    result = _answer(admission, clock, deadline=20.0)

    assert result.content == ANSWER
    assert provider.connections == [20.0]
    config = bedrock.runtime_config(20.0)
    assert config.connect_timeout == 5
    assert config.read_timeout == 15  # 20 seconds left, less the 5-second margin
    assert config.retries["total_max_attempts"] == 1


# ── Admission that used the time up does not start a generation ────────────


def test_no_generation_starts_once_admission_has_used_up_the_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = install(_Provider(clock, count_at=21.0))
    table = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, table)
    command = _command()

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _answer(_admission.meter(command).admission(), clock, deadline=20.0)

    assert failure.value.category == "deadline_exceeded"
    assert provider.invocations == []
    effect = next(i for i in table.items.values() if i.get("entity_type") == "allowance_effect")
    # Kept, not released: the retry of the same message reuses this reservation.
    assert effect["state"] == "reserved"

    clock.now = 0.0
    retry_provider = install(_Provider(clock))
    retry = _admission.meter(command).admission()
    assert _answer(retry, clock, deadline=20.0).content == ANSWER
    assert len(retry_provider.invocations) == 1
    effects = [i for i in table.items.values() if i.get("entity_type") == "allowance_effect"]
    assert len(effects) == 1


def test_a_deadline_passed_before_the_first_stream_event_stops_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    install(_Provider(clock, first_event_at=21.0, answer_at=22.0))

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _answer(None, clock, deadline=20.0)

    assert failure.value.category == "deadline_exceeded"


def test_an_answer_that_takes_ten_seconds_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = install(_Provider(clock, count_at=1.0, answer_at=10.0))
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    admission = _admission.meter(_command()).admission()

    assert _answer(admission, clock, deadline=20.0).content == ANSWER
    assert provider.invocations == [1.0]


def test_the_message_route_gives_the_answer_the_requests_deadline(
    table, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[float | None] = []
    real = _answering.ask_answer.answer

    def spy(asked: Any, asker: Any, call: Any, **kwargs: Any) -> Any:
        seen.append(call.deadline_monotonic)
        return real(asked, asker, call, **kwargs)

    monkeypatch.setattr(_answering.ask_answer, "answer", spy)
    monkeypatch.setattr(
        _answering.runtime_budget_service,
        "ai_deadline",
        lambda **kwargs: 12_345.0 if kwargs == {
            "fixed_seconds": _answering._AI_INVOCATION_DEADLINE_SECONDS,
            "reserve_seconds": _answering._AI_PERSIST_RESERVE_SECONDS,
        } else pytest.fail(f"unexpected budget arguments {kwargs}"),
    )
    _run_message_command(monkeypatch, text=_COMPLETE, stop_reason="end_turn")

    assert seen == [12_345.0]
