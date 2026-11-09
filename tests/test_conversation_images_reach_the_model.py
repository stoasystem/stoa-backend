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
import io
import json
from typing import Any

import pytest
from PIL import Image

from fakes.ask_question import (
    CONV,
    _client,
    _command_row,
    _messages,
    _patch_allowance_table,
    _upload,
)
from fakes.ask_question import _commit as _commit_message
from fakes.ask_question import _parser_in_process  # noqa: F401 - the fixture
from fakes.ask_question import bucket as bucket  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.bedrock import FakeBedrock
from stoa import aws
from stoa.aws import Kind
from stoa.jobs import conversation_generation
from stoa.services import attachment_service
from fakes.ask_question import AtomicAllowanceTable

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


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The prompt enrichment reads three tables; keep it out."""


@pytest.fixture(autouse=True)
def _answers(model: FakeBedrock) -> None:
    model.answer = MODEL_ANSWER


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
    [body] = model.requests
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
    [body] = model.requests
    assert [block["source"]["data"] for block in _image_blocks(body)] == [
        base64.b64encode(first).decode("ascii"),
        base64.b64encode(second).decode("ascii"),
    ]


def test_a_document_attachment_is_still_read_as_text(table, bucket, model) -> None:
    data = "Aufgabe 4: Berechne 1/2 + 1/4.".encode()
    _upload(table, bucket, "upload-doc", data, filename="aufgabe.txt", media_type="text/plain")

    response = _send("upload-doc")

    assert response.status_code == 200, response.text
    [body] = model.requests
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
    [body] = model.requests
    [block] = _image_blocks(body)
    assert block["source"]["data"] == base64.b64encode(image).decode("ascii")
    assert "Notizen zur Aufgabe" in _text(body)


def test_a_message_without_attachments_still_sends_plain_text(table, bucket, model) -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages",
        json={"content": "Was ist ein Bruch?", "idempotencyKey": "plain"},
    )

    assert response.status_code == 200, response.text
    [body] = model.requests
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
    assert model.requests == []
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
    [block] = _image_blocks(model.requests[0])
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
    assert model.requests == []


def test_bytes_that_are_not_the_image_they_claim_fail_as_invalid(table, bucket, model) -> None:
    data = b"not really a png at all"
    _upload(table, bucket, "upload-fake", data, filename="a.png", media_type="image/png")

    response = _send("upload-fake")

    assert response.status_code == 422, response.text
    assert _code(response) == "upload_invalid"
    assert model.requests == []


def _commit(*upload_ids: str, key: str) -> None:
    """Commit a message the way the request does, leaving the answer to the worker."""
    _commit_message(
        key,
        content="Kannst du mir bei dieser Aufgabe helfen?",
        attachmentIds=[{"uploadId": upload_id} for upload_id in upload_ids],
    )


def _assert_worker_refused(table, model, key: str) -> None:
    outcome = conversation_generation.handler(
        {"conversation_id": CONV, "idempotency_key": key}, None
    )

    assert outcome == {"outcome": "failed"}
    assert model.requests == []
    command = _command_row(table, key)
    assert command["status"] == "failed"
    assert command["failure_category"] == "attachment_invalid"
    assert _messages(table, "assistant") == []


def test_an_oversized_image_committed_before_the_limit_fails_the_worker_without_a_call(
    table, bucket, model, monkeypatch
) -> None:
    """A message committed before this limit existed is generated by the worker
    from what was stored. The model would refuse the image, so it is not called:
    the command fails with its reason instead of the image vanishing."""
    data = _image("PNG")
    _upload(table, bucket, "upload-image", data, filename="a.png", media_type="image/png")
    _commit("upload-image", key="key-old")
    monkeypatch.setattr(attachment_service, "MODEL_IMAGE_MAX_BYTES", len(data) - 1)

    _assert_worker_refused(table, model, "key-old")


# ── All the images of one message together ───────────────────────────────────

def _full_size_image() -> bytes:
    data = _image("PNG")
    return data + b"\0" * (attachment_service.MODEL_IMAGE_MAX_BYTES - len(data))


def test_images_of_one_message_exactly_at_the_total_limit_are_sent_within_the_body_limit(
    table, bucket, model
) -> None:
    """Bedrock refuses an InvokeModel body over 25,000,000 bytes. Images up to
    the total limit, base64 inside the JSON, leave room for everything else."""
    limit = attachment_service.MESSAGE_IMAGES_MAX_BYTES
    count = limit // attachment_service.MODEL_IMAGE_MAX_BYTES
    assert count * attachment_service.MODEL_IMAGE_MAX_BYTES == limit
    data = _full_size_image()
    for index in range(count):
        _upload(
            table, bucket, f"upload-{index}", data, filename=f"{index}.png", media_type="image/png"
        )

    response = _send(*(f"upload-{index}" for index in range(count)))

    assert response.status_code == 200, response.text
    [body] = model.requests
    assert len(_image_blocks(body)) == count
    # Room for the rest: the system prompt, history, star map and document text.
    assert len(json.dumps(body)) < 25_000_000 - 4_000_000


def test_images_of_one_message_over_the_total_limit_are_refused_before_anything_happens(
    table, bucket, model
) -> None:
    """Each image is within its own limit; together they are one byte over."""
    per_image = attachment_service.MODEL_IMAGE_MAX_BYTES
    count = attachment_service.MESSAGE_IMAGES_MAX_BYTES // per_image
    for index in range(count):
        _upload(
            table,
            bucket,
            f"upload-{index}",
            _image("PNG"),
            filename=f"{index}.png",
            media_type="image/png",
            declared_length=per_image,
        )
    _upload(
        table,
        bucket,
        "upload-extra",
        _image("PNG"),
        filename="extra.png",
        media_type="image/png",
        declared_length=1,
    )

    response = _send(*(f"upload-{index}" for index in range(count)), "upload-extra")

    assert response.status_code == 422, response.text
    assert _code(response) == "upload_too_large"
    assert model.requests == []
    assert _messages(table, "student") == []


def test_documents_do_not_count_toward_the_image_total(table, bucket, model, monkeypatch) -> None:
    image = _image("PNG")
    document = ("Notizen " * 40).encode()
    _upload(table, bucket, "upload-image", image, filename="a.png", media_type="image/png")
    _upload(
        table, bucket, "upload-doc", document, filename="notizen.txt", media_type="text/plain"
    )
    monkeypatch.setattr(attachment_service, "MESSAGE_IMAGES_MAX_BYTES", len(image))

    response = _send("upload-image", "upload-doc")

    assert response.status_code == 200, response.text


def test_images_committed_before_the_total_limit_fail_the_worker_without_a_call(
    table, bucket, model, monkeypatch
) -> None:
    first, second = _image("PNG", (10, 10)), _image("PNG", (20, 20))
    _upload(table, bucket, "upload-a", first, filename="a.png", media_type="image/png")
    _upload(table, bucket, "upload-b", second, filename="b.png", media_type="image/png")
    _commit("upload-a", "upload-b", key="key-old-total")
    monkeypatch.setattr(
        attachment_service, "MESSAGE_IMAGES_MAX_BYTES", len(first) + len(second) - 1
    )

    _assert_worker_refused(table, model, "key-old-total")


# ── Through the allowance client: counted as it is sent ──────────────────────

class _Bedrock(FakeBedrock):
    """The runtime client the allowance wrapper builds: counts, then answers."""

    def __init__(self) -> None:
        super().__init__(answer=MODEL_ANSWER)
        self.counted_bodies: list[dict[str, Any]] = []

    def count_tokens(self, *, modelId: str, input: dict[str, Any]):  # noqa: N803, A002
        self.counted_bodies.append(json.loads(input["invokeModel"]["body"]))
        return super().count_tokens()


def test_the_image_is_in_the_body_that_is_counted_and_the_body_that_is_sent(
    table, bucket, monkeypatch
) -> None:
    """No stand-in for the answer: the real allowance client admits the request
    by counting it with the provider, then sends that same body."""
    bedrock = _Bedrock()
    aws.install({Kind.S3: bucket, Kind.BEDROCK_RUNTIME: bedrock})
    _patch_allowance_table(monkeypatch, AtomicAllowanceTable())
    data = _image("JPEG")
    _upload(table, bucket, "upload-image", data, filename="a.jpg", media_type="image/jpeg")

    response = _send("upload-image")

    assert response.status_code == 200, response.text
    [counted] = bedrock.counted_bodies
    [sent] = bedrock.requests
    assert counted == sent
    [block] = _image_blocks(sent)
    assert block["source"]["data"] == base64.b64encode(data).decode("ascii")
