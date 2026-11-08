"""An upload's row state machine, from issuance to cleanup, on the real code paths (#252).

These used to run against repository doubles written for each test, which agreed with
whatever the test expected of them: a double that moved a row to `validated` on any
call proved nothing about the conditional update that has to. Here the upload rows
live in the shared DynamoDB double (`fakes.dynamodb.FakeTable`), reached through
`attachment_repo.get_table` exactly as `uploads._store` reaches the real table, and
S3 is `fakes.s3.MultipartS3`, which keeps multipart uploads, parts and object
versions. Calls go through the `uploads` entries and the sweep
(`jobs.upload_cleanup.cleanup_expired_uploads`).

A failure is injected into a double, never into the code under test: the table
refuses one chosen request (`_Table.fault`), or S3 raises, loses a response or
answers with a malformed coordinate. What a test asserts is what the table and the
bucket then hold, and what the caller was told.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import re
from typing import Any

from botocore.exceptions import ClientError
from PIL import Image
import pytest

from stoa.config import (
    DOCUMENT_MAX_BYTES,
    UPLOAD_INTENT_TTL_SECONDS,
    UPLOAD_ROW_RETENTION_SECONDS,
    Settings,
)
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.jobs import upload_cleanup
from stoa.jobs.upload_cleanup import cleanup_expired_uploads
from stoa.models.attachment import UploadIntentRequest, UploadPartUrlRequest, UploadPurpose
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import uploads
from stoa.services.attachment_service import UPLOAD_SPOOL_MEMORY_BYTES
from stoa.services.uploads import _store as upload_store
from fakes.dynamodb import FakeTable
from fakes.rekognition import FakeRekognition
from fakes.s3 import MIN_PART_BYTES, MultipartS3


OWNER = "student-1"
BUCKET = "images-bucket-canary"
SETTINGS = Settings(s3_images_bucket=BUCKET)
NOW = datetime(2026, 7, 16, tzinfo=UTC)
NOW_EPOCH = int(NOW.timestamp())
# Past every operation lease (120 s) and inside the usable window (1800 s).
AFTER_RESTART = NOW + timedelta(seconds=121)
CLEANUP_OWNER = "student-content-canary"

MALFORMED_PROVIDER_COORDINATES: list[object] = [None, False, True, 0, 1, [], {}, "", " \t"]


# ── Doubles ───────────────────────────────────────────────────────────────────


def _dynamodb_unavailable(message: str = "table-private-diagnostic-canary") -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "InternalServerError", "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": 500},
        },
        "UpdateItem",
    )


class _Table(FakeTable):
    """The shared table double, which raises whatever `fault` returns for a request.

    `fault(operation, request)` is asked before every point read, write and scan; it
    returns the exception the table answers with, or `None` to serve the request.
    """

    def __init__(self) -> None:
        super().__init__()
        self.fault: Callable[[str, dict[str, Any]], BaseException | None] = (
            lambda _operation, _request: None
        )

    def _serve(self, operation: str, request: dict[str, Any]) -> None:
        error = self.fault(operation, request)
        if error is not None:
            raise error

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self._serve("get_item", kwargs)
        return super().get_item(**kwargs)

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self._serve("update_item", kwargs)
        return super().update_item(**kwargs)

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self._serve("scan", kwargs)
        return super().scan(**kwargs)


def _once(
    matches: Callable[[str, dict[str, Any]], bool],
) -> Callable[[str, dict[str, Any]], BaseException | None]:
    """A fault for the first request `matches` picks, and for no other."""
    armed = [True]

    def fault(operation: str, request: dict[str, Any]) -> BaseException | None:
        if armed[0] and matches(operation, request):
            armed[0] = False
            return _dynamodb_unavailable()
        return None

    return fault


def _on(request: dict[str, Any], upload_id: str) -> bool:
    return (request.get("Key") or {}).get("PK") == f"UPLOAD#{upload_id}"


def _sets(request: dict[str, Any], attribute: str) -> bool:
    """Whether an update sets `attribute`, named directly or through a placeholder."""
    if attribute in (request.get("ExpressionAttributeNames") or {}).values():
        return True
    return re.search(rf"\b{attribute}\s*=", str(request.get("UpdateExpression") or "")) is not None


def _moves_to(request: dict[str, Any], status: str) -> bool:
    return (request.get("ExpressionAttributeValues") or {}).get(":target") == status


def _upload_write_setting(attribute: str) -> Callable[[str, dict[str, Any]], bool]:
    return lambda operation, request: operation == "update_item" and _sets(request, attribute)


class _S3(MultipartS3):
    """`MultipartS3`, plus what recovery and the sweep need from the bucket.

    `list_multipart_uploads` lists by prefix, as S3 does. `deletes` is every delete
    the code under test sent.
    """

    def __init__(self) -> None:
        super().__init__(BUCKET)
        self.deletes: list[tuple[str, str | None]] = []

    def list_multipart_uploads(self, **kwargs: Any) -> dict[str, Any]:
        prefix = str(kwargs.get("Prefix") or "")
        return {
            "Uploads": [
                {"Key": upload["Key"], "UploadId": upload_id}
                for upload_id, upload in self.uploads.items()
                if upload["Key"].startswith(prefix)
            ],
            "IsTruncated": False,
        }

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.deletes.append((kwargs["Key"], kwargs.get("VersionId")))
        return super().delete_object(**kwargs)

    # -- arranging a fixture ------------------------------------------------------

    def seed_object(self, key: str, data: bytes, metadata: dict[str, str] | None = None) -> str:
        """An object version already in the bucket; its version id."""
        return self._store(key, data, dict(metadata or {}))["VersionId"]

    def seed_multipart(self, key: str) -> str:
        """An unfinished multipart upload on `key`; its id."""
        return self.create_multipart_upload(Bucket=BUCKET, Key=key, ChecksumAlgorithm="SHA256")[
            "UploadId"
        ]

    def holds(self, key: str, version: str) -> bool:
        return (key, version) in self.objects

    def versions_of(self, key: str) -> list[str]:
        return [version for (stored, version) in self.objects if stored == key]

    def immutable_keys(self) -> list[str]:
        return [key for (key, _version) in self.objects if key.startswith("objects/")]


# ── Fixtures and helpers ──────────────────────────────────────────────────────


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> _Table:
    table = _Table()
    table.seed_active_account(OWNER)
    monkeypatch.setattr(attachment_repo, "get_table", lambda: table)
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
    return table


def _actor() -> Actor:
    return Actor(OWNER, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student")


def _row(table: FakeTable, upload_id: str) -> dict[str, Any]:
    return table.rows[(f"UPLOAD#{upload_id}", "META")]


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), (40, 90, 160)).save(output, "PNG")
    return output.getvalue()


def _request(
    data: bytes,
    *,
    filename: str = "work.png",
    content_type: str = "image/png",
    purpose: UploadPurpose = UploadPurpose.QUESTION_IMAGE,
) -> UploadIntentRequest:
    return UploadIntentRequest(
        purpose=purpose, filename=filename, contentType=content_type, sizeBytes=len(data)
    )


def _start(s3: _S3, data: bytes, *, now: datetime = NOW, **request: Any) -> dict[str, Any]:
    return uploads.start(_request(data, **request), _actor(), s3=s3, settings=SETTINGS, now=now)


def _put_parts(s3: _S3, upload_id: str, data: bytes, chunk_bytes: int) -> int:
    """Sign every part and put it on S3 the way the browser does; the part count."""
    parts = [data[start : start + chunk_bytes] for start in range(0, len(data), chunk_bytes)]
    for number, part in enumerate(parts, start=1):
        signed = uploads.sign_part(
            upload_id,
            number,
            UploadPartUrlRequest(sizeBytes=len(part), checksumSha256=hashlib.sha256(part).hexdigest()),
            _actor(),
            signer=s3,
            settings=SETTINGS,
            now=NOW,
        )
        assert s3.browser_put(signed["url"], signed["method"], signed["headers"], part) == 200
    return len(parts)


def _uploaded(s3: _S3, data: bytes, **request: Any) -> str:
    """An upload whose parts are all on S3, ready to complete."""
    intent = _start(s3, data, **request)
    _put_parts(s3, intent["uploadId"], data, intent["chunkBytes"])
    return intent["uploadId"]


def _complete(s3: _S3, upload_id: str, part_count: int = 1, *, now: datetime = NOW) -> dict[str, Any]:
    return uploads.complete(
        upload_id, part_count, _actor(), s3=s3, settings=SETTINGS, now=now, moderation=FakeRekognition()
    )


def _refused(call: Callable[[], object]) -> AttachmentErrorCode:
    with pytest.raises(AttachmentDecisionError) as refused:
        call()
    return refused.value.code


# ── Issuance ──────────────────────────────────────────────────────────────────


def test_gateway_issuance_is_owner_bound_opaque_and_multipart_private(table) -> None:
    s3 = _S3()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    result = _start(s3, b"0123456789", now=now)

    assert set(result) == {"uploadId", "expiresAt", "maxBytes", "chunkBytes", "acceptedTypes", "status"}
    assert result["chunkBytes"] == 5 * 1024 * 1024
    row = _row(table, result["uploadId"])
    assert row["owner_id"] == OWNER
    assert row["status"] == "pending_upload"
    # The usable window, not the table TTL: an issued upload has no `expires_at` (#250).
    assert row["usable_until"] == int(now.timestamp()) + UPLOAD_INTENT_TTL_SECONDS
    assert "expires_at" not in row
    # The multipart upload S3 opened is the one the row records, on the row's key.
    [(multipart_id, multipart)] = s3.uploads.items()
    assert row["multipart_upload_id"] == multipart_id
    assert multipart["Key"] == row["staging_object_key"]
    assert all(
        private not in str(result) for private in (row["staging_object_key"], multipart_id, BUCKET)
    )


def test_issuance_failure_is_service_unavailable_and_terminal(table) -> None:
    class RefusingS3(_S3):
        def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider-name-and-coordinate-canary")

    code = _refused(lambda: _start(RefusingS3(), b"0123456789"))

    assert code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    [row] = [row for (pk, _sk), row in table.rows.items() if pk.startswith("UPLOAD#")]
    assert row["status"] == "cleanup_pending"
    assert row["operation_kind"] == "staging_issuance"
    assert row["staging_object_key"]
    assert uploads.phase(row, NOW_EPOCH) is uploads.Phase.FAILED


@pytest.mark.parametrize(
    "response", [{}, *({"UploadId": value} for value in MALFORMED_PROVIDER_COORDINATES)]
)
def test_malformed_success_upload_id_retains_issuance_fence(table, response: dict) -> None:
    class MalformedSuccessS3(_S3):
        def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            return response

    code = _refused(lambda: _start(MalformedSuccessS3(), b"0123456789"))

    assert code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    [row] = [row for (pk, _sk), row in table.rows.items() if pk.startswith("UPLOAD#")]
    assert row["status"] == "cleanup_pending"
    assert row["operation_kind"] == "staging_issuance"
    assert row["operation_fence"]
    assert row["staging_object_key"]
    assert "multipart_upload_id" not in row


def test_issuing_lost_response_retains_exact_durable_cleanup_coordinate(table) -> None:
    """S3 opened the multipart upload but its answer was lost; cleanup still finds it."""

    class LostResponseS3(_S3):
        def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            super().create_multipart_upload(**kwargs)
            raise RuntimeError("provider-success-response-lost")

    s3 = LostResponseS3()

    code = _refused(lambda: _start(s3, b"0123456789"))

    assert code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    [row] = [row for (pk, _sk), row in table.rows.items() if pk.startswith("UPLOAD#")]
    [orphan] = s3.uploads.values()
    assert row["status"] == "cleanup_pending"
    assert row["operation_kind"] == "staging_issuance"
    assert row["staging_object_key"] == orphan["Key"]

    outcome = uploads.cleanup(dict(row), s3=s3, settings=SETTINGS, now=NOW, reference_scan_limit=100)

    assert outcome == "deleted"
    assert s3.uploads == {}


# ── Completion ────────────────────────────────────────────────────────────────


def test_gateway_completion_uses_only_contiguous_server_etags(table) -> None:
    """Assembly names each part by the ETag and checksum S3 gave it, in part order."""

    class RecordingS3(_S3):
        sent: list[dict[str, Any]] | None = None

        def complete_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            self.sent = list(kwargs["MultipartUpload"]["Parts"])
            return super().complete_multipart_upload(**kwargs)

    s3 = RecordingS3()
    data = b"a" * (MIN_PART_BYTES + 10)
    upload_id = _uploaded(
        s3,
        data,
        filename="notes.txt",
        content_type="text/plain",
        purpose=UploadPurpose.CONVERSATION_ATTACHMENT,
    )
    [held] = s3.uploads.values()
    expected = [
        {"PartNumber": number, "ETag": part["ETag"], "ChecksumSHA256": part["ChecksumSHA256"]}
        for number, part in sorted(held["parts"].items())
    ]

    result = _complete(s3, upload_id, 2)

    assert result == {"uploadId": upload_id, "status": "validated", "attachment": None}
    assert s3.sent == expected and [part["PartNumber"] for part in expected] == [1, 2]
    [immutable] = s3.immutable_keys()
    [version] = s3.versions_of(immutable)
    assert s3.objects[(immutable, version)]["data"] == data


# ── Validation and promotion ──────────────────────────────────────────────────

STAGING_KEY = "staging/private/document.txt"
STAGING_VERSION = "staging-version-exact"


def _seed_validating(
    table: FakeTable,
    size: int,
    *,
    max_bytes: int = DOCUMENT_MAX_BYTES,
    filename: str = "document.txt",
    declared_type: str = "text/plain",
) -> str:
    """A row whose staging object S3 has assembled, waiting to be validated."""
    upload_id = "upload-spool"
    table.seed(
        {
            **upload_store.upload_key(upload_id),
            "upload_id": upload_id,
            "owner_id": OWNER,
            "entity_type": "upload_intent",
            "status": "validating",
            "version": 4,
            "staging_object_key": STAGING_KEY,
            "staging_version_id": STAGING_VERSION,
            "original_filename": filename,
            "declared_type": declared_type,
            "expected_kind": "conversation_attachment",
            "expected_size": size,
            "max_bytes": max_bytes,
            "usable_until": NOW_EPOCH + UPLOAD_INTENT_TTL_SECONDS,
        }
    )
    return upload_id


class _StagingBodyS3(_S3):
    """The staging object's exact version reads back as `body`; any other is NoSuchVersion."""

    def __init__(self, body: object) -> None:
        super().__init__()
        self.body = body

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["Key"] != STAGING_KEY:
            return super().get_object(**kwargs)
        if kwargs.get("VersionId") != STAGING_VERSION:
            raise ClientError({"Error": {"Code": "NoSuchVersion", "Message": ""}}, "GetObject")
        return {"Body": self.body}


