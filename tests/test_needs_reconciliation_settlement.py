"""The sweep settles a reservation nobody will ever settle otherwise (E24, #18).

A command whose model call was made but whose answer was lost ends
`needs_reconciliation` and is never called again, so its reservation would hold
a share of the student's week until the week ends. After ten minutes the sweep
restores it with the cost recorded at the reservation's ceiling. A reservation
kept by a `deadline_exceeded` failure the student never sent again (E10) goes
the same way after twenty.

These run the real worker, route, repository and ledger against the shared
table double. Only the model call and the entitlement lookup are replaced.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from stoa.db.repositories import allowance_repo, attachment_repo
from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import ai_service, allowance_service
from test_conversation_generation_worker import _deliver, _expire_lease, _Killed, _running
from test_message_command_generation import (  # noqa: F401 - fixtures
    ANSWER,
    STUDENT,
    _client,
    _command_row,
    _commit,
    _generation,
)
from test_message_command_generation import table as table  # noqa: F401 - the fixture

RESERVED_INPUT = 120
RESERVED_OUTPUT = 800


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The prompt enrichment reads three tables; keep it out."""


class _Model:
    """Stands in for `ai_service.get_ai_answer`, reserving the way admission does.

    Each outcome is a dict of steps: `reserve` (admission reserved), `usage`
    (the provider reported these counts), `call` (the call was recorded), and
    `then`, the answer or the exception that ends it.
    """

    def __init__(self) -> None:
        self.outcomes: list[dict[str, Any]] = []
        self.calls = 0

    def __call__(self, **kwargs: Any) -> Any:
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else {"then": ANSWER}
        client = kwargs["client"]
        if outcome.get("reserve"):
            reserved = allowance_service.reserve_token_allowance(
                beneficiary_id=STUDENT,
                effect_id=client.allowance_effect_id,
                plan_id=client.plan_id,
                allowance_version=client.allowance_version,
                input_tokens=RESERVED_INPUT,
                max_output_tokens=RESERVED_OUTPUT,
                observed_at=client._observed_at,
                account_fence_generation=client.account_fence_generation,
            )
            assert reserved.disposition is allowance_repo.ReservationDisposition.ADMITTED
        if usage := outcome.get("usage"):
            observed = allowance_service.record_provider_usage(
                beneficiary_id=STUDENT,
                effect_id=client.allowance_effect_id,
                provider_request_id="req-1",
                model_id="model-1",
                input_tokens=usage[0],
                output_tokens=usage[1],
            )
            assert observed.disposition is allowance_repo.ProviderUsageDisposition.RECORDED
        if outcome.get("call"):
            client.mark_invocation()
        then = outcome.get("then", ANSWER)
        if isinstance(then, BaseException):
            raise then
        return dict(then)


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch, table) -> _Model:
    model = _Model()
    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", model)
    monkeypatch.setattr(allowance_repo, "get_table", lambda: table)
    return model


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    emitted: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        conversation_generation,
        "emit_private_event",
        lambda category, **fields: emitted.append((category, fields)),
    )
    return emitted


def _sweep() -> dict[str, Any]:
    return conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, None
    )


def _failed_minutes_ago(table, key: str, minutes: float) -> None:
    row = dict(_command_row(table, key))
    assert row["status"] == "failed"
    row["failed_at"] = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    table.seed(row)


def _counter(table, key: str) -> dict[str, Any]:
    asked = datetime.fromisoformat(_command_row(table, key)["created_at"])
    counter = allowance_repo.get_allowance_counter(
        beneficiary_id=STUDENT, week=allowance_service.zurich_week(asked), table=table
    )
    assert counter is not None
    return counter


def _evidence(table) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == "provider_usage_evidence"
    ]


def _lost_after_the_call(table, model: _Model, key: str, **steps: Any) -> None:
    """Called the model, then the Lambda died; the next attempt found nothing kept."""
    _commit(key)
    model.outcomes = [{"reserve": True, "call": True, "then": _Killed(), **steps}]
    with pytest.raises(_Killed):
        _deliver(key)
    _expire_lease(table, key)
    assert _deliver(key) == {"outcome": "failed"}
    row = _command_row(table, key)
    assert row["failure_category"] == "needs_reconciliation"


