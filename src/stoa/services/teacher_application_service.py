"""No-privilege teacher application, review, invitation, and activation lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import secrets
from typing import Any, Callable
from uuid import uuid4

from stoa.db.dynamodb import stored_int
from stoa.db.repositories import (
    capability_repo,
    identity_repo,
    security_audit_repo,
    teacher_application_repo,
)
from stoa.services import (
    account_provisioning_service,
    notify_service,
    teacher_identity_provider,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.services.account_errors import AccountErrorCode, AccountViolation


TEACHER_ROLE = "teacher"

FORBIDDEN_APPLICATION_FIELDS = frozenset(
    {"document", "documents", "credential", "credentials", "file", "files", "blob", "upload"}
)
ALLOWED_APPLICATION_FIELDS = frozenset(
    {"application_id", "email", "email_verified", "full_name", "subjects", "statement"}
)


def submit_application(
    payload: dict[str, Any],
    *,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Persist an immutable candidacy version without creating any identity privilege."""
    if FORBIDDEN_APPLICATION_FIELDS.intersection(payload):
        raise AccountViolation(AccountErrorCode.CREDENTIAL_DOCUMENTS_DEFERRED)
    unexpected = set(payload) - ALLOWED_APPLICATION_FIELDS
    if unexpected:
        raise AccountViolation(AccountErrorCode.APPLICATION_FIELDS_NOT_ALLOWED)
    email = _email(payload.get("email"))
    if payload.get("email_verified") is not True:
        raise AccountViolation(AccountErrorCode.VERIFIED_EMAIL_REQUIRED)
    application_id = str(payload.get("application_id") or f"teacherapp_{uuid4().hex}").strip()
    existing = teacher_application_repo.list_application_versions(application_id)
    version = max(
        (
            _positive_version(item.get("version"), AccountErrorCode.APPLICATION_STATE_INVALID)
            for item in existing
        ),
        default=0,
    ) + 1
    timestamp = _timestamp(now)
    row = teacher_application_repo.create_application_version(
        {
            "application_id": application_id,
            "version": version,
            "status": "pending_review",
            "verified_email": email,
            "full_name": _bounded(payload.get("full_name"), 120, "full_name"),
            "subjects": _subjects(payload.get("subjects")),
            "statement": _bounded(payload.get("statement"), 2000, "statement"),
            "created_at": timestamp,
        }
    )
    _audit(
        stream_id=application_id,
        event_type="teacher_application_submitted",
        actor_id=f"application:{application_id}",
        target_id=application_id,
        version=version,
        reason_code="public_application",
        created_at=timestamp,
    )
    return _application_metadata(row)


