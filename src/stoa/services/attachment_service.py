"""Attachments: the durable files a message or reply carries, and their retention.

An attachment is what a ready upload becomes when a message or a reply spends
it (`uploads.consume_operation` rides in that write). This module owns the
attachment rows and their references, downloads, quota and deletion, and the
strict parsers every S3 answer is read through, which `uploads` uses too.
The upload itself, from issuance to cleanup, is the `uploads` package's.

An attachment leaves by one of two actions, each on one row and safe to run
again (#636): `delete_attachment` deletes one file, `release_reference` lets go
of one reference and deletes the file with its last one. Neither checks a
fence; the conditional writes on the rows keep them safe. Cleaning one upload
is `uploads.cleanup`'s.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import logging
from tempfile import SpooledTemporaryFile
from typing import Any, Sequence
from urllib.parse import quote
from uuid import uuid4

from stoa.config import (
    FREE_STORAGE_BYTES,
    MESSAGE_IMAGES_MAX_BYTES,
    MODEL_IMAGE_MAX_BYTES,
    PAID_STORAGE_BYTES,
    Settings,
)
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, attachment_repo, upload_code_repo
from stoa.models.attachment import (
    AttachmentReference,
    AttachmentStatus,
    AttachmentSummary,
    SavedAttachmentDeleteResult,
    SavedAttachmentDeleteStatus,
    SavedAttachmentDetail,
    SavedAttachmentPage,
    UploadPurpose,
)
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor
from stoa.services.ai_service import PromptImage
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file
from stoa.services.document_extraction_service import (
    MAX_EXTRACTED_CHARACTERS,
    DocumentExtractionFailure,
)
from stoa.services.document_parser_worker import parse_document_isolated

logger = logging.getLogger(__name__)

# Bounds on one exact S3 read or listing, shared with `uploads`.
UPLOAD_SPOOL_MEMORY_BYTES = 1024 * 1024
CLEANUP_RECONCILIATION_MAX_PAGES = 10
CLEANUP_RECONCILIATION_MAX_ITEMS = 10_000


# Attached to a conversation message, these go to the model as images.
MESSAGE_IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})


class RetentionDisposition(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE_RETRYABLE = "incomplete_retryable"
    CONFLICT = "conflict"
    CONCEALED_MISSING = "concealed_missing"


class RetentionStage(StrEnum):
    FENCED = "fenced"
    REFERENCES_RELEASING = "references_releasing"
    OBJECT_DELETION_PENDING = "object_deletion_pending"
    OBJECT_ABSENCE_PROVEN = "object_absence_proven"
    QUOTA_FINALIZE_PENDING = "quota_finalize_pending"
    COMPLETE = "complete"
    RETRYABLE = "retryable"
    CONFLICT = "conflict"


class RetentionResult(dict[str, int]):
    """Typed retention outcome with legacy informational count mapping."""

    disposition: RetentionDisposition
    stage: RetentionStage

    def __init__(
        self,
        disposition: RetentionDisposition,
        stage: RetentionStage,
        *,
        released: int = 0,
        deleted: int = 0,
    ) -> None:
        super().__init__(released=released, deleted=deleted)
        self.disposition = disposition
        self.stage = stage


class LeaveOutcome(StrEnum):
    """Where one of the leave actions left its row."""

    # The row is gone: the file deleted, or the reference let go of (and, with
    # the last one, the file deleted too).
    DONE = "done"
    # The file is still referenced; nothing was changed.
    IN_USE = "in_use"
    # A step did not finish; running the action again carries on from there.
    RETRYABLE = "retryable"


class AttachmentPurgeBranchStatus(StrEnum):
    COMPLETE = "complete"
    RETRYABLE = "retryable"
    CONFLICT = "conflict"


PURGE_CURSOR_CATEGORIES = (
    "saved",
    "references",
    "intents",
    "multipart",
    "immutable",
    "staging",
    "quota",
    "provider_debt",
)


class AttachmentPurgeBranchResult(RetentionResult):
    """Attachment-only account-purge progress; never aggregate account closure."""

    status: AttachmentPurgeBranchStatus
    cursors: dict[str, Any]
    debt_counts: dict[str, int]
    quiescent: bool

    def __init__(
        self,
        status: AttachmentPurgeBranchStatus,
        *,
        cursors: dict[str, Any] | None = None,
        debt_counts: dict[str, int] | None = None,
        quiescent: bool = False,
        released: int = 0,
        deleted: int = 0,
    ) -> None:
        disposition = {
            AttachmentPurgeBranchStatus.COMPLETE: RetentionDisposition.COMPLETE,
            AttachmentPurgeBranchStatus.RETRYABLE: RetentionDisposition.INCOMPLETE_RETRYABLE,
            AttachmentPurgeBranchStatus.CONFLICT: RetentionDisposition.CONFLICT,
        }[status]
        stage = (
            RetentionStage.COMPLETE
            if status is AttachmentPurgeBranchStatus.COMPLETE
            else RetentionStage.RETRYABLE
            if status is AttachmentPurgeBranchStatus.RETRYABLE
            else RetentionStage.CONFLICT
        )
        super().__init__(disposition, stage, released=released, deleted=deleted)
        self.status = status
        supplied = cursors or {}
        self.cursors = {name: supplied.get(name) for name in PURGE_CURSOR_CATEGORIES}
        supplied_debt = debt_counts or {}
        self.debt_counts = {
            name: int(supplied_debt.get(name, 0)) for name in PURGE_CURSOR_CATEGORIES
        }
        self.quiescent = quiescent


@dataclass(slots=True)
class PreparedSavedAttachmentDownload:
    """Verified private bytes plus only safe public response metadata."""

    spool: Any
    filename: str
    media_type: str
    content_length: int

    def iter_bytes(self):
        try:
            while chunk := self.spool.read(UPLOAD_SPOOL_MEMORY_BYTES):
                yield chunk
        finally:
            self.spool.close()

    def public_headers(self) -> dict[str, str]:
        return {
            "Content-Length": str(self.content_length),
            "Content-Disposition": safe_attachment_content_disposition(self.filename),
        }


def _list_owner_account_attachment_items(
    owner_id: str, fence: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Read every attachment-owned account row, including non-GSI upload debt."""
    return attachment_repo.list_owner_attachment_items(
        owner_id, entity_types=None, fence=fence
    )


