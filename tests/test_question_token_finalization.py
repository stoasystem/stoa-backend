"""Question token allowance finalization at the durable replay boundary."""

from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timezone

from stoa.db.repositories import allowance_repo, question_submission_repo
from stoa.services import allowance_service
from tests.test_phase475_question_effect_recovery import (
    EffectRecoveryTable,
    _client,
    _effect,
    _patch_runtime,
    _request,
)
from tests.test_token_allowances import AtomicAllowanceTable

from stoa.routers import questions


NOW = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)


class _ResponseBody:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.closed = False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


class MockBedrockProvider:
    """CountTokens plus InvokeModel fake; no network/provider access."""

    def __init__(
        self,
        *,
        input_tokens: object = 100,
        actual_input_tokens: int = 80,
        actual_output_tokens: int = 30,
        invoke_error: Exception | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.actual_input_tokens = actual_input_tokens
        self.actual_output_tokens = actual_output_tokens
        self.invoke_error = invoke_error
        self.count_calls: list[dict[str, object]] = []
        self.invoke_calls: list[dict[str, object]] = []

    def count_tokens(self, **kwargs: object) -> dict[str, object]:
        self.count_calls.append(copy.deepcopy(kwargs))
        return {
            "inputTokens": self.input_tokens,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "count-request-1",
            },
        }

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        if self.invoke_error is not None:
            raise self.invoke_error
        content = {
            "answer": "The original durable answer",
            "steps": ["Subtract four", "Divide by two"],
            "hints": [],
            "similar_exercises": [],
            "knowledge_points": ["linear equations"],
        }
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": self.actual_input_tokens,
                        "output_tokens": self.actual_output_tokens,
                    },
                    "content": [{"text": json.dumps(content)}],
                }
            ),
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "invoke-request-1",
            },
        }


def _patch_allowance_runtime(
    monkeypatch,
    *,
    question_table: EffectRecoveryTable,
    allowance_table: AtomicAllowanceTable,
    provider: MockBedrockProvider,
) -> None:
    _patch_runtime(monkeypatch, question_table)
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda *_args, **_kwargs: {
            "effectivePlan": "free_trial",
            "source": "free_trial_activation",
            "grantId": "free-trial-grant-1",
            "allowanceVersion": 7,
            "limits": {"dailyAiQuestionLimit": 2},
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(
        questions.ai_service.boto3,
        "client",
        lambda *_args, **_kwargs: provider,
    )
    reserve = allowance_service.reserve_token_allowance
    observe = allowance_service.record_provider_usage
    finalize = allowance_service.finalize_token_allowance
    restore = allowance_service.restore_user_allowance
    monkeypatch.setattr(
        questions.allowance_service,
        "reserve_token_allowance",
        lambda **kwargs: reserve(**kwargs, table=allowance_table),
    )
    monkeypatch.setattr(
        questions.allowance_service,
        "record_provider_usage",
        lambda **kwargs: observe(**kwargs, table=allowance_table),
    )
    monkeypatch.setattr(
        questions.allowance_service,
        "finalize_token_allowance",
        lambda **kwargs: finalize(**kwargs, table=allowance_table),
    )
    monkeypatch.setattr(
        questions.allowance_service,
        "restore_user_allowance",
        lambda **kwargs: restore(**kwargs, table=allowance_table),
    )


def _allowance_effect(table: AtomicAllowanceTable) -> dict[str, object]:
    rows = [
        item
        for item in table.items.values()
        if item.get("entity_type") == "allowance_effect"
    ]
    assert len(rows) == 1
    return copy.deepcopy(rows[0])


def test_count_failure_is_actionable_and_never_reserves_or_invokes(monkeypatch) -> None:
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider(input_tokens="not-an-exact-count")
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )

    response = _client().post("/questions", json=_request())

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "provider_token_count_unavailable",
        "message": "Token admission is temporarily unavailable. Retry this question.",
        "action": "retry_same_submission",
    }
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []
    assert not any(
        item.get("entity_type") == "allowance_effect"
        for item in allowance_table.items.values()
    )


def test_allowance_denial_never_invokes_provider(monkeypatch) -> None:
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )
    monkeypatch.setattr(
        questions.allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: allowance_repo.ReservationResult(
            allowance_repo.ReservationDisposition.LIMIT_EXCEEDED
        ),
    )

    response = _client().post("/questions", json=_request())

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "allowance_exhausted",
        "message": "Weekly AI token allowance is exhausted.",
        "action": "view_allowance",
    }
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []


