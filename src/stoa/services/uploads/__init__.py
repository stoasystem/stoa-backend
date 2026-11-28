"""An upload: one file a student (or a teacher) sends, from issuance to its end.

An upload is issued, its parts go straight to S3 on signed URLs (ADR-004), and
completion assembles, validates, moderates and promotes it to one immutable
object. It is then ready until its usable window ends; a message or a reply
spends it on the attachment it becomes. One that fails, or is never spent,
is cleaned up. Its row is `UPLOAD#{id}` / `META`, with one `PART#{n:06d}`
row per part; `_store` is the only module that reads or writes them, and
every state an upload row is in is an `UploadStatus`, named only here.

Outside the package an upload is in one of four phases (`Phase`): in progress,
ready, failed or expired. The entry points:

- `start` issues an upload for its owner; `sign_part` signs one part's URL;
  `complete` assembles, validates and promotes it.
- `phase` and `status` say where an upload is; `preview` reads a ready
  upload's bytes for its owner.
- `usable` is a ready upload of the caller's for one purpose, the record a
  message or a reply makes its attachment from; `consume_operation` is the
  update that spends it, for the caller's own transaction.
- `cleanup` cleans one upload: the sweep's (`jobs.upload_cleanup`), on what
  `cleanup_candidates` finds, and account deletion's, on each of the account's
  upload rows. `purge_for_account` and `settle_staging_debts` are the old
  account purge's, until #655.

The durable attachment an upload becomes is `attachment_service`'s.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from stoa.config import Settings
from stoa.models.attachment import UploadPurpose, UploadStatus
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor
from stoa.services import attachment_service
from stoa.services.uploads import _lifecycle, _store
from stoa.services.uploads._lifecycle import (
    UPLOAD_CHUNK_BYTES,
    complete_upload as complete,
    create_upload_intent as start,
    sign_upload_part as sign_part,
)
from stoa.services.uploads._store import consume_operation

CLEANUP_PAGE_KEY = _store.CLEANUP_INDEX_PAGE_KEY

__all__ = [
    "CLEANUP_PAGE_KEY",
    "Phase",
    "UPLOAD_CHUNK_BYTES",
    "cleanup",
    "cleanup_candidates",
    "complete",
    "consume_operation",
    "phase",
    "preview",
    "purge_for_account",
    "settle_staging_debts",
    "sign_part",
    "start",
    "status",
    "usable",
]


class Phase(StrEnum):
    """Where an upload is, as anyone outside the package may know it."""

    IN_PROGRESS = "in_progress"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


_IN_PROGRESS = frozenset(
    {
        UploadStatus.ISSUING,
        UploadStatus.PENDING_UPLOAD,
        UploadStatus.ASSEMBLING,
        UploadStatus.VALIDATING,
        UploadStatus.PROMOTING,
    }
)


def phase(item: Mapping[str, object], now_epoch: int) -> Phase:
    """The phase of this upload row at `now_epoch`.

    Ready is validated within the usable window, or already spent: a spent
    upload went into a message, which is as ready as an upload gets. Expired
    is the window over before the upload was spent, whatever state it was
    left in; failed is refused or handed to cleanup.
    """
    state = item.get("status")
    if state == UploadStatus.CONSUMED:
        return Phase.READY
    if state in _IN_PROGRESS or state == UploadStatus.VALIDATED:
        if _store.usable_until(item) <= now_epoch:
            return Phase.EXPIRED
        return Phase.READY if state == UploadStatus.VALIDATED else Phase.IN_PROGRESS
    return Phase.FAILED


def status(upload_id: str, owner_id: str, *, now: datetime | None = None) -> Phase | None:
    """Where the owner's upload is; `None` when there is no such upload of theirs."""
    item = _read(upload_id)
    if item is None or item.get("owner_id") != owner_id:
        return None
    return phase(item, int((now or datetime.now(UTC)).timestamp()))


