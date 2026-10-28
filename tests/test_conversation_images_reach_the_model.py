"""Images in a learning conversation reach the model as images (#135).

Before this, every attachment went through document text extraction; a JPEG or
PNG has no text to extract, so it was skipped and the model never saw it.

These drive the real message route, the real attachment binding and the real
prompt assembly against the shared table double. The private bucket and the
model are fakes: the request body the model is handed is captured, so what the
model was actually shown is what is asserted.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import Any

import pytest
from PIL import Image

from fakes.dynamodb import FakeTable
from stoa.db.repositories import attachment_repo
from stoa.jobs import conversation_generation
from stoa.routers import conversations
from stoa.services import ai_service, attachment_service
from stoa.services.document_extraction_service import (
    DocumentExtractionFailure,
    extract_attachment_text,
)
from stoa.services.document_parser_worker import ParserResult
from test_conversations import _actor
from test_message_command_generation import (  # noqa: F401 - fixtures
    CONV,
    STUDENT,
    _client,
    _command_row,
    _messages,
)
from test_message_command_generation import table as table  # noqa: F401 - the fixture

MODEL_ANSWER = {
    "steps": ["Lies die Aufgabe auf dem Bild"],
    "answer": "Das Ergebnis ist 3/4.",
    "hints": [],
    "similar_exercises": [],
    "knowledge_points": [],
    "suggest_teacher": False,
}


def _image(fmt: str, size: tuple[int, int] = (32, 24)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


class _Body:
    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


class _Bucket:
    """The private bucket, holding each upload's exact immutable version."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, key: str, version: str, data: bytes) -> None:
        self.objects[(key, version)] = data

    def get_object(self, *, Bucket: str, Key: str, VersionId: str):  # noqa: N803 - boto3 casing
        data = self.objects[(Key, VersionId)]
        return {
            "Body": _Body(data),
            "ETag": f"etag-{Key}",
            "ContentLength": len(data),
        }


class _Model:
    """Bedrock as the real prompt assembly calls it; keeps every request body."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    def invoke_model_with_response_stream(self, *, modelId: str, body: str):  # noqa: N803
        self.bodies.append(json.loads(body))
        events = [
            {"type": "message_start", "message": {"id": "msg-images-1", "model": modelId,
                                                  "usage": {"input_tokens": 10}}},
            {"type": "content_block_delta", "delta": {"text": json.dumps(MODEL_ANSWER)}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"output_tokens": 5}},
        ]
        return {
            "ResponseMetadata": {"RequestId": "req-images-1"},
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
        }


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> _Bucket:
    bucket = _Bucket()
    monkeypatch.setattr(conversations.boto3, "client", lambda *_a, **_k: bucket)
    return bucket


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> _Model:
    """The real `get_ai_answer`, handed a capturing Bedrock client.

    The token allowance is not what these tests are about, so the answer goes
    back as a plain mapping, the way the other route harnesses return it.
    """
    model = _Model()
    real = ai_service.get_ai_answer

    def get_ai_answer(**kwargs: Any):
        kwargs["client"] = model
        return real(**kwargs).content

    monkeypatch.setattr(conversations.ai_service, "get_ai_answer", get_ai_answer)
    return model


@pytest.fixture(autouse=True)
def _plan(monkeypatch: pytest.MonkeyPatch, stub_memory_summary) -> None:
    monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free_trial")


@pytest.fixture(autouse=True)
def _parser_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The extraction the parser process runs, without the process.

    The process sets rlimits, which only exist on POSIX; on Windows it always
    answers `service_unavailable`. What it extracts is the same either way.
    """

    def parse(data: Any, media_type: str, **_kwargs: Any) -> ParserResult:
        data.seek(0)
        try:
            return ParserResult(text=extract_attachment_text(data.read(), media_type))
        except DocumentExtractionFailure as error:
            return ParserResult(category=error.category)

    monkeypatch.setattr(attachment_service, "parse_document_isolated", parse)


