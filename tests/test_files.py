from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.config import IMAGE_MAX_BYTES, Settings, get_settings
from stoa.deps import get_actor, get_s3_client
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.routers import files
from stoa.services import attachment_service
from stoa.db.repositories import attachment_repo


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
    assert response.headers["Retry-After"] == "30"


def _gateway_upload(status: str = "pending_upload") -> dict:
    item = {
        "upload_id": "upload-1",
        "owner_id": "student-1",
        "status": status,
        "version": 1,
        "expires_at": 2_000_000_000,
        "part_count": 1,
        "expected_size": 3,
        "max_bytes": 10,
        "original_filename": "work.txt",
        "declared_type": "text/plain",
        "staging_object_key": "private-stage-key-canary",
        "multipart_upload_id": "private-multipart-canary",
    }
    if status == "validating":
        item["staging_version_id"] = "private-version-canary"
    if status in {"assembling", "promoting"}:
        item.update(
            operation_kind=(
                "staging_assembly" if status == "assembling" else "immutable_promotion"
            ),
            operation_fence="private-fence-canary",
            operation_lease_expires_at=1,
        )
    if status == "promoting":
        item.update(
            immutable_object_key="private-immutable-key-canary",
            content_sha256="a" * 64,
            content_length=3,
        )
    return item


class _GatewayRepository:
    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.item = _gateway_upload(
            {
                "validation_read": "validating",
                "staging_recovery_lookup": "assembling",
                "promotion_recovery_lookup": "promoting",
            }.get(stage, "pending_upload")
        )

    def _fail(self, stage: str):
        if self.stage == stage:
            raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")
        if self.stage == f"{stage}_generic":
            raise RuntimeError("table-client-owner-key-provider-canary")

    def get_upload_intent(self, upload_id):
        self._fail("initial_lookup")
        return dict(self.item)

    def list_upload_parts(self, upload_id):
        self._fail("part_listing")
        return [
            {
                "part_number": 1,
                "status": "completed",
                "provider_etag": "private-etag-canary",
                "provider_checksum": "private-checksum-canary",
                "content_length": 3,
            }
        ]

    def claim_staging_assembly(self, *args, **kwargs):
        self._fail("assembly_claim")
        return True

    def recover_staging_completion(self, *args, **kwargs):
        self._fail("completion_persist")
        return True

    def claim_stale_upload_operation(self, *args, **kwargs):
        self._fail("recovery_claim")
        self.item["version"] += 1
        self.item["operation_fence"] = "replacement-fence"
        return dict(self.item)

    def claim_upload_part(self, *args, **kwargs):
        self._fail("chunk_claim")
        if self.stage == "replay_poll":
            return {"status": "uploading", "lease_owner": "other-worker", "attempt": 1}
        return {"status": "uploading", "lease_owner": args[4], "attempt": 2}

    def get_upload_part(self, *args, **kwargs):
        self._fail("replay_poll")
        return None


class _GatewayS3:
    def __init__(self, stage: str) -> None:
        self.stage = stage

    def complete_multipart_upload(self, **kwargs):
        if self.stage == "provider_completion":
            raise RuntimeError("S3 owner key version provider-canary")
        if self.stage == "malformed_provider_completion":
            return []
        if self.stage == "empty_coordinate_completion":
            return {"VersionId": " ", "ETag": "private-etag-canary"}
        return {"VersionId": "private-version-canary", "ETag": "private-etag-canary"}

    def list_object_versions(self, **kwargs):
        if self.stage in {"staging_recovery_lookup", "promotion_recovery_lookup"}:
            raise RuntimeError("provider recovery coordinate canary")
        return {"Versions": []}

    def get_object(self, **kwargs):
        if self.stage == "validation_read":
            raise RuntimeError("provider body key canary")
        return {"Body": object()}

    def list_parts(self, **kwargs):
        if self.stage == "provider_reconciliation":
            raise RuntimeError("provider part ledger canary")
        if self.stage == "malformed_provider_reconciliation":
            return {"Parts": [None]}
        return {"Parts": []}


@pytest.mark.parametrize(
    "stage",
    [
        "initial_lookup",
        "initial_lookup_generic",
        "part_listing",
        "assembly_claim",
        "provider_completion",
        "malformed_provider_completion",
        "empty_coordinate_completion",
        "completion_persist",
        "validation_read",
        "staging_recovery_lookup",
        "promotion_recovery_lookup",
        "recovery_claim",
    ],
)
def test_complete_gateway_dependency_matrix_is_one_redacted_safe_503(
    monkeypatch, stage: str
) -> None:
    repository = _GatewayRepository(stage)
    s3 = _GatewayS3(stage)

    def complete(upload_id, part_count, actor, **kwargs):
        return attachment_service.complete_upload(
            upload_id,
            part_count,
            actor,
            s3=s3,
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            now=datetime(2026, 7, 16, tzinfo=UTC),
            repository=repository,
        )

    monkeypatch.setattr(files, "complete_upload", complete)
    response = _client(monkeypatch).post("/files/upload-1/complete", json={"partCount": 1})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert response.headers["Retry-After"] == "30"
    rendered = response.text + str(response.headers)
    for canary in (
        "student-1",
        "private-stage-key-canary",
        "private-multipart-canary",
        "private-version-canary",
        "private-bucket-canary",
        "provider-canary",
        "dependency_failure",
    ):
        assert canary not in rendered


@pytest.mark.parametrize(
    "stage",
    [
        "chunk_claim",
        "replay_poll",
        "provider_reconciliation",
        "malformed_provider_reconciliation",
    ],
)
def test_chunk_gateway_dependency_matrix_is_one_redacted_safe_503(
    monkeypatch, stage: str
) -> None:
    repository = _GatewayRepository(stage)
    s3 = _GatewayS3(stage)

    async def no_sleep(_seconds):
        return None

    async def put(upload_id, part_number, chunks, actor, **kwargs):
        return await attachment_service.put_upload_chunk(
            upload_id,
            part_number,
            chunks,
            actor,
            s3=s3,
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            now=datetime(2026, 7, 16, tzinfo=UTC),
            repository=repository,
        )

    monkeypatch.setattr(attachment_service.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(files, "put_upload_chunk", put)
    response = _client(monkeypatch).put("/files/upload-1/chunks/1", content=b"abc")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_service_unavailable"
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert response.headers["Retry-After"] == "30"
    assert all(
        canary not in response.text
        for canary in (
            "student-1",
            "private-stage-key-canary",
            "private-multipart-canary",
            "provider",
            "dependency_failure",
        )
    )


def test_conditional_foreign_or_stale_gateway_state_stays_concealed_404(
    monkeypatch,
) -> None:
    repository = _GatewayRepository("conditional_lookup")

    def get_upload_intent(_upload_id):
        raise attachment_repo.AttachmentRepositoryConflict("conditional_conflict")

    repository.get_upload_intent = get_upload_intent

    def complete(upload_id, part_count, actor, **kwargs):
        return attachment_service.complete_upload(
            upload_id,
            part_count,
            actor,
            s3=_GatewayS3("none"),
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            repository=repository,
        )

    monkeypatch.setattr(files, "complete_upload", complete)
    response = _client(monkeypatch).post(
        "/files/foreign-or-stale-canary/complete", json={"partCount": 1}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "upload_not_found"
    assert set(response.json()["detail"]) == {"code", "message", "correlationId"}
    assert "foreign-or-stale-canary" not in response.text
    assert "conditional_conflict" not in response.text
    assert "Retry-After" not in response.headers
