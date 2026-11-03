"""Wave-0 faults for exact conversation replay and fenced AI completion."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

import pytest

from fakes.ask_question import _command_row, _commit, _parse_in_process, _submit, _upload
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import bucket as bucket  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import as_stored as _as_stored

from stoa.config import Settings
from stoa.db.repositories import attachment_repo
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import ai_service, attachment_service
from stoa.services.document_extraction_service import DocumentExtractionFailure


def _attachment(attachment_id: str, *, owner_id: str = "student-1") -> dict[str, Any]:
    data = f"private text for {attachment_id}".encode()
    return _as_stored({
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
    })


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


def _committed_with_an_attachment(table, bucket, monkeypatch) -> tuple[str, str]:
    """A message committed with one upload, its answer still to come.

    Returns the table key of the attachment it was bound as.
    """
    _parse_in_process(monkeypatch)
    _upload(table, bucket, "upload-1", b"private notes", filename="notes.txt", media_type="text/plain")
    _commit("replay-key", attachmentIds=[{"uploadId": "upload-1"}])
    [attachment_id] = _command_row(table, "replay-key")["deterministic_attachment_ids"]
    return tuple(attachment_repo.attachment_key(attachment_id).values())


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
    table, model, bucket, monkeypatch, field: str, bad_value: Any
) -> None:
    key = _committed_with_an_attachment(table, bucket, monkeypatch)
    table.rows[key][field] = bad_value

    # The student sends it again: the stored message is read back with its attachment.
    with pytest.raises(AttachmentDecisionError) as captured:
        _submit("replay-key", attachmentIds=[{"uploadId": "upload-1"}])

    assert captured.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert "private-canary" not in str(captured.value)
    assert model.calls == []


def test_replay_attachment_row_is_accepted_in_the_shape_the_table_returns(
    table, model, bucket, monkeypatch
) -> None:
    """The positive control the rejection cases rest on.

    Every number in the row comes back from the table as `Decimal`, so a guard
    written against `int` refuses the row it exists to accept.
    """
    key = _committed_with_an_attachment(table, bucket, monkeypatch)
    assert isinstance(table.rows[key]["content_length"], Decimal)

    answered = _submit("replay-key", attachmentIds=[{"uploadId": "upload-1"}])

    [attachment] = answered.studentMessage.attachments
    assert attachment.filename == "notes.txt"
    assert len(model.calls) == 1


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
def test_retryable_context_fault_is_typed_all_or_nothing_without_prompt_marker(
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

    class ProviderBody:
        def read(self) -> bytes:
            return json.dumps(
                {
                    "id": "msg-deadline-boundary",
                    "model": "anthropic.claude-sonnet-4-6",
                    "content": [{"text": '{"steps":["x"],"answer":"y"}'}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 9, "output_tokens": 3},
                }
            ).encode()

        def close(self) -> None:
            return None

    class Client:
        def invoke_model(self, **_kwargs):
            return {
                "body": ProviderBody(),
                "ResponseMetadata": {
                    "HTTPStatusCode": 200,
                    "RequestId": "request-deadline-boundary",
                },
            }

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service.invoke_answer(
            "Answer the question.",
            [{"role": "user", "content": "question"}],
            input_size=8,
            deadline_monotonic=100.0,
            clock=lambda: next(ticks),
            client=Client(),
        )
    assert captured.value.category == "deadline_exceeded"
