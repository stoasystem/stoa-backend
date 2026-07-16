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


def test_gateway_intent_returns_only_opaque_contract(monkeypatch) -> None:
    def create(body, actor, **kwargs):
        assert actor.user_id == "student-1"
        return {
            "uploadId": "upload-1",
            "expiresAt": datetime(2026, 1, 1, tzinfo=UTC),
            "maxBytes": IMAGE_MAX_BYTES,
            "chunkBytes": 5 * 1024 * 1024,
            "acceptedTypes": ["image/png"],
            "status": "pending_upload",
        }

    monkeypatch.setattr(files, "create_upload_intent", create)
    response = _client(monkeypatch).post(
        "/files/intents",
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
        "expiresAt",
        "maxBytes",
        "chunkBytes",
        "acceptedTypes",
        "status",
    }
    serialized = str(response.json()).lower()
    assert all(value not in serialized for value in ("s3_key", "bucket", "provider", "private-canary"))


def test_complete_returns_validated_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        files,
        "complete_upload",
        lambda upload_id, part_count, actor, **kwargs: {
            "uploadId": upload_id,
            "status": "validated",
            "attachment": None,
        },
    )
    response = _client(monkeypatch).post("/files/upload-1/complete", json={"partCount": 1})
    assert response.status_code == 200
    assert response.json() == {"uploadId": "upload-1", "status": "validated", "attachment": None}


def test_missing_and_foreign_complete_have_same_safe_shape(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND,
            internal_detail="uploads/private-provider-canary",
        )

    monkeypatch.setattr(files, "complete_upload", missing)
    response = _client(monkeypatch).post(
        "/files/foreign-upload/complete", json={"partCount": 1}
    )
    assert response.status_code == 404
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert "private-provider-canary" not in response.text
    assert response.headers["X-Correlation-ID"] == response.json()["detail"]["correlationId"]


def test_legacy_presign_and_finalize_routes_are_absent(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.post("/files/presign", json={}).status_code in {404, 405}
    assert client.post("/files/upload-1/finalize").status_code in {404, 405}


def test_chunk_route_projects_no_provider_receipt(monkeypatch) -> None:
    async def put(upload_id, part_number, chunks, actor, **kwargs):
        async for _ in chunks:
            pass
        return {
            "uploadId": upload_id,
            "partNumber": part_number,
            "sizeBytes": 3,
            "checksumSha256": "0" * 64,
            "status": "accepted",
        }

    monkeypatch.setattr(files, "put_upload_chunk", put)
    response = _client(monkeypatch).put("/files/upload-1/chunks/1", content=b"abc")
    assert response.status_code == 200
    assert set(response.json()) == {
        "uploadId",
        "partNumber",
        "sizeBytes",
        "checksumSha256",
        "status",
    }
    assert all(value not in response.text.lower() for value in ("etag", "versionid", "uploadid-provider", "bucket"))


def test_issuance_dependency_failure_has_exact_safe_503(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
            internal_detail="provider staging-key multipart-id canary",
        )

    monkeypatch.setattr(files, "create_upload_intent", unavailable)
    response = _client(monkeypatch).post(
        "/files/intents",
        json={
            "purpose": "question_image",
            "filename": "work.png",
            "contentType": "image/png",
            "sizeBytes": 10,
        },
    )
    assert response.status_code == 503
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert "provider" not in response.text
