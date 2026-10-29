"""A teacher's reply to a help request can carry images (#145).

Only students could open an upload, and a teacher's reply was text and formulas
alone. A teacher now opens an upload whose one purpose is a reply to a help
request; it is moderated on completion exactly as a student's image is (#138).
The reply names the uploads it carries, and only into a request the teacher is
on: the teacher it is offered to, or the teacher who took it. The student reads
the teacher's images with the conversation, as they read their own.

Rows, dispatch, the authorization facts and the teacher policy are real, over
the shared table double (see test_chat_help_request_lifecycle.py); S3 is the
multipart double and Rekognition `fakes.rekognition`.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import random
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from actor_helpers import install_actor_overrides
from fakes.rekognition import FakeRekognition
from fakes.s3 import MultipartS3
from stoa.config import Settings
from stoa.deps import (
    get_image_moderation_client,
    get_s3_client,
    get_s3_presign_client,
    get_settings,
)
from stoa.routers import conversations, files, teachers
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import attachment_service
from test_chat_help_request_lifecycle import (
    CONV,
    OTHER_TEACHER,
    REQUEST,
    STUDENT,
    TEACHER,
    _conv,
    _dispatch_to,
    _question,
    _set_status,
    _teacher_rows,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

BUCKET = "images-bucket-145"
PURPOSE = "help_reply_image"
RUDE_GESTURE = [
    {"Name": "Rude Gestures", "Confidence": 97.0, "ParentName": "", "TaxonomyLevel": 1},
    {"Name": "Middle Finger", "Confidence": 97.0, "ParentName": "Rude Gestures", "TaxonomyLevel": 2},
]


def _png(seed: int = 145) -> bytes:
    noise = random.Random(seed).randbytes(160 * 120 * 3)
    output = BytesIO()
    Image.frombytes("RGB", (160, 120), noise).save(output, "PNG")
    return output.getvalue()


class _Api:
    """The teacher, files and conversation routes over one S3 and one moderation double."""

    def __init__(self) -> None:
        self.s3 = MultipartS3(BUCKET)
        self.moderation = FakeRekognition()

    def client(self, user_id: str = TEACHER, role: str = "teacher") -> TestClient:
        app = FastAPI()
        app.include_router(teachers.router, prefix="/teachers")
        app.include_router(files.router, prefix="/files")
        app.include_router(conversations.router, prefix="/conversations")
        app.dependency_overrides[get_s3_client] = lambda: self.s3
        app.dependency_overrides[get_s3_presign_client] = lambda: self.s3
        app.dependency_overrides[get_image_moderation_client] = lambda: self.moderation
        app.dependency_overrides[get_settings] = lambda: Settings(s3_images_bucket=BUCKET)
        install_actor_overrides(app, {"sub": user_id, "role": role})
        # The helper's fact stand-in grants a teacher whatever they ask for; who
        # may post is the point here, so the facts are loaded from the table.
        del app.dependency_overrides[get_authorization_fact_repository]
        return TestClient(app)

    def intent(self, client: TestClient, data: bytes, **overrides: Any):
        return client.post(
            "/files/intents",
            json={
                "purpose": PURPOSE,
                "filename": "working.png",
                "contentType": "image/png",
                "sizeBytes": len(data),
                **overrides,
            },
        )

    def upload(self, client: TestClient, data: bytes):
        """The whole upload: an intent, its one part on the signed URL, completion."""
        intent = self.intent(client, data)
        assert intent.status_code == 200, intent.text
        upload_id = intent.json()["uploadId"]
        signed = client.post(
            f"/files/{upload_id}/parts/1",
            json={"sizeBytes": len(data), "checksumSha256": hashlib.sha256(data).hexdigest()},
        )
        assert signed.status_code == 200, signed.text
        url = signed.json()
        assert self.s3.browser_put(url["url"], url["method"], url["headers"], data) == 200
        return upload_id, client.post(f"/files/{upload_id}/complete", json={"partCount": 1})

    def uploaded(self, client: TestClient, data: bytes) -> str:
        upload_id, completed = self.upload(client, data)
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "validated"
        return upload_id


@pytest.fixture
def api(table) -> _Api:
    return _Api()


def _reply(client: TestClient, *upload_ids: str, content: str = "Schau dir meine Rechnung an."):
    return client.post(
        f"/teachers/me/help-requests/{REQUEST}/notes",
        json={"content": content, "attachmentIds": [{"uploadId": value} for value in upload_ids]},
    )


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _teacher_messages(api: _Api) -> list[dict[str, Any]]:
    response = api.client(STUDENT, role="student").get(f"/conversations/{CONV}")
    assert response.status_code == 200, response.text
    return [message for message in response.json()["messages"] if message["role"] == "teacher"]


def _written_replies(table) -> list[tuple[str, str]]:
    return [
        key
        for key in table.rows
        if key[0] == f"CONV#{CONV}" and key[1].startswith(("NOTE#", "MSG#"))
    ]


def _upload_status(table, upload_id: str) -> str:
    return table.rows[(f"UPLOAD#{upload_id}", "META")]["status"]


# --- The teacher's upload ---


def test_a_teacher_opens_an_upload_for_a_reply_and_it_is_moderated(api) -> None:
    data = _png()

    upload_id, completed = api.upload(api.client(), data)

    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "validated"
    assert [call["Image"]["Bytes"] for call in api.moderation.calls] == [data]


def test_a_teachers_image_the_moderation_blocks_is_refused(api) -> None:
    api.moderation.labels = RUDE_GESTURE

    upload_id, refused = api.upload(api.client(), _png())

    assert (refused.status_code, _code(refused)) == (422, "upload_content_blocked")
    assert [key for key in api.s3.objects if key[0].startswith("objects/")] == []


@pytest.mark.parametrize(
    ("role", "purpose"),
    [
        ("student", PURPOSE),
        ("teacher", "conversation_attachment"),
        ("teacher", "question_image"),
        ("parent", PURPOSE),
    ],
    ids=["student-reply-purpose", "teacher-conversation", "teacher-question", "parent"],
)
def test_the_reply_purpose_is_the_teachers_and_the_teachers_only_purpose(
    api, role, purpose
) -> None:
    user_id = {"student": STUDENT, "teacher": TEACHER, "parent": "parent-145"}[role]

    refused = api.intent(api.client(user_id, role=role), _png(), purpose=purpose)

    assert (refused.status_code, _code(refused)) == (404, "upload_not_found")


def test_a_teacher_uploads_only_images_for_a_reply(api) -> None:
    refused = api.intent(
        api.client(), b"%PDF-1.4\n", filename="working.pdf", contentType="application/pdf"
    )

    assert (refused.status_code, _code(refused)) == (422, "upload_type_not_supported")


# --- The reply carries it, and the student reads it ---


@pytest.mark.parametrize("accept_first", [False, True], ids=["reply_accepts", "accepted_then_reply"])
def test_the_student_sees_the_image_a_teacher_replied_with(table, api, accept_first) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    if accept_first:
        assert _set_status(teacher, "in_progress").status_code == 200
    data = _png()
    upload_id = api.uploaded(teacher, data)

    replied = _reply(teacher, upload_id)

    assert replied.status_code == 200, replied.text
    [sent] = replied.json()["attachments"]
    assert (sent["mediaType"], sent["sizeBytes"], sent["filename"]) == (
        "image/png",
        len(data),
        "working.png",
    )
    assert _conv(table)["teacher_id"] == TEACHER
    [message] = _teacher_messages(api)
    assert message["content"] == "Schau dir meine Rechnung an."
    assert message["attachments"] == [sent]
    student = api.client(STUDENT, role="student")
    content = student.get(f"/files/attachments/{sent['attachmentId']}/content")
    assert content.status_code == 200, content.text
    assert content.content == data
    assert _upload_status(table, upload_id) == "consumed"


def test_the_teacher_sees_their_image_in_the_request_too(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    data = _png()
    [sent] = _reply(teacher, api.uploaded(teacher, data)).json()["attachments"]

    detail = teacher.get(f"/teachers/me/help-requests/{REQUEST}")

    assert detail.status_code == 200, detail.text
    [message] = [m for m in detail.json()["messages"] if m["role"] == "teacher"]
    assert message["attachments"] == [sent]
    [note] = detail.json()["notes"]
    assert note["attachments"] == [sent]
    content = teacher.get(
        f"/teachers/me/help-requests/{REQUEST}/attachments/{sent['attachmentId']}/content"
    )
    assert content.status_code == 200, content.text
    assert content.content == data


def test_the_image_goes_with_the_students_conversation(table, api) -> None:
    # The image is the student's, as the reply is (#74): the hook the student's
    # account deletion releases each conversation's attachments through takes
    # it too, stored image and all.
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    [sent] = _reply(teacher, api.uploaded(teacher, _png())).json()["attachments"]
    # Neither side removes it from the conversation on its own.
    assert teacher.delete(f"/files/attachments/{sent['attachmentId']}").status_code == 404
    student = api.client(STUDENT, role="student")
    assert student.delete(f"/files/attachments/{sent['attachmentId']}").status_code == 409

    released = attachment_service.release_conversation_attachments(
        STUDENT, CONV, s3=api.s3, settings=Settings(s3_images_bucket=BUCKET)
    )

    assert (released.disposition, released["deleted"]) == ("complete", 1)
    assert [key for key in api.s3.objects if key[0].startswith("objects/")] == []
    assert (f"ATTACHMENT#{sent['attachmentId']}", "META") not in table.rows


PURGE_ROUNDS = 4


def _purge_account(table, api: _Api, user_id: str) -> list[str]:
    """Run the account purge's attachment branch for `user_id`, as the deletion job does.

    Each round is one job pass; the job stops at the first one that completes.
    """
    table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    outcomes = []
    for _round in range(PURGE_ROUNDS):
        result = attachment_service.purge_student_attachments(
            user_id,
            account_fence_generation=1,
            s3=api.s3,
            settings=Settings(s3_images_bucket=BUCKET),
        )
        outcomes.append(result.status.value)
        if result.status.value == "complete":
            break
    return outcomes


def test_the_teachers_account_deletion_completes_and_the_image_stays_the_students(
    table, api
) -> None:
    # Once sent, the image is no longer the teacher's to delete: the teacher's
    # deletion finishes without it, and the student keeps reading it.
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    data = _png()
    upload_id = api.uploaded(teacher, data)
    [sent] = _reply(teacher, upload_id).json()["attachments"]

    outcomes = _purge_account(table, api, TEACHER)

    assert outcomes[-1] == "complete", outcomes
    student = api.client(STUDENT, role="student")
    content = student.get(f"/files/attachments/{sent['attachmentId']}/content")
    assert content.status_code == 200, content.text
    assert content.content == data


def test_the_students_account_deletion_takes_the_teachers_image(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    upload_id = api.uploaded(teacher, _png())
    [sent] = _reply(teacher, upload_id).json()["attachments"]

    outcomes = _purge_account(table, api, STUDENT)

    assert outcomes[-1] == "complete", outcomes
    assert [key for key in api.s3.objects if key[0].startswith("objects/")] == []
    assert (f"ATTACHMENT#{sent['attachmentId']}", "META") not in table.rows
    assert (f"UPLOAD#{upload_id}", "META") not in table.rows


def test_a_reply_carries_several_images_in_order(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    first, second = _png(1), _png(2)
    uploads = [api.uploaded(teacher, first), api.uploaded(teacher, second)]

    replied = _reply(teacher, *uploads)

    assert replied.status_code == 200, replied.text
    [message] = _teacher_messages(api)
    student = api.client(STUDENT, role="student")
    assert [
        student.get(f"/files/attachments/{item['attachmentId']}/content").content
        for item in message["attachments"]
    ] == [first, second]


def test_a_reply_without_images_is_unchanged(table, api) -> None:
    _dispatch_to(table, TEACHER)

    replied = api.client().post(
        f"/teachers/me/help-requests/{REQUEST}/notes", json={"content": "Nur Text."}
    )

    assert replied.status_code == 200, replied.text
    assert replied.json()["attachments"] == []
    [message] = _teacher_messages(api)
    assert message["attachments"] == []


# --- What does not make a reply ---


def test_a_blocked_image_does_not_make_a_reply(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    api.moderation.labels = RUDE_GESTURE
    upload_id, blocked = api.upload(teacher, _png())
    assert _code(blocked) == "upload_content_blocked"

    refused = _reply(teacher, upload_id)

    assert (refused.status_code, _code(refused)) == (404, "upload_not_found")
    assert _written_replies(table) == []
    assert _teacher_messages(api) == []
    # Nor did the refused reply take the offer.
    assert "teacher_id" not in _conv(table)
    assert _question(table)["status"] == "escalated"


def test_an_image_moderation_could_not_judge_does_not_make_a_reply(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    api.moderation.error = TimeoutError("rekognition did not answer")
    upload_id, failed = api.upload(teacher, _png())
    assert (failed.status_code, _code(failed)) == (503, "upload_service_unavailable")

    refused = _reply(teacher, upload_id)

    assert refused.status_code == 404
    assert _written_replies(table) == []


def test_an_image_is_sent_once(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    upload_id = api.uploaded(teacher, _png())
    assert _reply(teacher, upload_id).status_code == 200

    again = _reply(teacher, upload_id, content="Noch einmal.")

    assert (again.status_code, _code(again)) == (404, "upload_not_found")
    assert len(_teacher_messages(api)) == 1


def test_the_same_image_twice_in_one_reply_is_refused(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    upload_id = api.uploaded(teacher, _png())

    refused = _reply(teacher, upload_id, upload_id)

    assert refused.status_code == 422
    assert _written_replies(table) == []
    assert _upload_status(table, upload_id) == "validated"


def test_a_reply_does_not_carry_a_students_upload(table, api) -> None:
    _dispatch_to(table, TEACHER)
    student = api.client(STUDENT, role="student")
    intent = api.intent(student, _png(), purpose="conversation_attachment")
    assert intent.status_code == 200, intent.text

    refused = _reply(api.client(), intent.json()["uploadId"])

    assert (refused.status_code, _code(refused)) == (404, "upload_not_found")
    assert _written_replies(table) == []


def test_a_teacher_does_not_send_another_teachers_image(table, api) -> None:
    _dispatch_to(table, TEACHER)
    theirs = api.uploaded(api.client(OTHER_TEACHER), _png())

    refused = _reply(api.client(), theirs)

    assert (refused.status_code, _code(refused)) == (404, "upload_not_found")
    assert _written_replies(table) == []
    assert _upload_status(table, theirs) == "validated"


# --- Only into a request the teacher is on ---


def test_a_teacher_whose_offer_lapsed_is_refused(table, api) -> None:
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    upload_id = api.uploaded(teacher, _png())
    for row in (_conv(table), _question(table)):
        row["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"

    refused = _reply(teacher, upload_id)

    assert refused.status_code == 403
    assert _written_replies(table) == []
    assert _upload_status(table, upload_id) == "validated"


def test_a_teacher_assigned_to_the_student_but_not_to_the_request_is_refused(
    table, api
) -> None:
    # A standing assignment may let a teacher read the request (#73); it does
    # not let them answer it.
    assigned = "teacher-145-assigned"
    table.seed(
        *_teacher_rows(assigned),
        {
            "PK": f"TEACHER_ASSIGNMENT#{assigned}",
            "SK": f"STUDENT#{STUDENT}",
            "teacher_id": assigned,
            "student_id": STUDENT,
            "status": "active",
            "resource_types": ["teacher_help_request", "attachment"],
            "actions": ["read"],
            "purposes": ["teacher_help"],
        },
    )
    table.rows[(f"USER#{assigned}", "PROFILE")]["dispatch_availability"] = "paused"
    _dispatch_to(table, TEACHER)
    client = api.client(assigned)
    assert client.get(f"/teachers/me/help-requests/{REQUEST}").status_code == 200
    upload_id = api.uploaded(client, _png())

    refused = _reply(client, upload_id)

    assert refused.status_code == 403
    assert _written_replies(table) == []
    assert _upload_status(table, upload_id) == "validated"


@pytest.mark.parametrize(
    "moved_on",
    [
        lambda conv: conv.update(teacher_id=OTHER_TEACHER),
        lambda conv: conv.pop("teacher_id"),
    ],
    ids=["held-by-another", "let-go"],
)
def test_a_holders_reply_lands_only_while_they_still_hold_the_request(
    table, api, monkeypatch, moved_on
) -> None:
    # The request was this teacher's when the route authorized the reply, and
    # stopped being theirs before the write: the reply and its image must not land.
    _dispatch_to(table, TEACHER)
    teacher = api.client()
    assert _set_status(teacher, "in_progress").status_code == 200
    upload_id = api.uploaded(teacher, _png())
    prepare = attachment_service.prepare_reply_images

    def authorized_then_moved_on(*args, **kwargs):
        prepared = prepare(*args, **kwargs)
        moved_on(_conv(table))
        return prepared

    monkeypatch.setattr(attachment_service, "prepare_reply_images", authorized_then_moved_on)

    refused = _reply(teacher, upload_id)

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "help_request_changed"
    assert _written_replies(table) == []
    assert _upload_status(table, upload_id) == "validated"


def test_a_teacher_with_nothing_to_do_with_the_request_is_refused_like_the_request(
    table, api
) -> None:
    # A teacher the request was never with learns nothing of it: refused as its
    # detail refuses them (the concealment rule #140 kept).
    _dispatch_to(table, TEACHER)
    other = api.client(OTHER_TEACHER)
    upload_id = api.uploaded(other, _png())

    refused = _reply(other, upload_id)

    assert refused.status_code == 404
    assert refused.status_code == other.get(f"/teachers/me/help-requests/{REQUEST}").status_code
    assert _written_replies(table) == []
    assert _upload_status(table, upload_id) == "validated"
