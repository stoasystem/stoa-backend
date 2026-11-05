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
- `cleanup_candidates` and `cleanup` are the sweep's (`jobs.upload_cleanup`);
  `purge_for_account` and `settle_staging_debts` are account deletion's.

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

__all__ = [
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
    """One page of uploads the sweep may clean, and where the next page starts."""
    return _store.list_upload_cleanup_candidates(
        now_epoch, limit=limit, exclusive_start_key=exclusive_start_key
    )


def cleanup(
    candidate: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    reference_scan_limit: int,
) -> str:
    """Clean one candidate a step further: `deleted`, `deferred`, `protected`, `retryable` or `skipped`."""
    return _lifecycle.cleanup_upload_intent(
        candidate,
        s3=s3,
        settings=settings,
        now=now,
        reference_scan_limit=reference_scan_limit,
    )


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
    """Clean every upload among the deleted account's rows that no live attachment holds.

    Each is claimed under the account's deletion fence, cleaned, and its
    tombstone deleted once nothing of it is left. An upload whose attachment
    is still live goes with that attachment instead. A step that fails leaves
    the upload for the purge's next pass.
    """
    for upload in owner_items:
        if upload.get("entity_type") != "upload_intent":
            continue
        durable_attachment_id = upload.get("durable_attachment_id")
        if isinstance(durable_attachment_id, str) and durable_attachment_id in live_attachment_ids:
            continue
        current: dict[str, Any] = dict(upload)
        if current.get("status") != UploadStatus.CLEANUP_PENDING:
            try:
                claimed = _store.claim_account_upload_cleanup(
                    current,
                    owner_id=student_id,
                    account_fence_generation=account_fence_generation,
                )
            except Exception:
                continue
            if not isinstance(claimed, dict):
                continue
            current = claimed
        outcome = _lifecycle.cleanup_upload_intent(
            current, s3=s3, settings=settings, now=now, reference_scan_limit=100
        )
        if outcome == "deleted":
            try:
                _store.delete_account_upload_tombstone(
                    current["upload_id"],
                    owner_id=student_id,
                    account_fence_generation=account_fence_generation,
                )
            except Exception:
                pass


def settle_staging_debts(student_id: str, *, s3: Any, settings: Settings) -> bool:
    """Delete every staging copy the owner's promoted uploads still owe; whether all went."""
    debts = _store.list_owner_staging_cleanup_debts(student_id)
    return all(
        _lifecycle._reconcile_staging_cleanup_debt(debt, s3=s3, settings=settings)
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
