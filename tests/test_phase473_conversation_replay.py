"""Wave-0 faults for exact conversation replay and fenced AI completion."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from stoa.config import Settings
from stoa.db.repositories import attachment_repo
from stoa.routers import conversations
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import ai_service, attachment_service
from stoa.services.document_extraction_service import DocumentExtractionFailure


def _attachment(attachment_id: str, *, owner_id: str = "student-1") -> dict[str, Any]:
    data = f"private text for {attachment_id}".encode()
    return {
        **attachment_repo.attachment_key(attachment_id),
        "entity_type": "attachment",
        "schema_version": "attachment.v1",
        "attachment_id": attachment_id,
        "owner_id": owner_id,
        "student_id": owner_id,
        "status": "active",
        "immutable_object_key": f"objects/private/{attachment_id}",
        "immutable_version_id": f"version-{attachment_id}",
        "immutable_etag": f"etag-{attachment_id}",
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "content_length": len(data),
        "detected_type": "text/plain",
        "original_filename": f"{attachment_id}.txt",
        "source_fingerprint": "a" * 64,
    }


class _BatchTable:
    name = "private-table"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def batch_get_item(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _batch_response(
    items: list[dict[str, Any]], *, unprocessed: list[str] | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {"Responses": {"private-table": items}}
    if unprocessed is not None:
        value["UnprocessedKeys"] = {
            "private-table": {
                "Keys": [attachment_repo.attachment_key(item) for item in unprocessed]
            }
        }
    return value


def test_batch_get_drains_only_unprocessed_keys_consistently_and_preserves_order() -> None:
    first = _attachment("attachment-1")
    second = _attachment("attachment-2")
    table = _BatchTable(
        [
            _batch_response([second], unprocessed=["attachment-1"]),
            _batch_response([first], unprocessed=[]),
        ]
    )

    result = attachment_repo.get_attachments(
        ["attachment-1", "attachment-2"], table=table
    )

    assert list(result) == ["attachment-1", "attachment-2"]
    assert len(table.requests) == 2
    first_request = table.requests[0]["RequestItems"][table.name]
    second_request = table.requests[1]["RequestItems"][table.name]
    assert first_request["ConsistentRead"] is True
    assert first_request["Keys"] == [
        attachment_repo.attachment_key("attachment-1"),
        attachment_repo.attachment_key("attachment-2"),
    ]
    assert second_request == {
        "ConsistentRead": True,
        "Keys": [attachment_repo.attachment_key("attachment-1")],
    }


@pytest.mark.parametrize(
    "responses",
    [
        [_batch_response([_attachment("attachment-1")])],
        [_batch_response([_attachment("attachment-1"), _attachment("attachment-1")])],
        [_batch_response([_attachment("attachment-1"), _attachment("attachment-extra")])],
        [{"Responses": []}],
        [{"Responses": {"private-table": [None]}}],
        [_batch_response([], unprocessed=["attachment-1"])] * 3,
    ],
    ids=[
        "missing-row",
        "duplicate-row",
        "extra-row",
        "malformed-response-map",
        "malformed-row",
        "unprocessed-exhaustion",
    ],
)
def test_batch_get_rejects_every_partial_duplicate_extra_or_malformed_shape(
    responses: list[dict[str, Any]],
) -> None:
    table = _BatchTable(responses)
    with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
        attachment_repo.get_attachments(
            ["attachment-1", "attachment-2"], table=table
        )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("PK", "ATTACHMENT#other"),
        ("SK", "OTHER"),
        ("attachment_id", "other"),
        ("owner_id", "foreign-student-private-canary"),
        ("student_id", "foreign-student-private-canary"),
        ("status", "deletion_pending"),
        ("entity_type", "upload_intent"),
        ("schema_version", "attachment.v0"),
        ("immutable_object_key", ""),
        ("immutable_version_id", False),
        ("immutable_etag", []),
        ("content_sha256", "A" * 64),
        ("content_length", True),
        ("content_length", 0),
        ("detected_type", None),
        ("original_filename", {}),
        ("source_fingerprint", "not-a-fingerprint"),
    ],
)
def test_replay_attachment_row_requires_exact_owner_active_schema_and_immutable_tuple(
    field: str, bad_value: Any
) -> None:
    row = {**_attachment("attachment-1"), field: bad_value}
    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._validate_replay_attachment(
            row, attachment_id="attachment-1", owner_id="student-1"
        )
    assert captured.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert "private-canary" not in str(captured.value)


def _message(message_id: str, created_at: str, content: str) -> dict[str, Any]:
    return {
        "PK": "CONV#conv-1",
        "SK": f"MSG#{message_id}",
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": message_id,
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "role": "student" if message_id.startswith("student") else "assistant",
        "content": content,
        "created_at": created_at,
    }


class _HistoryTable:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = list(pages)
        self.requests: list[dict[str, Any]] = []

    def query(self, **kwargs):
        self.requests.append(kwargs)
        return self.pages.pop(0)


def test_history_snapshot_is_consistent_paginated_ordered_and_ignores_later_rows() -> None:
    original = [
        _message("student-old", "2026-07-17T00:00:00Z", "original question"),
        _message("assistant-old", "2026-07-17T00:00:01Z", "original reply"),
    ]
    captured = conversations._history_snapshot_fingerprint(original)
    later = _message("student-later", "2026-07-17T00:00:09Z", "later private canary")
    table = _HistoryTable(
        [
            {"Items": [original[0]], "LastEvaluatedKey": {"PK": "p", "SK": "s"}},
            {"Items": [later, original[1]]},
        ]
    )

    snapshot = conversations._load_anchored_message_history(
        conversation_id="conv-1",
        owner_id="student-1",
        expected_message_ids=["student-old", "assistant-old"],
        expected_fingerprint=captured,
        table=table,
    )

    assert [row["message_id"] for row in snapshot] == [
        "student-old",
        "assistant-old",
    ]
    assert all(request["ConsistentRead"] is True for request in table.requests)
    assert table.requests[1]["ExclusiveStartKey"] == {"PK": "p", "SK": "s"}
    assert "later private canary" not in json.dumps(snapshot)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "changed", "malformed-page"])
def test_history_snapshot_rejects_missing_duplicate_changed_and_malformed_rows(
    mode: str,
) -> None:
    original = [
        _message("student-old", "2026-07-17T00:00:00Z", "original question"),
        _message("assistant-old", "2026-07-17T00:00:01Z", "original reply"),
    ]
    fingerprint = conversations._history_snapshot_fingerprint(original)
    rows: Any = list(original)
    if mode == "missing":
        rows = rows[:1]
    elif mode == "duplicate":
        rows.append(dict(rows[0]))
    elif mode == "changed":
        rows[1] = {**rows[1], "content": "changed after command"}
    else:
        rows = {}
    table = _HistoryTable([{"Items": rows}])

    with pytest.raises(AttachmentDecisionError) as captured:
        conversations._load_anchored_message_history(
            conversation_id="conv-1",
            owner_id="student-1",
            expected_message_ids=["student-old", "assistant-old"],
            expected_fingerprint=fingerprint,
            table=table,
        )
    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


def _provider_body(data: bytes, *, read_error: bool = False, close_error: bool = False):
    class Body:
        offset = 0

        def read(self, limit: int) -> bytes:
            if read_error:
                raise RuntimeError("provider-read-private-canary")
            value = data[self.offset : self.offset + limit]
            self.offset += len(value)
            return value

        def close(self) -> None:
            if close_error:
                raise RuntimeError("provider-close-private-canary")

    return Body()


@pytest.mark.parametrize(
    "stage",
    ["get", "body", "read", "close", "checksum", "parser-retryable"],
)
def test_retryable_extraction_fault_is_typed_all_or_nothing_without_prompt_marker(
    monkeypatch, stage: str
) -> None:
    row = _attachment("attachment-1")
    data = b"private text for attachment-1"

    class S3:
        def get_object(self, **_kwargs):
            if stage == "get":
                raise RuntimeError("provider-get-private-canary")
            return {
                "Body": None if stage == "body" else _provider_body(
                    data, read_error=stage == "read", close_error=stage == "close"
                ),
                "ETag": row["immutable_etag"],
                "ContentLength": len(data),
            }

    if stage == "checksum":
        row = {**row, "content_sha256": "0" * 64}
    if stage == "parser-retryable":
        monkeypatch.setattr(
            attachment_service,
            "parse_document_isolated",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                DocumentExtractionFailure("service_unavailable")
            ),
        )

    result = attachment_service.extract_message_attachment_context(
        [("attachment", row)],
        s3=S3(),
        settings=Settings(s3_images_bucket="private-bucket"),
    )

    assert result.disposition is attachment_service.AttachmentContextDisposition.RETRYABLE
    assert result.context == ""
    assert result.error_code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "[attachment:" not in str(result)
    assert "private-canary" not in str(result)


def test_terminal_parser_failure_is_closed_and_never_embedded_in_context(monkeypatch) -> None:
    row = _attachment("attachment-1")
    data = b"private text for attachment-1"

    class S3:
        def get_object(self, **_kwargs):
            return {
                "Body": _provider_body(data),
                "ETag": row["immutable_etag"],
                "ContentLength": len(data),
            }

    monkeypatch.setattr(
        attachment_service,
        "parse_document_isolated",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            DocumentExtractionFailure("invalid_document")
        ),
    )
    result = attachment_service.extract_message_attachment_context(
        [("attachment", row)],
        s3=S3(),
        settings=Settings(s3_images_bucket="private-bucket"),
    )
    assert result.disposition is attachment_service.AttachmentContextDisposition.INVALID
    assert result.context == ""
    assert result.error_code is AttachmentErrorCode.UPLOAD_INVALID


def test_ai_invocation_crossing_injected_deadline_is_rejected_without_result() -> None:
    ticks = iter([10.0, 10.0, 101.0])

    class Client:
        def invoke_model(self, **_kwargs):
            return {
                "body": _provider_body(
                    json.dumps(
                        {"content": [{"text": '{"steps":["x"],"answer":"y"}'}]}
                    ).encode()
                )
            }

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service.get_ai_answer(
            content="question",
            subject="math",
            grade="Sek1",
            deadline_monotonic=100.0,
            clock=lambda: next(ticks),
            client=Client(),
        )
    assert captured.value.category == "deadline_exceeded"


def test_completion_condition_binds_lease_owner_generation_and_unexpired_deadline(
    monkeypatch,
) -> None:
    captured: list[attachment_repo.TransactionOperation] = []

    def transact(operations, **_kwargs):
        captured.extend(operations)

    monkeypatch.setattr(attachment_repo, "transact", transact)
    result = attachment_repo.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-old",
        lease_attempt=1,
        completed_epoch=219,
        assistant_message={"PK": "CONV#conv-1", "SK": "MSG#assistant"},
        result_json='{"studentMessage":{},"assistantMessage":{}}',
        completed_at="2026-07-17T00:00:00Z",
        table=object(),
    )
    assert result.disposition is attachment_repo.MessageCommandDisposition.COMPLETED
    update = next(
        operation.item["Update"]
        for operation in captured
        if operation.kind is attachment_repo.TransactionOperationKind.MESSAGE_COMMAND_UPDATE
    )
    assert "leaseOwner=:lease_owner" in update["ConditionExpression"]
    assert "attempt=:lease_attempt" in update["ConditionExpression"]
    assert "expiresAt>:completed_epoch" in update["ConditionExpression"]
    assert update["ExpressionAttributeValues"][":lease_attempt"] == 1
    assert update["ExpressionAttributeValues"][":completed_epoch"] == 219


def test_stale_worker_result_is_refused_after_deterministic_takeover(monkeypatch) -> None:
    command = {
        "owner_id": "student-1",
        "status": "ai_running",
        "leaseOwner": "lease-new",
        "attempt": 2,
        "expiresAt": 401,
    }

    class Table:
        def transact_write_items(self, **_kwargs):
            raise attachment_repo.ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "private",
                    }
                },
                "TransactWriteItems",
            )

        def get_item(self, **_kwargs):
            return {"Item": dict(command)}

    result = attachment_repo.complete_message_command(
        conversation_id="conv-1",
        idempotency_key="message-key",
        owner_id="student-1",
        lease_owner="lease-old",
        lease_attempt=1,
        completed_epoch=281,
        assistant_message={"PK": "CONV#conv-1", "SK": "MSG#assistant"},
        result_json='{"studentMessage":{},"assistantMessage":{}}',
        completed_at="2026-07-17T00:00:00Z",
        table=Table(),
    )
    assert result.disposition is attachment_repo.MessageCommandDisposition.RETRYABLE


def test_regular_and_sse_share_one_closed_executor_boundary() -> None:
    source = open(conversations.__file__, encoding="utf-8").read()
    assert source.count("_execute_message_command(") == 4
    assert "[attachment:" not in source
    assert "Entschuldigung, ich konnte keine Antwort generieren." not in source
    assert "Es gab ein technisches Problem." not in source