class _GeneratedBody:
    """A stream of `size` copies of one byte, made as it is read."""

    def __init__(self, size: int, byte: bytes = b"a") -> None:
        self.remaining = size
        self.byte = byte
        self.total_read = 0
        self.largest_read = 0
        self.close_count = 0

    def read(self, limit: int) -> bytes:
        self.largest_read = max(self.largest_read, limit)
        amount = min(limit, self.remaining)
        self.remaining -= amount
        self.total_read += amount
        return self.byte * amount

    def close(self) -> None:
        self.close_count += 1


class _ProviderBody:
    """A provider body over `data`; its read or close can be made to raise."""

    def __init__(
        self,
        data: bytes,
        *,
        read_exception: Exception | None = None,
        close_exception: Exception | None = None,
    ) -> None:
        self.data = data
        self.offset = 0
        self.read_exception = read_exception
        self.close_exception = close_exception
        self.close_count = 0

    def read(self, limit: int) -> bytes:
        if self.read_exception is not None:
            raise self.read_exception
        value = self.data[self.offset : self.offset + limit]
        self.offset += len(value)
        return value

    def close(self) -> None:
        self.close_count += 1
        if self.close_exception is not None:
            raise self.close_exception


class _MalformedProviderBody:
    """A body whose `read` or `close` is missing, not callable, or raises when looked up."""

    def __init__(self, *, read_shape: str, close_shape: str = "callable") -> None:
        self.read_shape = read_shape
        self.close_shape = close_shape
        self.close_count = 0

    def __getattribute__(self, name: str):
        if name in ("read", "close"):
            shape = object.__getattribute__(self, f"{name}_shape")
            if shape == "missing":
                raise AttributeError(name)
            if shape == "property_raises":
                raise RuntimeError(f"{name}-property-private-canary")
            if shape == "non_callable":
                return None
        return object.__getattribute__(self, name)

    def read(self, limit: int) -> bytes:
        return b""

    def close(self) -> None:
        self.close_count += 1


