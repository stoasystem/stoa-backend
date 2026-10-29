"""One image from a phone that is not signed in, into one conversation (#146).

The computer mints a code for a learning conversation; the phone that scans it
presents the code instead of a session. The code is `<codeId>.<secret>`: the id
finds the row, and the secret (32 random bytes) is checked against the SHA-256 the
row holds, in constant time. Redeeming spends the code with a conditional write and
hands the phone an upload token of the same shape, good for that one upload and
nothing else, so a code seen over a shoulder after the scan opens nothing.

Every refusal of a code or token is the same `upload_code_invalid`, whether it was
wrong, spent, expired, made for a since-deleted conversation, or belongs to an
account in deletion: the answer tells a guesser nothing. Neither secret is logged,
stored, or put in a URL.

What the phone uploads is an ordinary upload owned by the student, bound to the
conversation the code was made in, and completed through the same path as any
other, moderation included (#138).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import re
import secrets
from typing import Any
from uuid import uuid4

from stoa.config import IMAGE_MAX_BYTES, Settings
from stoa.db.repositories import account_deletion_repo, attachment_repo, upload_code_repo
from stoa.models.attachment import UploadIntentRequest, UploadPartUrlRequest, UploadPurpose
from stoa.models.upload_code import (
    UploadCodeCompleteRequest,
    UploadCodePartRequest,
    UploadCodeRedeemRequest,
)
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import attachment_service, rate_limit
from stoa.services.file_validation_service import MIME_BY_EXTENSION


CODE_TTL_SECONDS = 600
UPLOAD_TOKEN_TTL_SECONDS = 600
_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png"})
_CODE_ID = re.compile(r"^[0-9a-f]{32}$")
_SECRET = re.compile(r"^[A-Za-z0-9_-]{43}$")
# Compared against when there is no row, so a miss costs what a hit costs.
_ABSENT_DIGEST = hashlib.sha256(b"no such upload code").hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _invalid() -> AttachmentDecisionError:
    return AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CODE_INVALID)


def _unavailable() -> AttachmentDecisionError:
    return AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)


def _admit(scope: str, source_digest: str, limit: int, settings: Settings) -> None:
    if not rate_limit.admit_source_window(
        scope=scope,
        source_digest=source_digest,
        limit=limit,
        window_seconds=settings.upload_code_window_seconds,
        now=_now(),
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED)


def _owner_actor(row: dict[str, Any]) -> Actor:
    """The student the code was made by, as the upload path expects its owner."""
    return Actor(
        str(row["owner_id"]),
        "stoa:upload-code",
        f"upload-code:{row['code_id']}",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        CanonicalRole.STUDENT.value,
    )


def _verified_row(presented: str, digest_field: str) -> dict[str, Any] | None:
    """The row whose `digest_field` matches the presented secret, else None."""
    code_id, _, secret = presented.partition(".")
    well_formed = bool(_CODE_ID.match(code_id) and _SECRET.match(secret))
    try:
        row = upload_code_repo.get_code(code_id) if well_formed else None
    except Exception:
        raise _unavailable() from None
    expected = row.get(digest_field) if row else None
    matches = hmac.compare_digest(
        _digest(secret), expected if isinstance(expected, str) else _ABSENT_DIGEST
    )
    return row if well_formed and row is not None and isinstance(expected, str) and matches else None


def _require_live_account(row: dict[str, Any]) -> None:
    try:
        account_deletion_repo.require_active_account_fence(
            str(row["owner_id"]), int(row["account_fence_generation"])
        )
    except account_deletion_repo.AccountDeletionConflict:
        raise _invalid() from None
    except Exception:
        raise _unavailable() from None


def _require_image(request: UploadCodeRedeemRequest) -> None:
    """Images only; checked before the code is spent, so a wrong pick costs nothing."""
    extension = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    if extension not in _IMAGE_EXTENSIONS:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    if request.content_type not in MIME_BY_EXTENSION[extension]:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
    if request.size_bytes > IMAGE_MAX_BYTES:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)


# -- the computer ---------------------------------------------------------------


def issue_code(conversation_id: str, actor: Actor, *, settings: Settings) -> dict[str, Any]:
    """A code for this conversation of this student; the secret is returned only here."""
    _admit(
        "UPLOAD_CODE_ISSUE",
        hashlib.sha256(actor.user_id.encode("utf-8")).hexdigest(),
        settings.upload_code_issue_max_per_window,
        settings,
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(actor.user_id)
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    except Exception:
        raise _unavailable() from None
    now = _now()
    code_id = uuid4().hex
    secret = secrets.token_urlsafe(32)
    expires_at = int(now.timestamp()) + CODE_TTL_SECONDS
    try:
        upload_code_repo.put_code(
            {
                "code_id": code_id,
                "owner_id": actor.user_id,
                "student_id": actor.user_id,
                "conversation_id": conversation_id,
                "secret_sha256": _digest(secret),
                "status": "issued",
                "account_fence_generation": int(fence["generation"]),
                "created_at": now.isoformat(),
                "expires_at": expires_at,
            }
        )
    except Exception:
        raise _unavailable() from None
    return {
        "codeId": code_id,
        "code": f"{code_id}.{secret}",
        "expiresAt": datetime.fromtimestamp(expires_at, UTC),
    }


def code_status(conversation_id: str, code_id: str, actor: Actor) -> dict[str, Any]:
    if not _CODE_ID.match(code_id):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    try:
        row = upload_code_repo.get_code(code_id)
    except Exception:
        raise _unavailable() from None
    if (
        row is None
        or row.get("owner_id") != actor.user_id
        or row.get("conversation_id") != conversation_id
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now_epoch = int(_now().timestamp())
    status, upload_id = "waiting", None
    expires_at = int(row["expires_at"])
    if row.get("status") == "redeemed":
        expires_at = int(row["token_expires_at"])
        try:
            upload = attachment_repo.get_upload_intent(str(row["upload_id"]))
        except Exception:
            raise _unavailable() from None
        upload_status = (upload or {}).get("status")
        if upload_status in {"validated", "consuming", "consumed"}:
            status, upload_id = "ready", str(row["upload_id"])
        elif upload_status in {"invalid", "expired", None}:
            status = "failed"
        else:
            status = "uploading"
    if status in {"waiting", "uploading"} and now_epoch >= expires_at:
        status = "expired"
    return {
        "codeId": code_id,
        "status": status,
        "expiresAt": datetime.fromtimestamp(expires_at, UTC),
        "uploadId": upload_id,
    }


# -- the phone ------------------------------------------------------------------


def redeem_code(
    request: UploadCodeRedeemRequest,
    *,
    source_digest: str,
    s3: Any,
    settings: Settings,
) -> dict[str, Any]:
    """Spend the code on one image upload into its conversation; hand back the token."""
    _admit("UPLOAD_CODE_REDEEM", source_digest, settings.upload_code_redeem_max_per_window, settings)
    _require_image(request)
    now = _now()
    now_epoch = int(now.timestamp())
    row = _verified_row(request.code.get_secret_value(), "secret_sha256")
    if row is None or row.get("status") != "issued" or now_epoch >= int(row["expires_at"]):
        raise _invalid()
    _require_live_account(row)
    try:
        conversation = upload_code_repo.get_conversation(str(row["conversation_id"]))
    except Exception:
        raise _unavailable() from None
    if (
        conversation is None
        or conversation.get("student_id") != row["owner_id"]
        or conversation.get("status") == "deleted"
    ):
        raise _invalid()
    upload_id = str(uuid4())
    token_secret = secrets.token_urlsafe(32)
    token_expires_at = now_epoch + UPLOAD_TOKEN_TTL_SECONDS
    try:
        claimed = upload_code_repo.claim_code(
            str(row["code_id"]),
            now_epoch=now_epoch,
            upload_id=upload_id,
            token_sha256=_digest(token_secret),
            token_expires_at=token_expires_at,
            redeemed_at=now.isoformat(),
        )
    except Exception:
        raise _unavailable() from None
    if not claimed:
        raise _invalid()
    intent = attachment_service.create_upload_intent(
        UploadIntentRequest(
            purpose=UploadPurpose.CONVERSATION_ATTACHMENT,
            filename=request.filename,
            contentType=request.content_type,
            sizeBytes=request.size_bytes,
        ),
        _owner_actor(row),
        s3=s3,
        settings=settings,
        now=now,
        upload_id=upload_id,
        conversation_id=str(row["conversation_id"]),
    )
    return {
        "uploadToken": f"{row['code_id']}.{token_secret}",
        "expiresAt": datetime.fromtimestamp(token_expires_at, UTC),
        "maxBytes": intent["maxBytes"],
        "chunkBytes": intent["chunkBytes"],
        "acceptedTypes": intent["acceptedTypes"],
    }


def _redeemed_row(token: str) -> dict[str, Any]:
    row = _verified_row(token, "token_sha256")
    if (
        row is None
        or row.get("status") != "redeemed"
        or int(_now().timestamp()) >= int(row["token_expires_at"])
    ):
        raise _invalid()
    _require_live_account(row)
    return row


def sign_part(
    part_number: int,
    request: UploadCodePartRequest,
    *,
    source_digest: str,
    signer: Any,
    settings: Settings,
) -> dict[str, Any]:
    _admit("UPLOAD_CODE_UPLOAD", source_digest, settings.upload_code_upload_max_per_window, settings)
    row = _redeemed_row(request.upload_token.get_secret_value())
    signed = attachment_service.sign_upload_part(
        str(row["upload_id"]),
        part_number,
        UploadPartUrlRequest(sizeBytes=request.size_bytes, checksumSha256=request.checksum_sha256),
        _owner_actor(row),
        signer=signer,
        settings=settings,
        now=_now(),
    )
    return {key: value for key, value in signed.items() if key != "uploadId"}


def complete(
    request: UploadCodeCompleteRequest,
    *,
    source_digest: str,
    s3: Any,
    settings: Settings,
    moderation: Any,
) -> dict[str, Any]:
    _admit("UPLOAD_CODE_UPLOAD", source_digest, settings.upload_code_upload_max_per_window, settings)
    row = _redeemed_row(request.upload_token.get_secret_value())
    completed = attachment_service.complete_upload(
        str(row["upload_id"]),
        request.part_count,
        _owner_actor(row),
        s3=s3,
        settings=settings,
        now=_now(),
        moderation=moderation,
    )
    if completed.get("status") != "validated":
        raise _unavailable()
    return {"status": "validated"}
