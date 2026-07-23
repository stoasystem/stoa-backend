"""Recovery, reversal, attachment-retention, and replay proof for Plan 475-03."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
import threading

from botocore.exceptions import ClientError
import pytest

from stoa.db.repositories import question_submission_repo
from stoa.jobs import reconcile_question_submissions
from stoa.services import usage_ledger_service
from tests.dynamodb_expression_assertions import (
    assert_expression_placeholders_closed,
)


STUDENT_ID = "student-opaque-1"
REQUEST_ID = question_submission_repo.question_submission_command_digest(
    STUDENT_ID, "request-opaque-1"
)
QUESTION_ID = "question-opaque-1"
PERIOD = "2026-07-22"
COMMAND_KEY = (f"USER#{STUDENT_ID}", f"QUESTION_SUBMISSION#{REQUEST_ID}")
QUESTION_KEY = (f"QUESTION#{QUESTION_ID}", "META")
COUNTER_KEY = (f"USAGE#{STUDENT_ID}", f"QUESTION#{PERIOD}")
LEDGER_KEY = (
    f"USAGE_LEDGER#{STUDENT_ID}",
    f"EVENT#question_submission#{PERIOD}#{REQUEST_ID}",
)
ATTACHMENT_KEY = ("ATTACHMENT#attachment-opaque-1", "META")
STORAGE_KEY = (f"USER#{STUDENT_ID}", "ATTACHMENT_STORAGE")


def _conditional_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "private-provider-canary",
            },
            "CancellationReasons": [],
        },
        "TransactWriteItems",
    )


def _seed(*, terminal: bool = False) -> dict[tuple[str, str], dict[str, object]]:
    status = "terminal_failed" if terminal else "processing"
    terminal_effect_id = "e" * 64
    command: dict[str, object] = {
        "PK": COMMAND_KEY[0],
        "SK": COMMAND_KEY[1],
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "command_id": REQUEST_ID,
        "student_id": STUDENT_ID,
        "idempotency_digest": REQUEST_ID,
        "fingerprint": "f" * 64,
        "question_id": QUESTION_ID,
        "quota_period": PERIOD,
        "counter_value": 1,
        "ledger_identity": REQUEST_ID,
        "attachment_identities": ["attachment:opaque"],
        "status": status,
        "version": 2 if terminal else 1,
        "account_fence_generation": 1,
        "created_at": "2026-07-22T08:00:00+00:00",
        "updated_at": "2026-07-22T08:00:00+00:00",
    }
    if terminal:
        command.update(
            terminal_failure_code="provider_terminal_rejection",
            terminal_failure_proven_at="2026-07-22T08:01:00+00:00",
            terminal_effect_id=terminal_effect_id,
            terminal_effect_kind="ocr",
        )
    question: dict[str, object] = {
        "PK": QUESTION_KEY[0],
        "SK": QUESTION_KEY[1],
        "entity_type": "question",
        "schema_version": "question.v1",
        "question_id": QUESTION_ID,
        "student_id": STUDENT_ID,
        "account_fence_generation": 1,
        "status": "pending" if terminal else "ai_answered",
        "version": 2 if terminal else 1,
        "ai_response": None if terminal else {"answer": "private-answer-canary"},
        "attachment_id": "attachment-opaque-1",
        "content": "private-question-canary",
    }
    if terminal:
        question.update(
            terminal_failure_code=command["terminal_failure_code"],
            terminal_failure_proven_at=command["terminal_failure_proven_at"],
            terminal_effect_id=terminal_effect_id,
            terminal_effect_kind="ocr",
        )
    ledger = {
        "PK": LEDGER_KEY[0],
        "SK": LEDGER_KEY[1],
        "entity_type": "usage_ledger_event",
        "event_id": command["ledger_identity"],
        "student_id": STUDENT_ID,
        "question_id": QUESTION_ID,
        "action": "question_submission",
        "quantity": 1,
        "quota_period": PERIOD,
        "idempotency_digest": REQUEST_ID,
        "status": "active",
    }
    return {
        COMMAND_KEY: command,
        QUESTION_KEY: question,
        COUNTER_KEY: {
            "PK": COUNTER_KEY[0],
            "SK": COUNTER_KEY[1],
            "count": 1,
            "used_bytes": 9999,
        },
        LEDGER_KEY: ledger,
        ATTACHMENT_KEY: {
            "PK": ATTACHMENT_KEY[0],
            "SK": ATTACHMENT_KEY[1],
            "attachment_id": "attachment-opaque-1",
            "owner_id": STUDENT_ID,
            "status": "active",
            "content_length": 4096,
            "immutable_object_key": "private/object/key",
            "immutable_version_id": "private-version-id",
        },
        STORAGE_KEY: {
            "PK": STORAGE_KEY[0],
            "SK": STORAGE_KEY[1],
            "used_bytes": 4096,
            "limit_bytes": 10000,
        },
    }


class _ReconciliationTable:
    def __init__(
        self,
        items: dict[tuple[str, str], dict[str, object]],
        *,
        synchronize_transactions: bool = False,
        fail_after_commit: bool = False,
        fail_operation_index: int | None = None,
    ) -> None:
        self.items = copy.deepcopy(items)
        self.transactions: list[list[dict[str, object]]] = []
        self._lock = threading.Lock()
        self._barrier = threading.Barrier(2) if synchronize_transactions else None
        self._failed_after_commit = not fail_after_commit
        self._fail_operation_index = fail_operation_index

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        with self._lock:
            item = copy.deepcopy(self.items.get((Key["PK"], Key["SK"])))
        return {"Item": item} if item is not None else {}

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        operations = copy.deepcopy(TransactItems)
        if self._barrier is not None:
            try:
                self._barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
        with self._lock:
            self._validate(operations)
            if self._fail_operation_index is not None:
                assert 0 <= self._fail_operation_index < len(operations)
                raise _conditional_error()
            self._apply(operations)
            self.transactions.append(operations)
            if not self._failed_after_commit:
                self._failed_after_commit = True
                raise TimeoutError("lost-response-private-canary")
        return {}

    def _validate(self, operations: list[dict[str, object]]) -> None:
        for operation in operations:
            assert_expression_placeholders_closed(operation)
            update = operation.get("Update") or operation.get("ConditionCheck")
            key = (update["Key"]["PK"], update["Key"]["SK"])
            current = self.items.get(key)
            if current is None:
                raise _conditional_error()
            values = update["ExpressionAttributeValues"]
            if "ConditionCheck" in operation:
                if current.get("student_id") != values[":student"]:
                    raise _conditional_error()
                if current.get("question_id") != values[":question"]:
                    raise _conditional_error()
                expected_version = values.get(":question_version")
                if expected_version is None and "version" in current:
                    raise _conditional_error()
                if expected_version is not None and current.get("version") != expected_version:
                    raise _conditional_error()
                if ":question_status" in values:
                    if current.get("status") != values[":question_status"]:
                        raise _conditional_error()
                elif not isinstance(current.get("ai_response"), dict):
                    raise _conditional_error()
                continue
            if key == COMMAND_KEY:
                expected_status = values.get(":processing", values.get(":terminal"))
                if current.get("status") != expected_status:
                    raise _conditional_error()
                if current.get("version") != values[":version"]:
                    raise _conditional_error()
                if current.get("reversal_id") is not None:
                    raise _conditional_error()
            elif key == QUESTION_KEY:
                if current.get("status") == "submission_failed":
                    raise _conditional_error()
                expected_version = values.get(":question_version")
                if expected_version is None:
                    if "version" in current:
                        raise _conditional_error()
                elif current.get("version") != expected_version:
                    raise _conditional_error()
            elif key == COUNTER_KEY:
                if current.get("count") != values[":expected"]:
                    raise _conditional_error()
            elif key == LEDGER_KEY:
                if current.get("event_id") != values[":ledger"]:
                    raise _conditional_error()
                if current.get("status", "active") != "active":
                    raise _conditional_error()
                if current.get("reversal_id") is not None:
                    raise _conditional_error()

    def _apply(self, operations: list[dict[str, object]]) -> None:
        for operation in operations:
            if "Update" not in operation:
                continue
            update = operation["Update"]
            key = (update["Key"]["PK"], update["Key"]["SK"])
            current = self.items[key]
            values = update["ExpressionAttributeValues"]
            if key == COMMAND_KEY and ":completed" in values:
                current.update(
                    status="completed",
                    completed_at=values[":applied_at"],
                    updated_at=values[":applied_at"],
                    version=values[":next_version"],
                )
            elif key == COMMAND_KEY:
                current.update(
                    reversal_id=values[":reversal"],
                    reversed_at=values[":reversed_at"],
                    updated_at=values[":reversed_at"],
                    version=values[":next_version"],
                )
            elif key == QUESTION_KEY:
                current.update(
                    status="submission_failed",
                    failure_code=values[":failure_code"],
                    failed_at=values[":reversed_at"],
                    version=int(current.get("version", 0)) + 1,
                )
            elif key == COUNTER_KEY:
                current["count"] = int(current["count"]) - 1
            elif key == LEDGER_KEY:
                current.update(
                    status="reversed",
                    reversal_id=values[":reversal"],
                    reversed_at=values[":reversed_at"],
                    updated_at=values[":reversed_at"],
                )


def _preview(
    table: _ReconciliationTable,
    **kwargs: object,
) -> question_submission_repo.QuestionReconciliationPreview:
    return question_submission_repo.preview_question_submission_reconciliation(
        student_id=STUDENT_ID,
        idempotency_key=REQUEST_ID,
        table=table,
        **kwargs,
    )


def _apply(
    table: _ReconciliationTable,
    preview: question_submission_repo.QuestionReconciliationPreview,
) -> question_submission_repo.QuestionReconciliationPreview:
    return question_submission_repo.apply_question_submission_reconciliation(
        preview,
        student_id=STUDENT_ID,
        idempotency_key=REQUEST_ID,
        applied_at="2026-07-22T09:00:00+00:00",
        table=table,
    )


def test_preview_is_write_free_and_classifies_current_and_legacy_states() -> None:
    complete = _ReconciliationTable(_seed())
    terminal = _ReconciliationTable(_seed(terminal=True))
    legacy_items = _seed()
    legacy_items.pop(COMMAND_KEY)
    legacy_items.pop(QUESTION_KEY)
    legacy = _ReconciliationTable(legacy_items)

    recovered = _preview(complete)
    reversed_preview = _preview(terminal)
    historical = _preview(
        legacy,
        question_id=QUESTION_ID,
        quota_period=PERIOD,
    )

    assert recovered.disposition.value == "recoverable_processing"
    assert recovered.proposed_action == "mark_command_completed"
    assert reversed_preview.disposition.value == "proven_terminal_failure"
    assert historical.disposition.value == "legacy_counter_ledger_without_question"
    assert historical.proposed_action == "report_only"
    assert complete.transactions == terminal.transactions == legacy.transactions == []


def test_apply_repairs_durable_result_once_and_retry_writes_nothing() -> None:
    table = _ReconciliationTable(_seed())
    preview = _preview(table)

    first = _apply(table, preview)
    writes_after_first = len(table.transactions)
    second = _apply(table, preview)

    assert first.disposition.value == "committed"
    assert first.mutation_count == 1
    assert table.items[COMMAND_KEY]["status"] == "completed"
    assert table.items[COMMAND_KEY]["version"] == 2
    assert second.disposition.value == "changed_after_preview"
    assert second.mutation_count == 0
    assert len(table.transactions) == writes_after_first == 1


def test_terminal_reversal_is_exact_once_and_attachment_storage_are_unchanged() -> None:
    table = _ReconciliationTable(_seed(terminal=True))
    attachment_before = copy.deepcopy(table.items[ATTACHMENT_KEY])
    storage_before = copy.deepcopy(table.items[STORAGE_KEY])
    preview = _preview(table)

    first = usage_ledger_service.reverse_terminal_question_admission(
        preview,
        student_id=STUDENT_ID,
        idempotency_key=REQUEST_ID,
        reversed_at="2026-07-22T09:00:00+00:00",
        table=table,
    )
    fresh = _preview(table)
    second = usage_ledger_service.reverse_terminal_question_admission(
        fresh,
        student_id=STUDENT_ID,
        idempotency_key=REQUEST_ID,
        reversed_at="2026-07-22T09:01:00+00:00",
        table=table,
    )

    assert first.disposition.value == "committed"
    assert first.mutation_count == 4
    assert second.disposition.value == "committed"
    assert second.mutation_count == 0
    assert table.items[COUNTER_KEY]["count"] == 0
    assert table.items[LEDGER_KEY]["quantity"] == 1
    assert table.items[LEDGER_KEY]["status"] == "reversed"
    assert table.items[QUESTION_KEY]["status"] == "submission_failed"
    assert table.items[COMMAND_KEY]["reversal_id"] == table.items[LEDGER_KEY]["reversal_id"]
    assert table.items[ATTACHMENT_KEY] == attachment_before
    assert table.items[STORAGE_KEY] == storage_before
    assert all(
        operation["Update"]["Key"] not in (
            {"PK": ATTACHMENT_KEY[0], "SK": ATTACHMENT_KEY[1]},
            {"PK": STORAGE_KEY[0], "SK": STORAGE_KEY[1]},
        )
        for transaction in table.transactions
        for operation in transaction
    )


def test_changed_after_preview_and_conflicting_history_are_report_only() -> None:
    table = _ReconciliationTable(_seed())
    preview = _preview(table)
    table.items[QUESTION_KEY]["ai_response"] = {"answer": "newer-private-answer"}

    changed = _apply(table, preview)

    conflict_items = _seed()
    conflict_items[LEDGER_KEY]["question_id"] = "different-question"
    conflict = _preview(_ReconciliationTable(conflict_items))
    assert changed.disposition.value == "changed_after_preview"
    assert changed.mutation_count == 0
    assert table.transactions == []
    assert conflict.disposition.value == "conflicting_evidence"
    assert conflict.proposed_action == "report_only"


def test_two_concurrent_reversals_commit_one_exact_compensation() -> None:
    table = _ReconciliationTable(_seed(terminal=True), synchronize_transactions=True)
    preview = _preview(table)
    outcomes: list[question_submission_repo.QuestionReconciliationPreview] = []

    def run() -> None:
        outcomes.append(_apply(table, preview))

    workers = [threading.Thread(target=run), threading.Thread(target=run)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    assert table.items[COUNTER_KEY]["count"] == 0
    assert table.items[LEDGER_KEY]["status"] == "reversed"
    assert len(table.transactions) == 1
    assert {result.disposition.value for result in outcomes} <= {
        "committed",
        "changed_after_preview",
    }


def test_lost_apply_response_reconciles_without_second_compensation() -> None:
    table = _ReconciliationTable(_seed(terminal=True), fail_after_commit=True)
    preview = _preview(table)

    first = _apply(table, preview)
    second = _apply(table, preview)

    assert first.disposition.value == "committed"
    assert second.disposition.value == "changed_after_preview"
    assert table.items[COUNTER_KEY]["count"] == 0
    assert len(table.transactions) == 1


def test_each_terminal_transaction_boundary_fails_without_partial_compensation() -> None:
    for operation_index in range(4):
        table = _ReconciliationTable(
            _seed(terminal=True), fail_operation_index=operation_index
        )
        before = copy.deepcopy(table.items)

        outcome = _apply(table, _preview(table))

        assert outcome.disposition.value == "changed_after_preview"
        assert outcome.mutation_count == 0
        assert table.items == before
        assert table.transactions == []


def test_reversed_events_do_not_count_as_consumed_but_keep_audit_quantity(monkeypatch) -> None:
    events = [copy.deepcopy(_seed(terminal=True)[LEDGER_KEY])]
    events[0]["status"] = "reversed"
    monkeypatch.setattr(
        usage_ledger_service.usage_ledger_repo,
        "get_daily_question_counter",
        lambda *_args, **_kwargs: {"count": 0},
    )
    monkeypatch.setattr(
        usage_ledger_service.usage_ledger_repo,
        "list_usage_events",
        lambda **_kwargs: events,
    )

    result = usage_ledger_service.reconcile_question_usage(
        student_id=STUDENT_ID,
        day=PERIOD,
    )

    assert result["counterCount"] == result["ledgerCount"] == 0
    assert result["status"] == "no-usage"
    assert events[0]["quantity"] == 1


def test_job_defaults_to_preview_and_apply_uses_only_bounded_coordinates() -> None:
    table = _ReconciliationTable(_seed())
    coordinate = reconcile_question_submissions.QuestionReconciliationCoordinate(
        student_id=STUDENT_ID,
        command_digest=REQUEST_ID,
    )

    preview = reconcile_question_submissions.reconcile_question_submissions(
        (coordinate,), table=table
    )
    applied = reconcile_question_submissions.reconcile_question_submissions(
        (coordinate,),
        apply=True,
        table=table,
        now=datetime(2026, 7, 22, 9, tzinfo=UTC),
    )

    assert preview.mode == "preview"
    assert preview.mutated == 0
    assert table.items[COMMAND_KEY]["status"] == "completed"
    assert applied.mode == "apply"
    assert applied.inspected == 1
    assert applied.mutated == 1
    public_output = str(preview.public_dict())
    assert "request-opaque-1" not in public_output
    assert "private-question-canary" not in public_output
    assert "private-answer-canary" not in public_output
    assert "private/object/key" not in public_output
    assert "private-version-id" not in public_output


class _PreviewRepositorySpy:
    def __init__(self) -> None:
        self.preview_calls: list[dict[str, object]] = []

    def preview_question_submission_reconciliation(
        self, **kwargs: object
    ) -> question_submission_repo.QuestionReconciliationPreview:
        self.preview_calls.append(kwargs)
        return question_submission_repo.QuestionReconciliationPreview(
            disposition=(
                question_submission_repo.QuestionReconciliationDisposition.COMMITTED
            ),
            command_id=REQUEST_ID,
            question_id=QUESTION_ID,
            observed_command_version=2,
            observed_question_version=3,
            observed_digest="e" * 64,
            proposed_action="none",
        )


def test_privacy_rejects_malformed_coordinate_before_repository_access() -> None:
    raw_key_canary = "student@example.invalid private question text"
    repository = _PreviewRepositorySpy()
    coordinate = reconcile_question_submissions.QuestionReconciliationCoordinate(
        student_id=STUDENT_ID,
        command_digest=raw_key_canary,
    )

    with pytest.raises(ValueError) as raised:
        reconcile_question_submissions.reconcile_question_submissions(
            (coordinate,), repository=repository
        )

    assert repository.preview_calls == []
    assert raw_key_canary not in str(raised.value)


def test_lambda_accepts_only_closed_opaque_coordinate_fields(monkeypatch) -> None:
    raw_key_canary = "raw-lambda-private-canary"
    calls: list[tuple[object, ...]] = []

    def fake_reconcile(coordinates, **_kwargs):
        calls.append(tuple(coordinates))
        return reconcile_question_submissions.QuestionReconciliationJobResult(
            mode="preview", inspected=1, mutated=0, results=()
        )

    monkeypatch.setattr(
        reconcile_question_submissions,
        "reconcile_question_submissions",
        fake_reconcile,
    )

    result = reconcile_question_submissions.handler(
        {
            "coordinates": [
                {"studentId": STUDENT_ID, "commandDigest": REQUEST_ID}
            ]
        },
        None,
    )

    assert result == {
        "mode": "preview",
        "inspected": 1,
        "mutated": 0,
        "results": (),
    }
    assert len(calls) == 1
    assert calls[0][0].student_id == STUDENT_ID
    assert calls[0][0].command_digest == REQUEST_ID

    for invalid in (
        {
            "coordinates": [
                {"studentId": STUDENT_ID, "idempotencyKey": raw_key_canary}
            ]
        },
        {
            "coordinates": [
                {
                    "studentId": STUDENT_ID,
                    "commandDigest": REQUEST_ID,
                    "questionText": raw_key_canary,
                }
            ]
        },
        {
            "coordinates": [
                {"studentId": STUDENT_ID, "commandDigest": raw_key_canary}
            ]
        },
    ):
        with pytest.raises(ValueError) as raised:
            reconcile_question_submissions.handler(invalid, None)
        assert raw_key_canary not in str(raised.value)

    assert len(calls) == 1


def test_cli_uses_command_digest_and_redacts_invalid_input(monkeypatch, capsys) -> None:
    raw_key_canary = "raw-cli-private-canary"
    captured_coordinates: list[object] = []

    def fake_reconcile(coordinates, **_kwargs):
        captured_coordinates.extend(coordinates)
        return reconcile_question_submissions.QuestionReconciliationJobResult(
            mode="preview", inspected=1, mutated=0, results=()
        )

    monkeypatch.setattr(
        reconcile_question_submissions,
        "reconcile_question_submissions",
        fake_reconcile,
    )

    assert (
        reconcile_question_submissions.main(
            [
                "--student-id",
                STUDENT_ID,
                "--command-digest",
                REQUEST_ID,
            ]
        )
        == 0
    )
    assert captured_coordinates[0].command_digest == REQUEST_ID

    with pytest.raises(SystemExit):
        reconcile_question_submissions.main(
            [
                "--student-id",
                STUDENT_ID,
                "--idempotency-key",
                raw_key_canary,
            ]
        )

    diagnostics = capsys.readouterr().err
    assert raw_key_canary not in diagnostics


def test_preview_output_is_closed_and_contains_only_opaque_identities() -> None:
    repository = _PreviewRepositorySpy()
    coordinate = reconcile_question_submissions.QuestionReconciliationCoordinate(
        student_id=STUDENT_ID,
        command_digest=REQUEST_ID,
    )

    result = reconcile_question_submissions.reconcile_question_submissions(
        (coordinate,), repository=repository
    ).public_dict()

    assert set(result) == {"mode", "inspected", "mutated", "results"}
    assert set(result["results"][0]) == {
        "disposition",
        "commandId",
        "questionId",
        "observedCommandVersion",
        "observedQuestionVersion",
        "observedDigest",
        "proposedAction",
        "mutationCount",
    }
    assert result["results"][0]["commandId"] == REQUEST_ID
    assert repository.preview_calls == [
        {
            "student_id": STUDENT_ID,
            "idempotency_key": REQUEST_ID,
            "table": None,
        }
    ]
