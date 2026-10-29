"""A refused image becomes a case in the admin moderation queue (#139).

When moderation refuses an upload (#138), the image is kept as evidence in the
images bucket and a case is opened with what refused it (each label, its blocked
category and confidence), who uploaded it and the learning session it was meant
for. Admins are told in-app with the existing "new moderation case" notice. Only
an admin can read the image; it is deleted 90 days after the case is handled,
and at once when the uploader's account is deleted.

The seam is the real files, admin and notification routers and the real
repositories on the shared DynamoDB double, S3 replaced by the multipart double
and Rekognition by `fakes.rekognition`. Deletion runs the scheduled retention job
and the account-deletion moderation branch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import random
from typing import Any

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from stoa.config import Settings
from stoa.db.repositories import (
    account_deletion_repo,
    attachment_repo,
    moderation_repo,
    notification_repo,
    user_repo,
)
from stoa.deps import (
    get_actor,
    get_image_moderation_client,
    get_s3_client,
    get_s3_presign_client,
    get_settings,
)
from stoa.jobs import moderation_image_retention
from stoa.routers import admin, files, notifications
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import account_deletion_service, locale_service, message_catalog
from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable, as_stored
from fakes.rekognition import FakeRekognition
from fakes.s3 import MultipartS3


STUDENT = "student-139"
OTHER_STUDENT = "student-other"
CONVERSATION = "conv-139"
BUCKET = "images-bucket-139"
ADMIN = {"sub": "admin-139", "role": "admin"}


def _png(*, seed: int = 139) -> bytes:
    noise = random.Random(seed).randbytes(120 * 120 * 3)
    output = BytesIO()
    Image.frombytes("RGB", (120, 120), noise).save(output, "PNG", compress_level=0)
    return output.getvalue()


def _label(name: str, confidence: float, parent: str = "", level: int = 1) -> dict[str, Any]:
    return {"Name": name, "Confidence": confidence, "ParentName": parent, "TaxonomyLevel": level}


# Two hits under one blocked category at different confidences, under a parent
# that is not itself blocked, so the record has to keep each one as it came.
REFUSING_LABELS = [
    _label("Violence", 99.0),
    _label("Graphic Violence", 91.5, "Violence", 2),
    _label("Blood & Gore", 84.25, "Graphic Violence", 3),
]
EXPECTED_HITS = [
    {"label": "Graphic Violence", "category": "Graphic Violence", "confidence": 91.5},
    {"label": "Blood & Gore", "category": "Graphic Violence", "confidence": 84.25},
]


def _actor(user_id: str, role: CanonicalRole) -> Actor:
    return Actor(user_id, "issuer", "subject", role, AccountStatus.ACTIVE, role.value)


class _World:
    """One table, one bucket, one moderation answer; clients for each reader."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, labels: list[dict[str, Any]]) -> None:
        self.table = FakeTable()
        self.table.seed_active_account(STUDENT, generation=3)
        self.table.seed_active_account(OTHER_STUDENT)
        for user_id in (STUDENT, OTHER_STUDENT):
            self.table.seed(
                {
                    "PK": f"CONV#{CONVERSATION if user_id == STUDENT else 'conv-other'}",
                    "SK": "CONV",
                    "entity_type": "conversation",
                    "conversation_id": CONVERSATION if user_id == STUDENT else "conv-other",
                    "student_id": user_id,
                    "title": "Fractions",
                }
            )
        for module in (attachment_repo, account_deletion_repo, moderation_repo, notification_repo):
            monkeypatch.setattr(module, "get_table", lambda: self.table)
        monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
        # The admin reads in the language they stored; no request asked for one
        # (an earlier test can leave its request's language bound).
        locale_service.set_request_locale(None)
        self.locale = "en"
        monkeypatch.setattr(
            user_repo,
            "get_user",
            lambda user_id, **_kwargs: {
                "user_id": user_id,
                "role": "admin",
                "account_status": "active",
                "preferred_locale": self.locale,
            }
            if user_id == ADMIN["sub"]
            else None,
        )
        self.s3 = MultipartS3(BUCKET)
        self.moderation = FakeRekognition(labels)
        self.settings = Settings(s3_images_bucket=BUCKET)
        student = FastAPI()
        student.include_router(files.router, prefix="/files")
        student.dependency_overrides[get_actor] = lambda: _actor(STUDENT, CanonicalRole.STUDENT)
        student.dependency_overrides[get_s3_client] = lambda: self.s3
        student.dependency_overrides[get_s3_presign_client] = lambda: self.s3
        student.dependency_overrides[get_image_moderation_client] = lambda: self.moderation
        student.dependency_overrides[get_settings] = lambda: self.settings
        self.student = TestClient(student)

    def reader(self, user: dict[str, str]) -> TestClient:
        app = FastAPI()
        app.include_router(admin.router, prefix="/admin")
        app.include_router(notifications.admin_router, prefix="/admin")
        install_actor_overrides(app, user)
        app.dependency_overrides[get_s3_client] = lambda: self.s3
        app.dependency_overrides[get_settings] = lambda: self.settings
        return TestClient(app)

    @property
    def admin(self) -> TestClient:
        return self.reader(ADMIN)

    def intent(self, data: bytes, purpose: str = "conversation_attachment", **extra: Any):
        return self.student.post(
            "/files/intents",
            json={
                "purpose": purpose,
                "filename": "homework.png",
                "contentType": "image/png",
                "sizeBytes": len(data),
                **extra,
            },
        )

    def upload(
        self,
        data: bytes,
        conversation_id: str | None = CONVERSATION,
        purpose: str = "conversation_attachment",
    ) -> str:
        extra = {"conversationId": conversation_id} if conversation_id else {}
        intent = self.intent(data, purpose, **extra)
        assert intent.status_code == 200, intent.text
        upload_id = intent.json()["uploadId"]
        signed = self.student.post(
            f"/files/{upload_id}/parts/1",
            json={"sizeBytes": len(data), "checksumSha256": _sha256(data)},
        )
        assert signed.status_code == 200, signed.text
        url = signed.json()
        assert self.s3.browser_put(url["url"], url["method"], url["headers"], data) == 200
        return upload_id

    def complete(self, upload_id: str):
        return self.student.post(f"/files/{upload_id}/complete", json={"partCount": 1})

    def cases(self) -> list[dict[str, Any]]:
        response = self.admin.get("/admin/moderation/cases")
        assert response.status_code == 200, response.text
        return response.json()["items"]

    def evidence(self) -> list[bytes]:
        return [
            stored["data"]
            for (key, _version), stored in self.s3.objects.items()
            if not key.startswith(("staging/", "objects/"))
        ]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def world(monkeypatch) -> _World:
    return _World(monkeypatch, REFUSING_LABELS)