def preview(
    upload_id: str,
    owner_id: str,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
) -> attachment_service.PreparedSavedAttachmentDownload:
    """The bytes of the owner's ready upload, read from its exact immutable version."""
    item = _read(upload_id)
    if (
        item is None
        or item.get("owner_id") != owner_id
        or phase(item, int((now or datetime.now(UTC)).timestamp())) is not Phase.READY
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return attachment_service.read_immutable_object(
        {field: item.get(field) for field in attachment_service.IMMUTABLE_OBJECT_FIELDS},
        s3=s3,
        settings=settings,
    )


def usable(
    upload_id: str,
    actor: Actor,
    *,
    purpose: UploadPurpose,
    conversation_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The caller's validated upload for `purpose`, still in its usable window.

    An upload bound to a conversation (a phone upload, #146) is usable in that
    conversation only. Anything else is `UPLOAD_NOT_FOUND`, or `UPLOAD_EXPIRED`
    once the window is over.
    """
    item = _lifecycle.resolve_owned_upload(upload_id, actor, now=now)
    bound_to = item.get("bound_conversation_id")
    if (
        item.get("status") != UploadStatus.VALIDATED
        or item.get("expected_kind") != purpose
        or (bound_to is not None and bound_to != conversation_id)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return item


def cleanup_candidates(
    now_epoch: int, *, limit: int, exclusive_start_key: dict[str, Any] | None
) -> tuple[list[dict[str, object]], dict[str, Any] | None]:
    """One page of the uploads due for cleanup, earliest due first, and where the next starts.

    Read from the cleanup's index (#611); `CLEANUP_PAGE_KEY` is what a
    continuation key of it holds.
    """
    return _store.query_upload_cleanup_candidates(
        now_epoch, limit=limit, exclusive_start_key=exclusive_start_key
    )


def cleanup(
    candidate: Mapping[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    account_fence_generation: int | None = None,
) -> str:
    """Clean one upload a step further: `deleted`, `deferred`, `protected`, `retryable` or `skipped`.

    Cleaning takes its parts, its staging and immutable copies, its PART rows and
    any staging copy it still owed; the row is left `cleanup_complete` until its
    TTL. Safe to run again: each step is recorded on the row before the next.

    An upload whose attachment is still there is `protected` and left alone:
    those bytes are the attachment's, which deletes them when it goes, and the
    next pass finds the upload free. Once the attachment is gone, it is cleaned.

    The sweep passes an upload it found due. Account deletion passes each of
    the closing account's upload rows with its fence generation, which takes an
    upload in any state (`_store.claim_account_upload_cleanup`) instead of only
    one past its usable window.
    """
    if account_fence_generation is None:
        return _lifecycle.cleanup_upload_intent(
            dict(candidate),
            s3=s3,
            settings=settings,
            now=now,
        )
    owner_id = candidate.get("owner_id")
    if not isinstance(owner_id, str) or not owner_id:
        return "skipped"
    try:
        if _lifecycle._attachment_still_holds(dict(candidate)):
            return "protected"
    except Exception:
        return "retryable"
    current: dict[str, Any] = dict(candidate)
    if current.get("status") == UploadStatus.CLEANUP_COMPLETE:
        return "deleted"
    if current.get("status") != UploadStatus.CLEANUP_PENDING:
        try:
            claimed = _store.claim_account_upload_cleanup(
                current,
                owner_id=owner_id,
                account_fence_generation=account_fence_generation,
            )
        except Exception:
            return "retryable"
        if not isinstance(claimed, dict):
            return "retryable"
        current = claimed
    return _lifecycle.cleanup_upload_intent(
        current,
        s3=s3,
        settings=settings,
        now=now,
    )


def leave_for_account_deletion(
    upload: Mapping[str, Any],
    *,
    account_fence_generation: int,
    s3: Any,
    settings: Settings,
    now: datetime,
) -> bool:
    """Clean one of a closing account's uploads and delete its row; whether it is gone (#641).

    `cleanup` with the account's fence generation, then, once cleaned, the
    row itself, under the account's deletion fence. An upload whose attachment
    is still there, or a step that did not finish, is left for the next pass.
    """
    owner_id = upload.get("owner_id")
    upload_id = upload.get("upload_id")
    if not isinstance(owner_id, str) or not owner_id:
        return False
    if not isinstance(upload_id, str) or not upload_id:
        return False
    outcome = cleanup(
        upload,
        s3=s3,
        settings=settings,
        now=now,
        account_fence_generation=account_fence_generation,
    )
    if outcome != "deleted":
        current = _store.get_upload_intent(upload_id)
        if current is None:
            return True
        if current.get("status") != UploadStatus.CLEANUP_COMPLETE:
            return False
    try:
        if _store.delete_account_upload_tombstone(
            upload_id, owner_id=owner_id, account_fence_generation=account_fence_generation
        ):
            return True
    except Exception:
        pass
    return _store.get_upload_intent(upload_id) is None


def purge_for_account(
    student_id: str,
    owner_items: Iterable[Mapping[str, Any]],
    *,
    account_fence_generation: int,
    live_attachment_ids: set[str],
    s3: Any,
    settings: Settings,
    now: datetime,
) -> None:
    """Clean every upload among the deleted account's rows, by `cleanup` on each.

    An upload whose attachment is still live goes with that attachment instead.
    Each cleaned upload's tombstone is deleted under the account's deletion
    fence. A step that fails leaves the upload for the purge's next pass.
    """
    for upload in owner_items:
        if upload.get("entity_type") != "upload_intent":
            continue
        durable_attachment_id = upload.get("durable_attachment_id")
        if isinstance(durable_attachment_id, str) and durable_attachment_id in live_attachment_ids:
            continue
        if upload.get("owner_id") != student_id:
            continue
        outcome = cleanup(
            upload,
            s3=s3,
            settings=settings,
            now=now,
            account_fence_generation=account_fence_generation,
        )
        if outcome == "deleted":
            try:
                _store.delete_account_upload_tombstone(
                    str(upload["upload_id"]),
                    owner_id=student_id,
                    account_fence_generation=account_fence_generation,
                )
            except Exception:
                pass


def settle_staging_debts(student_id: str, *, s3: Any, settings: Settings) -> bool:
    """Delete every staging copy the owner's promoted uploads still owe; whether all went."""
    debts = _store.list_owner_staging_cleanup_debts(student_id)
    return all(
        _lifecycle._reconcile_staging_cleanup_debt(
            debt, s3=s3, settings=settings, repository=_store
        )
        for debt in debts
    )


def _read(upload_id: str) -> dict[str, Any] | None:
    try:
        item = _store.get_upload_intent(upload_id)
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    if item is not None and not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return item