def _upload(
    table: FakeTable,
    bucket: _Bucket,
    upload_id: str,
    data: bytes,
    *,
    filename: str,
    media_type: str,
    declared_length: int | None = None,
) -> None:
    key = f"objects/private/{upload_id}"
    bucket.put(key, "immutable-version", data)
    table.seed(
        {
            **attachment_repo.upload_key(upload_id),
            "upload_id": upload_id,
            "owner_id": STUDENT,
            "immutable_object_key": key,
            "immutable_version_id": "immutable-version",
            "immutable_etag": f"etag-{key}",
            "content_sha256": hashlib.sha256(data).hexdigest(),
            "original_filename": filename,
            "detected_type": media_type,
            "content_length": len(data) if declared_length is None else declared_length,
            "status": "validated",
            "expected_kind": "conversation_attachment",
            "version": 3,
            "expires_at": 4_000_000_000,
        }
    )


def _send(*upload_ids: str, key: str = "key-1"):
    return _client().post(
        f"/conversations/{CONV}/messages",
        json={
            "content": "Kannst du mir bei dieser Aufgabe helfen?",
            "idempotencyKey": key,
            "attachmentIds": [{"uploadId": upload_id} for upload_id in upload_ids],
        },
        headers={"Accept-Language": "de"},
    )


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _student_turn(body: dict[str, Any]) -> list[dict[str, Any]]:
    turn = body["messages"][-1]
    assert turn["role"] == "user"
    content = turn["content"]
    return content if isinstance(content, list) else [{"type": "text", "text": content}]


def _image_blocks(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [block for block in _student_turn(body) if block.get("type") == "image"]


def _text(body: dict[str, Any]) -> str:
    return "\n".join(
        block["text"] for block in _student_turn(body) if block.get("type") == "text"
    )


@pytest.mark.parametrize(
    ("fmt", "filename", "media_type"),
    [("PNG", "aufgabe.png", "image/png"), ("JPEG", "aufgabe.jpg", "image/jpeg")],
)
def test_an_image_attachment_reaches_the_model_as_an_image_block(
    table, bucket, model, fmt, filename, media_type
) -> None:
    data = _image(fmt)
    _upload(table, bucket, "upload-image", data, filename=filename, media_type=media_type)

    response = _send("upload-image")

    assert response.status_code == 200, response.text
    [body] = model.bodies
    [block] = _image_blocks(body)
    assert block["source"] == {
        "type": "base64",
        "media_type": media_type,
        "data": base64.b64encode(data).decode("ascii"),
    }
    # The student's words still go with it, after the image.
    turn = _student_turn(body)
    assert turn[-1]["type"] == "text"
    assert "Kannst du mir bei dieser Aufgabe helfen?" in turn[-1]["text"]
    assert len(_messages(table, "assistant")) == 1


def test_each_image_of_a_message_is_its_own_block_in_the_order_sent(
    table, bucket, model
) -> None:
    first, second = _image("PNG", (10, 10)), _image("JPEG", (20, 20))
    _upload(table, bucket, "upload-a", first, filename="a.png", media_type="image/png")
    _upload(table, bucket, "upload-b", second, filename="b.jpg", media_type="image/jpeg")

    response = _send("upload-a", "upload-b")

    assert response.status_code == 200, response.text
    [body] = model.bodies
    assert [block["source"]["data"] for block in _image_blocks(body)] == [
        base64.b64encode(first).decode("ascii"),
        base64.b64encode(second).decode("ascii"),
    ]


def test_a_document_attachment_is_still_read_as_text(table, bucket, model) -> None:
    data = "Aufgabe 4: Berechne 1/2 + 1/4.".encode()
    _upload(table, bucket, "upload-doc", data, filename="aufgabe.txt", media_type="text/plain")

    response = _send("upload-doc")

    assert response.status_code == 200, response.text
    [body] = model.bodies
    assert _image_blocks(body) == []
    # Unchanged from before: the text rides in the student's own turn, fenced.
    assert isinstance(body["messages"][-1]["content"], str)
    assert "<student_attachment_context>" in _text(body)
    assert "Aufgabe 4: Berechne 1/2 + 1/4." in _text(body)


def test_an_image_and_a_document_in_one_message_each_go_their_own_way(
    table, bucket, model
) -> None:
    image = _image("PNG")
    _upload(table, bucket, "upload-image", image, filename="a.png", media_type="image/png")
    _upload(
        table,
        bucket,
        "upload-doc",
        "Notizen zur Aufgabe".encode(),
        filename="notizen.txt",
        media_type="text/plain",
    )

    response = _send("upload-image", "upload-doc")

    assert response.status_code == 200, response.text
    [body] = model.bodies
    [block] = _image_blocks(body)
    assert block["source"]["data"] == base64.b64encode(image).decode("ascii")
    assert "Notizen zur Aufgabe" in _text(body)


def test_a_message_without_attachments_still_sends_plain_text(table, bucket, model) -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages",
        json={"content": "Was ist ein Bruch?", "idempotencyKey": "plain"},
    )

    assert response.status_code == 200, response.text
    [body] = model.bodies
    assert body["messages"][-1]["content"] == "Was ist ein Bruch?"