def _blocked(world: _World, data: bytes | None = None) -> tuple[str, dict[str, Any]]:
    data = data or _png()
    upload_id = world.upload(data)
    refused = world.complete(upload_id)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (422, "upload_content_blocked")
    [case] = world.cases()
    return upload_id, case


def test_a_refused_image_opens_a_case_with_its_hits_uploader_and_session(world) -> None:
    upload_id, case = _blocked(world)

    assert case["surface"] == "image_upload"
    assert case["status"] == "open"
    assert case["reason"] == "unsafe_content"
    assert case["severity"] == "high"
    assert case["question_id"] is None
    assert case["student_id"] == STUDENT
    assert case["reporter_role"] == "system"
    uploaded_at = datetime.fromisoformat(case["image_context"]["uploaded_at"])
    assert uploaded_at.tzinfo is not None
    assert uploaded_at <= datetime.fromisoformat(case["created_at"]) + timedelta(seconds=1)
    assert case["image_context"] == {
        "upload_id": upload_id,
        "conversation_id": CONVERSATION,
        "uploaded_at": case["image_context"]["uploaded_at"],
        "uploader_id": STUDENT,
        "uploader_role": "student",
        "media_type": "image/png",
        "size_bytes": len(_png()),
        "hits": EXPECTED_HITS,
        "image_status": "stored",
        "image_deleted_at": None,
    }
    opened = world.admin.get(f"/admin/moderation/cases/{case['case_id']}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["image_context"]["hits"] == EXPECTED_HITS
    # Where the image is kept is not part of what an admin is handed.
    assert "moderation/" not in opened.text and "VersionId" not in opened.text


def test_an_upload_without_a_session_still_opens_a_case(world) -> None:
    upload_id = world.upload(_png(), conversation_id=None)

    assert world.complete(upload_id).status_code == 422
    [case] = world.cases()
    assert case["image_context"]["conversation_id"] is None
    assert case["image_context"]["uploader_id"] == STUDENT


def test_an_image_that_passes_opens_no_case(monkeypatch) -> None:
    world = _World(monkeypatch, [_label("Graphic Violence", 79.0, "Violence", 2)])

    assert world.complete(world.upload(_png())).status_code == 200
    assert world.cases() == []
    assert world.evidence() == []


def test_a_session_that_is_not_the_students_own_is_refused_at_the_intent(world) -> None:
    for conversation_id in ("conv-other", "conv-missing"):
        refused = world.intent(_png(), conversationId=conversation_id)
        assert refused.status_code == 404, refused.text
        assert refused.json()["detail"]["code"] == "upload_not_found"


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_admins_are_told_in_app_in_their_language(world, locale) -> None:
    world.locale = locale
    _upload_id, case = _blocked(world)

    response = world.admin.get("/admin/notifications?event_type=moderation_case_update")

    assert response.status_code == 200, response.text
    [notice] = response.json()["items"]
    assert notice["title"] == message_catalog.TEXT["moderation.created.title"][locale]
    assert notice["summary"] == message_catalog.TEXT["moderation.created.summary.high"][locale]
    assert notice["targetId"] == case["case_id"]


def test_only_an_admin_can_read_the_refused_image(world) -> None:
    data = _png(seed=7)
    upload_id, case = _blocked(world, data)

    shown = world.admin.get(f"/admin/moderation/cases/{case['case_id']}/image")

    assert shown.status_code == 200, shown.text
    assert shown.content == data
    assert shown.headers["content-type"] == "image/png"
    assert shown.headers["cache-control"] == "no-store"
    assert shown.headers["x-content-type-options"] == "nosniff"
    for reader in ({"sub": STUDENT, "role": "student"}, {"sub": "teacher-1", "role": "teacher"}):
        refused = world.reader(reader).get(f"/admin/moderation/cases/{case['case_id']}/image")
        assert refused.status_code == 403, refused.text
    # The uploader holds nothing that reaches it either: no attachment, no upload.
    assert world.student.get("/files/attachments").json()["items"] == []
    assert world.complete(upload_id).status_code == 404


def test_a_case_without_an_image_has_none_to_read(world) -> None:
    world.table.seed(
        {
            "PK": "MODERATION#mod-question",
            "SK": "SUMMARY",
            "entity_type": "moderation_case",
            "case_id": "mod-question",
            "status": "open",
            "reason": "abuse",
            "severity": "medium",
            "surface": "question",
            "question_id": "question-1",
            "student_id": STUDENT,
            "privacy_generation": 3,
            "reporter_id": STUDENT,
            "reporter_role": "student",
            "created_at": "2026-10-01T00:00:00+00:00",
            "updated_at": "2026-10-01T00:00:00+00:00",
        }
    )

    assert world.admin.get("/admin/moderation/cases/mod-question/image").status_code == 404
    assert world.admin.get("/admin/moderation/cases/mod-missing/image").status_code == 404


def _handle(world: _World, case_id: str, status: str = "actioned") -> datetime:
    handled = world.admin.patch(f"/admin/moderation/cases/{case_id}", json={"status": status})
    assert handled.status_code == 200, handled.text
    return datetime.fromisoformat(handled.json()["closed_at"])


def _retain(world: _World, now: datetime) -> Any:
    return moderation_image_retention.run(s3=world.s3, settings_obj=world.settings, now=now)


@pytest.mark.parametrize("status", ["actioned", "dismissed", "closed"])
def test_the_image_is_deleted_ninety_days_after_the_case_is_handled(world, status) -> None:
    _upload_id, case = _blocked(world)
    handled_at = _handle(world, case["case_id"], status)

    _retain(world, handled_at + timedelta(days=90) - timedelta(seconds=1))

    assert len(world.evidence()) == 1
    image = f"/admin/moderation/cases/{case['case_id']}/image"
    assert world.admin.get(image).status_code == 200

    summary = _retain(world, handled_at + timedelta(days=90))

    assert summary.deleted == 1
    assert world.evidence() == []
    assert world.admin.get(image).status_code == 404
    [kept] = world.cases()
    assert kept["image_context"]["image_status"] == "deleted"
    assert kept["image_context"]["image_deleted_at"] is not None
    assert kept["image_context"]["hits"] == EXPECTED_HITS
    history = world.admin.get(f"/admin/moderation/cases/{case['case_id']}").json()["history"]
    assert [event["event_type"] for event in history][-1] == "image_deleted"
    # A second run finds nothing left to do.
    assert _retain(world, handled_at + timedelta(days=91)).deleted == 0


def test_an_unhandled_case_keeps_its_image_for_365_days_from_upload(world) -> None:
    """No one handled it: deleted when a year has passed, as promised to parents."""
    _upload_id, case = _blocked(world)
    uploaded_at = datetime.fromisoformat(case["image_context"]["uploaded_at"])
    image = f"/admin/moderation/cases/{case['case_id']}/image"

    _retain(world, uploaded_at + timedelta(days=364))
    _retain(world, uploaded_at + timedelta(days=365) - timedelta(seconds=1))

    assert len(world.evidence()) == 1
    assert world.admin.get(image).status_code == 200

    assert _retain(world, uploaded_at + timedelta(days=365)).deleted == 1

    assert world.evidence() == []
    assert world.admin.get(image).status_code == 404
    [kept] = world.cases()
    assert kept["status"] == "open"
    assert kept["image_context"]["image_status"] == "deleted"


def test_a_case_handled_late_is_still_deleted_at_365_days(world) -> None:
    """Handled on day 300: the year from upload comes before the 90 days."""
    _upload_id, case = _blocked(world)
    uploaded_at = datetime.fromisoformat(case["image_context"]["uploaded_at"])
    _handle(world, case["case_id"])
    key = (f"MODERATION#{case['case_id']}", "SUMMARY")
    late = (uploaded_at + timedelta(days=300)).replace(microsecond=0)
    world.table.rows[key] = {**world.table.rows[key], "closed_at": late.isoformat()}

    _retain(world, uploaded_at + timedelta(days=365) - timedelta(seconds=1))
    assert len(world.evidence()) == 1
    _retain(world, uploaded_at + timedelta(days=365))
    assert world.evidence() == []


def test_a_reopened_case_keeps_its_image(world) -> None:
    _upload_id, case = _blocked(world)
    handled_at = _handle(world, case["case_id"])
    reopened = world.admin.patch(f"/admin/moderation/cases/{case['case_id']}", json={"status": "in_review"})
    assert reopened.status_code == 200, reopened.text

    _retain(world, handled_at + timedelta(days=120))

    assert len(world.evidence()) == 1


def test_the_retention_job_is_reached_from_its_schedule(world, monkeypatch) -> None:
    _upload_id, case = _blocked(world)
    _handle(world, case["case_id"])
    monkeypatch.setattr(moderation_image_retention.boto3, "client", lambda *_a, **_k: world.s3)
    monkeypatch.setattr(moderation_image_retention, "settings", world.settings)
    later = datetime.now(UTC) + timedelta(days=91)
    monkeypatch.setattr(moderation_image_retention, "_now", lambda: later)

    from stoa.jobs import account_deletion

    result = account_deletion.handler(
        {"source": "stoa.scheduler", "job": "moderation_image_retention"}, None
    )

    assert result["deleted"] == 1
    assert world.evidence() == []


def test_account_deletion_removes_the_image_and_the_case(world, monkeypatch) -> None:
    _upload_id, case = _blocked(world)
    world.table.seed(
        as_stored(
            {
                "PK": f"USER#{STUDENT}",
                "SK": "ACCOUNT_FENCE",
                "status": "deletion_pending",
                "generation": 3,
            }
        )
    )
    monkeypatch.setattr(account_deletion_service.boto3, "client", lambda *_a, **_k: world.s3)
    monkeypatch.setattr(account_deletion_service, "get_settings", lambda: world.settings)

    previous: dict[str, Any] = {}
    for _ in range(6):
        result = account_deletion_service._moderation_support_branch(
            command={"user_id": STUDENT, "generation": 3}, previous=previous
        )
        previous = result.persisted(datetime.now(UTC).isoformat())
        if result.status == "complete":
            break

    assert result.status == "complete"
    assert world.evidence() == []
    assert world.cases() == []
    assert world.admin.get(f"/admin/moderation/cases/{case['case_id']}").status_code == 404


def test_a_lost_image_keeps_account_deletion_waiting(world, monkeypatch) -> None:
    """If the image cannot be deleted, the case is not scrubbed and its coordinates kept."""
    _blocked(world)
    world.table.seed(
        as_stored(
            {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE", "status": "deletion_pending", "generation": 3}
        )
    )

    def refuse(**_kwargs: Any) -> dict[str, Any]:
        raise ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "DeleteObject")

    world.s3.delete_object = refuse
    monkeypatch.setattr(account_deletion_service.boto3, "client", lambda *_a, **_k: world.s3)
    monkeypatch.setattr(account_deletion_service, "get_settings", lambda: world.settings)

    result = account_deletion_service._moderation_support_branch(
        command={"user_id": STUDENT, "generation": 3}, previous={}
    )

    assert result.status == "retryable"
    assert len(world.evidence()) == 1
    [summary] = [
        row for (pk, sk), row in world.table.rows.items() if pk.startswith("MODERATION#") and sk == "SUMMARY"
    ]
    assert summary.get("privacy_deleted") is not True


def test_a_retried_refusal_opens_no_second_case(world, monkeypatch) -> None:
    """The case is written, then ending the upload fails; the retry finds the case."""
    upload_id = world.upload(_png())
    mark_invalid = attachment_repo.mark_invalid
    failures = [RuntimeError("table unavailable")]

    def fail_once(*args: Any, **kwargs: Any) -> Any:
        if failures:
            raise failures.pop()
        return mark_invalid(*args, **kwargs)

    monkeypatch.setattr(attachment_repo, "mark_invalid", fail_once)

    assert world.complete(upload_id).status_code == 503
    assert world.complete(upload_id).status_code == 422
    assert len(world.cases()) == 1
    assert len(world.evidence()) == 1
    notices = world.admin.get("/admin/notifications?event_type=moderation_case_update").json()["items"]
    assert len(notices) == 1


def test_when_the_image_cannot_be_kept_the_upload_stays_retryable(world) -> None:
    """No case, no refusal: the next completion asks again and records it then."""
    data = _png()
    upload_id = world.upload(data)
    put_object = world.s3.put_object

    def refuse_evidence(**kwargs: Any) -> dict[str, Any]:
        if not str(kwargs["Key"]).startswith("objects/"):
            raise ClientError({"Error": {"Code": "InternalError", "Message": "x"}}, "PutObject")
        return put_object(**kwargs)

    world.s3.put_object = refuse_evidence
    failed = world.complete(upload_id)

    assert (failed.status_code, failed.json()["detail"]["code"]) == (503, "upload_service_unavailable")
    assert world.cases() == []

    world.s3.put_object = put_object
    refused = world.complete(upload_id)

    assert (refused.status_code, refused.json()["detail"]["code"]) == (422, "upload_content_blocked")
    assert len(world.cases()) == 1
    assert world.evidence() == [data]


def test_a_teachers_refused_reply_image_names_the_teacher(world) -> None:
    """A teacher's image for a help reply (#145) is moderated and queued the same way."""
    world.table.seed_active_account("teacher-1", generation=4)
    world.student.app.dependency_overrides[get_actor] = lambda: _actor("teacher-1", CanonicalRole.TEACHER)
    data = _png(seed=145)

    upload_id = world.upload(data, conversation_id=None, purpose="help_reply_image")

    refused = world.complete(upload_id)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (422, "upload_content_blocked")
    [case] = world.cases()
    assert case["image_context"]["upload_id"] == upload_id
    assert (case["image_context"]["uploader_id"], case["image_context"]["uploader_role"]) == (
        "teacher-1",
        "teacher",
    )
    assert case["image_context"]["hits"] == EXPECTED_HITS
    assert case["student_id"] == "teacher-1"
    assert world.admin.get(f"/admin/moderation/cases/{case['case_id']}/image").content == data


def test_a_case_closed_again_counts_from_its_last_handling(world) -> None:
    """Reopened and closed again: the 90 days start at the second close."""
    _upload_id, case = _blocked(world)
    _handle(world, case["case_id"])
    key = (f"MODERATION#{case['case_id']}", "SUMMARY")
    first_close = datetime.now(UTC).replace(microsecond=0) - timedelta(days=60)
    world.table.rows[key] = {**world.table.rows[key], "closed_at": first_close.isoformat()}
    reopened = world.admin.patch(f"/admin/moderation/cases/{case['case_id']}", json={"status": "in_review"})
    assert reopened.status_code == 200, reopened.text

    closed_again = _handle(world, case["case_id"], "closed")

    assert closed_again > first_close + timedelta(days=59)
    _retain(world, closed_again + timedelta(days=89))
    assert len(world.evidence()) == 1
    _retain(world, closed_again + timedelta(days=90))
    assert world.evidence() == []


def test_a_run_that_could_not_delete_fails_so_the_schedule_retries_and_alarms(world, monkeypatch) -> None:
    _upload_id, case = _blocked(world)
    _handle(world, case["case_id"])

    def refuse(**_kwargs: Any) -> dict[str, Any]:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "x"}}, "DeleteObject")

    world.s3.delete_object = refuse
    monkeypatch.setattr(moderation_image_retention.boto3, "client", lambda *_a, **_k: world.s3)
    monkeypatch.setattr(moderation_image_retention, "settings", world.settings)
    later = datetime.now(UTC) + timedelta(days=91)
    monkeypatch.setattr(moderation_image_retention, "_now", lambda: later)

    from stoa.jobs import account_deletion

    with pytest.raises(RuntimeError, match="retention incomplete"):
        account_deletion.handler({"source": "stoa.scheduler", "job": "moderation_image_retention"}, None)
    assert len(world.evidence()) == 1