def _out_of_time_at_admission(model: _Model, key: str) -> None:
    """E10: reserved, then no time left to call; the reservation is kept."""
    _commit(key)
    model.outcomes = [
        {"reserve": True, "then": ai_service.AIInvocationFailure("deadline_exceeded")}
    ]
    _deliver(key)


def test_a_lost_answer_is_settled_at_its_reservation_ceiling(table, model, events) -> None:
    _lost_after_the_call(table, model, "lost")
    assert _counter(table, "lost")["reserved_output_tokens"] == RESERVED_OUTPUT
    _failed_minutes_ago(table, "lost", 11)

    summary = _sweep()

    assert summary["reconciled"] == 1
    counter = _counter(table, "lost")
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == RESERVED_INPUT
    assert counter["provider_cost_output_tokens"] == RESERVED_OUTPUT
    assert counter["finalized_output_tokens"] == 0
    [evidence] = _evidence(table)
    assert evidence["cost_basis"] == "unknown_cost"
    assert _command_row(table, "lost")["allowance_settled_at"]
    assert [category for category, _ in events] == [
        "conversation_ai_needs_reconciliation_settled"
    ]
    assert model.calls == 1


def test_a_settled_command_is_not_settled_again(table, model, events) -> None:
    _lost_after_the_call(table, model, "lost")
    _failed_minutes_ago(table, "lost", 11)
    _sweep()
    settled_at = _command_row(table, "lost")["allowance_settled_at"]

    again = _sweep()

    # Not a candidate at all: the ledger's own refusal is not what stops it.
    assert (again["reconciled"], again["settled"], again["errored"]) == (0, 0, 0)
    assert _command_row(table, "lost")["allowance_settled_at"] == settled_at
    assert _counter(table, "lost")["provider_cost_output_tokens"] == RESERVED_OUTPUT
    assert len(_evidence(table)) == 1
    assert len(events) == 1


def test_a_lost_answer_is_left_while_it_is_recent(table, model, events) -> None:
    _lost_after_the_call(table, model, "lost")
    _failed_minutes_ago(table, "lost", 5)

    summary = _sweep()

    assert summary["reconciled"] == 0
    assert _counter(table, "lost")["reserved_output_tokens"] == RESERVED_OUTPUT
    assert "allowance_settled_at" not in _command_row(table, "lost")
    assert events == []


def test_a_lost_answer_whose_usage_was_observed_keeps_that_usage(
    table, model, events
) -> None:
    _lost_after_the_call(table, model, "lost", usage=(100, 300))
    _failed_minutes_ago(table, "lost", 11)

    _sweep()

    counter = _counter(table, "lost")
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 100
    assert counter["provider_cost_output_tokens"] == 300
    [evidence] = _evidence(table)
    assert "cost_basis" not in evidence
    assert len(events) == 1


def test_a_reservation_kept_at_admission_is_settled_once_nobody_retried(
    table, model, events
) -> None:
    _out_of_time_at_admission(model, "admitted")
    row = _command_row(table, "admitted")
    assert (row["failure_category"], row["failure_retryable"]) == ("deadline_exceeded", True)
    _failed_minutes_ago(table, "admitted", 21)

    summary = _sweep()

    assert summary["reconciled"] == 1
    counter = _counter(table, "admitted")
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_output_tokens"] == RESERVED_OUTPUT
    row = _command_row(table, "admitted")
    assert row["allowance_settled_at"]
    # Its reservation is gone, so the same command may not be generated again.
    assert row["failure_retryable"] is False
    assert len(events) == 1