def review_application(
    *,
    actor: dict[str, Any],
    application_id: str,
    version: int,
    decision: str,
    reason: str,
    invitation_expiry_seconds: int = 900,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    if decision not in {"approved", "rejected"}:
        raise AccountViolation(AccountErrorCode.INVALID_REVIEW_DECISION)
    clean_reason = _bounded(reason, 1000, "reason")
    application = teacher_application_repo.get_application_version(application_id, version)
    if not application:
        raise AccountViolation(AccountErrorCode.APPLICATION_VERSION_NOT_FOUND)
    timestamp_dt = (now or (lambda: datetime.now(UTC)))()
    timestamp = timestamp_dt.isoformat()
    reviewer_id = _actor_id(actor)
    review_id = f"review_{uuid4().hex}"
    teacher_application_repo.create_review(
        {
            "application_id": application_id,
            "version": int(version),
            "review_id": review_id,
            "decision": decision,
            "internal_reason": clean_reason,
            "reviewer_id": reviewer_id,
            "created_at": timestamp,
        }
    )
    evidence = f"teacher-review:{review_id}"
    _audit(
        stream_id=application_id,
        event_type=f"teacher_application_{decision}",
        actor_id=reviewer_id,
        target_id=application_id,
        version=version,
        reason_code="review_recorded",
        evidence_reference=evidence,
        created_at=timestamp,
    )
    teacher_application_repo.set_application_review_state(
        application_id, int(version), review_state=decision, decided_at=timestamp
    )
    response: dict[str, Any] = {
        "applicationId": application_id,
        "version": version,
        "decision": decision,
        "evidenceReference": evidence,
    }
    if decision == "approved":
        response.update(
            _issue_invitation(
                application=application,
                application_id=application_id,
                version=int(version),
                reviewer_id=reviewer_id,
                reason=clean_reason,
                invitation_expiry_seconds=invitation_expiry_seconds,
                timestamp_dt=timestamp_dt,
            )
        )
    return response


def reissue_invitation(
    *,
    actor: dict[str, Any],
    application_id: str,
    version: int,
    invitation_expiry_seconds: int = 259200,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Issue a replacement invitation for an already approved version.

    A token is readable only at issue time, so an undelivered or expired invitation
    cannot be recovered — it has to be replaced. Requires an existing approval so this
    never becomes a second path to grant a teacher identity.
    """
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    application = teacher_application_repo.get_application_version(application_id, version)
    if not application:
        raise AccountViolation(AccountErrorCode.APPLICATION_VERSION_NOT_FOUND)
    review = teacher_application_repo.get_review(application_id, version)
    if not review or review.get("decision") != "approved":
        raise AccountViolation(AccountErrorCode.APPLICATION_NOT_APPROVED)
    timestamp_dt = (now or (lambda: datetime.now(UTC)))()
    return {
        "applicationId": application_id,
        "version": int(version),
        "decision": "approved",
        **_issue_invitation(
            application=application,
            application_id=application_id,
            version=int(version),
            reviewer_id=_actor_id(actor),
            reason=str(review.get("internal_reason") or "reissued invitation"),
            invitation_expiry_seconds=invitation_expiry_seconds,
            timestamp_dt=timestamp_dt,
        ),
    }


def _issue_invitation(
    *,
    application: dict[str, Any],
    application_id: str,
    version: int,
    reviewer_id: str,
    reason: str,
    invitation_expiry_seconds: int,
    timestamp_dt: datetime,
) -> dict[str, Any]:
    """Create one single-use invitation and hand the token to the candidate by email."""
    timestamp = timestamp_dt.isoformat()
    token = secrets.token_urlsafe(32)
    digest = _token_digest(token)
    invitation_id = f"invitation_{uuid4().hex}"
    expires_at = timestamp_dt + timedelta(seconds=max(60, invitation_expiry_seconds))
    recipient = str(application["verified_email"])
    teacher_application_repo.create_invitation(
        {
            "invitation_id": invitation_id,
            "token_digest": digest,
            "application_id": application_id,
            "application_version": version,
            "verified_email": recipient,
            "status": "issued",
            "version": 1,
            "issued_by": reviewer_id,
            "issued_at": timestamp,
            # Numeric epoch so the table's time-to-live attribute actually expires the
            # row; the readable copy is kept beside it for responses and audits.
            "expires_at": int(expires_at.timestamp()),
            "expires_at_iso": expires_at.isoformat(),
            "reason": reason,
        }
    )
    _audit(
        stream_id=application_id,
        event_type="teacher_invitation_issued",
        actor_id=reviewer_id,
        target_id=application_id,
        version=version,
        reason_code="approved_version",
        evidence_reference=f"teacher-invitation:{invitation_id}",
        created_at=timestamp,
    )
    # The reviewer never receives the token: delivery goes straight to the address the
    # invitation is bound to, so an approval cannot be turned into a usable credential
    # by whoever performed the review.
    delivered = True
    try:
        notify_service.send_teacher_invitation_email(
            recipient,
            activation_token=token,
            expires_at=expires_at.isoformat(),
            full_name=str(application.get("full_name") or ""),
        )
    except Exception:
        delivered = False
        _audit(
            stream_id=application_id,
            event_type="teacher_invitation_delivery_failed",
            actor_id=reviewer_id,
            target_id=application_id,
            version=version,
            reason_code="delivery_unavailable",
            evidence_reference=f"teacher-invitation:{invitation_id}",
            created_at=timestamp,
        )
    return {
        "invitationId": invitation_id,
        "expiresAt": expires_at.isoformat(),
        "invitationDelivered": delivered,
    }


def applications_for_reviewer(
    actor: dict[str, Any], *, review_state: str = "pending_review", limit: int = 50
) -> dict[str, Any]:
    """List candidacy versions in one review state without exposing statements."""
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    if review_state not in {"pending_review", "approved", "rejected"}:
        raise AccountViolation(AccountErrorCode.INVALID_REVIEW_STATE)
    items = teacher_application_repo.list_applications_by_review_state(review_state, limit=limit)
    return {
        "reviewState": review_state,
        "items": [
            {
                **_application_metadata(item),
                "reviewState": item.get("review_state"),
                "verifiedEmail": item.get("verified_email"),
                "fullName": item.get("full_name"),
                "subjects": item.get("subjects") or [],
            }
            for item in items
        ],
        "count": len(items),
    }


def application_status(application_id: str) -> dict[str, Any]:
    """Return decision-free progress for a candidate holding the opaque application id.

    Deliberately excludes the reviewer's reason and every submitted field, so an
    enumerated id leaks nothing beyond how far the application has moved.
    """
    versions = teacher_application_repo.list_application_versions(application_id)
    if not versions:
        raise AccountViolation(AccountErrorCode.APPLICATION_NOT_FOUND)
    latest = max(versions, key=lambda item: int(item.get("version") or 0))
    return {
        "applicationId": application_id,
        "version": int(latest.get("version") or 0),
        "reviewState": str(latest.get("review_state") or "pending_review"),
        "createdAt": latest.get("created_at"),
        "decidedAt": latest.get("decided_at"),
    }


def activate_from_invitation(
    *,
    token: str,
    verified_email: str,
    issuer: str,
    subject: str,
    provider: Any,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Consume once and resume one deny-first activation command across partial failures."""
    digest = _token_digest(token)
    invitation = teacher_application_repo.get_invitation(digest)
    if not invitation:
        raise AccountViolation(AccountErrorCode.INVITATION_INVALID)
    email = _email(verified_email)
    if not hmac.compare_digest(str(invitation.get("verified_email") or ""), email):
        raise AccountViolation(AccountErrorCode.INVITATION_EMAIL_MISMATCH)
    instant = (now or (lambda: datetime.now(UTC)))()
    if _invitation_expiry(invitation) <= instant:
        raise AccountViolation(AccountErrorCode.INVITATION_EXPIRED)

    command_id = str(invitation.get("command_id") or f"teacheractivate_{digest[:24]}")
    existing = teacher_application_repo.get_activation_command(command_id)
    if invitation.get("status") != "issued":
        if not existing or existing.get("status") not in {"provider_failed", "reconciling"}:
            raise AccountViolation(AccountErrorCode.INVITATION_ALREADY_USED)
        return _resume_activation(existing, provider=provider, now=instant)

    user_id = f"teacher_{sha256(command_id.encode()).hexdigest()[:24]}"
    command = teacher_application_repo.create_activation_command(
        {
            "command_id": command_id,
            "application_id": invitation["application_id"],
            "application_version": _positive_version(
                invitation.get("application_version"),
                AccountErrorCode.INVITATION_APPLICATION_STATE_INVALID,
            ),
            "invitation_id": invitation["invitation_id"],
            "verified_email": email,
            "issuer": issuer.strip().rstrip("/"),
            "subject": subject.strip(),
            "user_id": user_id,
            "status": "pending",
            "version": 1,
            "created_at": instant.isoformat(),
            "updated_at": instant.isoformat(),
        }
    )
    won = teacher_application_repo.claim_invitation(
        digest,
        command_id=command_id,
        consumed_at=instant.isoformat(),
    )
    if not won:
        raise AccountViolation(AccountErrorCode.INVITATION_ALREADY_USED)
    _audit(
        stream_id=command["application_id"],
        event_type="teacher_invitation_consumed",
        actor_id=user_id,
        target_id=user_id,
        version=command["application_version"],
        reason_code="same_verified_email",
        command_id=command_id,
        created_at=instant.isoformat(),
    )
    return _resume_activation(command, provider=provider, now=instant)


def claim_and_activate(
    *,
    token: str,
    password: str,
    issuer: str,
    provider: Any,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Exchange a single-use invitation for one account and one active teacher identity.

    This is the only path that creates a teacher account, and it cannot be reached
    without a reviewer-issued token. The account address is taken from the invitation,
    never from the caller, so holding a token grants exactly the identity that was
    approved and nothing else.
    """
    digest = _token_digest(token)
    invitation = teacher_application_repo.get_invitation(digest)
    if not invitation:
        raise AccountViolation(AccountErrorCode.INVITATION_INVALID)
    instant = (now or (lambda: datetime.now(UTC)))()
    if _invitation_expiry(invitation) <= instant:
        raise AccountViolation(AccountErrorCode.INVITATION_EXPIRED)
    if invitation.get("status") != "issued":
        command_id = str(invitation.get("command_id") or "")
        existing = (
            teacher_application_repo.get_activation_command(command_id) if command_id else None
        )
        if existing and existing.get("status") in {"provider_failed", "reconciling"}:
            # The account was already created by an earlier attempt, so the candidate can
            # finish through the signed-in activation path instead of creating a second one.
            raise AccountViolation(AccountErrorCode.ACTIVATION_RESUME_REQUIRED)
        raise AccountViolation(AccountErrorCode.INVITATION_ALREADY_USED)

    email = _email(invitation.get("verified_email"))
    try:
        subject = provider.create_teacher_account(email=email, password=password)
    except teacher_identity_provider.TeacherAccountExists as exc:
        raise AccountViolation(AccountErrorCode.ACCOUNT_EXISTS) from exc
    except teacher_identity_provider.TeacherAccountPasswordRejected as exc:
        raise AccountViolation(AccountErrorCode.PASSWORD_REJECTED) from exc
    except Exception as exc:
        raise AccountViolation(AccountErrorCode.ACTIVATION_TEMPORARILY_UNAVAILABLE) from exc

    return activate_from_invitation(
        token=token,
        verified_email=email,
        issuer=issuer,
        subject=subject,
        provider=provider,
        now=lambda: instant,
    )


def full_application_for_reviewer(
    actor: dict[str, Any], application_id: str, version: int
) -> dict[str, Any]:
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    item = teacher_application_repo.get_application_version(application_id, version)
    if not item:
        raise AccountViolation(AccountErrorCode.APPLICATION_VERSION_NOT_FOUND)
    return {
        **_application_metadata(item),
        "fullName": item.get("full_name"),
        "subjects": item.get("subjects") or [],
        "statement": item.get("statement"),
    }


def _resume_activation(command: dict[str, Any], *, provider: Any, now: datetime) -> dict[str, Any]:
    if command.get("status") == "active":
        raise AccountViolation(AccountErrorCode.INVITATION_ALREADY_USED)
    user_id = command["user_id"]
    # The review decided who may hold a teacher account; the opening itself is the same
    # one every other role gets, so the number, the birthday, the change-password flag
    # and the `(address, role)` claim all come from there.
    try:
        account_provisioning_service.open_account(
            account_id=user_id,
            role=TEACHER_ROLE,
            email=command["verified_email"],
            account_status="pending_review",
            created_by=command["command_id"],
            extra_fields={"activation_command_id": command["command_id"]},
            now=lambda: now,
        )
    except AccountViolation as exc:
        # A refusal the store will repeat forever is not a step to come back to, and
        # deferring it would leave a resumable command that can never finish. The
        # status code cannot tell the two apart: losing a race for an account number
        # also answers 409, and that one happens *after* the row has landed, so
        # refusing to defer it strands the account half-opened with its address held.
        if exc.code in account_provisioning_service.TERMINAL_OPEN_ACCOUNT_CODES:
            raise
        raise _defer_activation(command, user_id=user_id, now=now) from exc

    try:
        if hasattr(provider, "ensure_teacher_identity"):
            provider.ensure_teacher_identity(
                email=command["verified_email"], user_id=user_id, group="teachers"
            )
        else:
            provider.admin_add_user_to_group(Username=command["subject"], GroupName="teachers")
        identity_repo.create_identity_binding(
            issuer=command["issuer"],
            subject=command["subject"],
            user_id=user_id,
            created_at=now.isoformat(),
            created_by=command["command_id"],
        )
    except Exception as exc:
        raise _defer_activation(command, user_id=user_id, now=now) from exc

    account_provisioning_service.transition_account_status(
        account_id=user_id,
        expected_status="pending_review",
        next_status="active",
        now=lambda: now,
    )
    latest = teacher_application_repo.get_activation_command(command["command_id"]) or command
    completed = teacher_application_repo.update_activation_command(
        command["command_id"],
        expected_version=_positive_version(
            latest.get("version"), AccountErrorCode.ACTIVATION_COMMAND_STATE_INVALID
        ),
        status="active",
        updated_at=now.isoformat(),
        evidence_reference=f"teacher-activation:{command['command_id']}",
    )
    _audit(
        stream_id=command["application_id"],
        event_type="teacher_identity_activated",
        actor_id=user_id,
        target_id=user_id,
        version=command["application_version"],
        reason_code="identity_reconciled",
        evidence_reference=completed.get("evidence_reference"),
        command_id=command["command_id"],
        created_at=now.isoformat(),
    )
    return {
        "status": "active",
        "userId": user_id,
        "applicationId": command["application_id"],
        "applicationVersion": command["application_version"],
        "evidenceReference": completed.get("evidence_reference"),
    }


def _defer_activation(
    command: dict[str, Any], *, user_id: str, now: datetime
) -> AccountViolation:
    """Park one activation where a retry can pick it up, and say so once."""
    latest = teacher_application_repo.get_activation_command(command["command_id"]) or command
    teacher_application_repo.update_activation_command(
        command["command_id"],
        expected_version=_positive_version(
            latest.get("version"), AccountErrorCode.ACTIVATION_COMMAND_STATE_INVALID
        ),
        status="provider_failed",
        updated_at=now.isoformat(),
        evidence_reference=f"teacher-activation:{command['command_id']}",
    )
    _audit(
        stream_id=command["application_id"],
        event_type="teacher_activation_deferred",
        actor_id=user_id,
        target_id=user_id,
        version=command["application_version"],
        reason_code="provider_step_incomplete",
        command_id=command["command_id"],
        created_at=now.isoformat(),
    )
    return AccountViolation(AccountErrorCode.ACTIVATION_TEMPORARILY_UNAVAILABLE)


def _require_capability(actor: dict[str, Any], required: str) -> None:
    if actor.get("role") != "admin" or actor.get("account_status") != "active":
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    grants = actor.get("current_grants") or []
    from_current_grants = any(
        isinstance(grant, dict)
        and grant.get("capability") == required
        and grant.get("status") == "active"
        and int(grant.get("version") or 0) > 0
        for grant in grants
    )
    projected = actor.get("capabilities")
    from_actor_projection = isinstance(projected, dict) and (
        projected.get(required) is True or str(projected.get(required)).lower() == "granted"
    )
    if not from_current_grants and not from_actor_projection:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)


def _audit(**event: Any) -> None:
    stream_id = str(event.pop("stream_id"))
    security_audit_repo.append_event(
        stream_id,
        {"event_id": f"event_{uuid4().hex}", **event},
    )


def _application_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "applicationId": item.get("application_id"),
        "version": int(item.get("version") or 0),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
    }


def _actor_id(actor: dict[str, Any]) -> str:
    value = str(actor.get("user_id") or actor.get("sub") or "").strip()
    if not value:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    return value


def _token_digest(token: str) -> str:
    clean = str(token or "").strip()
    if not clean:
        raise AccountViolation(AccountErrorCode.INVITATION_INVALID)
    return sha256(clean.encode("utf-8")).hexdigest()


def _email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if not email or "@" not in email or len(email) > 320:
        raise AccountViolation(AccountErrorCode.VALID_EMAIL_REQUIRED)
    return email


def _bounded(value: Any, limit: int, field: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or len(cleaned) > limit:
        raise AccountViolation(
            AccountErrorCode.INVALID_APPLICATION_FIELD, params={"field": field}
        )
    return cleaned


def _subjects(value: Any) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise AccountViolation(
            AccountErrorCode.INVALID_APPLICATION_FIELD, params={"field": "subjects"}
        )
    return [_bounded(item, 80, "subjects") for item in value]


def _timestamp(now: Callable[[], datetime] | None) -> str:
    return (now or (lambda: datetime.now(UTC)))().isoformat()


def _parse_timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _invitation_expiry(invitation: dict[str, Any]) -> datetime:
    """When this invitation stops being usable, whichever way the row spells it.

    `expires_at` is the table's time-to-live attribute, so it now holds a numeric
    epoch and the readable copy moved beside it. A row issued before that carries the
    readable value under `expires_at` and must keep being honoured.
    """
    readable = invitation.get("expires_at_iso")
    return _parse_timestamp(readable if readable is not None else invitation.get("expires_at"))


def _positive_version(value: object, code: AccountErrorCode) -> int:
    number = stored_int(value)
    if number is None or number <= 0:
        raise AccountViolation(code)
    return number