def test_handling_an_image_case_tells_no_reporter(world) -> None:
    """Moderation opened it; there is no person behind `system:image_moderation`."""
    _upload_id, case = _blocked(world)
    _handle(world, case["case_id"])
    noted = world.admin.post(f"/admin/moderation/cases/{case['case_id']}/notes", json={"note": "seen"})
    assert noted.status_code == 200, noted.text

    recipients = {row.get("recipient_id") for row in world.table.rows.values()}

    assert "system:image_moderation" not in recipients


def test_a_case_written_despite_an_error_keeps_its_image(world, monkeypatch) -> None:
    """The write landed but answered with an error: the image the case points to stays."""
    data = _png(seed=21)
    upload_id = world.upload(data)
    put_case = moderation_repo.put_case
    lost = [TimeoutError("response lost")]

    def landed_then_failed(*args: Any, **kwargs: Any) -> Any:
        result = put_case(*args, **kwargs)
        if lost:
            raise lost.pop()
        return result

    monkeypatch.setattr(moderation_repo, "put_case", landed_then_failed)

    assert world.complete(upload_id).status_code == 503
    assert world.complete(upload_id).status_code == 422
    [case] = world.cases()
    shown = world.admin.get(f"/admin/moderation/cases/{case['case_id']}/image")
    assert shown.status_code == 200, shown.text
    assert shown.content == data
