"""The worker that generates a committed command's answer outside the request (E20, #18).

A command must reach exactly one answer however often it is delivered, and an
attempt whose Lambda died is recovered by what is known about it:

- the model was never called: generate again;
- the answer was stored before the Lambda died: finish storing it, no new call;
- the model was called and nothing came back: `needs_reconciliation`, no new
  call, because a second call would pay for an answer that may already exist.

These run the real worker, route and repository against the shared table
double. Only the model call and the entitlement lookup are replaced.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from stoa.db.repositories import attachment_repo
from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import ai_service
from test_message_command_generation import (  # noqa: F401 - fixtures
    ANSWER,
    CONV,
    _client,
    _command_row,
    _commit,
    _generation,
    _messages,
)
from test_message_command_generation import table as table  # noqa: F401 - the fixture


class _Killed(BaseException):
    """The Lambda stopped here: nothing after this line ran."""


class _Model:
    """Stands in for `ai_service.get_ai_answer`.

    Each outcome is the answer, an exception, or a `_Called(then)`: the call got
    as far as the provider (the allowance client's invocation hook ran) and then
    did `then`.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[Any] = []
        self.gate: threading.Event | None = None

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.gate is not None:
            self.gate.wait(5)
        outcome = self.outcomes.pop(0) if self.outcomes else ANSWER
        if isinstance(outcome, _Called):
            kwargs["client"].mark_invocation()
            outcome = outcome.then
        if isinstance(outcome, BaseException):
            raise outcome
        return dict(outcome)


class _Called:
    def __init__(self, then: Any = None) -> None:
        self.then = ANSWER if then is None else then


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> _Model:
    model = _Model()
    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", model)
    return model


def _deliver(key: str) -> dict[str, Any]:
    return conversation_generation.handler(
        {"conversation_id": CONV, "idempotency_key": key}, None
    )


def _expire_lease(table, key: str) -> None:
    row = dict(_command_row(table, key))
    assert row["status"] == "ai_running"
    row["expiresAt"] = 1
    table.seed(row)


def test_the_worker_generates_a_committed_command(table, model) -> None:
    _commit("key-1")

    outcome = _deliver("key-1")

    assert outcome == {"outcome": "completed"}
    assert _command_row(table, "key-1")["status"] == "completed"
    assert len(_messages(table, "assistant")) == 1
    assert model.calls[0]["language"] == "de"


def test_a_second_delivery_of_the_same_command_changes_nothing(table, model) -> None:
    _commit("key-1")
    _deliver("key-1")

    again = _deliver("key-1")

    assert again == {"outcome": "settled"}
    assert len(model.calls) == 1
    assert len(_messages(table, "assistant")) == 1
    [quota] = [row for key, row in table.rows.items() if key[1].startswith("CHAT#")]
    assert quota["count"] == 1


def test_two_deliveries_that_both_find_the_command_waiting_produce_one_answer(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both read the command as unclaimed; only the conditional claim is between them."""
    _commit("key-1")
    both_read = threading.Barrier(2, timeout=5)
    claim = attachment_repo.claim_message_ai_lease

    def claim_once_both_have_read(**kwargs: Any) -> Any:
        both_read.wait()
        return claim(**kwargs)

    monkeypatch.setattr(attachment_repo, "claim_message_ai_lease", claim_once_both_have_read)
    model.gate = threading.Event()
    outcomes: list[dict[str, Any]] = []
    deliveries = [
        threading.Thread(target=lambda: outcomes.append(_deliver("key-1"))) for _ in range(2)
    ]
    for delivery in deliveries:
        delivery.start()
    deadline = time.monotonic() + 3
    while not outcomes and time.monotonic() < deadline:
        time.sleep(0.01)
    model.gate.set()
    for delivery in deliveries:
        delivery.join(5)

    assert sorted(outcome["outcome"] for outcome in outcomes) == ["completed", "held"]
    assert len(model.calls) == 1
    assert len(_messages(table, "assistant")) == 1


def test_an_attempt_lost_before_the_model_was_called_is_generated_again(
    table, model
) -> None:
    _commit("key-1")
    model.outcomes = [_Killed()]
    with pytest.raises(_Killed):
        _deliver("key-1")
    _expire_lease(table, "key-1")

    outcome = _deliver("key-1")

    assert outcome == {"outcome": "completed"}
    assert len(model.calls) == 2
    assert _generation(_client(), "key-1")["attempt"] == 2


def test_an_attempt_lost_after_its_answer_was_stored_is_only_finished(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit("key-1")
    model.outcomes = [_Called()]
    renew = attachment_repo.renew_message_ai_lease
    calls = {"renew": 0}

    def die_on_first_renewal(**kwargs: Any) -> bool:
        calls["renew"] += 1
        if calls["renew"] == 1:
            raise _Killed()
        return renew(**kwargs)

    monkeypatch.setattr(attachment_repo, "renew_message_ai_lease", die_on_first_renewal)
    with pytest.raises(_Killed):
        _deliver("key-1")
    _expire_lease(table, "key-1")

    outcome = _deliver("key-1")

    assert outcome == {"outcome": "completed"}
    assert len(model.calls) == 1
    [assistant] = _messages(table, "assistant")
    assert "So kürzt man." in assistant["content"]
    assert "provider_result_json" not in _command_row(table, "key-1")


def test_an_attempt_lost_after_the_model_was_called_is_not_called_again(
    table, model
) -> None:
    _commit("key-1")
    model.outcomes = [_Called(_Killed())]
    with pytest.raises(_Killed):
        _deliver("key-1")
    _expire_lease(table, "key-1")

    outcome = _deliver("key-1")

    assert outcome == {"outcome": "failed"}
    assert len(model.calls) == 1
    assert _messages(table, "assistant") == []
    generation = _generation(_client(), "key-1")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "needs_reconciliation"
    assert generation["retryable"] is False


def test_a_command_without_context_is_generated_in_the_profile_language(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Commands committed before E19 carry no context, and there is no request."""
    _commit("key-1")
    row = dict(_command_row(table, "key-1"))
    row.pop("generation_context")
    table.seed(row)
    monkeypatch.setattr(
        conversations.user_repo, "get_user", lambda *_a, **_k: {"preferred_locale": "it"}
    )

    assert _deliver("key-1") == {"outcome": "completed"}

    assert model.calls[0]["language"] == "it"
    assert model.calls[0]["subject"] == "math"
    assert model.calls[0]["grade"] == "Grade 6"


def test_the_sweep_finishes_unclaimed_commands_and_expired_leases(table, model) -> None:
    for key in ("old", "fresh", "expired", "failed"):
        _commit(key)
    old = dict(_command_row(table, "old"))
    old["message_committed_at"] = "2026-09-24T08:00:00+00:00"
    table.seed(old)
    model.outcomes = [_Killed()]
    with pytest.raises(_Killed):
        _deliver("expired")
    _expire_lease(table, "expired")
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    _deliver("failed")
    assert _command_row(table, "failed")["status"] == "failed"

    summary = conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, None
    )

    assert summary["completed"] == 2
    assert _command_row(table, "old")["status"] == "completed"
    assert _command_row(table, "expired")["status"] == "completed"
    assert _command_row(table, "fresh")["status"] == "message_committed"
    # A failed answer is the student's to send again, not the sweep's.
    assert _command_row(table, "failed")["status"] == "failed"


def test_the_sweep_stops_starting_answers_when_the_lambda_is_nearly_out_of_time(
    table, model
) -> None:
    _commit("old")
    old = dict(_command_row(table, "old"))
    old["message_committed_at"] = "2026-09-24T08:00:00+00:00"
    table.seed(old)

    class _Context:
        def get_remaining_time_in_millis(self) -> int:
            return 20_000

    summary = conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, _Context()
    )

    assert summary["candidates"] == 1
    assert summary["deferred"] == 1
    assert model.calls == []