def test_fifty_mib_document_promotion_uses_bounded_spool_and_exact_version(table) -> None:
    body = _GeneratedBody(DOCUMENT_MAX_BYTES)
    s3 = _StagingBodyS3(body)
    upload_id = _seed_validating(table, DOCUMENT_MAX_BYTES)

    result = _complete(s3, upload_id)

    assert result["status"] == "validated"
    assert body.total_read == DOCUMENT_MAX_BYTES
    assert body.largest_read <= UPLOAD_SPOOL_MEMORY_BYTES
    assert body.close_count == 1
    row = _row(table, upload_id)
    [immutable] = s3.immutable_keys()
    [version] = s3.versions_of(immutable)
    assert row["status"] == "validated"
    assert row["immutable_object_key"] == immutable
    assert row["immutable_version_id"] == version
    assert len(s3.objects[(immutable, version)]["data"]) == DOCUMENT_MAX_BYTES
    assert row["content_sha256"] == hashlib.sha256(b"a" * DOCUMENT_MAX_BYTES).hexdigest()


def test_max_plus_one_is_rejected_after_exact_sentinel_read_and_no_promotion(table) -> None:
    body = _GeneratedBody(4096)
    s3 = _StagingBodyS3(body)
    upload_id = _seed_validating(table, 1024, max_bytes=1024)

    code = _refused(lambda: _complete(s3, upload_id))

    assert code is AttachmentErrorCode.UPLOAD_TOO_LARGE
    # One byte past the maximum is read, and no more of the object.
    assert body.total_read == 1025
    assert body.close_count == 1
    assert s3.immutable_keys() == []
    row = _row(table, upload_id)
    assert row["status"] == "invalid"
    assert row["validation_failure"] == "upload_too_large"


@pytest.mark.parametrize("read_shape", ["missing", "non_callable", "property_raises"])
def test_validation_non_readable_body_ownership_closes_once(table, read_shape: str) -> None:
    body = _MalformedProviderBody(read_shape=read_shape)
    upload_id = _seed_validating(table, 3, max_bytes=3)
    before = deepcopy(_row(table, upload_id))

    with pytest.raises(AttachmentDecisionError) as refused:
        _complete(_StagingBodyS3(body), upload_id)

    assert refused.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(refused.value)
    assert body.close_count == 1
    assert _row(table, upload_id) == before


