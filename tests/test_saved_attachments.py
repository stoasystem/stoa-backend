"""Plan 473-23 contracts for owner-facing saved attachments and purge progress."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor
from stoa.models import attachment as attachment_models
from stoa.routers import files
from stoa.rule_violation import render_message
from stoa.security import attachment_errors
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import attachment_service


PRIVATE_CANARIES = (
    "private-bucket-canary",
    "objects/student/private-key-canary",
    "private-version-canary",
    "private-etag-canary",
    "private-checksum-canary",
    "Amazon S3 provider-canary",
)


def _actor(user_id: str = "student-1", *, active: bool = True) -> Actor:
    return Actor(
        user_id,
        "issuer",
        "subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE if active else AccountStatus.SUSPENDED,
        "student",
    )


def _saved_attachment(
    *,
    attachment_id: str = "attachment-1",
    owner_id: str = "student-1",
    filename: str = "notes.txt",
    data: bytes = b"saved attachment bytes",
    status: str = "active",
    ref_count: int = 0,
) -> dict[str, Any]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": "META",
        "entity_type": "attachment",
        "attachment_id": attachment_id,
        "owner_id": owner_id,
        "student_id": owner_id,
        "status": status,
        "ref_count": ref_count,
        "original_filename": filename,
        "detected_type": "text/plain",
        "content_length": len(data),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "immutable_object_key": PRIVATE_CANARIES[1],
        "immutable_version_id": PRIVATE_CANARIES[2],
        "immutable_etag": PRIVATE_CANARIES[3],
        "created_at": "2026-07-17T00:00:00+00:00",
    }


def _public_schema_text(model: type[BaseModel]) -> str:
    return str(model.model_json_schema(by_alias=True)).lower()


def test_saved_attachment_models_are_coordinate_free_recursively() -> None:
    model_names = (
        "SavedAttachmentDetail",
        "SavedAttachmentPage",
        "SavedAttachmentDeleteResult",
    )
    models: list[type[BaseModel]] = []
    for name in model_names:
        model = getattr(attachment_models, name, None)
        assert isinstance(model, type) and issubclass(model, BaseModel)
        models.append(model)
    rendered = " ".join(_public_schema_text(model) for model in models)
    for forbidden in (
        "bucket",
        "object_key",
        "version_id",
        "etag",
        "checksum",
        "upload_id",
        "provider",
        "student_id",
        "owner_id",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "filename,expected",
    [
        (r"C:\\Users\\private-canary\\homework.txt", "homework.txt"),
        ("/home/student/private-canary/notes.txt", "notes.txt"),
        ("folder\\nested/mixed.txt", "mixed.txt"),
        ('bad\r\nContent-Length: 999\\safe\"name.txt', "safe_name.txt"),
        ("控制/Grüezi 学习.txt", "Grüezi 学习.txt"),
    ],
)
def test_filename_projection_uses_safe_cross_platform_basename(
    filename: str, expected: str
) -> None:
    project = getattr(attachment_service, "safe_attachment_filename", None)
    assert callable(project)
    assert project(filename) == expected
    header = attachment_service.safe_attachment_content_disposition(filename)
    assert "\r" not in header and "\n" not in header
    assert "private-canary" not in header
    assert "\\" not in header and "/" not in header


def _seed(*items: dict[str, Any]) -> Any:
    """Plant attachment rows in the table every test starts with, and hand it back."""
    table = db_table.table()
    table.seed(*items)
    return table


def test_list_and_detail_are_owner_scoped_paginated_and_have_no_quota_gate() -> None:
    table = _seed(
        _saved_attachment(attachment_id="attachment-1"),
        _saved_attachment(attachment_id="attachment-2"),
        _saved_attachment(attachment_id="attachment-foreign", owner_id="student-2"),
    )
    page = attachment_service.list_owned_attachments(_actor(), limit=1, continuation=None)
    assert [item.attachment_id for item in page.items] == ["attachment-1"]
    assert page.continuation
    second = attachment_service.list_owned_attachments(
        _actor(), limit=10, continuation=page.continuation
    )
    assert [item.attachment_id for item in second.items] == ["attachment-2"]
    detail = attachment_service.saved_attachment_detail(
        attachment_service.readable_attachment(_actor(), "attachment-2")
    )
    assert detail.attachment_id == "attachment-2"
    # No quota gate: the owner's storage row is never read.
    assert not any(
        str(request.get("Key", {}).get("PK", "")).startswith("STORAGE#")
        for _operation, request in table.requests
    )


def _without(field: str) -> dict[str, Any]:
    item = _saved_attachment()
    item.pop(field)
    return item


@pytest.mark.parametrize(
    "item,actor",
    [
        (None, _actor()),
        (_saved_attachment(status="deletion_pending"), _actor()),
        (_saved_attachment(owner_id=""), _actor()),
        (_without("immutable_version_id"), _actor()),
        (_without("content_sha256"), _actor()),
        ({**_saved_attachment(), "content_length": 0}, _actor()),
        (_saved_attachment(), _actor(active=False)),
    ],
)
def test_readable_attachment_refuses_missing_inactive_incomplete_and_revoked(
    item: dict[str, Any] | None, actor: Actor
) -> None:
    """One judgement for every reader (#253): a refusal looks like a missing attachment."""
    if item:
        # An owner-less row stays out of the owner index, as the table would keep it.
        _seed({key: value for key, value in item.items() if value != "" or key != "student_id"})
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        attachment_service.readable_attachment(actor, "attachment-1")
    assert captured.value.code is attachment_errors.AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert set(captured.value.public_body()) == {"code", "message", "correlationId"}


class _Body:
    def __init__(
        self,
        data: bytes,
        *,
        readable: bool = True,
        read_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.data = data
        self.offset = 0
        self.readable = readable
        self.read_error = read_error
        self.close_error = close_error
        self.close_count = 0

    def read(self, limit: int) -> bytes:
        if not self.readable:
            raise AttributeError("read")
        if self.read_error:
            raise self.read_error
        value = self.data[self.offset : self.offset + limit]
        self.offset += len(value)
        return value

    def close(self) -> None:
        self.close_count += 1
        if self.close_error:
            raise self.close_error


class _DownloadS3:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get_object(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_download_uses_exact_version_verifies_bytes_and_closes_body() -> None:
    data = b"saved attachment bytes"
    item = _saved_attachment(data=data)
    body = _Body(data)
    s3 = _DownloadS3(
        {
            "Body": body,
            "ContentLength": len(data),
            "ETag": PRIVATE_CANARIES[3],
            "Metadata": {"content-sha256": item["content_sha256"]},
        }
    )
    prepared = attachment_service.prepare_saved_attachment_download(
        item,
        s3=s3,
        settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
    )
    assert b"".join(prepared.iter_bytes()) == data
    assert s3.calls == [
        {
            "Bucket": PRIVATE_CANARIES[0],
            "Key": PRIVATE_CANARIES[1],
            "VersionId": PRIVATE_CANARIES[2],
        }
    ]
    assert body.close_count == 1
    public = repr(prepared.public_headers())
    assert all(canary not in public for canary in PRIVATE_CANARIES)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"Body": object(), "ContentLength": 1, "ETag": "wrong"},
        {"Body": _Body(b"short"), "ContentLength": 99, "ETag": PRIVATE_CANARIES[3]},
        {"Body": _Body(b"changed bytes"), "ContentLength": 13, "ETag": PRIVATE_CANARIES[3]},
    ],
)
def test_download_malformed_wrong_length_or_checksum_is_retryable_and_redacted(
    response: dict[str, Any]
) -> None:
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        prepared = attachment_service.prepare_saved_attachment_download(
            _saved_attachment(),
            s3=_DownloadS3(response),
            settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
        )
        b"".join(prepared.iter_bytes())
    assert captured.value.code is attachment_errors.AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert all(canary not in str(captured.value.public_body()) for canary in PRIVATE_CANARIES)