def test_a_reservation_kept_at_admission_is_left_for_the_students_retry(
    table, model, events
) -> None:
    _out_of_time_at_admission(model, "admitted")
    _failed_minutes_ago(table, "admitted", 15)

    summary = _sweep()

    assert summary["reconciled"] == 0
    assert _counter(table, "admitted")["reserved_output_tokens"] == RESERVED_OUTPUT
    assert _command_row(table, "admitted")["failure_retryable"] is True


def test_completed_and_other_retryable_commands_are_not_settled(
    table, model, events
) -> None:
    _commit("done")
    model.outcomes = [{"reserve": True}]
    assert _deliver("done") == {"outcome": "completed"}
    _commit("other")
    model.outcomes = [
        {"reserve": True, "then": ai_service.AIInvocationFailure("provider_unavailable")}
    ]
    _deliver("other")
    _failed_minutes_ago(table, "other", 30)
    reserved = _counter(table, "done")["reserved_output_tokens"]

    summary = _sweep()

    assert summary["reconciled"] == 0
    assert _counter(table, "done")["reserved_output_tokens"] == reserved
    assert _counter(table, "done")["provider_cost_output_tokens"] == 0
    assert "allowance_settled_at" not in _command_row(table, "done")
    assert "allowance_settled_at" not in _command_row(table, "other")
    assert events == []


def test_a_failure_that_reserved_nothing_is_only_marked_settled(table, model, events) -> None:
    _commit("unreserved")
    model.outcomes = [{"then": ai_service.AIInvocationFailure("deadline_exceeded")}]
    _deliver("unreserved")
    _failed_minutes_ago(table, "unreserved", 21)

    summary = _sweep()

    assert (summary["reconciled"], summary["settled"]) == (0, 1)
    assert _command_row(table, "unreserved")["allowance_settled_at"]
    assert _evidence(table) == []
    assert events == []