@pytest.mark.parametrize("close_shape", ["missing", "non_callable", "property_raises"])
def test_validation_close_property_shape_preserves_primary_outcome(table, close_shape: str) -> None:
    """A body that cannot even be closed does not replace the outcome the read decided."""
    body = _MalformedProviderBody(read_shape="non_callable", close_shape=close_shape)
    upload_id = _seed_validating(table, 3, max_bytes=3)
    before = deepcopy(_row(table, upload_id))

    with pytest.raises(AttachmentDecisionError) as refused:
        _complete(_StagingBodyS3(body), upload_id)

    assert refused.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "private-canary" not in str(refused.value)
    assert _row(table, upload_id) == before


@pytest.mark.parametrize(
    "case,data,expected_size,max_bytes,expected_code",
    [
        ("length_mismatch", b"ab", 3, 3, AttachmentErrorCode.UPLOAD_INVALID),
        ("oversize", b"abcd", 3, 3, AttachmentErrorCode.UPLOAD_TOO_LARGE),
        ("read_exception", b"abc", 3, 3, AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE),
    ],
)
def test_validation_provider_body_closes_once_on_every_read_exit(
    table, case, data, expected_size, max_bytes, expected_code
) -> None:
    body = _ProviderBody(
        data,
        read_exception=RuntimeError("provider-read-private-canary") if case == "read_exception" else None,
    )
    upload_id = _seed_validating(table, expected_size, max_bytes=max_bytes)

    code = _refused(lambda: _complete(_StagingBodyS3(body), upload_id))

    assert code is expected_code
    assert body.close_count == 1


def test_validation_failure_and_close_exception_preserve_stable_error(table) -> None:
    """A PDF that is not one fails validation; a close that raises does not hide why."""
    body = _ProviderBody(b"abc", close_exception=RuntimeError("close-provider-private-canary"))
    upload_id = _seed_validating(
        table, 3, max_bytes=3, filename="document.pdf", declared_type="application/pdf"
    )

    with pytest.raises(AttachmentDecisionError) as refused:
        _complete(_StagingBodyS3(body), upload_id)

    assert refused.value.code is AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH
    assert "private-canary" not in str(refused.value)
    assert body.close_count == 1
    assert _row(table, upload_id)["status"] == "invalid"


# ── Crash and fence recovery ──────────────────────────────────────────────────


class _LateWorkerS3(_S3):
    """While recovery lists the bucket, the worker from before the restart writes late.

    `late_write` is that worker's write, made once, at the first listing after it is
    set; `late_result` is what the store answered it.
    """

    late_write: Callable[[], bool] | None = None
    late_result: bool | None = None

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        if self.late_write is not None:
            self.late_result, self.late_write = self.late_write(), None
        return super().list_object_versions(**kwargs)


def test_assembling_provider_success_repository_split_recovers_after_restart(table) -> None:
    """S3 assembled the object, the row never heard; a later completion finds that version.

    The restart takes the operation over under a new fence, so the worker from
    before it can no longer record anything, even with the row's version and fence.
    """
    data = _png()
    s3 = _LateWorkerS3()
    upload_id = _uploaded(s3, data)
    table.fault = _once(_upload_write_setting("staging_version_id"))

    assert _refused(lambda: _complete(s3, upload_id)) is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE

    row = deepcopy(_row(table, upload_id))
    assert row["status"] == "assembling"
    [assembled] = s3.versions_of(row["staging_object_key"])
    s3.late_write = lambda: upload_store.recover_staging_completion(
        upload_id,
        OWNER,
        int(row["version"]),
        operation_fence=row["operation_fence"],
        staging_version_id=assembled,
        staging_etag="late-etag",
    )

    recovered = _complete(s3, upload_id, now=AFTER_RESTART)

    assert recovered["status"] == "validated"
    assert s3.late_result is False
    assert s3.completions_sent == 1
    # The version recovered is the one S3 assembled: it was promoted, then deleted.
    assert (row["staging_object_key"], assembled) in s3.deletes
    [immutable] = s3.immutable_keys()
    [version] = s3.versions_of(immutable)
    assert s3.objects[(immutable, version)]["data"] == data
    assert _row(table, upload_id)["status"] == "validated"


def test_promotion_provider_success_repository_split_recovers_exact_version(table) -> None:
    """S3 stored the promoted object, the row never heard; recovery records that exact version.

    As for assembly, the worker from before the restart is fenced out of the row.
    """
    s3 = _LateWorkerS3()
    upload_id = _uploaded(s3, _png())
    table.fault = _once(_upload_write_setting("immutable_version_id"))

    assert _refused(lambda: _complete(s3, upload_id)) is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE

    promoting = deepcopy(_row(table, upload_id))
    assert promoting["status"] == "promoting"
    s3.late_write = lambda: upload_store.record_immutable_version(
        upload_id,
        OWNER,
        int(promoting["version"]),
        operation_fence=promoting["operation_fence"],
        immutable_version_id="late-version",
        immutable_etag="late-etag",
        validated_at=NOW.isoformat(),
    )

    recovered = _complete(s3, upload_id, now=AFTER_RESTART)

    assert recovered["status"] == "validated"
    assert s3.late_result is False
    row = _row(table, upload_id)
    # One put only: a second promotion would have written a second immutable key.
    [immutable] = s3.immutable_keys()
    [version] = s3.versions_of(immutable)
    assert row["immutable_object_key"] == promoting["immutable_object_key"] == immutable
    assert row["immutable_version_id"] == version
    # Recovery pays the staging debt as the uninterrupted promotion does (#267).
    assert not s3.holds(promoting["staging_object_key"], promoting["staging_version_id"])
    assert (promoting["staging_object_key"], promoting["staging_version_id"]) in s3.deletes
    assert not any(
        name in row
        for name in (
            "staging_cleanup_status",
            "staging_object_key",
            "staging_version_id",
            "staging_etag",
            "multipart_upload_id",
        )
    )


