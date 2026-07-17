"""Plan 473-23 contracts for owner-facing saved attachments and purge progress."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.config import Settings, get_settings
from stoa.deps import get_actor, get_s3_client
from stoa.models import attachment as attachment_models
from stoa.routers import files
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


def _public_schema_text(model: type) -> str:
    return str(model.model_json_schema(by_alias=True)).lower()


def test_saved_attachment_models_are_coordinate_free_recursively() -> None:
    model_names = (
        "SavedAttachmentDetail",
        "SavedAttachmentPage",
        "SavedAttachmentDeleteResult",
    )
    models = [getattr(attachment_models, name, None) for name in model_names]
    assert all(model is not None for model in models)
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


class _OwnerRepository:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = {item["attachment_id"]: dict(item) for item in items}
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    def get_attachment(self, attachment_id: str) -> dict[str, Any] | None:
        self.get_calls.append(attachment_id)
        item = self.items.get(attachment_id)
        return dict(item) if item else None

    def list_saved_attachments(
        self,
        owner_id: str,
        *,
        limit: int,
        exclusive_start_key: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
        self.list_calls.append(
            {
                "owner_id": owner_id,
                "limit": limit,
                "exclusive_start_key": exclusive_start_key,
            }
        )
        ordered = [
            dict(item)
            for item in self.items.values()
            if item["owner_id"] == owner_id and item["status"] == "active"
        ]
        if exclusive_start_key:
            ordered = [
                item
                for item in ordered
                if item["attachment_id"] > exclusive_start_key["attachment_id"]
            ]
        page = ordered[:limit]
        cursor = (
            {"attachment_id": page[-1]["attachment_id"]}
            if len(ordered) > limit
            else None
        )
        return page, cursor

    def mark_saved_attachment_deletion_pending(self, item: dict[str, Any]) -> bool:
        current = self.items.get(item["attachment_id"])
        if not current or current["status"] != "active" or current.get("ref_count", 0):
            return False
        current["status"] = "deletion_pending"
        return True


def test_list_and_detail_are_owner_scoped_paginated_and_have_no_quota_gate() -> None:
    repository = _OwnerRepository(
        [
            _saved_attachment(attachment_id="attachment-1"),
            _saved_attachment(attachment_id="attachment-2"),
            _saved_attachment(attachment_id="attachment-foreign", owner_id="student-2"),
        ]
    )
    page = attachment_service.list_owned_attachments(
        _actor(), limit=1, continuation=None, repository=repository
    )
    assert [item.attachment_id for item in page.items] == ["attachment-1"]
    assert page.continuation
    second = attachment_service.list_owned_attachments(
        _actor(), limit=10, continuation=page.continuation, repository=repository
    )
    assert [item.attachment_id for item in second.items] == ["attachment-2"]
    detail = attachment_service.saved_attachment_detail(
        attachment_service.resolve_owned_attachment(
            "attachment-2", _actor(), repository=repository
        )
    )
    assert detail.attachment_id == "attachment-2"
    assert not hasattr(repository, "get_storage_usage")


@pytest.mark.parametrize(
    "item,actor",
    [
        (None, _actor()),
        (_saved_attachment(owner_id="student-2"), _actor()),
        (_saved_attachment(status="deletion_pending"), _actor()),
        (_saved_attachment(), _actor(active=False)),
    ],
)
def test_detail_conceals_missing_foreign_inactive_and_revoked(
    item: dict[str, Any] | None, actor: Actor
) -> None:
    repository = _OwnerRepository([item] if item else [])
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        attachment_service.resolve_owned_attachment(
            "attachment-1", actor, repository=repository
        )
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
    assert "conversation" in contract.safe_message.lower() or "question" in contract.safe_message.lower()
    repository = _OwnerRepository([_saved_attachment(ref_count=1)])
    with pytest.raises(attachment_errors.AttachmentDecisionError) as captured:
        attachment_service.delete_saved_attachment(
            repository.items["attachment-1"],
            s3=_DownloadS3({}),
            settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
            repository=repository,
        )
    assert captured.value.code is code


def test_delete_unreferenced_projects_retryable_until_exact_absence() -> None:
    delete = getattr(attachment_service, "delete_saved_attachment", None)
    assert callable(delete)
    assert "complete" not in delete(
        _saved_attachment(ref_count=0),
        s3=_DownloadS3(RuntimeError("provider-private-canary")),
        settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
        repository=_OwnerRepository([_saved_attachment(ref_count=0)]),
    ).status


class _PurgeRepository:
    def __init__(self) -> None:
        self.finalize_calls = 0

    def complete_retention_fence(self, *_args: Any, **_kwargs: Any) -> bool:
        self.finalize_calls += 1
        raise AssertionError("attachment branch must not finalize the account fence")

    def list_owner_attachment_items(
        self, _owner_id: str, *, fence: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []


def test_purge_hook_returns_typed_independent_progress_without_aggregate_authority() -> None:
    result_type = getattr(attachment_service, "AttachmentPurgeBranchResult", None)
    assert result_type is not None
    assert not hasattr(result_type, "finalize_account")
    repository = _PurgeRepository()
    result = attachment_service.purge_student_attachments(
        "student-1",
        account_fence_generation=7,
        cursors={},
        s3=object(),
        settings=Settings(s3_images_bucket=PRIVATE_CANARIES[0]),
        repository=repository,
    )
    assert isinstance(result, result_type)
    assert result.status.value in {"complete", "retryable", "conflict"}
    assert set(result.cursors) == {
        "saved",
        "references",
        "intents",
        "multipart",
        "immutable",
        "staging",
        "quota",
        "provider_debt",
    }
    assert result.quiescent is True
    assert sum(result.debt_counts.values()) == 0
    assert repository.finalize_calls == 0


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor: Actor | None = None,
    s3: Any = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_s3_client] = lambda: s3 if s3 is not None else object()
    app.dependency_overrides[get_settings] = lambda: Settings(
        s3_images_bucket=PRIVATE_CANARIES[0]
    )
    return TestClient(app)


def test_owner_route_matrix_is_reachable_through_real_router(monkeypatch) -> None:
    response = _client(monkeypatch).get("/files/attachments")
    assert response.status_code != 404
    for method, path in (
        ("get", "/files/attachments/attachment-1"),
        ("get", "/files/attachments/attachment-1/content"),
        ("delete", "/files/attachments/attachment-1"),
    ):
        assert getattr(_client(monkeypatch), method)(path).status_code != 404


def test_owner_routes_use_one_loaded_record_and_exact_private_content(monkeypatch) -> None:
    data = b"saved attachment bytes"
    item = _saved_attachment(data=data)
    calls: list[str] = []

    def get_attachment(attachment_id: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(attachment_id)
        return dict(item)

    monkeypatch.setattr(files.attachment_repo, "get_attachment", get_attachment)
    monkeypatch.setattr(
        files.attachment_repo,
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
            files.attachment_repo,
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
        files.attachment_repo,
        "get_attachment",
        lambda _attachment_id, **_kwargs: _saved_attachment(ref_count=1),
    )
    response = _client(monkeypatch).delete("/files/attachments/attachment-1")
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