def _gateway_call(
    operation, *, conflict_code=AttachmentErrorCode.UPLOAD_NOT_FOUND
):
    """Keep repository/provider diagnostics behind one closed upload boundary."""
    try:
        return operation()
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "dependency_failure":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        if exc.category == "chunk_conflict":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT
            ) from None
        raise AttachmentDecisionError(conflict_code) from None
    except Exception as exc:
        # The caller only ever sees "temporarily unavailable", so without this the
        # operator has no way to tell a provider outage from a contract error.
        logger.error(
            "upload_gateway_failed error_class=%s message=%s",
            type(exc).__name__,
            _safe_gateway_detail(exc),
        )
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None


def _safe_gateway_detail(exc: Exception) -> str:
    """Report the provider's own error code without echoing private coordinates."""
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return str(error.get("Code") or "unknown")
    return type(exc).__name__


def _provider_mapping(operation) -> dict[str, Any]:
    response = _gateway_call(operation)
    if not isinstance(response, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return response


def _required_provider_coordinate(response: dict[str, Any], field: str) -> str:
    """Accept only an exact non-blank provider coordinate without coercion."""
    value = response.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _positive_provider_integer(value: Any) -> int:
    """Parse an exact positive integer without accepting bools or string coercion."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _canonical_sha256(value: Any) -> str:
    """Accept only a canonical lowercase SHA-256 hex digest."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _provider_sha256(value: Any, *, expected_hex: str | None = None) -> str:
    """Validate one canonical provider base64 SHA-256 acknowledgement."""
    if not isinstance(value, str) or not value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None
    if len(decoded) != hashlib.sha256().digest_size:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if base64.b64encode(decoded).decode("ascii") != value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if expected_hex is not None and decoded.hex() != _canonical_sha256(expected_hex):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _provider_truncation(value: Any) -> bool:
    if not isinstance(value, bool):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _close_provider_body(body: Any) -> bool:
    """Release one provider response body without replacing the primary outcome."""
    try:
        close = getattr(body, "close", None)
    except Exception:
        return False
    if not callable(close):
        return False
    try:
        close()
    except Exception:
        # Provider cleanup is best-effort and must not replace the stable decision.
        return False
    return True


def attachment_storage_limit(
    effective_plan: str,
    *,
    settings: Settings | None = None,
) -> int:
    """Return the admission-only byte limit for one effective product plan."""
    paid = effective_plan in {"student", "teacher_supported", "online_classroom"}
    if settings is not None:
        return (
            settings.paid_attachment_storage_bytes
            if paid
            else settings.free_attachment_storage_bytes
        )
    return PAID_STORAGE_BYTES if paid else FREE_STORAGE_BYTES


def storage_limit_for_entitlement(effective_plan: str) -> int:
    """Compatibility wrapper for callers that use the locked default limits."""
    return attachment_storage_limit(effective_plan)


def _cleanup_cursor_pair(
    cursor: Any, first: str, second: str
) -> tuple[str, str] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, dict) or set(cursor) != {first, second}:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return (
        _required_provider_coordinate(cursor, first),
        _required_provider_coordinate(cursor, second),
    )