@pytest.mark.parametrize(
    "field,value",
    [("VersionId", value) for value in MALFORMED_PROVIDER_COORDINATES]
    + [("ETag", value) for value in MALFORMED_PROVIDER_COORDINATES],
)
def test_malformed_success_staging_coordinate_retains_assembly_fence(
    table, field: str, value: object
) -> None:
    class MalformedCompletionS3(_S3):
        def complete_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            result = super().complete_multipart_upload(**kwargs)
            result[field] = value
            return result

    s3 = MalformedCompletionS3()
    upload_id = _uploaded(s3, _png())
    multipart_id = _row(table, upload_id)["multipart_upload_id"]

    assert _refused(lambda: _complete(s3, upload_id)) is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE

    row = _row(table, upload_id)
    assert row["status"] == "assembling"
    assert row["operation_kind"] == "staging_assembly"
    assert row["operation_fence"]
    assert row["multipart_upload_id"] == multipart_id
    assert "staging_version_id" not in row


@pytest.mark.parametrize(
    "field,value",
    [("VersionId", value) for value in MALFORMED_PROVIDER_COORDINATES]
    + [("ETag", value) for value in MALFORMED_PROVIDER_COORDINATES],
)
def test_malformed_success_immutable_coordinate_retains_promotion_fence(
    table, field: str, value: object
) -> None:
    class MalformedPromotionS3(_S3):
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            result = super().put_object(**kwargs)
            result[field] = value
            return result

    s3 = MalformedPromotionS3()
    upload_id = _uploaded(s3, _png())

    assert _refused(lambda: _complete(s3, upload_id)) is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE

    row = _row(table, upload_id)
    assert row["status"] == "promoting"
    assert row["operation_kind"] == "immutable_promotion"
    assert row["operation_fence"]
    assert row["immutable_object_key"]
    assert row["content_sha256"]
    assert "immutable_version_id" not in row


def test_malformed_success_coordinates_recover_after_restart_without_new_mutation(table) -> None:
    class LostCoordinatesS3(_S3):
        def complete_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
            result = super().complete_multipart_upload(**kwargs)
            return {**result, "VersionId": " "}

    s3 = LostCoordinatesS3()
    upload_id = _uploaded(s3, _png())

    _refused(lambda: _complete(s3, upload_id))
    assert _row(table, upload_id)["status"] == "assembling"

    recovered = _complete(s3, upload_id, now=AFTER_RESTART)

    assert recovered["status"] == "validated"
    assert s3.completions_sent == 1


@pytest.mark.parametrize("coordinate", MALFORMED_PROVIDER_COORDINATES)
def test_repository_coordinate_guards_run_before_fence_removal(table, coordinate: object) -> None:
    """A malformed coordinate is refused before any write, on a row that would take the write.

    Each row is in exactly the state, version and fence its transition expects, so a
    missing guard would move it on and drop its fence; the valid call at the end
    shows each row would indeed have accepted the write.
    """

    def seed(upload_id: str, status: str) -> None:
        table.seed(
            {
                **upload_store.upload_key(upload_id),
                "upload_id": upload_id,
                "owner_id": OWNER,
                "status": status,
                "version": 1,
                "operation_kind": "any",
                "operation_fence": "fence",
                "usable_until": NOW_EPOCH + UPLOAD_INTENT_TTL_SECONDS,
            }
        )

    seed("issuing", "issuing")
    seed("assembling", "assembling")
    seed("promoting", "promoting")
    validated_at = NOW.isoformat()

    def record_multipart(value: object) -> bool:
        return upload_store.record_staging_multipart(
            "issuing", OWNER, 1, operation_fence="fence", multipart_upload_id=value
        )

    def record_staging(version_id: object, etag: object) -> bool:
        return upload_store.recover_staging_completion(
            "assembling", OWNER, 1, operation_fence="fence", staging_version_id=version_id, staging_etag=etag
        )

    def record_immutable(version_id: object, etag: object) -> bool:
        return upload_store.record_immutable_version(
            "promoting",
            OWNER,
            1,
            operation_fence="fence",
            immutable_version_id=version_id,
            immutable_etag=etag,
            validated_at=validated_at,
        )

    before = deepcopy(table.rows)
    for call in (
        lambda: record_multipart(coordinate),
        lambda: record_staging(coordinate, "etag"),
        lambda: record_staging("version", coordinate),
        lambda: record_immutable(coordinate, "etag"),
        lambda: record_immutable("version", coordinate),
    ):
        with pytest.raises(attachment_repo.AttachmentRepositoryConflict) as refused:
            call()
        assert refused.value.category == "invalid_provider_coordinate"

    assert table.calls["update_item"] == 0
    assert table.rows == before
    assert record_multipart("mp-1") and record_staging("version", "etag") and record_immutable("version", "etag")
    assert all("operation_fence" not in _row(table, name) for name in ("issuing", "assembling", "promoting"))


# ── Cleanup ───────────────────────────────────────────────────────────────────


def _staging_key(upload_id: str) -> str:
    return f"staging/private/{upload_id}-key-canary.png"


def _seed_cleanup(
    table: FakeTable,
    s3: _S3,
    upload_id: str,
    status: str,
    *,
    usable_until: int = 1,
    staged: bool = True,
    **fields: Any,
) -> dict[str, Any]:
    """An upload row for the sweep; with `staged`, its staging copy is in the bucket."""
    row: dict[str, Any] = {
        **upload_store.upload_key(upload_id),
        "upload_id": upload_id,
        "owner_id": CLEANUP_OWNER,
        "entity_type": "upload_intent",
        "staging_object_key": _staging_key(upload_id),
        "status": status,
        "version": 1,
        "usable_until": usable_until,
        **fields,
    }
    if staged:
        row["staging_version_id"] = s3.seed_object(
            _staging_key(upload_id), b"abc", {"upload-id": upload_id}
        )
    table.seed(row)
    return row


def _seed_attachment(table: FakeTable, attachment_id: str, **fields: Any) -> None:
    """A durable attachment row, of the kind that holds an upload's bytes."""
    table.seed(
        {
            **attachment_repo.attachment_key(attachment_id),
            "attachment_id": attachment_id,
            "entity_type": "attachment",
            "owner_id": CLEANUP_OWNER,
            "status": "active",
            **fields,
        }
    )


def _sweep(s3: _S3, **kwargs: Any) -> upload_cleanup.CleanupSummary:
    return cleanup_expired_uploads(s3=s3, settings_obj=SETTINGS, now=NOW, **kwargs)