def test_a_settlement_cut_short_is_finished_by_the_next_run_without_charging_twice(
    table, model, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lost_after_the_call(table, model, "lost")
    _failed_minutes_ago(table, "lost", 11)
    complete = allowance_repo._complete_allowance
    monkeypatch.setattr(
        allowance_repo,
        "_complete_allowance",
        lambda **_: allowance_repo.FinalizationResult(
            allowance_repo.FinalizationDisposition.RETRYABLE
        ),
    )

    first = _sweep()

    assert first["errored"] == 1
    assert "allowance_settled_at" not in _command_row(table, "lost")
    assert _counter(table, "lost")["reserved_output_tokens"] == RESERVED_OUTPUT
    monkeypatch.setattr(allowance_repo, "_complete_allowance", complete)

    second = _sweep()

    assert second["reconciled"] == 1
    counter = _counter(table, "lost")
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_output_tokens"] == RESERVED_OUTPUT
    assert len(_evidence(table)) == 1


# E27: what E24 does not reach (ticket 15). A command whose last attempt died
# ends `terminal_failed`; one whose lease ran out outside the sweep's window is
# never taken up and stays `ai_running`.


def _died_after_the_call(table, model: _Model, key: str, **steps: Any) -> None:
    _commit(key)
    model.outcomes = [{"reserve": True, "call": True, "then": _Killed(), **steps}]
    with pytest.raises(_Killed):
        _deliver(key)


def _last_attempt_died(table, model: _Model, key: str, **steps: Any) -> None:
    """The attempt that called and died was the third; the sweep ends the command."""
    _died_after_the_call(table, model, key, **steps)
    row = dict(_command_row(table, key))
    row.update(attempt=3, provider_invoked_attempt=3)
    table.seed(row)
    _expire_lease(table, key)
    _sweep()
    assert _command_row(table, key)["status"] == "terminal_failed"


def _ended_minutes_ago(table, key: str, minutes: float) -> None:
    row = dict(_command_row(table, key))
    row["terminal_at"] = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    table.seed(row)


def test_a_command_whose_last_attempt_died_is_settled_at_the_ceiling(
    table, model, events
) -> None:
    _last_attempt_died(table, model, "last")
    _ended_minutes_ago(table, "last", 11)

    summary = _sweep()

    assert summary["reconciled"] == 1
    counter = _counter(table, "last")
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == RESERVED_INPUT
    assert counter["provider_cost_output_tokens"] == RESERVED_OUTPUT
    [evidence] = _evidence(table)
    assert evidence["cost_basis"] == "unknown_cost"
    assert _command_row(table, "last")["allowance_settled_at"]
    assert [category for category, _ in events] == [
        "conversation_ai_needs_reconciliation_settled"
    ]

    again = _sweep()

    assert (again["reconciled"], again["settled"], again["errored"]) == (0, 0, 0)
    assert len(events) == 1


def test_a_command_whose_last_attempt_died_is_left_while_it_is_recent(
    table, model, events
) -> None:
    _last_attempt_died(table, model, "last")
    _ended_minutes_ago(table, "last", 5)

    assert _sweep()["reconciled"] == 0
    assert _counter(table, "last")["reserved_output_tokens"] == RESERVED_OUTPUT
    assert events == []


def test_a_last_attempt_whose_usage_was_observed_keeps_that_usage(
    table, model, events
) -> None:
    _last_attempt_died(table, model, "last", usage=(100, 300))
    _ended_minutes_ago(table, "last", 11)

    _sweep()

    counter = _counter(table, "last")
    assert counter["reserved_output_tokens"] == 0
    assert counter["provider_cost_output_tokens"] == 300
    [evidence] = _evidence(table)
    assert "cost_basis" not in evidence


def test_a_lease_nobody_took_up_is_ended_and_settled(table, model, events) -> None:
    _died_after_the_call(table, model, "stale")
    _running(table, "stale", attempt=1, claimed_minutes_ago=40)

    summary = _sweep()

    assert summary["reconciled"] == 1
    row = _command_row(table, "stale")
    assert row["status"] == "terminal_failed"
    assert row["allowance_settled_at"]
    assert "leaseOwner" not in row
    assert _counter(table, "stale")["reserved_output_tokens"] == 0
    assert _counter(table, "stale")["provider_cost_output_tokens"] == RESERVED_OUTPUT
    generation = _generation(_client(), "stale")
    assert (generation["status"], generation["retryable"]) == ("failed", False)
    assert model.calls == 1


def test_a_lease_that_ran_out_within_the_window_is_generated_not_settled(
    table, model, events
) -> None:
    _commit("recent")
    model.outcomes = [{"reserve": True, "then": _Killed()}]
    with pytest.raises(_Killed):
        _deliver("recent")
    _running(table, "recent", attempt=1, claimed_minutes_ago=8)

    summary = _sweep()

    # Taken up by the sweep and nothing else: not a settlement candidate too.
    assert (summary["completed"], summary["reconciled"], summary["held"]) == (1, 0, 0)
    assert _command_row(table, "recent")["status"] == "completed"
    assert "allowance_settled_at" not in _command_row(table, "recent")


def test_a_lease_taken_up_after_the_sweep_read_it_is_left_alone(
    table, model, events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The student sent it again between the sweep's read and its write.

    That attempt died too, so its lease has also run out: only that it is not
    the lease the sweep read keeps the sweep from ending a recent attempt.
    """
    _died_after_the_call(table, model, "stale")
    _running(table, "stale", attempt=1, claimed_minutes_ago=40)
    close = attachment_repo.close_stale_lease

    def retried_first(**kwargs: Any) -> bool:
        row = dict(_command_row(table, "stale"))
        now = int(datetime.now(UTC).timestamp())
        row.update(leaseOwner="retry", claimedAt=now - 360, expiresAt=now - 60)
        table.seed(row)
        return close(**kwargs)

    monkeypatch.setattr(attachment_repo, "close_stale_lease", retried_first)

    summary = _sweep()

    assert (summary["reconciled"], summary["held"]) == (0, 1)
    row = _command_row(table, "stale")
    assert (row["status"], row["leaseOwner"]) == ("ai_running", "retry")
    assert _counter(table, "stale")["reserved_output_tokens"] == RESERVED_OUTPUT
    assert events == []