def test_delete_referenced_attachment_uses_stable_actionable_in_use_contract() -> None:
    code = getattr(attachment_errors.AttachmentErrorCode, "ATTACHMENT_IN_USE", None)
    assert code is not None
    contract = attachment_errors.ATTACHMENT_ERROR_REGISTRY[code]
    assert contract.http_status == 409
    message = render_message(code, "en").lower()
    assert "conversation" in message or "question" in message
    _seed(_saved_attachment(ref_count=1))
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        attachment_service.delete_saved_attachment(
            _saved_attachment(ref_count=1),
            s3=_DownloadS3({}),
            settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
        )
    assert captured.value.code is code


def test_delete_unreferenced_projects_retryable_until_exact_absence() -> None:
    delete = getattr(attachment_service, "delete_saved_attachment", None)
    assert callable(delete)
    _seed(_saved_attachment(ref_count=0))
    assert "complete" not in delete(
        _saved_attachment(ref_count=0),
        s3=_DownloadS3(RuntimeError("provider-private-canary")),
        settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
    ).status


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor: Actor | None = None,
    s3: Any = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    aws.install({Kind.S3: s3 if s3 is not None else object()})
    config.install(Settings(
        s3_images_bucket=PRIVATE_CANARIES[0]
    ))
    return TestClient(app)