def test_an_event_that_names_no_command_is_refused_without_a_retry(table, model) -> None:
    """Raising would have Lambda deliver it twice more, and it can never succeed."""
    outcome = conversation_generation.handler({"conversation_id": CONV}, None)

    assert outcome == {"outcome": "invalid_event"}


def test_the_lease_outlasts_the_sweep_period() -> None:
    assert conversations._AI_LEASE_SECONDS >= 300


def test_the_worker_handler_ships_in_the_lambda_package() -> None:
    import build_lambda_dist

    assert (
        build_lambda_dist.EXPECTED_HANDLERS["stoa.jobs.conversation_generation.handler"]
        == "stoa/jobs/conversation_generation.py"
    )


def _allowance_client(monkeypatch: pytest.MonkeyPatch):
    from test_conversation_token_finalization import _command, _patch_allowance_table
    from test_token_allowances import AtomicAllowanceTable
    from test_truncated_ai_output import _COMPLETE, _Provider

    provider = _Provider(text=_COMPLETE, stop_reason="end_turn")
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    monkeypatch.setattr(ai_service.boto3, "client", lambda *_a, **_k: provider)
    return conversations._ConversationAllowanceBedrockClient(_command()), provider


def _ask(client) -> Any:
    from test_conversation_token_finalization import NOW

    return ai_service.get_ai_answer(
        content="Wie kürze ich Brüche?",
        subject="math",
        grade="Grade 6",
        effect_id=client.allowance_effect_id,
        client=client,
        observed_at=NOW,
        on_step=lambda _i, _s: None,
    )


