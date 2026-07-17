"""Plan 473-19 exact provider-absence and cleanup convergence contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from stoa.config import Settings
from stoa.db.repositories import attachment_repo
from stoa.jobs.upload_cleanup import cleanup_expired_uploads
from stoa.services.attachment_service import cleanup_upload_intent


NOW = datetime(2026, 7, 17, tzinfo=UTC)
NOW_EPOCH = int(NOW.timestamp())
PRIVATE_KEY = "staging/private/owner-coordinate-canary.png"
PRIVATE_UPLOAD_ID = "provider-upload-coordinate-canary"
PRIVATE_VERSION_ID = "provider-version-coordinate-canary"


def _candidate(
    upload_id: str = "opaque-upload",
    *,
    status: str = "invalid",
    expires_at: int = 1,
) -> dict[str, Any]:
    return {
        "PK": f"UPLOAD#{upload_id}",
        "SK": "META",
        "upload_id": upload_id,
        "owner_id": "student-content-canary",
        "status": status,
        "version": 1,
        "expires_at": expires_at,
        "staging_object_key": PRIVATE_KEY,
        "multipart_upload_id": PRIVATE_UPLOAD_ID,
    }


class StatefulProvider:
    """Provider fake whose mutations change listed state, not response fixtures."""

    def __init__(self) -> None:
        self.multipart_uploads: list[dict[str, str]] = []
        self.versions: list[dict[str, str]] = []
        self.abort_mode = "success"
        self.delete_mode = "success"
        self.multipart_page_size = 100
        self.version_page_size = 100
        self.repeat_multipart_marker = False
        self.malformed_version_marker = False
        self.abort_calls = 0
        self.delete_calls = 0
        self.list_multipart_calls = 0
        self.list_version_calls = 0

    def abort_multipart_upload(self, *, Bucket: str, Key: str, UploadId: str) -> dict:
        del Bucket
        self.abort_calls += 1
        if self.abort_mode != "noop":
            self.multipart_uploads = [
                value
                for value in self.multipart_uploads
                if not (value["Key"] == Key and value["UploadId"] == UploadId)
            ]
        if self.abort_mode == "commit_then_raise":
            raise RuntimeError("abort-private-provider-diagnostic-canary")
        return {}

    def list_multipart_uploads(self, **request: Any) -> dict[str, Any]:
        self.list_multipart_calls += 1
        start = int(request.get("KeyMarker", "0"))
        page = self.multipart_uploads[start : start + self.multipart_page_size]
        next_index = start + len(page)
        truncated = next_index < len(self.multipart_uploads)
        response: dict[str, Any] = {
            "Uploads": [dict(value) for value in page],
            "IsTruncated": truncated,
        }
        if truncated:
            marker = str(start if self.repeat_multipart_marker else next_index)
            response["NextKeyMarker"] = marker
            response["NextUploadIdMarker"] = marker
        return response

    def delete_object(self, *, Bucket: str, Key: str, VersionId: str) -> dict:
        del Bucket
        self.delete_calls += 1
        if self.delete_mode != "noop":
            self.versions = [
                value
                for value in self.versions
                if not (value["Key"] == Key and value["VersionId"] == VersionId)
            ]
        if self.delete_mode == "commit_then_raise":
            raise RuntimeError("delete-private-provider-diagnostic-canary")
        return {}

    def list_object_versions(self, **request: Any) -> dict[str, Any]:
        self.list_version_calls += 1
        start = int(request.get("KeyMarker", "0"))
        page = self.versions[start : start + self.version_page_size]
        next_index = start + len(page)
        truncated = next_index < len(self.versions)
        response: dict[str, Any] = {
            "Versions": [dict(value) for value in page],
            "DeleteMarkers": [],
            "IsTruncated": truncated,
        }
        if truncated:
            response["NextKeyMarker"] = None if self.malformed_version_marker else str(next_index)
            response["NextVersionIdMarker"] = str(next_index)
        return response


class StatefulCleanupRepository:
    """Versioned cleanup fake retaining progress, cursors, and PART rows."""

    def __init__(self, uploads: list[dict[str, Any]]) -> None:
        self.uploads = {value["upload_id"]: dict(value) for value in uploads}
        self.parts: dict[str, list[dict[str, Any]]] = {
            value["upload_id"]: [] for value in uploads
        }
        self.claims = 0

    def list_upload_cleanup_candidates(
        self, now_epoch: int, *, limit: int, exclusive_start_key=None
    ) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
        ordered = sorted(self.uploads.values(), key=lambda value: value["upload_id"])
        start = 0
        if exclusive_start_key:
            previous = str(exclusive_start_key["PK"]).removeprefix("UPLOAD#")
            start = next(
                (index + 1 for index, value in enumerate(ordered) if value["upload_id"] == previous),
                0,
            )
        page = ordered[start : start + limit]
        next_cursor = None
        if start + len(page) < len(ordered) and page:
            next_cursor = {"PK": page[-1]["PK"], "SK": "META"}
        # Deliberately model the pre-fix lease eligibility. The service must
        # independently refuse destructive work before the intent TTL.
        eligible = [
            dict(value)
            for value in page
            if value["status"] in {"invalid", "expired", "cleanup_pending"}
            or value.get("expires_at", 0) <= now_epoch
            or (
                value["status"] in {"issuing", "assembling", "promoting"}
                and value.get("operation_lease_expires_at", 0) <= now_epoch
            )
        ]
        return eligible, next_cursor

    def claim_upload_cleanup(self, upload_id, version, now_epoch, reason):
        value = self.uploads.get(upload_id)
        if not value or value["version"] != version:
            return None
        eligible = (
            value["status"] in {"invalid", "expired", "cleanup_pending"}
            or value.get("expires_at", 0) <= now_epoch
            or (
                value["status"] in {"issuing", "assembling", "promoting"}
                and value.get("operation_lease_expires_at", 0) <= now_epoch
            )
        )
        if not eligible:
            return None
        self.claims += 1
        value["status"] = "cleanup_pending"
        value["cleanup_reason"] = reason
        value["version"] += 1
        return dict(value)

    def get_upload_intent(self, upload_id):
        value = self.uploads.get(upload_id)
        return dict(value) if value else None

    def scan_durable_upload_references(self, *args, **kwargs):
        return False, None

    def advance_upload_cleanup_reference_scan(self, upload_id, version, cursor):
        return self._advance(upload_id, version, cleanup_reference_cursor=cursor)

    def block_upload_cleanup(self, upload_id, version):
        return self._advance(upload_id, version, status="cleanup_blocked")

    def defer_cleanup_reconciliation(
        self, upload_id, version, kind, cursor, *, mutation_attempted, pages
    ):
        value = self.uploads[upload_id]
        previous_mutations = int(value.get(f"cleanup_{kind}_mutation_attempts", 0))
        previous_pages = int(value.get(f"cleanup_{kind}_reconciliation_pages", 0))
        return self._advance(
            upload_id,
            version,
            **{
                f"cleanup_{kind}_cursor": cursor,
                f"cleanup_{kind}_mutation_attempts": previous_mutations
                + int(mutation_attempted),
                f"cleanup_{kind}_reconciliation_pages": previous_pages + pages,
            },
        )

    def scrub_upload_parts(self, upload_id, version, *, limit, exclusive_start_key=None):
        value = self.uploads[upload_id]
        if value["status"] != "cleanup_pending" or value["version"] != version:
            return None
        rows = self.parts[upload_id]
        selected = rows[:limit]
        del rows[: len(selected)]
        return len(selected), None

    def advance_cleanup_part_scrub(self, upload_id, version, cursor):
        return self._advance(upload_id, version, cleanup_part_cursor=cursor)

    def mark_cleanup_parts_absent(self, upload_id, version):
        return self._advance(upload_id, version, cleanup_parts_absent=True)

    def mark_cleanup_multipart_aborted(self, upload_id, version):
        return self._advance(upload_id, version, cleanup_multipart_aborted=True)

    def mark_cleanup_staging_deleted(self, upload_id, version):
        return self._advance(upload_id, version, cleanup_staging_deleted=True)

    def mark_cleanup_immutable_deleted(self, upload_id, version):
        return self._advance(upload_id, version, cleanup_immutable_deleted=True)

    def record_cleanup_staging_version(self, upload_id, version, version_id, etag):
        return self._advance(
            upload_id, version, staging_version_id=version_id, staging_etag=etag
        )

    def record_cleanup_immutable_version(self, upload_id, version, version_id, etag):
        return self._advance(
            upload_id, version, immutable_version_id=version_id, immutable_etag=etag
        )

    def complete_upload_cleanup(self, upload_id, version, cleaned_at):
        value = self.uploads[upload_id]
        required = (
            "cleanup_multipart_aborted",
            "cleanup_staging_deleted",
            "cleanup_immutable_deleted",
            "cleanup_parts_absent",
        )
        if (
            value["version"] != version
            or value["status"] != "cleanup_pending"
            or not all(value.get(field) for field in required)
            or self.parts[upload_id]
        ):
            return False
        value.update(status="cleanup_complete", cleaned_at=cleaned_at, version=version + 1)
        return True

    def _advance(self, upload_id, version, **changes):
        value = self.uploads[upload_id]
        if value["status"] != "cleanup_pending" or value["version"] != version:
            return False
        value.update(changes)
        value["version"] += 1
        return True


def _run_one(repository: StatefulCleanupRepository, provider: StatefulProvider) -> str:
    candidate = next(iter(repository.uploads.values()))
    return cleanup_upload_intent(
        dict(candidate),
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        now=NOW,
        reference_scan_limit=10,
        repository=repository,
    )


@pytest.mark.parametrize("mode", ["noop", "commit_then_raise"])
def test_multipart_abort_requires_listed_exact_absence(mode: str) -> None:
    repository = StatefulCleanupRepository([_candidate()])
    provider = StatefulProvider()
    provider.abort_mode = mode
    provider.multipart_uploads = [
        {"Key": PRIVATE_KEY, "UploadId": PRIVATE_UPLOAD_ID},
        {"Key": PRIVATE_KEY, "UploadId": "unrelated-provider-upload-canary"},
    ]

    outcome = _run_one(repository, provider)

    current = repository.uploads["opaque-upload"]
    if mode == "noop":
        assert outcome == "retryable"
        assert current.get("cleanup_multipart_aborted") is not True
    else:
        assert outcome in {"retryable", "deferred", "deleted"}
        assert current.get("cleanup_multipart_aborted") is True
    assert provider.list_multipart_calls >= 1
    assert any(value["UploadId"] == "unrelated-provider-upload-canary" for value in provider.multipart_uploads)


@pytest.mark.parametrize("mode", ["noop", "commit_then_raise"])
def test_version_delete_requires_full_exact_absence(mode: str) -> None:
    upload = _candidate()
    upload.pop("multipart_upload_id")
    upload["staging_version_id"] = PRIVATE_VERSION_ID
    repository = StatefulCleanupRepository([upload])
    provider = StatefulProvider()
    provider.delete_mode = mode
    provider.versions = [
        {"Key": PRIVATE_KEY, "VersionId": "unrelated-version-canary", "ETag": "unrelated-etag"},
        {"Key": PRIVATE_KEY, "VersionId": PRIVATE_VERSION_ID, "ETag": "exact-etag"},
    ]
    provider.version_page_size = 1

    outcome = _run_one(repository, provider)

    current = repository.uploads["opaque-upload"]
    if mode == "noop":
        assert outcome == "retryable"
        assert current.get("cleanup_staging_deleted") is not True
    else:
        assert outcome in {"retryable", "deferred", "deleted"}
        assert current.get("cleanup_staging_deleted") is True
    assert provider.list_version_calls >= (2 if mode == "noop" else 1)
    assert any(value["VersionId"] == "unrelated-version-canary" for value in provider.versions)


def test_malformed_or_repeating_pagination_is_incomplete_and_redacted() -> None:
    repository = StatefulCleanupRepository([_candidate()])
    provider = StatefulProvider()
    provider.abort_mode = "noop"
    provider.multipart_page_size = 1
    provider.repeat_multipart_marker = True
    provider.multipart_uploads = [
        {"Key": PRIVATE_KEY, "UploadId": "unrelated-provider-upload-canary"},
        {"Key": PRIVATE_KEY, "UploadId": PRIVATE_UPLOAD_ID},
    ]

    outcome = _run_one(repository, provider)

    assert outcome == "retryable"
    rendered = str(repository.uploads["opaque-upload"].get("cleanup_reason", ""))
    assert "provider-upload-coordinate-canary" not in rendered
    assert "private-provider-diagnostic-canary" not in rendered


def test_provider_reconciliation_continuation_resumes_after_page_budget() -> None:
    repository = StatefulCleanupRepository([_candidate()])
    provider = StatefulProvider()
    provider.abort_mode = "noop"
    provider.multipart_page_size = 1
    provider.multipart_uploads = [
        {"Key": PRIVATE_KEY, "UploadId": f"unrelated-upload-{index}"}
        for index in range(10)
    ] + [{"Key": PRIVATE_KEY, "UploadId": PRIVATE_UPLOAD_ID}]

    first = _run_one(repository, provider)
    after_first = repository.uploads["opaque-upload"]

    assert first == "deferred"
    assert after_first["cleanup_multipart_cursor"] == {
        "KeyMarker": "10",
        "UploadIdMarker": "10",
    }
    assert after_first["cleanup_multipart_mutation_attempts"] == 1
    assert after_first["cleanup_multipart_reconciliation_pages"] == 10

    second = _run_one(repository, provider)

    assert second == "retryable"
    assert repository.uploads["opaque-upload"].get("cleanup_multipart_aborted") is not True
    assert provider.abort_calls == 2


def test_operation_lease_expiry_before_intent_ttl_never_destroys() -> None:
    upload = _candidate(status="issuing", expires_at=NOW_EPOCH + 600)
    upload.update(operation_kind="staging_issuance", operation_lease_expires_at=NOW_EPOCH - 1)
    repository = StatefulCleanupRepository([upload])
    provider = StatefulProvider()
    provider.multipart_uploads = [{"Key": PRIVATE_KEY, "UploadId": PRIVATE_UPLOAD_ID}]

    outcome = _run_one(repository, provider)

    assert outcome == "skipped"
    assert repository.claims == 0
    assert provider.abort_calls == provider.delete_calls == 0


def test_stale_cleanup_generation_makes_zero_provider_calls() -> None:
    upload = _candidate()
    repository = StatefulCleanupRepository([upload])
    repository.uploads[upload["upload_id"]]["version"] += 1
    provider = StatefulProvider()

    outcome = cleanup_upload_intent(
        upload,
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        now=NOW,
        reference_scan_limit=10,
        repository=repository,
    )

    assert outcome == "skipped"
    assert provider.abort_calls == provider.delete_calls == 0


def test_terminal_cleanup_scrubs_every_part_before_completion() -> None:
    upload = _candidate()
    upload.pop("multipart_upload_id")
    upload.pop("staging_object_key")
    repository = StatefulCleanupRepository([upload])
    repository.parts[upload["upload_id"]] = [
        {"PK": "UPLOAD#opaque-upload", "SK": f"PART#{index:05d}", "expires_at": NOW_EPOCH}
        for index in range(1, 4)
    ]
    provider = StatefulProvider()

    outcomes = [_run_one(repository, provider) for _ in range(4)]

    assert repository.parts[upload["upload_id"]] == []
    assert repository.uploads[upload["upload_id"]]["status"] == "cleanup_complete"
    assert "deleted" in outcomes


class _PutRecordingTable:
    def __init__(self, *, intent_expires_at: int | None = None) -> None:
        self.item: dict[str, Any] | None = None
        self.intent_expires_at = intent_expires_at

    def get_item(self, **kwargs):
        del kwargs
        if self.intent_expires_at is None:
            return {}
        return {"Item": {"expires_at": self.intent_expires_at}}

    def put_item(self, **kwargs):
        self.item = kwargs["Item"]
        return {}


def test_part_rows_receive_lifecycle_ttl() -> None:
    parent_expiry = NOW_EPOCH + 600
    table = _PutRecordingTable(intent_expires_at=parent_expiry)

    attachment_repo.claim_upload_part(
        "opaque-upload",
        1,
        "a" * 64,
        3,
        "lease-owner",
        NOW_EPOCH,
        table=table,
    )

    assert table.item is not None
    assert table.item["expires_at"] == parent_expiry


class _EligibilityRecordingTable:
    def __init__(self) -> None:
        self.scan_request: dict[str, Any] | None = None

    def scan(self, **kwargs):
        self.scan_request = kwargs
        return {"Items": []}


def test_repository_candidate_policy_never_uses_operation_lease_as_ttl() -> None:
    table = _EligibilityRecordingTable()

    attachment_repo.list_upload_cleanup_candidates(NOW_EPOCH, limit=10, table=table)

    assert table.scan_request is not None
    assert "operation_lease_expires_at" not in table.scan_request["FilterExpression"]


def test_job_isolates_candidate_failure_and_preserves_continuation(monkeypatch) -> None:
    uploads = [_candidate(f"opaque-{index}") for index in range(3)]
    repository = StatefulCleanupRepository(uploads)
    visited: list[str] = []

    def isolated(candidate, **kwargs):
        visited.append(candidate["upload_id"])
        if candidate["upload_id"] == "opaque-0":
            raise RuntimeError("candidate-private-provider-diagnostic-canary")
        return "deleted"

    monkeypatch.setattr("stoa.jobs.upload_cleanup.cleanup_upload_intent", isolated)
    result = cleanup_expired_uploads(
        s3=StatefulProvider(),
        settings_obj=Settings(s3_images_bucket="private-bucket-canary"),
        now=NOW,
        batch_limit=2,
        page_limit=3,
        repository=repository,
    )

    assert visited == ["opaque-0", "opaque-1"]
    assert result.retryable == result.deleted == 1
    assert result.continuation_token is not None
    assert "private-provider-diagnostic-canary" not in str(result.public_dict())


def test_job_continuation_wraparound_visits_every_candidate(monkeypatch) -> None:
    uploads = [_candidate(f"opaque-{index}") for index in range(5)]
    repository = StatefulCleanupRepository(uploads)
    visited: list[str] = []

    def observed(candidate, **kwargs):
        visited.append(candidate["upload_id"])
        return "deferred"

    monkeypatch.setattr("stoa.jobs.upload_cleanup.cleanup_upload_intent", observed)
    token = None
    for _ in range(3):
        result = cleanup_expired_uploads(
            s3=StatefulProvider(),
            settings_obj=Settings(s3_images_bucket="private-bucket-canary"),
            now=NOW,
            batch_limit=2,
            page_limit=5,
            continuation_token=token,
            repository=repository,
        )
        token = result.continuation_token

    assert visited == ["opaque-0", "opaque-1", "opaque-2", "opaque-3", "opaque-4"]
    assert token is None

    wrapped = cleanup_expired_uploads(
        s3=StatefulProvider(),
        settings_obj=Settings(s3_images_bucket="private-bucket-canary"),
        now=NOW,
        batch_limit=2,
        page_limit=5,
        continuation_token=token,
        repository=repository,
    )
    assert wrapped.scanned == 2
    assert visited[-2:] == ["opaque-0", "opaque-1"]