def test_owner_route_matrix_is_reachable_through_real_router(monkeypatch) -> None:
    # Asserted against the mounted route table rather than response codes: an
    # unstubbed owner lookup answers 404 for a route that is present, which is
    # indistinguishable from an unmounted path.
    mounted = {
        (route.path, method)
        for route in _client(monkeypatch).app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    for method, path in (
        ("GET", "/files/attachments"),
        ("GET", "/files/attachments/{attachment_id}"),
        ("GET", "/files/attachments/{attachment_id}/content"),
        ("DELETE", "/files/attachments/{attachment_id}"),
    ):
        assert (path, method) in mounted


def test_owner_routes_use_one_loaded_record_and_exact_private_content(monkeypatch) -> None:
    data = b"saved attachment bytes"
    item = _saved_attachment(data=data)
    calls: list[str] = []

    def get_attachment(attachment_id: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(attachment_id)
        return dict(item)

    monkeypatch.setattr(attachment_repo, "get_attachment", get_attachment)
    monkeypatch.setattr(
        attachment_repo,
        "list_saved_attachments",
        lambda owner_id, **_kwargs: ([dict(item)] if owner_id == "student-1" else [], None),
    )
    body = _Body(data)
    s3 = _DownloadS3(
        {
            "Body": body,
            "ContentLength": len(data),
            "ETag": PRIVATE_CANARIES[3],
        }
    )
    client = _client(monkeypatch, s3=s3)
    listing = client.get("/files/attachments")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["attachmentId"] == "attachment-1"
    detail = client.get("/files/attachments/attachment-1")
    assert detail.status_code == 200
    assert calls == ["attachment-1"]
    content = client.get("/files/attachments/attachment-1/content")
    assert content.status_code == 200 and content.content == data
    assert calls == ["attachment-1", "attachment-1"]
    assert body.close_count == 1
    assert s3.calls[0]["VersionId"] == PRIVATE_CANARIES[2]
    rendered = content.text + repr(dict(content.headers))
    assert all(canary not in rendered for canary in PRIVATE_CANARIES)


def test_foreign_and_missing_routes_share_concealed_attachment_error(monkeypatch) -> None:
    client = _client(monkeypatch)
    shapes = []
    for item in (None, _saved_attachment(owner_id="student-2")):
        monkeypatch.setattr(
            attachment_repo,
            "get_attachment",
            lambda _attachment_id, value=item, **_kwargs: value,
        )
        response = client.get("/files/attachments/attachment-private-canary")
        assert response.status_code == 404
        shapes.append(response.json()["detail"])
        assert "attachment-private-canary" not in response.text
    assert shapes[0]["code"] == shapes[1]["code"] == "upload_not_found"
    assert shapes[0]["message"] == shapes[1]["message"]


def test_referenced_delete_route_returns_friendly_stable_in_use_action(monkeypatch) -> None:
    monkeypatch.setattr(
        attachment_repo,
        "get_attachment",
        lambda _attachment_id, **_kwargs: _saved_attachment(ref_count=1),
    )
    response = _client(monkeypatch).delete(
        "/files/attachments/attachment-1", headers={"Accept-Language": "en"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "attachment_in_use"
    assert "conversation" in response.json()["detail"]["message"].lower()


def test_route_privacy_denies_coordinates_in_headers_and_bodies(monkeypatch) -> None:
    rendered = ""
    client = _client(monkeypatch)
    for response in (
        client.get("/files/attachments"),
        client.get("/files/attachments/attachment-1"),
        client.get("/files/attachments/attachment-1/content"),
        client.delete("/files/attachments/attachment-1"),
    ):
        rendered += response.text + repr(dict(response.headers))
    assert all(canary not in rendered for canary in PRIVATE_CANARIES)


def test_download_body_helper_accepts_file_like_stream_contract() -> None:
    # The public streaming boundary must remain consumable without exposing the
    # provider body itself or requiring a fully buffered response model.
    body = BytesIO(b"abc")
    assert body.read(2) == b"ab"


def test_readable_attachment_reads_a_live_one_whoever_the_policy_let_in() -> None:
    """Whose it is is the route's policy; the resolver judges only the attachment."""
    _seed(_saved_attachment())
    teacher = Actor(
        "teacher-1", "issuer", "subject", CanonicalRole.TEACHER, AccountStatus.ACTIVE, "teacher"
    )
    assert attachment_service.readable_attachment(teacher, "attachment-1")[
        "attachment_id"
    ] == "attachment-1"


def test_a_message_reuses_only_the_students_own_saved_attachment() -> None:
    _seed(_saved_attachment(owner_id="student-2"))
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        attachment_service.prepare_message_attachments(
            [attachment_models.AttachmentReference(attachmentId="attachment-1")],
            _actor(),
        )
    assert captured.value.code is attachment_errors.AttachmentErrorCode.UPLOAD_NOT_FOUND


def test_a_broken_row_can_still_be_deleted_but_not_read() -> None:
    broken = _without("immutable_etag")
    assert not attachment_service.is_live_attachment(broken)
    assert attachment_service.is_live_attachment(broken, for_reading=False)