def test_the_call_is_recorded_after_admission_and_before_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider = _allowance_client(monkeypatch)
    seen: list[int] = []
    client.on_invocation = lambda: seen.append(len(provider.invoke_calls)) or True

    _ask(client)

    assert seen == [0]
    assert len(provider.invoke_calls) == 1


def test_no_call_is_made_when_the_record_of_it_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, provider = _allowance_client(monkeypatch)
    client.on_invocation = lambda: False

    with pytest.raises(ai_service.AIInvocationFailure) as failure:
        _ask(client)

    assert failure.value.category == "lease_lost"
    assert provider.invoke_calls == []


def test_an_invocation_leaves_no_answer_budget_behind(table, model) -> None:
    """A warm Lambda's next answer would otherwise start already out of time."""
    from stoa.services import runtime_budget_service

    class _Context:
        def get_remaining_time_in_millis(self) -> int:
            return 170_000

    _commit("key-1")
    conversation_generation.handler({"conversation_id": CONV, "idempotency_key": "key-1"}, _Context())

    assert runtime_budget_service.ai_deadline(
        fixed_seconds=90, reserve_seconds=4, clock=lambda: 1000.0
    ) == 1090.0


def _die_on_renewals(monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    renew = attachment_repo.renew_message_ai_lease
    calls = {"renew": 0}

    def renew_or_die(**kwargs: Any) -> bool:
        calls["renew"] += 1
        if calls["renew"] <= count:
            raise _Killed()
        return renew(**kwargs)

    monkeypatch.setattr(attachment_repo, "renew_message_ai_lease", renew_or_die)


def test_a_kept_answer_survives_a_recovering_attempt_that_also_dies(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit("key-1")
    model.outcomes = [_Called()]
    _die_on_renewals(monkeypatch, 2)
    for _ in range(2):
        with pytest.raises(_Killed):
            _deliver("key-1")
        _expire_lease(table, "key-1")

    outcome = _deliver("key-1")

    assert outcome == {"outcome": "completed"}
    assert len(model.calls) == 1
    assert _generation(_client(), "key-1")["attempt"] == 3


def test_a_call_whose_failure_was_recorded_does_not_block_a_later_attempt(
    table, model
) -> None:
    """A recorded failure is a known outcome; only an unrecorded call is unknown."""
    committed = _commit("key-1")
    model.outcomes = [_Called(RuntimeError("provider refused")), _Killed()]
    with pytest.raises(conversations.AttachmentDecisionError):
        conversations.generate_for_command(committed)
    assert "provider_invoked_attempt" not in _command_row(table, "key-1")
    with pytest.raises(_Killed):
        conversations.generate_for_command(
            conversations.load_committed_message(dict(_command_row(table, "key-1")))
        )
    _expire_lease(table, "key-1")

    assert _deliver("key-1") == {"outcome": "completed"}
    assert len(model.calls) == 3


def test_a_duplicate_delivery_does_not_retry_a_failed_command(table, model) -> None:
    _commit("key-1")
    model.outcomes = [ai_service.AIInvocationFailure("deadline_exceeded")]
    assert _deliver("key-1") == {"outcome": "failed"}

    assert _deliver("key-1") == {"outcome": "settled"}
    assert len(model.calls) == 1


def test_a_recorded_failure_clears_what_the_attempt_left_behind(table, model) -> None:
    """Its outcome is known, so neither its mark nor any kept text should outlive it."""
    _commit("key-1")
    row = dict(_command_row(table, "key-1"))
    row.update(
        status="ai_running",
        leaseOwner="owner-1",
        attempt=1,
        expiresAt=2_000_000_000,
        provider_invoked_attempt=1,
        provider_result_attempt=1,
        provider_result_json='{"content":"private answer","allowance":null}',
    )
    table.seed(row)

    failed = attachment_repo.fail_message_command(
        conversation_id=CONV,
        idempotency_key="key-1",
        owner_id="student-1",
        lease_owner="owner-1",
        lease_attempt=1,
        failure_category="provider_error",
        retryable=True,
        now_iso="2026-09-25T08:00:00+00:00",
    )

    assert failed is True
    stored = _command_row(table, "key-1")
    for field in ("provider_invoked_attempt", "provider_result_attempt", "provider_result_json"):
        assert field not in stored


def test_a_claim_does_not_act_on_a_copy_read_before_a_call_was_marked(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit("key-1")
    model.outcomes = [_Called(_Killed())]
    with pytest.raises(_Killed):
        _deliver("key-1")
    _expire_lease(table, "key-1")
    stale = dict(_command_row(table, "key-1"))
    stale.pop("provider_invoked_attempt")
    read = attachment_repo.get_message_command
    monkeypatch.setattr(
        attachment_repo, "get_message_command", lambda *_a, **_k: dict(stale)
    )

    claimed = attachment_repo.claim_message_ai_lease(
        conversation_id=CONV,
        idempotency_key="key-1",
        owner_id="student-1",
        lease_owner="late",
        now_epoch=2_000_000_000,
        expires_at=2_000_000_300,
        account_fence_generation=1,
    )

    monkeypatch.setattr(attachment_repo, "get_message_command", read)
    assert claimed.disposition is not attachment_repo.MessageCommandDisposition.CLAIMED
    assert _command_row(table, "key-1").get("leaseOwner") != "late"


def test_one_command_that_breaks_does_not_stop_the_sweep(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("broken", "fine"):
        _commit(key)
        row = dict(_command_row(table, key))
        row["message_committed_at"] = "2026-09-24T08:00:00+00:00"
        row["created_at"] = row["created_at"] if key == "fine" else "2026-09-24T07:00:00+00:00"
        table.seed(row)
    load = conversations.load_committed_message

    def load_or_break(command: dict) -> Any:
        if command["idempotency_key"] == "broken":
            raise RuntimeError("unexpected")
        return load(command)

    monkeypatch.setattr(conversations, "load_committed_message", load_or_break)

    summary = conversation_generation.handler(
        {"source": "stoa.scheduler", "job": "conversation_generation_sweep"}, None
    )

    assert summary["errored"] == 1
    assert summary["completed"] == 1
    assert _command_row(table, "fine")["status"] == "completed"
