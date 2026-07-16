from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import IMAGE_MAX_BYTES, Settings, get_settings
from stoa.deps import get_actor, get_s3_client
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.routers import files


def _actor(user_id: str = "student-1") -> Actor:
    return Actor(
        user_id, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student"
    )


def _client(monkeypatch, *, actor: Actor | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_settings] = lambda: Settings(s3_images_bucket="images-bucket")
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_s3_client] = lambda: object()
    return TestClient(app)


def test_presign_returns_only_opaque_post_contract(monkeypatch) -> None:
    def create(body, actor, **kwargs):
        assert actor.user_id == "student-1"
        return {
            "uploadId": "upload-1",
            "url": "https://uploads.invalid",
            "fields": {"key": "private-canary"},
            "expiresAt": datetime(2026, 1, 1, tzinfo=UTC),
            "maxBytes": IMAGE_MAX_BYTES,
            "acceptedTypes": ["image/png"],
            "status": "pending_upload",
        }

    monkeypatch.setattr(files, "create_upload_intent", create)
    response = _client(monkeypatch).post(
        "/files/presign",
        json={
            "purpose": "question_image",
            "filename": "work.png",
            "contentType": "image/png",
            "sizeBytes": 10,
        },
    )
    assert response.status_code == 200
    assert set(response.json()) == {
        "uploadId",
        "url",
        "fields",
        "expiresAt",
        "maxBytes",
        "acceptedTypes",
        "status",
    }
    assert "s3_key" not in str(response.json()).lower()


def test_finalize_returns_validated_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        files,
        "finalize_upload",
        lambda upload_id, actor, **kwargs: {
            "uploadId": upload_id,
            "status": "validated",
            "attachment": None,
        },
    )
    response = _client(monkeypatch).post("/files/upload-1/finalize")
    assert response.status_code == 200
    assert response.json() == {"uploadId": "upload-1", "status": "validated", "attachment": None}


def test_missing_and_foreign_finalize_have_same_safe_shape(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND,
            internal_detail="uploads/private-provider-canary",
        )

    monkeypatch.setattr(files, "finalize_upload", missing)
    response = _client(monkeypatch).post("/files/foreign-upload/finalize")
    assert response.status_code == 404
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert "private-provider-canary" not in response.text
    assert response.headers["X-Correlation-ID"] == response.json()["detail"]["correlationId"]