def test_cleanup_is_bounded_idempotent_and_never_deletes_active_or_durable_uploads(table) -> None:
    s3 = _S3()
    expired = _seed_cleanup(table, s3, "expired", "validated")
    invalid = _seed_cleanup(table, s3, "invalid", "invalid", usable_until=2_000_000_000)
    durable = _seed_cleanup(table, s3, "durable", "expired")
    active = _seed_cleanup(table, s3, "active", "validated", usable_until=2_000_000_000)
    _seed_cleanup(table, s3, "consumed", "consumed")
    _seed_attachment(table, "attachment-durable", source_upload_id="durable")

    result = _sweep(s3, batch_limit=3, page_limit=9)

    assert result.scanned == result.claimed == 3
    assert result.deleted == 2 and result.protected == 1
    assert not s3.holds(expired["staging_object_key"], expired["staging_version_id"])
    assert not s3.holds(invalid["staging_object_key"], invalid["staging_version_id"])
    assert s3.holds(durable["staging_object_key"], durable["staging_version_id"])
    assert s3.holds(active["staging_object_key"], active["staging_version_id"])

    repeated = _sweep(s3)

    assert repeated.deleted == 0 and repeated.scanned == 0
    assert s3.holds(durable["staging_object_key"], durable["staging_version_id"])
    assert _row(table, "durable")["status"] == "cleanup_blocked"
    # An ended row's TTL counts from the sweep's clock, not the wall clock (#269).
    assert _row(table, "durable")["expires_at"] == NOW_EPOCH + UPLOAD_ROW_RETENTION_SECONDS
    assert _row(table, "expired")["expires_at"] == NOW_EPOCH + UPLOAD_ROW_RETENTION_SECONDS
    assert _row(table, "active")["status"] == "validated"
    assert _row(table, "consumed")["status"] == "consumed"


def test_validated_cleanup_deletes_staging_and_immutable_exact_versions_before_complete(table) -> None:
    s3 = _S3()
    immutable_key = "objects/private/both-key"
    immutable_version = s3.seed_object(immutable_key, b"abc")
    newer_unrelated = s3.seed_object(immutable_key, b"other")
    upload = _seed_cleanup(
        table,
        s3,
        "both",
        "validated",
        immutable_object_key=immutable_key,
        immutable_version_id=immutable_version,
        immutable_etag="immutable-etag-old",
        content_sha256="a" * 64,
        content_length=3,
    )

    result = _sweep(s3)

    assert result.deleted == 1
    assert not s3.holds(upload["staging_object_key"], upload["staging_version_id"])
    assert not s3.holds(immutable_key, immutable_version)
    assert s3.holds(immutable_key, newer_unrelated)
    row = _row(table, "both")
    assert row["status"] == "cleanup_complete"
    assert row["cleaned_at"] == NOW.isoformat()
    assert row["expires_at"] == NOW_EPOCH + UPLOAD_ROW_RETENTION_SECONDS
    assert not any(
        name in row
        for name in (
            "staging_object_key",
            "staging_version_id",
            "multipart_upload_id",
            "immutable_object_key",
            "immutable_version_id",
            "operation_fence",
            "operation_lease_expires_at",
        )
    )


def test_stale_operation_cleanup_recovers_exact_targets_and_preserves_unrelated(table) -> None:
    """Each interrupted operation is cleaned by its exact coordinate, and only that."""
    s3 = _S3()
    stale = {"operation_lease_expires_at": 1}
    issuing = _seed_cleanup(
        table, s3, "issuing", "issuing", staged=False,
        operation_kind="staging_issuance", operation_fence="issuance-fence", **stale,
    )
    unfinished = s3.seed_multipart(issuing["staging_object_key"])
    unrelated_multipart = s3.seed_multipart(issuing["staging_object_key"] + "-other")

    assembling = _seed_cleanup(
        table, s3, "assembling", "assembling", staged=False,
        operation_kind="staging_assembly", operation_fence="assembly-fence",
        expected_size=3, multipart_upload_id="completed-upload", **stale,
    )
    assembled = s3.seed_object(assembling["staging_object_key"], b"abc", {"upload-id": "assembling"})
    newer_staging = s3.seed_object(assembling["staging_object_key"], b"abcd", {"upload-id": "other"})

    promoting = _seed_cleanup(
        table, s3, "promoting", "promoting",
        operation_kind="immutable_promotion", operation_fence="promotion-fence",
        immutable_object_key="objects/private/promotion-key",
        content_sha256="b" * 64, content_length=3, **stale,
    )
    promoted = s3.seed_object(promoting["immutable_object_key"], b"abc", {"content-sha256": "b" * 64})
    newer_immutable = s3.seed_object(
        promoting["immutable_object_key"], b"abc", {"content-sha256": "c" * 64}
    )

    result = _sweep(s3)

    assert result.deleted == 3
    assert unfinished not in s3.uploads
    assert unrelated_multipart in s3.uploads
    assert not s3.holds(assembling["staging_object_key"], assembled)
    assert s3.holds(assembling["staging_object_key"], newer_staging)
    assert not s3.holds(promoting["staging_object_key"], promoting["staging_version_id"])
    assert not s3.holds(promoting["immutable_object_key"], promoted)
    assert s3.holds(promoting["immutable_object_key"], newer_immutable)
    assert {_row(table, name)["status"] for name in ("issuing", "assembling", "promoting")} == {
        "cleanup_complete"
    }


def test_exact_immutable_durable_reference_blocks_all_cleanup_provider_mutations(table) -> None:
    """An attachment holding the exact immutable version protects the upload, by key and version."""
    s3 = _S3()
    immutable_key = "objects/private/protected"
    immutable_version = s3.seed_object(immutable_key, b"abc")
    upload = _seed_cleanup(
        table, s3, "tuple-protected", "validated",
        immutable_object_key=immutable_key, immutable_version_id=immutable_version,
    )
    _seed_attachment(
        table, "attachment-other-source",
        source_upload_id="another-upload",
        immutable_object_key=immutable_key,
        immutable_version_id=immutable_version,
    )
    held = deepcopy(s3.objects)

    result = _sweep(s3)

    assert result.protected == 1
    assert s3.objects == held and s3.deletes == []
    assert s3.holds(upload["staging_object_key"], upload["staging_version_id"])
    assert _row(table, "tuple-protected")["status"] == "cleanup_blocked"


class _FailingDeleteS3(_S3):
    """Every delete raises and deletes nothing, until `failing` is turned off."""

    failing = True

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.failing:
            raise RuntimeError("provider payload key-canary")
        return super().delete_object(**kwargs)