def _exact_version_absence(
    s3: Any,
    settings: Settings,
    key: str,
    version_id: str,
    *,
    cursor: Any = None,
) -> tuple[bool, dict[str, str] | None, int]:
    """Prove one exact version absent across versions and delete markers."""
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Prefix": key,
        "MaxKeys": 1000,
    }
    previous = _cleanup_cursor_pair(cursor, "KeyMarker", "VersionIdMarker")
    if previous:
        request["KeyMarker"], request["VersionIdMarker"] = previous
    item_count = 0
    for page in range(1, CLEANUP_RECONCILIATION_MAX_PAGES + 1):
        response = _provider_mapping(lambda: s3.list_object_versions(**request))
        versions = response.get("Versions", [])
        delete_markers = response.get("DeleteMarkers", [])
        if (
            not isinstance(versions, list)
            or any(not isinstance(value, dict) for value in versions)
            or not isinstance(delete_markers, list)
            or any(not isinstance(value, dict) for value in delete_markers)
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        for value in [*versions, *delete_markers]:
            item_count += 1
            if item_count > CLEANUP_RECONCILIATION_MAX_ITEMS:
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
            listed_key = _required_provider_coordinate(value, "Key")
            listed_version = _required_provider_coordinate(value, "VersionId")
            if listed_key == key and listed_version == version_id:
                return False, None, page
        for value in versions:
            _required_provider_coordinate(value, "ETag")
        if not _provider_truncation(response.get("IsTruncated", False)):
            return True, None, page
        markers = (
            _required_provider_coordinate(response, "NextKeyMarker"),
            _required_provider_coordinate(response, "NextVersionIdMarker"),
        )
        if markers == previous:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous = markers
        request["KeyMarker"], request["VersionIdMarker"] = markers
    assert previous is not None
    return False, {"KeyMarker": previous[0], "VersionIdMarker": previous[1]}, page


def is_live_attachment(item: object, *, for_reading: bool = True) -> bool:
    """Whether a stored row is a live attachment: active and owned.

    For reading it must also name every immutable field its bytes are read and
    checked by (`IMMUTABLE_OBJECT_FIELDS`); a row without them is refused, not
    read. Deleting one needs only the first two, so a broken row can still go.
    """
    if not isinstance(item, Mapping) or item.get("status") != AttachmentStatus.ACTIVE:
        return False
    owner_id = item.get("owner_id")
    if not isinstance(owner_id, str) or not owner_id:
        return False
    if for_reading:
        try:
            _require_immutable_record(item)
        except (AttachmentDecisionError, TypeError, ValueError):
            return False
    return True


def readable_attachment(actor: Actor, attachment_id: str) -> dict[str, Any]:
    """The live attachment an authorized actor asked for, or `UPLOAD_NOT_FOUND`.

    Who may read whose attachment (its owner, a parent or teacher the policy
    lets in) is the route's to decide before it asks; this decides whether the
    attachment can be read at all, and whether the actor's account still can.
    Everything that reads an attachment for someone judges it here, or by
    `is_live_attachment` on a row it has already read.
    """
    if actor.account_status is not AccountStatus.ACTIVE:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    item = _gateway_call(lambda: attachment_repo.get_attachment(attachment_id))
    if item is not None and not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if not is_live_attachment(item):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return item


def safe_attachment_filename(value: str) -> str:
    """Return one header-safe basename across POSIX and Windows input styles."""
    normalized = str(value).replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    safe = "".join(
        "_" if ord(character) < 32 or character in {'"', "'"} else character
        for character in basename
    ).strip(" .")
    return (safe or "attachment")[:255]


def safe_attachment_content_disposition(filename: str) -> str:
    safe = safe_attachment_filename(filename)
    return f"attachment; filename*=UTF-8''{quote(safe, safe='._-')}"


ATTACHMENT_CONTINUATION_SCOPE = "attachment_continuation"
_ATTACHMENT_POSITION = ("attachment_id",)


def _encode_attachment_continuation(cursor: dict[str, str] | None) -> str | None:
    if cursor is None:
        return None
    try:
        position = db_table.page_key(cursor, key=_ATTACHMENT_POSITION)
    except db_table.PageTokenInvalid:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    return db_table.page_token(ATTACHMENT_CONTINUATION_SCOPE, position)


def _decode_attachment_continuation(value: str | None) -> dict[str, str] | None:
    if value is None:
        return None
    try:
        position = db_table.read_page_token(
            value, ATTACHMENT_CONTINUATION_SCOPE, key=_ATTACHMENT_POSITION
        )
    except db_table.PageTokenInvalid:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    if not isinstance(position["attachment_id"], str):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return {"attachment_id": position["attachment_id"]}


def saved_attachment_detail(item: dict[str, Any]) -> SavedAttachmentDetail:
    _require_immutable_record(item)
    return SavedAttachmentDetail(
        attachmentId=item["attachment_id"],
        filename=safe_attachment_filename(item["original_filename"]),
        mediaType=item["detected_type"],
        sizeBytes=int(item["content_length"]),
        status=AttachmentStatus.ACTIVE,
        createdAt=item["created_at"],
    )


def list_owned_attachments(
    actor: Actor,
    *,
    limit: int = 50,
    continuation: str | None = None,
) -> SavedAttachmentPage:
    """List durable owner files without consulting storage quota."""
    if actor.account_status.value != "active":
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    cursor = _decode_attachment_continuation(continuation)
    try:
        items, next_cursor = attachment_repo.list_saved_attachments(
            actor.user_id,
            limit=limit,
            exclusive_start_key=cursor,
        )
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentRepositoryConflict as exc:
        code = (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            if exc.category == "dependency_failure"
            else AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
        raise AttachmentDecisionError(code) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    projected: list[AttachmentSummary] = []
    for item in items:
        if item.get("owner_id") != actor.user_id or item.get("status") != "active":
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        projected.append(saved_attachment_detail(item))
    return SavedAttachmentPage(
        items=projected,
        continuation=_encode_attachment_continuation(next_cursor),
    )


def prepare_saved_attachment_download(
    item: dict[str, Any], *, s3: Any, settings: Settings
) -> PreparedSavedAttachmentDownload:
    """Read, verify, and spool only the exact authorized immutable version."""
    return read_immutable_object(item, s3=s3, settings=settings)


# What names one immutable object version and the bytes it must hold.
IMMUTABLE_OBJECT_FIELDS = (
    "immutable_object_key",
    "immutable_version_id",
    "immutable_etag",
    "content_sha256",
    "content_length",
    "original_filename",
    "detected_type",
)


def read_immutable_object(
    item: Mapping[str, Any], *, s3: Any, settings: Settings
) -> PreparedSavedAttachmentDownload:
    """Spool the exact immutable version `item` names, verified against its length and SHA-256.

    `item` holds the `IMMUTABLE_OBJECT_FIELDS`: a saved attachment's, or a ready
    upload's for its owner's preview (`uploads.preview`).
    """
    _require_immutable_record(item)
    expected_length = int(item["content_length"])
    spool = SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b")
    body = None
    primary_error: AttachmentDecisionError | None = None
    try:
        response = _provider_mapping(
            lambda: s3.get_object(
                Bucket=settings.s3_images_bucket,
                Key=item["immutable_object_key"],
                VersionId=item["immutable_version_id"],
            )
        )
        body = response.get("Body")
        if body is None:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        if (
            type(response.get("ContentLength")) is not int
            or response["ContentLength"] != expected_length
            or not isinstance(response.get("ETag"), str)
            or response["ETag"] != item["immutable_etag"]
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        read = getattr(body, "read", None)
        if not callable(read):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        digest = hashlib.sha256()
        measured = 0
        while True:
            chunk = read(min(UPLOAD_SPOOL_MEMORY_BYTES, expected_length + 1 - measured))
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            measured += len(chunk)
            if measured > expected_length:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            digest.update(chunk)
            spool.write(chunk)
        if measured != expected_length or digest.hexdigest() != item["content_sha256"]:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    except AttachmentDecisionError as error:
        primary_error = error
    except Exception:
        primary_error = AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    finally:
        close_ok = body is None or _close_provider_body(body)
    if primary_error is None and not close_ok:
        primary_error = AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    if primary_error is not None:
        spool.close()
        raise primary_error
    spool.seek(0)
    return PreparedSavedAttachmentDownload(
        spool=spool,
        filename=safe_attachment_filename(item["original_filename"]),
        media_type=str(item["detected_type"]),
        content_length=expected_length,
    )


def delete_saved_attachment(
    item: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
) -> SavedAttachmentDeleteResult:
    """The owner deletes one of their saved files: `delete_attachment`, as the route answers it.

    A file a message still holds is `ATTACHMENT_IN_USE` (409); a delete that did
    not finish is `retryable`, and asking again carries it on.
    """
    _require_immutable_record(item)
    outcome = delete_attachment(item, s3=s3, settings=settings, now=now)
    if outcome is LeaveOutcome.IN_USE:
        raise AttachmentDecisionError(AttachmentErrorCode.ATTACHMENT_IN_USE)
    return SavedAttachmentDeleteResult(
        attachmentId=item["attachment_id"],
        status=(
            SavedAttachmentDeleteStatus.DELETED
            if outcome is LeaveOutcome.DONE
            else SavedAttachmentDeleteStatus.RETRYABLE
        ),
    )


_DELETION_PENDING = "deletion_pending"


def delete_attachment(
    attachment: Mapping[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
) -> LeaveOutcome:
    """Delete one file: its exact S3 version, its row and its bytes off the quota.

    `attachment` is its row as last read. An active one is marked
    `deletion_pending` only while nothing references it (`active` and
    `ref_count=0`, one conditional write); reusing it in a message needs it
    `active`, so of a delete and a reuse that race, one is refused. Then the
    exact version is deleted and listed absent, and the row deleted with the
    quota row lowered in one transaction.

    A file still referenced is `IN_USE`, with nothing changed. A row already
    `deletion_pending` (a step that did not finish, or the last reference let
    go) carries on from where it stopped; a row already gone is `DONE`.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    attachment_id = attachment.get("attachment_id")
    if not isinstance(attachment_id, str) or not attachment_id:
        return LeaveOutcome.RETRYABLE
    current: Mapping[str, Any] | None = attachment
    if attachment.get("status") == AttachmentStatus.ACTIVE:
        if int(attachment.get("ref_count", 0)) > 0:
            return LeaveOutcome.IN_USE
        try:
            marked = attachment_repo.mark_saved_attachment_deletion_pending(dict(attachment))
        except Exception:
            marked = False
        if marked:
            current = {
                **attachment,
                "status": _DELETION_PENDING,
                "deletion_stage": RetentionStage.OBJECT_DELETION_PENDING.value,
                "deletion_resource_type": "saved_attachment",
                "deletion_resource_id": attachment_id,
            }
        else:
            # Refused: referenced since it was read, gone, or already being deleted.
            try:
                current = attachment_repo.get_attachment(attachment_id)
            except Exception:
                return LeaveOutcome.RETRYABLE
            if current is None:
                return LeaveOutcome.DONE
            if current.get("status") == AttachmentStatus.ACTIVE:
                if int(current.get("ref_count", 0)) > 0:
                    return LeaveOutcome.IN_USE
                return LeaveOutcome.RETRYABLE
    if current.get("status") != _DELETION_PENDING:
        return LeaveOutcome.RETRYABLE
    if _finish_pending_deletion(dict(current), s3=s3, settings=settings, now=now):
        return LeaveOutcome.DONE
    return LeaveOutcome.RETRYABLE


def release_reference(
    association: Mapping[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
) -> LeaveOutcome:
    """Let go of one reference (an `attachment_association` row); with the last, delete the file.

    The reference row is deleted and the file's `ref_count` lowered in one
    transaction, conditional on the row still being there and the count being
    what was read, so running it twice never lowers the count twice. The last
    reference marks the file `deletion_pending` in that same transaction and
    `delete_attachment` deletes it. A reference whose file is gone or already
    being deleted holds nothing and is simply deleted.
    """
    return _release_reference(
        association, s3=s3, settings=settings, now=(now or datetime.now(UTC)).astimezone(UTC)
    )[0]


def _release_reference(
    association: Mapping[str, Any], *, s3: Any, settings: Settings, now: datetime
) -> tuple[LeaveOutcome, bool]:
    """`release_reference`, and whether the file was deleted with it."""
    attachment_id = association.get("attachment_id")
    if not isinstance(attachment_id, str) or not attachment_id:
        return LeaveOutcome.RETRYABLE, False
    try:
        attachment = attachment_repo.get_attachment(attachment_id)
    except Exception:
        return LeaveOutcome.RETRYABLE, False
    if attachment is not None and attachment.get("status") == AttachmentStatus.ACTIVE:
        last = int(attachment.get("ref_count", 1)) <= 1
        try:
            attachment_repo.transact(
                attachment_repo.build_release_reference_transaction(
                    attachment=attachment,
                    association=dict(association),
                    last_reference=last,
                )
            )
        except Exception:
            # Refused: the reference already let go of, or the count moved since
            # it was read. Only the first leaves nothing to do here.
            try:
                if attachment_repo.get_association(association) is not None:
                    return LeaveOutcome.RETRYABLE, False
                attachment = attachment_repo.get_attachment(attachment_id)
            except Exception:
                return LeaveOutcome.RETRYABLE, False
        else:
            if not last:
                return LeaveOutcome.DONE, False
            attachment = {
                **attachment,
                "status": _DELETION_PENDING,
                "deletion_stage": RetentionStage.OBJECT_DELETION_PENDING.value,
                "deletion_resource_type": association.get("resource_type"),
                "deletion_resource_id": association.get("resource_id"),
            }
    else:
        try:
            attachment_repo.delete_association(association)
        except Exception:
            return LeaveOutcome.RETRYABLE, False
    if attachment is not None and attachment.get("status") == _DELETION_PENDING:
        outcome = delete_attachment(attachment, s3=s3, settings=settings, now=now)
        return outcome, outcome is LeaveOutcome.DONE
    return LeaveOutcome.DONE, False


def _require_immutable_record(item: Mapping[str, Any]) -> None:
    if (
        not all(
            item.get(field)
            for field in (
                "immutable_object_key",
                "immutable_version_id",
                "immutable_etag",
                "content_sha256",
                "original_filename",
                "detected_type",
            )
        )
        or int(item.get("content_length", 0)) <= 0
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)


def _require_model_sized_images(items: Iterable[dict[str, Any]]) -> None:
    """Images the model would refuse are refused here, before the message exists.

    Each image has its own limit, and all of a message's images together have
    one, so the request they ride in stays within what Bedrock accepts.
    """
    total = 0
    for item in items:
        if item.get("detected_type") not in MESSAGE_IMAGE_TYPES:
            continue
        length = int(item.get("content_length", 0))
        if length > MODEL_IMAGE_MAX_BYTES:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)
        total += length
    if total > MESSAGE_IMAGES_MAX_BYTES:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)


def prepare_message_attachments(
    references: list[AttachmentReference],
    actor: Actor,
    *,
    now: datetime | None = None,
    conversation_id: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve the complete owner list before any message, quota, or AI effect.

    An upload bound to a conversation (a phone upload, #146) goes into that one
    conversation and no other.
    """
    now = now or datetime.now(UTC)
    prepared: list[tuple[str, dict[str, Any]]] = []
    for reference in references:
        if reference.upload_id is not None:
            item = _uploads.usable(
                reference.upload_id,
                actor,
                purpose=UploadPurpose.CONVERSATION_ATTACHMENT,
                conversation_id=conversation_id,
                now=now,
            )
            _require_immutable_record(item)
            prepared.append(("upload", item))
        else:
            item = readable_attachment(actor, str(reference.attachment_id))
            # A message carries only the student's own saved attachments.
            if item.get("owner_id") != actor.user_id:
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
            prepared.append(("attachment", item))
    _require_model_sized_images(item for _, item in prepared)
    return prepared


def _attachment_from_upload(
    upload: dict[str, Any], *, attachment_id: str, owner_id: str, now: datetime
) -> dict[str, Any]:
    """The durable attachment a validated upload becomes, owned by `owner_id`."""
    return {
        "attachment_id": attachment_id,
        "owner_id": owner_id,
        "student_id": owner_id,
        "entity_type": "attachment",
        "schema_version": "attachment.v1",
        "immutable_object_key": upload["immutable_object_key"],
        "immutable_version_id": upload["immutable_version_id"],
        "immutable_etag": upload["immutable_etag"],
        "content_sha256": upload["content_sha256"],
        "original_filename": upload["original_filename"],
        "detected_type": upload["detected_type"],
        "content_length": int(upload["content_length"]),
        "status": "active",
        "created_at": now.isoformat(),
        "source_upload_id": upload["upload_id"],
        "ref_count": 1,
    }


def prepare_reply_images(
    upload_ids: Sequence[str],
    actor: Actor,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The replying teacher's own reply images, resolved before the reply exists (#145).

    Only a completed upload is `validated`: one moderation refused, or could not
    judge, never is (#138).
    """
    now = now or datetime.now(UTC)
    uploads: list[dict[str, Any]] = []
    for upload_id in upload_ids:
        item = _uploads.usable(
            upload_id, actor, purpose=UploadPurpose.HELP_REPLY_IMAGE, now=now
        )
        if item.get("detected_type") not in MESSAGE_IMAGE_TYPES:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        _require_immutable_record(item)
        uploads.append(item)
    return uploads


def reply_image_operations(
    uploads: Sequence[dict[str, Any]],
    *,
    teacher_id: str,
    student_id: str,
    account_fence_generation: int,
    conversation_id: str,
    message_id: str,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[AttachmentSummary]]:
    """Put a teacher's reply images into the student's conversation (#145).

    The upload was the teacher's; it and the attachment it becomes are the
    student's from here, as the reply it rides in is the student's message
    (#74). So the student reads it as their own, it goes with the conversation
    and with their account, and the teacher's account deletion does not wait
    on it.
    The operations ride in the reply's own transaction, which already checks
    the student's account fence.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fresh: list[tuple[dict[str, Any], dict[str, Any]]] = []
    associations: list[dict[str, Any]] = []
    for upload in uploads:
        attachment = _attachment_from_upload(
            upload, attachment_id=str(uuid4()), owner_id=student_id, now=now
        )
        fresh.append(
            (
                _uploads.consume_operation(
                    upload,
                    attachment_id=attachment["attachment_id"],
                    now_epoch=int(now.timestamp()),
                    owner_id=teacher_id,
                    new_owner_id=student_id,
                    account_fence_generation=account_fence_generation,
                ),
                attachment,
            )
        )
        associations.append(
            {
                **attachment_repo.association_key(
                    attachment["attachment_id"], "conversation", conversation_id, message_id
                ),
                "attachment_id": attachment["attachment_id"],
                "owner_id": student_id,
                "student_id": student_id,
                "entity_type": "attachment_association",
                "resource_type": "conversation",
                "resource_id": conversation_id,
                "message_id": message_id,
                "created_at": now.isoformat(),
            }
        )
    operations = attachment_repo.build_reply_image_operations(
        fresh=fresh,
        associations=associations,
        owner_id=student_id,
        account_fence_generation=account_fence_generation,
        conversation_id=conversation_id,
        now_iso=now.isoformat(),
    )
    return operations, [_attachment_summary(attachment) for _, attachment in fresh]


def ensure_message_attachment_capacity(
    prepared: list[tuple[str, dict[str, Any]]],
    owner_id: str,
    effective_plan: str,
) -> None:
    fresh_bytes = sum(int(item["content_length"]) for kind, item in prepared if kind == "upload")
    used_bytes = _gateway_call(lambda: attachment_repo.get_storage_usage(owner_id))
    if used_bytes + fresh_bytes > storage_limit_for_entitlement(
        effective_plan
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED)


def bind_message_attachments(
    *,
    message_id: str,
    message_put: Callable[[list[str], int], dict[str, object]],
    conversation_id: str,
    actor: Actor,
    prepared: list[tuple[str, dict[str, Any]]],
    effective_plan: str,
    now: datetime | None = None,
    command_operations: Callable[..., Sequence[attachment_repo.TransactionOperation]]
    | None = None,
    deterministic_attachment_ids: Sequence[object] | None = None,
) -> list[AttachmentSummary]:
    """Atomically persist a message and every fresh/reused attachment reference.

    `message_put(attachment_ids, generation)` builds the message's own put
    (`learning_session.append`), called once with the ids bound here and the
    account fence generation the transaction is checked against.

    `command_operations(owner_id=..., now_iso=...)` builds what the message's
    owner writes with it (a question's command row); they go last, in the same
    transaction.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fresh_count = sum(kind == "upload" for kind, _ in prepared)
    if deterministic_attachment_ids is not None:
        if len(deterministic_attachment_ids) != fresh_count or any(
            not isinstance(value, str) or not value.strip()
            for value in deterministic_attachment_ids
        ):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    fresh: list[tuple[dict[str, Any], dict[str, Any]]] = []
    reused: list[dict[str, Any]] = []
    summaries: list[AttachmentSummary] = []
    associations: list[dict[str, Any]] = []
    bound_attachment_ids: list[str] = []
    valid_deterministic_ids = (
        [value for value in deterministic_attachment_ids if isinstance(value, str)]
        if deterministic_attachment_ids is not None
        else []
    )
    deterministic_ids = iter(valid_deterministic_ids)
    for kind, item in prepared:
        if kind == "upload":
            attachment_id = (
                next(deterministic_ids)
                if deterministic_attachment_ids is not None
                else str(uuid4())
            )
            attachment = _attachment_from_upload(
                item, attachment_id=attachment_id, owner_id=actor.user_id, now=now
            )
            fresh.append(
                (
                    _uploads.consume_operation(
                        item,
                        attachment_id=attachment_id,
                        now_epoch=int(now.timestamp()),
                        owner_id=actor.user_id,
                    ),
                    attachment,
                )
            )
        else:
            attachment = item
            attachment_id = str(item["attachment_id"])
            reused.append(item)
        bound_attachment_ids.append(attachment_id)
        associations.append(
            {
                **attachment_repo.association_key(
                    attachment_id, "conversation", conversation_id, message_id
                ),
                "attachment_id": attachment_id,
                "owner_id": actor.user_id,
                "student_id": actor.user_id,
                "entity_type": "attachment_association",
                "resource_type": "conversation",
                "resource_id": conversation_id,
                "message_id": message_id,
                "created_at": now.isoformat(),
            }
        )
        summaries.append(_attachment_summary(attachment))
    limit = storage_limit_for_entitlement(effective_plan)
    ensure_message_attachment_capacity(prepared, actor.user_id, effective_plan)
    try:
        account_fence = account_deletion_repo.require_active_account_fence(actor.user_id)
        generation = int(account_fence["generation"])
        attachment_repo.transact(
            attachment_repo.build_message_attachment_transaction(
                message_put=message_put(bound_attachment_ids, generation),
                fresh=fresh,
                reused=reused,
                associations=associations,
                owner_id=actor.user_id,
                limit_bytes=limit,
                now_iso=now.isoformat(),
                trailing_operations=(
                    command_operations(owner_id=actor.user_id, now_iso=now.isoformat())
                    if command_operations is not None
                    else ()
                ),
            ),
            owner=actor.user_id,
            generation=generation,
        )
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    except attachment_repo.AttachmentTransactionError as exc:
        raise AttachmentDecisionError(_transaction_error_code(exc.outcome)) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None
    return summaries


def _transaction_error_code(
    outcome: attachment_repo.AttachmentTransactionOutcome,
) -> AttachmentErrorCode:
    return {
        attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED: (
            AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
        ),
        attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY: (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ),
        attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT: (
            AttachmentErrorCode.UPLOAD_NOT_FOUND
        ),
    }[outcome]


class AttachmentContextDisposition(StrEnum):
    READY = "ready"
    RETRYABLE = "retryable"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class AttachmentContextResult:
    disposition: AttachmentContextDisposition
    context: str = ""
    error_code: AttachmentErrorCode | None = None
    images: tuple[PromptImage, ...] = ()


def extract_message_attachment_context(
    prepared: list[tuple[str, dict[str, Any]]],
    *,
    s3: Any,
    settings: Settings,
) -> AttachmentContextResult:
    """Return one all-or-nothing typed context from exact immutable private bytes.

    Documents become text. Images go to the model as they are, in the order the
    student attached them: there is no text in a photo to extract.
    """
    parts: list[str] = []
    images: list[PromptImage] = []
    total = 0
    for _, item in prepared:
        try:
            _require_immutable_record(item)
        except AttachmentDecisionError:
            return AttachmentContextResult(
                AttachmentContextDisposition.INVALID,
                error_code=AttachmentErrorCode.UPLOAD_NOT_FOUND,
            )
    try:
        _require_model_sized_images(item for _, item in prepared)
    except AttachmentDecisionError:
        return AttachmentContextResult(
            AttachmentContextDisposition.INVALID,
            error_code=AttachmentErrorCode.UPLOAD_TOO_LARGE,
        )
    for _, item in prepared:
        length = int(item["content_length"])
        body = None
        primary_error: DocumentExtractionFailure | None = None
        value = ""
        image: PromptImage | None = None
        try:
            response = _provider_mapping(
                lambda: s3.get_object(
                    Bucket=settings.s3_images_bucket,
                    Key=item["immutable_object_key"],
                    VersionId=item["immutable_version_id"],
                )
            )
            body = response.get("Body")
            if body is None:
                raise DocumentExtractionFailure("service_unavailable")
            response_etag = response.get("ETag")
            response_length = response.get("ContentLength")
            if (
                not isinstance(response_etag, str)
                or response_etag != item["immutable_etag"]
                or type(response_length) is not int
                or response_length != length
            ):
                raise DocumentExtractionFailure("immutable_bytes_changed")
            digest = hashlib.sha256()
            measured = 0
            read = getattr(body, "read", None)
            if not callable(read):
                raise DocumentExtractionFailure("service_unavailable")
            with SpooledTemporaryFile(
                max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b"
            ) as spool:
                while True:
                    chunk = read(
                        min(UPLOAD_SPOOL_MEMORY_BYTES, length + 1 - measured)
                    )
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise DocumentExtractionFailure("service_unavailable")
                    spool.write(chunk)
                    digest.update(chunk)
                    measured += len(chunk)
                    if measured > length:
                        break
                if measured != length or digest.hexdigest() != item["content_sha256"]:
                    raise DocumentExtractionFailure("immutable_bytes_changed")
                spool.seek(0)
                try:
                    detected = validate_uploaded_file(
                        spool,
                        item["original_filename"],
                        item["detected_type"],
                    )
                except ValidationFailure:
                    raise DocumentExtractionFailure("invalid_document") from None
                if detected.media_type != item["detected_type"]:
                    raise DocumentExtractionFailure("immutable_bytes_changed")
                spool.seek(0)
                if detected.media_type in MESSAGE_IMAGE_TYPES:
                    image = PromptImage(detected.media_type, spool.read())
                else:
                    parsed = parse_document_isolated(spool, item["detected_type"])
                    if parsed.category is not None:
                        raise DocumentExtractionFailure(parsed.category)
                    value = (parsed.text or "").strip()
        except DocumentExtractionFailure as error:
            primary_error = error
        except Exception:
            primary_error = DocumentExtractionFailure("service_unavailable")
        finally:
            close_ok = body is None or _close_provider_body(body)
        if primary_error is None and not close_ok:
            primary_error = DocumentExtractionFailure("service_unavailable")
        if primary_error is not None:
            if primary_error.category == "no_extractable_text":
                continue
            if primary_error.category in {
                "invalid_document",
                "active_content",
                "encrypted_document",
                "unsupported_document",
                "document_limit_exceeded",
            }:
                return AttachmentContextResult(
                    AttachmentContextDisposition.INVALID,
                    error_code=AttachmentErrorCode.UPLOAD_INVALID,
                )
            return AttachmentContextResult(
                AttachmentContextDisposition.RETRYABLE,
                error_code=AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
            )
        if image is not None:
            images.append(image)
            continue
        if not value:
            continue
        remaining = MAX_EXTRACTED_CHARACTERS - total
        if remaining <= 0:
            continue
        value = value[:remaining]
        parts.append(value)
        total += len(value)
    return AttachmentContextResult(
        AttachmentContextDisposition.READY,
        context="\n\n".join(parts),
        images=tuple(images),
    )


def release_resource_attachments(
    owner_id: str,
    resource_type: str,
    resource_id: str,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
) -> RetentionResult:
    """Let go of every reference one resource holds, by `release_reference` on each.

    Account deletion's, under the resource's retention fence until #655 removes
    both: the new deletion flow calls `release_reference` row by row.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        fence: dict[str, Any] = attachment_repo.activate_retention_fence(
            owner_id,
            resource_type=resource_type,
            resource_id=resource_id,
            now_iso=now.isoformat(),
        )
    except attachment_repo.AttachmentRepositoryConflict as exc:
        disposition = (
            RetentionDisposition.INCOMPLETE_RETRYABLE
            if exc.category == "dependency_failure"
            else RetentionDisposition.CONFLICT
        )
        return RetentionResult(disposition, RetentionStage.FENCED)

    def holds(item: Mapping[str, Any]) -> bool:
        """One of this resource's references, or a file its last one left being deleted."""
        if item.get("entity_type") == "attachment_association":
            return (
                item.get("resource_type") == resource_type
                and item.get("resource_id") == resource_id
            )
        return (
            item.get("entity_type") == "attachment"
            and item.get("status") == _DELETION_PENDING
            and item.get("deletion_resource_type") == resource_type
            and item.get("deletion_resource_id") == resource_id
        )

    try:
        items = attachment_repo.list_owner_attachment_items(owner_id, fence=fence)
    except attachment_repo.AttachmentRepositoryConflict as exc:
        disposition = (
            RetentionDisposition.INCOMPLETE_RETRYABLE
            if exc.category == "dependency_failure"
            else RetentionDisposition.CONFLICT
        )
        return RetentionResult(disposition, RetentionStage.RETRYABLE)
    released = deleted = 0
    for item in items:
        if not holds(item):
            continue
        if item.get("entity_type") == "attachment_association":
            outcome, file_deleted = _release_reference(
                item, s3=s3, settings=settings, now=now
            )
            released += outcome is LeaveOutcome.DONE
            deleted += file_deleted
        elif delete_attachment(item, s3=s3, settings=settings, now=now) is LeaveOutcome.DONE:
            deleted += 1
    try:
        remaining = [
            item
            for item in attachment_repo.list_owner_attachment_items(owner_id, fence=fence)
            if holds(item)
        ]
    except attachment_repo.AttachmentRepositoryConflict:
        remaining = None
    if remaining is None or remaining:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    try:
        if not attachment_repo.complete_retention_fence(fence, now_iso=now.isoformat()):
            return RetentionResult(
                RetentionDisposition.CONFLICT,
                RetentionStage.CONFLICT,
                released=released,
                deleted=deleted,
            )
    except attachment_repo.AttachmentRepositoryConflict:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    return RetentionResult(
        RetentionDisposition.COMPLETE,
        RetentionStage.COMPLETE,
        released=released,
        deleted=deleted,
    )


def purge_student_attachments(
    student_id: str,
    *,
    account_fence_generation: int | None = None,
    cursors: dict[str, Any] | None = None,
    s3: Any,
    settings: Settings,
) -> AttachmentPurgeBranchResult:
    """Advance only attachment/provider debt under an existing account fence.

    Each row goes by its own action: a reference by `release_reference` (through
    `release_resource_attachments`, a resource at a time, until #655), a file by
    `delete_attachment`, an upload by `uploads.cleanup`.
    """
    now = datetime.now(UTC)
    fence: dict[str, Any] | None = None
    progress = {name: (cursors or {}).get(name) for name in PURGE_CURSOR_CATEGORIES}
    if account_fence_generation is not None:
        if (
            isinstance(account_fence_generation, bool)
            or not isinstance(account_fence_generation, int)
            or account_fence_generation <= 0
        ):
            return AttachmentPurgeBranchResult(
                AttachmentPurgeBranchStatus.CONFLICT, cursors=progress
            )
        fence = {
            **attachment_repo.retention_fence_key(student_id),
            "owner_id": student_id,
            "status": "deletion_pending",
            "generation": account_fence_generation,
        }
    try:
        items = _list_owner_account_attachment_items(student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE, cursors=progress
        )
    # Phone upload codes (#146) are already dead once the fence leaves active;
    # this removes the rows themselves.
    for item in items:
        if item.get("entity_type") != upload_code_repo.ENTITY_TYPE:
            continue
        try:
            upload_code_repo.delete_code(str(item["code_id"]))
        except Exception:
            return AttachmentPurgeBranchResult(
                AttachmentPurgeBranchStatus.RETRYABLE, cursors=progress
            )
    resources = {
        (str(item["resource_type"]), str(item["resource_id"]))
        for item in items
        if item.get("entity_type") == "attachment_association"
    }
    released = deleted = 0
    for resource_type, resource_id in sorted(resources):
        result = release_resource_attachments(
            student_id,
            resource_type,
            resource_id,
            s3=s3,
            settings=settings,
        )
        released += result["released"]
        deleted += result["deleted"]
        if result.disposition is not RetentionDisposition.COMPLETE:
            return AttachmentPurgeBranchResult(
                AttachmentPurgeBranchStatus.RETRYABLE,
                cursors=progress,
                released=released,
                deleted=deleted,
            )
    try:
        pending_items = _list_owner_account_attachment_items(student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE,
            cursors=progress,
            released=released,
            deleted=deleted,
        )
    for attachment in pending_items:
        if (
            attachment.get("entity_type") == "attachment"
            and delete_attachment(attachment, s3=s3, settings=settings, now=now)
            is LeaveOutcome.DONE
        ):
            deleted += 1

    if account_fence_generation is not None:
        try:
            after_attachments = _list_owner_account_attachment_items(student_id, fence)
        except attachment_repo.AttachmentRepositoryConflict:
            return AttachmentPurgeBranchResult(
                AttachmentPurgeBranchStatus.RETRYABLE,
                cursors=progress,
                released=released,
                deleted=deleted,
            )
        live_attachment_ids = {
            str(item["attachment_id"])
            for item in after_attachments
            if item.get("entity_type") == "attachment"
            and isinstance(item.get("attachment_id"), str)
        }
        _uploads.purge_for_account(
            student_id,
            after_attachments,
            account_fence_generation=account_fence_generation,
            live_attachment_ids=live_attachment_ids,
            s3=s3,
            settings=settings,
            now=now,
        )
    try:
        pending_items = _list_owner_account_attachment_items(student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE,
            cursors=progress,
            released=released,
            deleted=deleted,
        )
    for attachment in pending_items:
        if (
            attachment.get("entity_type") == "attachment"
            and attachment.get("status") == _DELETION_PENDING
            and delete_attachment(attachment, s3=s3, settings=settings, now=now)
            is LeaveOutcome.DONE
        ):
            deleted += 1
    try:
        debts_settled = _uploads.settle_staging_debts(student_id, s3=s3, settings=settings)
    except attachment_repo.AttachmentRepositoryConflict:
        debts_settled = False
    if not debts_settled:
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE,
            cursors=progress,
            released=released,
            deleted=deleted,
        )
    try:
        quiescent_items = _list_owner_account_attachment_items(student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE,
            cursors=progress,
            released=released,
            deleted=deleted,
        )
    remaining = [
        item
        for item in quiescent_items
        if item.get("entity_type")
        in {"attachment", "attachment_association", "upload_intent"}
    ]
    if remaining:
        debt = {
            **{name: 0 for name in PURGE_CURSOR_CATEGORIES},
            "saved": sum(item.get("entity_type") == "attachment" for item in remaining),
            "references": sum(
                item.get("entity_type") == "attachment_association" for item in remaining
            ),
            "intents": sum(
                item.get("entity_type") == "upload_intent" for item in remaining
            ),
            "multipart": sum(
                bool(item.get("multipart_upload_id")) for item in remaining
            ),
            "immutable": sum(
                bool(item.get("immutable_version_id")) for item in remaining
            ),
            "staging": sum(
                bool(item.get("staging_version_id")) for item in remaining
            ),
            "provider_debt": sum(
                item.get("staging_cleanup_status") == "pending" for item in remaining
            ),
        }
        return AttachmentPurgeBranchResult(
            AttachmentPurgeBranchStatus.RETRYABLE,
            cursors=progress,
            debt_counts=debt,
            released=released,
            deleted=deleted,
        )
    if account_fence_generation is not None:
        try:
            if not attachment_repo.delete_empty_storage_usage(
                student_id,
                account_fence_generation=account_fence_generation,
            ):
                return AttachmentPurgeBranchResult(
                    AttachmentPurgeBranchStatus.RETRYABLE,
                    cursors=progress,
                    debt_counts={"quota": 1},
                    released=released,
                    deleted=deleted,
                )
        except Exception:
            return AttachmentPurgeBranchResult(
                AttachmentPurgeBranchStatus.RETRYABLE,
                cursors=progress,
                debt_counts={"quota": 1},
                released=released,
                deleted=deleted,
            )
    return AttachmentPurgeBranchResult(
        AttachmentPurgeBranchStatus.COMPLETE,
        cursors=progress,
        quiescent=True,
        released=released,
        deleted=deleted,
    )


def release_conversation_attachments(
    owner_id: str,
    conversation_id: str,
    *,
    s3: Any,
    settings: Settings,
) -> RetentionResult:
    """Conversation-deletion integration hook."""
    return release_resource_attachments(
        owner_id,
        "conversation",
        conversation_id,
        s3=s3,
        settings=settings,
    )


def _finish_pending_deletion(
    attachment: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
) -> bool:
    """Delete a `deletion_pending` file's exact version, then its row; whether it is gone.

    Each step is conditional on the one before, so a run that stopped part way
    resumes: the version is listed absent before the row records it, and the row
    goes, with its bytes off the quota, only once it has.
    """
    try:
        _require_immutable_record(attachment)
    except Exception:
        return False
    attachment_id = str(attachment["attachment_id"])
    try:
        s3.delete_object(
            Bucket=settings.s3_images_bucket,
            Key=attachment["immutable_object_key"],
            VersionId=attachment["immutable_version_id"],
        )
    except Exception:
        # A provider error may be a lost response; exact listing decides progress.
        pass
    try:
        absent, cursor, _pages = _exact_version_absence(
            s3,
            settings,
            str(attachment["immutable_object_key"]),
            str(attachment["immutable_version_id"]),
        )
        if not absent or cursor is not None:
            return False
        if not attachment_repo.mark_deletion_absence_proven(attachment):
            current = attachment_repo.get_attachment(attachment_id)
            if current is None:
                return True
            if current.get("deletion_stage") != RetentionStage.OBJECT_ABSENCE_PROVEN:
                return False
        attachment_repo.transact(
            attachment_repo.build_finalize_deletion_transaction(
                {**attachment, "deletion_stage": RetentionStage.OBJECT_ABSENCE_PROVEN.value},
                now.isoformat(),
            )
        )
    except Exception:
        # The finalize may have committed before its response was lost.
        try:
            return attachment_repo.get_attachment(attachment_id) is None
        except Exception:
            return False
    return True


def list_attachment_summaries(attachment_ids: list[str]) -> dict[str, AttachmentSummary]:
    records = attachment_repo.get_attachments(list(dict.fromkeys(attachment_ids)))
    return {
        attachment_id: _attachment_summary(item)
        for attachment_id, item in records.items()
        if is_live_attachment(item)
    }


def attachment_summaries_for_records(
    attachment_ids: list[str], records: dict[str, dict[str, Any]]
) -> list[AttachmentSummary]:
    """Project already-authorized live records without another repository read."""
    return [
        _attachment_summary(records[value])
        for value in attachment_ids
        if value in records and is_live_attachment(records[value])
    ]


def _attachment_summary(item: dict[str, Any]) -> AttachmentSummary:
    return AttachmentSummary(
        attachmentId=item["attachment_id"],
        filename=item["original_filename"],
        mediaType=item["detected_type"],
        sizeBytes=int(item["content_length"]),
        status=AttachmentStatus.ACTIVE,
        createdAt=item["created_at"],
    )


# `uploads` reads S3 through the parsers above, so it imports this module; this
# import comes last, once they are defined, whichever of the two is imported first.
from stoa.services import uploads as _uploads  # noqa: E402