def test_provider_timeout_after_reserve_remains_recoverable_without_restore(
    monkeypatch,
) -> None:
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider(invoke_error=TimeoutError("timeout-canary"))
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )

    response = _client().post("/questions", json=_request())

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert len(provider.invoke_calls) == 1
    effect = _allowance_effect(allowance_table)
    assert effect["state"] == "reserved"
    assert effect["reservation_input_tokens"] == 100
    assert effect["reservation_output_tokens"] == 2048
    counter = allowance_table.counter()
    assert counter["reserved_input_tokens"] == 100
    assert counter["reserved_output_tokens"] == 2048
    assert counter["finalized_input_tokens"] == 0
    assert counter.get("restored_input_tokens", 0) == 0
    assert _effect(question_table, "ai")["status"] == "provider_outcome_unknown"


def test_result_store_ambiguity_neither_finalizes_nor_restores(monkeypatch) -> None:
    question_table = EffectRecoveryTable()
    question_table.fail_result_before_commit = 3
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )

    response = _client().post("/questions", json=_request())

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert len(provider.invoke_calls) == 1
    effect = _allowance_effect(allowance_table)
    assert effect["state"] == "observed"
    assert effect.get("finalized_input_tokens", 0) == 0
    counter = allowance_table.counter()
    assert counter["reserved_input_tokens"] == 100
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["finalized_input_tokens"] == 0


def test_terminal_result_validation_failure_restores_user_but_retains_provider_cost(
    monkeypatch,
) -> None:
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )
    monkeypatch.setattr(
        question_submission_repo,
        "record_question_effect_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("validated-result-store-rejected")
        ),
    )

    response = _client().post("/questions", json=_request())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "question_submission_terminal_failed"
    effect = _allowance_effect(allowance_table)
    assert effect["state"] == "restored"
    counter = allowance_table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["finalized_output_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["provider_cost_output_tokens"] == 30
    assert len(allowance_table.evidence()) == 1


def test_finalize_timeout_replays_durable_result_then_commits_one_exact_debit(
    monkeypatch,
) -> None:
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )
    real_finalize = questions.allowance_service.finalize_token_allowance
    calls = 0

    def timeout_once(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return allowance_repo.FinalizationResult(
                allowance_repo.FinalizationDisposition.RETRYABLE
            )
        return real_finalize(**kwargs)

    monkeypatch.setattr(
        questions.allowance_service,
        "finalize_token_allowance",
        timeout_once,
    )

    first = _client().post("/questions", json=_request())
    second = _client().post("/questions", json=_request())

    assert first.status_code == 503
    assert first.json()["detail"]["code"] == "allowance_finalization_recoverable"
    assert second.status_code == 201
    assert second.json()["status"] == "ai_answered"
    assert second.json()["ai_response"]["answer"] == "The original durable answer"
    assert len(provider.invoke_calls) == 1
    counter = allowance_table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 80
    assert counter["finalized_output_tokens"] == 30


def test_disconnect_style_replay_keeps_exact_result_and_one_final_debit(
    monkeypatch,
) -> None:
    question_table = EffectRecoveryTable()
    question_table.fail_completion_after_commit = 1
    allowance_table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )

    first = _client().post("/questions", json=_request())
    durable_after_disconnect = copy.deepcopy(
        question_table.items[("QUESTION#question-effect-1", "META")]
    )
    second = _client().post("/questions", json=_request())

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(provider.invoke_calls) == 1
    assert durable_after_disconnect["status"] == "ai_answered"
    internal = durable_after_disconnect["ai_response"]
    assert internal["allowance_effect_id"]
    assert internal["provider_usage_evidence_id"]
    assert internal["allowance_finalization_status"] == "durable_result_boundary"
    public = json.dumps(second.json(), sort_keys=True)
    assert "allowance_effect_id" not in public
    assert "provider_usage_evidence_id" not in public
    assert "allowance_finalization_status" not in public
    counter = allowance_table.counter()
    assert counter["finalized_input_tokens"] == 80
    assert counter["finalized_output_tokens"] == 30
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["provider_cost_output_tokens"] == 30
    assert len(allowance_table.evidence()) == 1
    serialized_evidence = json.dumps(allowance_table.evidence(), default=str)
    assert "Please solve" not in serialized_evidence
    assert "original durable answer" not in serialized_evidence


def test_source_binds_phase475_effect_to_allowance_reserve_and_finalize() -> None:
    source = inspect.getsource(questions)
    reserve_at = source.index("reserve_token_allowance")
    invoke_at = source.index("invoke_model", reserve_at)
    assert reserve_at < invoke_at
    assert "question_effect_identity" in source
    assert "allowance_effect_id" in source
    assert "record_provider_usage" in source
    assert "finalize_token_allowance" in source
    assert "restore_user_allowance" in source
