"""The teacher sees the images a student sent in a chat help request (#140).

A help request's detail used to carry message text only, and attachment content
was readable by its owner alone, so the teacher who took the request over could
not see what the student had photographed. The detail's messages now carry each
attachment's summary, and the teacher the request is with reads the content
under that request: the teacher it is offered to, or the teacher who took it.
Anyone else is refused the way the request itself refuses them.

Rows, dispatch, the authorization facts and the teacher policy are real, over
the shared table double (see test_chat_help_request_lifecycle.py); only S3 is
replaced.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from stoa.deps import get_s3_client
from stoa.routers import files, teachers
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import teacher_dispatch_service
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

IMAGE = b"\x89PNG\r\n\x1a\n homework photo"
ATTACHMENT = "att-140"
OTHER_ATTACHMENT = "att-140-other-conversation"
ETAG = '"etag-140"'


def _attachment_row(attachment_id: str, owner_id: str = STUDENT) -> dict[str, Any]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": "META",
        "entity_type": "attachment",
        "schema_version": "attachment.v1",
        "attachment_id": attachment_id,
        "owner_id": owner_id,
        "student_id": owner_id,
        "status": "active",
        "ref_count": 1,
        "original_filename": "homework.png",
        "detected_type": "image/png",
        "content_length": len(IMAGE),
        "content_sha256": hashlib.sha256(IMAGE).hexdigest(),
        "immutable_object_key": f"objects/{owner_id}/{attachment_id}",
        "immutable_version_id": "version-140",
        "immutable_etag": ETAG,
        "created_at": "2026-09-28T11:58:00+00:00",
    }


def _message_row(message_id: str, created_at: str, **extra: Any) -> dict[str, Any]:
    return {
        "PK": f"CONV#{CONV}",
        "SK": f"MSG#{created_at}#{message_id}",
        "entity_type": "message",
        "message_id": message_id,
        "conversation_id": CONV,
        "owner_id": STUDENT,
        "student_id": STUDENT,
        "role": "user",
        "created_at": created_at,
        **extra,
    }


@pytest.fixture
def sent_image(table):
    """The student's conversation: a photo with a question, then a text follow-up.

    A second photo of the same student's sits in another conversation.
    """
    table.seed(
        _attachment_row(ATTACHMENT),
        _attachment_row(OTHER_ATTACHMENT),
        _message_row(
            "msg-photo",
            "2026-09-28T11:58:30+00:00",
            content="What is step 2 here?",
            attachment_ids=[ATTACHMENT],
        ),
        _message_row("msg-text", "2026-09-28T11:59:00+00:00", content="Still stuck."),
    )
    return table


class _S3:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"Body": _Body(IMAGE), "ContentLength": len(IMAGE), "ETag": ETAG}


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self, limit: int) -> bytes:
        value, self.data = self.data[:limit], self.data[limit:]
        return value

    def close(self) -> None:
        pass


def _client(user_id: str, role: str = "teacher", s3: _S3 | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_s3_client] = lambda: s3 or _S3()
    install_actor_overrides(app, {"sub": user_id, "role": role})
    # The helper's fact stand-in grants a teacher whatever they ask for; who may
    # read is the point here, so the facts are loaded from the table.
    del app.dependency_overrides[get_authorization_fact_repository]
    return TestClient(app)


def _content(client: TestClient, attachment_id: str = ATTACHMENT):
    return client.get(
        f"/teachers/me/help-requests/{REQUEST}/attachments/{attachment_id}/content"
    )


def _redispatch_to_the_other_teacher(table) -> None:
    for row in (_conv(table), _question(table)):
        row["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    table.rows[(f"USER#{OTHER_TEACHER}", "PROFILE")]["dispatch_availability"] = "available"
    teacher_dispatch_service.reconcile_dispatches()
    assert _conv(table)["dispatched_teacher_id"] == OTHER_TEACHER


# --- The detail names each message's attachments ---


def test_the_detail_carries_each_messages_attachment_summary(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)

    response = _client(TEACHER).get(f"/teachers/me/help-requests/{REQUEST}")

    assert response.status_code == 200, response.text
    messages = {message["id"]: message for message in response.json()["messages"]}
    assert messages["msg-photo"]["attachments"] == [
        {
            "attachmentId": ATTACHMENT,
            "filename": "homework.png",
            "mediaType": "image/png",
            "sizeBytes": len(IMAGE),
            "status": "active",
            "createdAt": "2026-09-28T11:58:00Z",
        }
    ]
    assert messages["msg-text"]["attachments"] == []
    # The summary is a summary: nothing that locates the stored object.
    assert "objects/" not in response.text and "version-140" not in response.text


# --- Who reads the content ---


def test_the_teacher_it_is_offered_to_reads_the_image_before_accepting(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    s3 = _S3()

    response = _content(_client(TEACHER, s3=s3))

    assert response.status_code == 200, response.text
    assert response.content == IMAGE
    assert response.headers["content-type"] == "image/png"
    assert s3.calls[0]["Key"] == f"objects/{STUDENT}/{ATTACHMENT}"
    assert s3.calls[0]["VersionId"] == "version-140"
    assert "teacher_id" not in _conv(sent_image), "reading is not taking"


def test_the_teacher_who_took_it_reads_the_image_while_open_and_after_resolving(
    sent_image,
) -> None:
    _dispatch_to(sent_image, TEACHER)
    client = _client(TEACHER)
    assert _set_status(client, "in_progress").status_code == 200

    assert _content(client).content == IMAGE

    assert _set_status(client, "resolved").status_code == 200
    assert _content(client).content == IMAGE


def test_another_teacher_is_refused_like_the_request_itself(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    other = _client(OTHER_TEACHER)

    refused = _content(other)

    assert refused.status_code == 404
    assert refused.status_code == other.get(f"/teachers/me/help-requests/{REQUEST}").status_code
    assert IMAGE not in refused.content


def test_after_a_redispatch_only_the_new_teacher_reads_the_image(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    assert _content(_client(TEACHER)).status_code == 200

    _redispatch_to_the_other_teacher(sent_image)

    earlier = _client(TEACHER)
    refused = _content(earlier)
    assert refused.status_code == 404
    assert refused.status_code == earlier.get(f"/teachers/me/help-requests/{REQUEST}").status_code
    assert _content(_client(OTHER_TEACHER)).content == IMAGE


def test_another_teacher_learns_nothing_about_which_attachments_exist(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    other = _client(OTHER_TEACHER)

    sent, missing = _content(other), _content(other, "att-140-does-not-exist")

    def shape(response):
        return response.status_code, {**response.json()["detail"], "correlationId": None}

    assert shape(sent) == shape(missing)


def test_a_teacher_assigned_to_the_student_reads_the_request_but_not_its_images(
    sent_image,
) -> None:
    # A standing assignment may admit a teacher to the request (user decision
    # on #73), but only the teacher the request is with opens what the student
    # sent in it.
    assigned = "teacher-140-assigned"
    sent_image.seed(
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
    sent_image.rows[(f"USER#{assigned}", "PROFILE")]["dispatch_availability"] = "paused"
    _dispatch_to(sent_image, TEACHER)
    client = _client(assigned)

    assert client.get(f"/teachers/me/help-requests/{REQUEST}").status_code == 200
    refused = _content(client)
    assert refused.status_code == 403
    assert IMAGE not in refused.content


def test_a_lapsed_offer_no_longer_reads_the_image(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    for row in (_conv(sent_image), _question(sent_image)):
        row["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"

    assert _content(_client(TEACHER)).status_code == 403


@pytest.mark.parametrize("student_id", [STUDENT, "student-140-other"], ids=["owner", "other"])
def test_students_do_not_read_through_the_teacher_route(sent_image, student_id) -> None:
    _dispatch_to(sent_image, TEACHER)

    refused = _content(_client(student_id, role="student"))

    assert refused.status_code in {403, 404}
    assert IMAGE not in refused.content


def test_the_student_still_reads_their_own_image(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)

    response = _client(STUDENT, role="student").get(f"/files/attachments/{ATTACHMENT}/content")

    assert response.status_code == 200, response.text
    assert response.content == IMAGE


def test_the_teacher_still_cannot_read_through_the_owners_route(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)

    response = _client(TEACHER).get(f"/files/attachments/{ATTACHMENT}/content")

    assert response.status_code == 404


# --- Only what was sent in this request ---


def test_the_students_other_images_stay_out_of_reach(sent_image) -> None:
    # The teacher holds this request; the attachment is the same student's, but
    # was never sent in it.
    _dispatch_to(sent_image, TEACHER)
    s3 = _S3()

    response = _content(_client(TEACHER, s3=s3), OTHER_ATTACHMENT)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "upload_not_found"
    assert s3.calls == []


def test_an_attachment_owned_by_someone_else_is_not_read_even_if_referenced(
    sent_image,
) -> None:
    foreign = "att-140-foreign"
    sent_image.seed(_attachment_row(foreign, owner_id="student-140-other"))
    sent_image.rows[(f"CONV#{CONV}", "MSG#2026-09-28T11:58:30+00:00#msg-photo")][
        "attachment_ids"
    ] = [ATTACHMENT, foreign]
    _dispatch_to(sent_image, TEACHER)

    response = _content(_client(TEACHER), foreign)

    assert response.status_code == 403
    assert IMAGE not in response.content


def test_a_deleted_attachment_is_not_read(sent_image) -> None:
    _dispatch_to(sent_image, TEACHER)
    sent_image.rows[(f"ATTACHMENT#{ATTACHMENT}", "META")]["status"] = "deleted"

    response = _content(_client(TEACHER))

    assert response.status_code == 404
