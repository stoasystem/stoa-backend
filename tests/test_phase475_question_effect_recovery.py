"""Source-real recovery proof for question OCR and AI provider effects."""

from __future__ import annotations

import copy
import inspect
import threading
from collections.abc import Mapping

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import Settings, get_settings
from stoa.db.repositories import question_repo, question_submission_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import questions
from stoa.security.identity import AccountStatus, Actor, CanonicalRole


STUDENT_ID = "student-1"
QUESTION_ID = "question-effect-1"
NOW = "2026-07-22T12:00:00+00:00"


def _conditional_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "private-effect-condition-canary",
            },
            "CancellationReasons": [],
        },
        "TransactWriteItems",
    )


class EffectRecoveryTable:
    """Atomic fake that executes repository operations and injects boundary loss."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {
            (f"USER#{STUDENT_ID}", "ACCOUNT_FENCE"): {
                "PK": f"USER#{STUDENT_ID}",
                "SK": "ACCOUNT_FENCE",
                "entity_type": "account_fence",
                "status": "active",
                "generation": 1,
                "version": 1,
            }
        }
        self.transactions: list[list[dict[str, object]]] = []
        self.update_attempts: list[dict[str, object]] = []
        self.fail_completion_before_commit = 0
        self.fail_completion_after_commit = 0
        self.fail_result_before_commit = 0
        self._lock = threading.Lock()

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        with self._lock:
            item = copy.deepcopy(self.items.get((Key["PK"], Key["SK"])))
        return {"Item": item} if item is not None else {}

    def update_item(self, **kwargs):
        with self._lock:
            self.update_attempts.append(copy.deepcopy(kwargs))
            values = kwargs["ExpressionAttributeValues"]
            if ":result_ready" in values and self.fail_result_before_commit:
                self.fail_result_before_commit -= 1
                raise TimeoutError("result-receipt-precommit-canary")
            key = (kwargs["Key"]["PK"], kwargs["Key"]["SK"])
            current = self.items.get(key)
            if current is None:
                raise _conditional_error()
            self._validate_effect_update(current, kwargs)
            self._apply_effect_update(current, kwargs)
        return {}

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        operations = copy.deepcopy(TransactItems)
        completion = any(
            ":completed" in operation.get("Update", {}).get(
                "ExpressionAttributeValues", {}
            )
            for operation in operations
        )
        with self._lock:
            self._validate_transaction(operations)
            if completion and self.fail_completion_before_commit:
                self.fail_completion_before_commit -= 1
                raise TimeoutError("completion-precommit-canary")
            self._apply_transaction(operations)
            self.transactions.append(operations)
            if completion and self.fail_completion_after_commit:
                self.fail_completion_after_commit -= 1
                raise TimeoutError("completion-committed-response-lost-canary")
        return {}

    def _validate_transaction(self, operations: list[dict[str, object]]) -> None:
        for operation in operations:
            if "ConditionCheck" in operation:
                check = operation["ConditionCheck"]
                current = self.items.get((check["Key"]["PK"], check["Key"]["SK"]))
                if current is None:
                    raise _conditional_error()
                values = check.get("ExpressionAttributeValues", {})
                if ":active" in values and current.get("status") != values[":active"]:
                    raise _conditional_error()
                if ":generation" in values and current.get("generation") != values[":generation"]:
                    raise _conditional_error()
                self._validate_bound_row(current, values)
            elif "Put" in operation:
                put = operation["Put"]
                item = put["Item"]
                key = (item["PK"], item["SK"])
                if key in self.items:
                    raise _conditional_error()
            elif "Update" in operation:
                update = operation["Update"]
                key = (update["Key"]["PK"], update["Key"]["SK"])
                current = self.items.get(key)
                values = update["ExpressionAttributeValues"]
                if key[0].startswith("USAGE#"):
                    expected = values.get(":expected")
                    count = int(current.get("count", 0)) if current else 0
                    if expected is None and current is not None:
                        raise _conditional_error()
                    if expected is not None and count != expected:
                        raise _conditional_error()
                    if int(values[":next"]) > int(values[":limit"]):
                        raise _conditional_error()
                    continue
                if current is None:
                    raise _conditional_error()
                self._validate_bound_row(current, values)
                if key[1].startswith("QUESTION_EFFECT#"):
                    self._validate_effect_update(current, update)

    @staticmethod
    def _validate_bound_row(current: Mapping[str, object], values: Mapping[str, object]) -> None:
        comparisons = {
            ":student": "student_id",
            ":owner": "student_id",
            ":command_id": "command_id",
            ":question": "question_id",
            ":fingerprint": "fingerprint",
            ":effect_id": "effect_id",
            ":effect_kind": "effect_kind",
            ":schema": "schema_version",
            ":generation": "account_fence_generation",
        }
        for token, field in comparisons.items():
            if token in values and field in current and current.get(field) != values[token]:
                raise _conditional_error()
        for token in (
            ":command_version",
            ":question_version",
            ":effect_version",
            ":expected_version",
        ):
            if token in values and current.get("version") != values[token]:
                raise _conditional_error()
        expected_status = values.get(":expected_status")
        if expected_status is not None and current.get("status") != expected_status:
            raise _conditional_error()
        if ":processing" in values and current.get("status") != values[":processing"]:
            raise _conditional_error()
        if ":result_ready" in values and ":completed" in values:
            if current.get("status") != values[":result_ready"]:
                raise _conditional_error()
            if current.get("result_digest") != values[":result_digest"]:
                raise _conditional_error()

    def _validate_effect_update(self, current, update) -> None:
        self._validate_bound_row(current, update["ExpressionAttributeValues"])

    @staticmethod
    def _apply_effect_update(current, update) -> None:
        values = update["ExpressionAttributeValues"]
        if ":result_ready" in values and ":result" in values:
            current.update(
                status=values[":result_ready"],
                result=copy.deepcopy(values[":result"]),
                result_digest=values[":result_digest"],
                result_recorded_at=values[":recorded_at"],
                version=values[":next_version"],
            )
        elif ":outcome_unknown" in values:
            current.update(
                status=values[":outcome_unknown"],
                outcome_unknown_at=values[":observed_at"],
                version=values[":next_version"],
            )
        elif ":terminal" in values:
            current.update(
                status=values[":terminal"],
                terminal_failure_code=values[":failure_code"],
                terminal_at=values[":failed_at"],
                version=values[":next_version"],
            )
        elif ":completed" in values:
            current.update(
                status=values[":completed"],
                completed_at=values[":completed_at"],
                version=values[":next_effect_version"],
            )

    def _apply_transaction(self, operations: list[dict[str, object]]) -> None:
        for operation in operations:
            if "Put" in operation:
                item = copy.deepcopy(operation["Put"]["Item"])
                self.items[(item["PK"], item["SK"])] = item
                continue
            if "Update" not in operation:
                continue
            update = operation["Update"]
            key = (update["Key"]["PK"], update["Key"]["SK"])
            values = update["ExpressionAttributeValues"]
            current = self.items.setdefault(key, {"PK": key[0], "SK": key[1]})
            if key[0].startswith("USAGE#"):
                current.update(
                    count=values[":next"],
                    expires_at=values[":expires"],
                    usage_type=values[":usage_type"],
                )
            elif key[1].startswith("QUESTION_EFFECT#"):
                self._apply_effect_update(current, update)
            elif key[0].startswith("QUESTION#"):
                current["status"] = values[":next_status"]
                current["version"] = values[":next_question_version"]
                for token, value in values.items():
                    if token.startswith(":field_"):
                        current[token.removeprefix(":field_")] = copy.deepcopy(value)
            elif key[1].startswith("QUESTION_SUBMISSION#"):
                current.update(
                    status=values[":next_command_status"],
                    version=values[":next_command_version"],
                    updated_at=values[":completed_at"],
                    last_effect_id=values[":effect_id"],
                    last_effect_kind=values[":effect_kind"],
                )


def _actor() -> Actor:
    return Actor(
        STUDENT_ID,
        "https://identity.test",
        "student-1-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        CanonicalRole.STUDENT.value,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = lambda: Settings(
        free_tier_daily_question_limit=2,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
    )
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _patch_runtime(monkeypatch, table: EffectRecoveryTable) -> None:
    monkeypatch.setattr(question_submission_repo, "get_table", lambda: table)
    monkeypatch.setattr(question_repo, "get_table", lambda: table)
    monkeypatch.setattr(questions.uuid, "uuid4", lambda: QUESTION_ID)
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda _student_id: {
            "user_id": STUDENT_ID,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda *_args, **_kwargs: {
            "effectivePlan": "free",
            "source": "local",
            "limits": {"dailyAiQuestionLimit": 2},
            "blockingReason": None,
        },
    )


def _request(*, attachment: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "content": "Please solve 2x + 4 = 10",
        "subject": "math",
        "idempotencyKey": "question-effect-recovery",
    }
    if attachment:
        body["attachment"] = {"attachmentId": "attachment-1"}
    return body


def _ai_answer() -> dict[str, object]:
    return {
        "answer": "The original durable answer",
        "steps": ["Subtract four", "Divide by two"],
        "hints": [],
        "similar_exercises": [],
        "knowledge_points": ["linear equations"],
    }


def _effect(table: EffectRecoveryTable, kind: str) -> dict[str, object]:
    matches = [
        item
        for item in table.items.values()
        if item.get("entity_type") == "question_provider_effect"
        and item.get("effect_kind") == kind
    ]
    assert len(matches) == 1
    return matches[0]


def test_ai_success_then_completion_failure_replays_durable_receipt_without_provider(
    monkeypatch,
) -> None:
    table = EffectRecoveryTable()
    table.fail_completion_before_commit = 1
    _patch_runtime(monkeypatch, table)
    provider_results: list[dict[str, object]] = []

    def answer(**_kwargs):
        result = _ai_answer()
        provider_results.append(result)
        return copy.deepcopy(result)

    monkeypatch.setattr(questions.ai_service, "get_ai_answer", answer)

    first = _client().post("/questions", json=_request())
    receipt_after_failure = copy.deepcopy(_effect(table, "ai"))
    second = _client().post("/questions", json=_request())

    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == "pending"
    assert second.json()["status"] == "ai_answered"
    assert second.json()["ai_response"] == _ai_answer()
    assert provider_results == [_ai_answer()]
    assert receipt_after_failure["status"] == "result_ready"
    assert receipt_after_failure["schema_version"] == "question-provider-effect.v1"
    assert receipt_after_failure["student_id"] == STUDENT_ID
    assert receipt_after_failure["question_id"] == QUESTION_ID
    assert receipt_after_failure["account_fence_generation"] == 1
    assert receipt_after_failure["command_version"] == 1
    assert receipt_after_failure["question_version"] == 1
    assert receipt_after_failure["result"]["ai_response"] == _ai_answer()
    assert _effect(table, "ai")["status"] == "completed"


def test_committed_completion_response_loss_reconciles_exact_original_result(
    monkeypatch,
) -> None:
    table = EffectRecoveryTable()
    table.fail_completion_after_commit = 1
    _patch_runtime(monkeypatch, table)
    provider_calls = 0

    def answer(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return _ai_answer()

    monkeypatch.setattr(questions.ai_service, "get_ai_answer", answer)

    first = _client().post("/questions", json=_request())
    second = _client().post("/questions", json=_request())

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["ai_response"] == _ai_answer()
    assert provider_calls == 1
    assert _effect(table, "ai")["status"] == "completed"


def test_result_receipt_failure_closes_unknown_state_and_never_blindly_reinvokes(
    monkeypatch,
) -> None:
    table = EffectRecoveryTable()
    table.fail_result_before_commit = 1
    _patch_runtime(monkeypatch, table)
    provider_calls = 0

    def answer(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return _ai_answer()

    monkeypatch.setattr(questions.ai_service, "get_ai_answer", answer)

    first = _client().post("/questions", json=_request())
    second = _client().post("/questions", json=_request())

    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == second.json()["status"] == "pending"
    assert provider_calls == 1
    assert _effect(table, "ai")["status"] == "provider_outcome_unknown"
    assert table.items[(f"QUESTION#{QUESTION_ID}", "META")]["ai_response"] is None


def test_ocr_success_receipt_recovers_real_question_and_command_transaction(
    monkeypatch,
) -> None:
    table = EffectRecoveryTable()
    table.fail_completion_before_commit = 1
    _patch_runtime(monkeypatch, table)
    ocr_calls = 0
    ai_calls = 0
    prepared = {
        "attachment": {
            "attachment_id": "attachment-1",
            "original_filename": "exercise.png",
            "detected_type": "image/png",
            "content_length": 123,
            "created_at": NOW,
            "status": "active",
            "immutable_object_key": "private-key-canary",
            "immutable_version_id": "private-version-canary",
            "immutable_etag": "private-etag-canary",
            "content_sha256": "a" * 64,
        }
    }
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *_args, **_kwargs: copy.deepcopy(prepared),
    )
    monkeypatch.setattr(questions, "_question_attachment_operations", lambda **_kwargs: ())

    def ocr(*_args, **_kwargs):
        nonlocal ocr_calls
        ocr_calls += 1
        return "x + 4 = 10"

    def ai(**_kwargs):
        nonlocal ai_calls
        ai_calls += 1
        return _ai_answer()

    monkeypatch.setattr(questions.ocr_service, "extract_text_from_attachment", ocr)
    monkeypatch.setattr(questions.ai_service, "get_ai_answer", ai)

    first = _client().post("/questions", json=_request(attachment=True))
    second = _client().post("/questions", json=_request(attachment=True))

    assert first.status_code == second.status_code == 201
    assert first.json()["ocr_metadata"]["status"] == "processing"
    assert second.json()["ocr_metadata"]["status"] == "succeeded"
    assert ocr_calls == 1
    assert ai_calls == 0
    receipt = _effect(table, "ocr")
    assert receipt["status"] == "completed"
    assert receipt["result"]["ocr_text"] == "x + 4 = 10"
    assert table.items[(f"QUESTION#{QUESTION_ID}", "META")]["version"] == 2
    command = next(
        item
        for item in table.items.values()
        if item.get("entity_type") == "question_submission_command"
    )
    assert command["version"] == 2
    assert command["status"] == "processing"


def test_effect_proof_executes_repository_boundaries_instead_of_monkeypatching_them() -> None:
    module = inspect.getmodule(
        test_ai_success_then_completion_failure_replays_durable_receipt_without_provider
    )
    assert module is not None
    source = inspect.getsource(module)

    for function_name in (
        "admit_question_submission",
        "begin_question_effect",
        "record_question_effect_result",
        "complete_question_effect",
    ):
        assert (
            f'setattr(questions.question_submission_repo, "{function_name}"'
            not in source
        )
    assert (
        "setattr(questions.question_repo, " + '"get_question"'
        not in source
    )