def test_an_image_over_the_model_limit_is_refused_with_a_code_before_anything_happens(
    table, bucket, model
) -> None:
    limit = attachment_service.MODEL_IMAGE_MAX_BYTES
    _upload(
        table,
        bucket,
        "upload-big",
        _image("PNG"),
        filename="gross.png",
        media_type="image/png",
        declared_length=limit + 1,
    )

    response = _send("upload-big")

    assert response.status_code == 422, response.text
    assert _code(response) == "upload_too_large"
    assert model.bodies == []
    assert _messages(table, "student") == []
    assert _messages(table, "assistant") == []


def test_an_image_exactly_at_the_model_limit_is_accepted(table, bucket, model) -> None:
    """The boundary of the check above. Base64 of this many bytes is 5 MiB, the
    most Claude takes for one image."""
    limit = attachment_service.MODEL_IMAGE_MAX_BYTES
    assert len(base64.b64encode(b"\0" * limit)) == 5 * 1024 * 1024
    data = _image("PNG")
    data += b"\0" * (limit - len(data))  # trailing bytes after IEND still decode
    _upload(table, bucket, "upload-edge", data, filename="rand.png", media_type="image/png")

    response = _send("upload-edge")

    assert response.status_code == 200, response.text
    [block] = _image_blocks(model.bodies[0])
    assert len(block["source"]["data"]) == 5 * 1024 * 1024


def test_an_image_that_cannot_be_read_back_fails_with_a_code_instead_of_vanishing(
    table, bucket, model
) -> None:
    data = _image("PNG")
    _upload(table, bucket, "upload-image", data, filename="a.png", media_type="image/png")
    # The stored bytes no longer match what was validated.
    bucket.put("objects/private/upload-image", "immutable-version", data[:-1] + b"\x01")

    response = _send("upload-image")

    assert response.status_code == 503, response.text
    assert _code(response) == "upload_service_unavailable"
    assert model.bodies == []


def test_bytes_that_are_not_the_image_they_claim_fail_as_invalid(table, bucket, model) -> None:
    data = b"not really a png at all"
    _upload(table, bucket, "upload-fake", data, filename="a.png", media_type="image/png")

    response = _send("upload-fake")

    assert response.status_code == 422, response.text
    assert _code(response) == "upload_invalid"
    assert model.bodies == []


def test_an_oversized_image_committed_before_the_limit_fails_the_worker_without_a_call(
    table, bucket, model, monkeypatch
) -> None:
    """A message committed before this limit existed is generated by the worker
    from what was stored. The model would refuse the image, so it is not called:
    the command fails with its reason instead of the image vanishing."""
    data = _image("PNG")
    _upload(table, bucket, "upload-image", data, filename="a.png", media_type="image/png")
    body = conversations.SendMessageRequest.model_validate(
        {
            "content": "Kannst du mir bei dieser Aufgabe helfen?",
            "idempotencyKey": "key-old",
            "attachmentIds": [{"uploadId": "upload-image"}],
        }
    )
    conversations.commit_message_command(
        conv_id=CONV,
        student_id=STUDENT,
        subject="Mathematik",
        grade="Grade 6",
        body=body,
        command_context={
            "actor": _actor(),
            "fingerprint": conversations.message_request_fingerprint(body),
            "existing": None,
        },
    )
    monkeypatch.setattr(attachment_service, "MODEL_IMAGE_MAX_BYTES", len(data) - 1)

    outcome = conversation_generation.handler(
        {"conversation_id": CONV, "idempotency_key": "key-old"}, None
    )

    assert outcome == {"outcome": "failed"}
    assert model.bodies == []
    command = _command_row(table, "key-old")
    assert command["status"] == "failed"
    assert command["failure_category"] == "attachment_invalid"
    assert _messages(table, "assistant") == []