def test_cleanup_delete_failure_stays_unusable_retryable_and_redacted(table) -> None:
    s3 = _FailingDeleteS3()
    upload = _seed_cleanup(table, s3, "retry", "invalid")

    failed = _sweep(s3)

    assert failed.retryable == 1
    assert _row(table, "retry")["status"] == "cleanup_pending"
    assert uploads.status("retry", CLEANUP_OWNER, now=NOW) is uploads.Phase.FAILED
    assert s3.holds(upload["staging_object_key"], upload["staging_version_id"])
    serialized = str(failed.public_dict())
    assert "retry-key-canary" not in serialized
    assert CLEANUP_OWNER not in serialized

    s3.failing = False
    retried = _sweep(s3)

    assert retried.deleted == 1
    assert _row(table, "retry")["status"] == "cleanup_complete"
    assert not s3.holds(upload["staging_object_key"], upload["staging_version_id"])


def test_no_false_cleanup_complete_when_assembly_version_is_unproven(table) -> None:
    """A staging version that is not this upload's is neither deleted nor taken as absence."""
    s3 = _S3()
    upload = _seed_cleanup(
        table, s3, "unproven-assembly", "assembling", staged=False,
        operation_kind="staging_assembly", operation_fence="assembly-fence-canary",
        operation_lease_expires_at=1, expected_size=3,
        multipart_upload_id="completed-multipart-canary",
    )
    unverified = s3.seed_object(
        upload["staging_object_key"], b"abcd", {"upload-id": "different-upload-canary"}
    )

    result = _sweep(s3)

    assert result.retryable == 1
    row = _row(table, "unproven-assembly")
    assert row["status"] == "cleanup_pending"
    assert row["operation_kind"] == "staging_assembly"
    assert row["operation_fence"] == "assembly-fence-canary"
    assert row.get("cleanup_staging_deleted") is not True
    assert s3.holds(upload["staging_object_key"], unverified)
    assert s3.deletes == []


FIRST = "first-private-candidate-canary"
LATER = "later-private-candidate-canary"
DIAGNOSTIC = "first-private-diagnostic-canary"


def _first_table_fault(stage: str) -> Callable[[str, dict[str, Any]], BaseException | None]:
    """The table refuses, every time, one kind of request about the first candidate."""

    def matches(operation: str, request: dict[str, Any]) -> bool:
        if stage == "repository_scan":
            values = request.get("ExpressionAttributeValues") or {}
            return operation == "scan" and values.get(":upload_id") == FIRST
        if not _on(request, FIRST):
            return False
        if stage == "repository_get":
            return operation == "get_item"
        if operation != "update_item":
            return False
        if stage == "repository_claim":
            return _sets(request, "cleanup_reason")
        if stage == "repository_progress":
            return _sets(request, "cleanup_multipart_aborted")
        return _moves_to(request, "cleanup_complete")

    return lambda operation, request: (
        _dynamodb_unavailable(DIAGNOSTIC) if matches(operation, request) else None
    )


class _FirstCandidateS3(_S3):
    """S3, failing at `stage` for the first candidate's keys only."""

    def __init__(self, stage: str) -> None:
        super().__init__()
        self.stage = stage

    def _first(self, key: str) -> bool:
        return key == _staging_key(FIRST)

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        if self._first(kwargs["Prefix"]):
            if self.stage == "list_versions_failure":
                raise RuntimeError(f"provider-list-key-{DIAGNOSTIC}")
            if self.stage == "list_versions_malformed":
                return {"Versions": [None]}
        return super().list_object_versions(**kwargs)

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if self._first(kwargs["Key"]):
            if self.stage == "head_failure":
                raise RuntimeError(f"provider-head-version-{DIAGNOSTIC}")
            if self.stage == "head_malformed":
                return []  # type: ignore[return-value]
        return super().head_object(**kwargs)

    def abort_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        if self.stage == "abort_failure" and self._first(kwargs["Key"]):
            raise RuntimeError(f"provider-abort-upload-{DIAGNOSTIC}")
        return super().abort_multipart_upload(**kwargs)

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.stage == "delete_failure" and self._first(kwargs["Key"]):
            raise RuntimeError(f"provider-delete-version-{DIAGNOSTIC}")
        return super().delete_object(**kwargs)


@pytest.mark.parametrize(
    "failure_stage",
    [
        "repository_get",
        "repository_claim",
        "repository_scan",
        "repository_progress",
        "repository_complete",
        "list_versions_failure",
        "list_versions_malformed",
        "head_failure",
        "head_malformed",
        "abort_failure",
        "delete_failure",
    ],
)
def test_cleanup_batch_candidate_isolation_continues_after_first_failure(
    table, failure_stage: str, caplog
) -> None:
    s3 = _FirstCandidateS3(failure_stage)
    if failure_stage.startswith(("list_versions", "head")):
        _seed_cleanup(
            table, s3, FIRST, "assembling", staged=False,
            operation_kind="staging_assembly", operation_fence="first-private-fence-canary",
            operation_lease_expires_at=1, expected_size=3,
            multipart_upload_id="first-private-multipart-canary",
        )
        s3.seed_object(_staging_key(FIRST), b"abc", {"upload-id": FIRST})
    elif failure_stage == "abort_failure":
        _seed_cleanup(
            table, s3, FIRST, "invalid", staged=False,
            multipart_upload_id=s3.seed_multipart(_staging_key(FIRST)),
        )
    else:
        _seed_cleanup(table, s3, FIRST, "invalid")
    later = _seed_cleanup(table, s3, LATER, "invalid")
    if failure_stage.startswith("repository"):
        table.fault = _first_table_fault(failure_stage)

    result = _sweep(s3)

    assert result.scanned == result.claimed == 2
    assert result.retryable == result.deleted == 1
    assert _row(table, FIRST)["status"] in {"invalid", "cleanup_pending"}
    assert _row(table, LATER)["status"] == "cleanup_complete"
    assert not s3.holds(later["staging_object_key"], later["staging_version_id"])

    repeated = _sweep(s3)

    assert repeated.retryable == 1 and repeated.deleted == 0
    assert s3.deletes.count((later["staging_object_key"], later["staging_version_id"])) == 1
    rendered = str(result.public_dict()) + str(repeated.public_dict()) + caplog.text
    assert "private-candidate-canary" not in rendered
    assert "private-diagnostic-canary" not in rendered
    assert "provider" not in rendered


