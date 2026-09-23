"""The escalation consumer against the record shapes SQS actually delivers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, question_repo
from stoa.jobs import teacher_escalation
from stoa.services import teacher_dispatch_service


PAYLOAD = {"operation_id": "operation-1", "question_id": "question-1", "generation": 3}


@pytest.fixture
def dispatched(monkeypatch: Any) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        question_repo,
        "get_question",
        lambda question_id: {"question_id": question_id, "student_id": "student-1"},
    )
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda owner_id, generation: {"generation": generation},
    )
    monkeypatch.setattr(
        teacher_dispatch_service,
        "dispatch_question",
        lambda question_id, question=None: calls.append(question_id),
    )
    return calls


def _native_record(body: object, **overrides: Any) -> dict[str, Any]:
    """One record in the shape the Lambda SQS event source delivers."""
    record = {
        "messageId": "message-1",
        "receiptHandle": "receipt-1",
        "body": body,
        "attributes": {
            "ApproximateReceiveCount": "1",
            "SentTimestamp": "1774000000000",
            "SenderId": "sender-1",
            "ApproximateFirstReceiveTimestamp": "1774000000001",
        },
        "messageAttributes": {},
        "md5OfBody": "0" * 32,
        "eventSource": "aws:sqs",
        "eventSourceARN": "arn:aws:sqs:eu-central-2:000000000000:stoa-teacher-escalation.fifo",
        "awsRegion": "eu-central-2",
    }
    record.update(overrides)
    return record


def _fifo_record(body: object) -> dict[str, Any]:
    record = _native_record(body)
    record["attributes"].update(
        {
            "MessageGroupId": "student-1",
            "MessageDeduplicationId": "operation-1",
            "SequenceNumber": "18855924000000000000",
        }
    )
    return record


def test_native_sqs_lambda_event_dispatches_valid_escalation(
    dispatched: list[str],
) -> None:
    event = {"Records": [_native_record(json.dumps(PAYLOAD))]}
    assert teacher_escalation.handler(event, None) == {
        "processed": 1,
        "fenced": 0,
        "dropped": 0,
        "legacy_debt": 0,
    }
    assert dispatched == ["question-1"]


def test_native_fifo_records_dispatch_each_escalation(dispatched: list[str]) -> None:
    event = {"Records": [_fifo_record(json.dumps(PAYLOAD)), _fifo_record(json.dumps(PAYLOAD))]}
    assert teacher_escalation.handler(event, None)["processed"] == 2
    assert dispatched == ["question-1", "question-1"]


def test_client_receive_message_shape_still_dispatches(dispatched: list[str]) -> None:
    assert teacher_escalation.consume_message({"Body": json.dumps(PAYLOAD)}) == "processed"
    assert dispatched == ["question-1"]


@pytest.mark.parametrize(
    "record",
    [
        {"messageId": "message-1", "eventSource": "aws:sqs"},
        _native_record(None),
        _native_record(b"{}"),
        "not-a-record",
    ],
)
def test_record_without_a_readable_body_fails_loudly(
    dispatched: list[str], record: object
) -> None:
    with pytest.raises(teacher_escalation.EscalationEnvelopeError):
        teacher_escalation.handler({"Records": [record]}, None)
    assert dispatched == []


@pytest.mark.parametrize(
    "body",
    [
        "",
        "not-json",
        json.dumps({"student_id": "student-1", "subject": "math", "content": "help"}),
        json.dumps({**PAYLOAD, "student_id": "student-1"}),
        json.dumps({"operation_id": "operation-1"}),
        json.dumps([PAYLOAD]),
    ],
)
def test_legacy_payloads_stay_debt_and_never_dispatch(
    dispatched: list[str], body: str
) -> None:
    event = {"Records": [_native_record(body)]}
    assert teacher_escalation.handler(event, None)["legacy_debt"] == 1
    assert dispatched == []


def test_native_record_for_a_missing_question_is_dropped(
    dispatched: list[str], monkeypatch: Any
) -> None:
    monkeypatch.setattr(question_repo, "get_question", lambda question_id: None)
    event = {"Records": [_native_record(json.dumps(PAYLOAD))]}
    assert teacher_escalation.handler(event, None)["dropped"] == 1
    assert dispatched == []


def test_native_record_for_a_deleted_account_is_fenced(
    dispatched: list[str], monkeypatch: Any
) -> None:
    def refuse(owner_id: str, generation: int) -> None:
        raise account_deletion_repo.AccountDeletionConflict("stale generation")

    monkeypatch.setattr(account_deletion_repo, "require_active_account_fence", refuse)
    event = {"Records": [_native_record(json.dumps(PAYLOAD))]}
    assert teacher_escalation.handler(event, None)["fenced"] == 1
    assert dispatched == []