def test_cleanup_batch_unexpected_candidate_isolation_keeps_opaque_continuation(table, caplog) -> None:
    """An error no layer expected, on one candidate, costs that candidate only."""
    s3 = _S3()
    for index in range(3):
        _seed_cleanup(table, s3, f"candidate-private-{index}", "invalid")
    table.fault = lambda operation, request: (
        ValueError("unexpected-owner-key-provider-coordinate-private-canary")
        if operation == "update_item" and _on(request, "candidate-private-0")
        else None
    )

    result = _sweep(s3, batch_limit=2)

    assert result.scanned == result.claimed == 2
    assert result.retryable == result.deleted == 1
    assert _row(table, "candidate-private-0")["status"] == "invalid"
    assert _row(table, "candidate-private-1")["status"] == "cleanup_complete"
    # Not reached this run: the continuation resumes after the last candidate it took.
    assert _row(table, "candidate-private-2")["status"] == "invalid"
    assert upload_cleanup._decode_cursor(result.continuation_token) == upload_store.upload_key(
        "candidate-private-1"
    )
    rendered = str(result.public_dict()) + caplog.text
    assert "candidate-private" not in rendered
    assert "provider-coordinate-private-canary" not in rendered


def test_cleanup_batch_global_candidate_listing_failure_is_not_empty_success(table) -> None:
    table.fault = lambda operation, request: (
        _dynamodb_unavailable("global-table-provider-private-canary")
        if operation == "scan" and (request.get("ExpressionAttributeValues") or {}).get(":upload")
        else None
    )

    with pytest.raises(ClientError, match="global-table-provider-private-canary"):
        _sweep(_S3())


def test_cleanup_repository_split_after_exact_delete_retries_without_reviving_upload(table) -> None:
    """S3 deleted the staging copy but the row never heard; the next run carries on."""
    s3 = _S3()
    immutable_key = "objects/private/delete-split"
    immutable_version = s3.seed_object(immutable_key, b"abc")
    upload = _seed_cleanup(
        table, s3, "delete-split", "invalid",
        immutable_object_key=immutable_key, immutable_version_id=immutable_version,
    )
    table.fault = _once(_upload_write_setting("cleanup_staging_deleted"))

    first = _sweep(s3)

    assert first.retryable == 1
    row = _row(table, "delete-split")
    assert row["status"] == "cleanup_pending"
    assert row["cleanup_multipart_aborted"] is True
    assert not s3.holds(upload["staging_object_key"], upload["staging_version_id"])
    assert uploads.status("delete-split", CLEANUP_OWNER, now=NOW) is uploads.Phase.FAILED

    second = _sweep(s3)

    assert second.deleted == 1
    assert _row(table, "delete-split")["status"] == "cleanup_complete"
    assert s3.deletes.count((immutable_key, immutable_version)) == 1
    assert not s3.holds(immutable_key, immutable_version)


def test_an_issuance_still_in_flight_is_not_cleanup_eligible(table) -> None:
    """An issuing upload inside its usable window is not swept, whatever its lease says."""
    s3 = _S3()
    active = _seed_cleanup(
        table, s3, "active-issuing", "issuing", staged=False,
        usable_until=NOW_EPOCH + UPLOAD_INTENT_TTL_SECONDS,
        operation_kind="staging_issuance", operation_fence="active-fence",
        operation_lease_expires_at=NOW_EPOCH + 120,
    )
    multipart = s3.seed_multipart(active["staging_object_key"])

    result = _sweep(s3)

    assert result.scanned == result.claimed == result.deleted == 0
    assert _row(table, "active-issuing")["status"] == "issuing"
    assert multipart in s3.uploads
    assert s3.deletes == []


class _SweepDuringPromotionS3(_S3):
    """The sweep runs at `sweep_at` while the promoting worker's put to `objects/` is in flight.

    The put lands once the sweep is done, as a provider write already sent does: no
    fence stops it. `sweep` is what that sweep reported.
    """

    def __init__(self, sweep_at: datetime) -> None:
        super().__init__()
        self.sweep_at = sweep_at
        self.sweep: upload_cleanup.CleanupSummary | None = None

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.sweep is None and str(kwargs["Key"]).startswith("objects/"):
            self.sweep = cleanup_expired_uploads(s3=self, settings_obj=SETTINGS, now=self.sweep_at)
        return super().put_object(**kwargs)


def test_a_promotion_whose_lease_outlives_the_usable_window_is_not_swept_under_it(table) -> None:
    """#268: a completion late in the usable window holds a lease past its end.

    The sweep at that moment must leave the row to the worker: had it claimed the
    row, it would find no immutable object yet, report the upload clean, and the
    worker's put would then leave an object no row records.
    """
    usable_until = NOW + timedelta(seconds=UPLOAD_INTENT_TTL_SECONDS)
    completed_at = usable_until - timedelta(seconds=10)
    s3 = _SweepDuringPromotionS3(sweep_at=usable_until + timedelta(seconds=30))
    upload_id = _uploaded(s3, _png())

    result = _complete(s3, upload_id, now=completed_at)

    assert s3.sweep is not None and s3.sweep.claimed == 0
    assert result["status"] == "validated"
    row = _row(table, upload_id)
    [immutable] = s3.immutable_keys()
    assert row["immutable_object_key"] == immutable
    assert s3.versions_of(immutable) == [row["immutable_version_id"]]


def test_a_lapsed_lease_past_the_usable_window_is_swept(table) -> None:
    """The lease only defers the sweep: once it lapses, the abandoned promotion is cleaned."""
    s3 = _S3()
    _seed_cleanup(
        table, s3, "lapsed", "promoting",
        operation_kind="immutable_promotion", operation_fence="lapsed-fence",
        operation_lease_expires_at=NOW_EPOCH,
        immutable_object_key="objects/private/lapsed-key",
        content_sha256="d" * 64, content_length=3,
    )

    result = _sweep(s3)

    assert result.claimed == result.deleted == 1
    assert _row(table, "lapsed")["status"] == "cleanup_complete"


def test_cleanup_rejects_invalid_cursor_without_touching_the_table(table) -> None:
    s3 = _S3()
    _seed_cleanup(table, s3, "invalid-cursor", "invalid")
    before = deepcopy(table.rows)

    result = _sweep(s3, continuation_token="raw-object-key-canary")

    assert result.invalid_continuation == 1
    assert table.rows == before
    assert table.calls["scan"] == 0 and table.calls["update_item"] == 0
