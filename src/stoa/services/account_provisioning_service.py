"""Role-neutral account provisioning: invite and activate, or assign directly.

Two administrator-driven openings of an account, sharing one invitation lifecycle:

* invite  - create the account row, pre-allocate its number, hand out a single-use
            token the invitee exchanges for a password of their own choosing;
* assign  - create the account row, pre-allocate its number, mint one initial
            password that is readable exactly once by the issuing administrator.

The token lifecycle is lifted from the teacher application flow, which stays in place
with its review semantics. Only the digest of a token is ever stored, so an invitation
that was not delivered cannot be recovered - it has to be reissued.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.dynamodb import stored_int
from stoa.db.repositories import (
    account_deletion_repo,
    account_email_claim_repo,
    account_invitation_repo,
    capability_repo,
    identity_repo,
    public_identity_repo,
    security_audit_repo,
    user_repo,
)
from stoa.models.user import DATE_OF_BIRTH_FIELD, normalize_date_of_birth
from stoa.security.identity import MUST_CHANGE_PASSWORD_FIELD
from stoa.services import account_numbering_service


PROVISIONABLE_ROLES = ("student", "teacher", "parent", "admin")

ROLE_GROUPS = {
    "student": "students",
    "teacher": "teachers",
    "parent": "parents",
    "admin": "admins",
}

DEFAULT_INVITATION_SECONDS = 259200
MIN_INVITATION_SECONDS = 60
MAX_INVITATION_SECONDS = 1209600

# Terminal parking state for an opening that failed part-way. The row keeps the number
# it burned - numbers are never recycled - but gives the address back, so the same
# person can be opened again instead of being locked out by a half-written attempt.
FAILED_ACCOUNT_STATUS = "provisioning_failed"

# Fields the account row owns. A caller passing extra profile fields cannot rewrite
# the address, the role or the identity the claim row was taken for.
RESERVED_PROFILE_FIELDS = frozenset(
    {
        "PK",
        "SK",
        "user_id",
        "role",
        "email",
        "account_status",
        "account_number",
        "version",
        DATE_OF_BIRTH_FIELD,
        MUST_CHANGE_PASSWORD_FIELD,
        # How the account came to exist, and as what. The sign-in guard reads
        # both, so a caller's extra fields must not be able to restate them.
        "registration_command",
        "registration_role",
    }
)

# Refusals an opening will meet again on every retry: the pair belongs to another
# account, the row being resumed is not this account's, or the role cannot be opened
# at all. Everything else `open_account` raises is contention or a dependency that is
# briefly unavailable, and those are what a resumable command exists to come back to.
TERMINAL_OPEN_ACCOUNT_CODES = frozenset(
    {"account_exists", "account_state_invalid", "role_not_provisionable"}
)

INITIAL_PASSWORD_LENGTH = 16
PASSWORD_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
PASSWORD_LOWER = "abcdefghijkmnopqrstuvwxyz"
PASSWORD_DIGITS = "23456789"

# One payload for every unusable token. A missing digest and a burned digest must be
# answered with the same bytes, or the difference tells a caller which tokens existed.
INVITATION_REJECTION_STATUS = 409
INVITATION_REJECTION_DETAIL = {"code": "invitation_invalid"}


def invite_account(
    *,
    actor: dict[str, Any],
    role: str,
    email: str,
    full_name: str = "",
    date_of_birth: str | None = None,
    invitation_expiry_seconds: int = DEFAULT_INVITATION_SECONDS,
    deliver: Callable[..., None] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Open one account in `invited` state and issue its single-use token."""
    _require_account_administrator(actor)
    clean_role = _role(role)
    address = _email(email)
    instant = _instant(now)
    birthday = _date_of_birth(date_of_birth, now=instant)
    account_id = _new_account_id(clean_role)
    _create_account_row(
        account_id=account_id,
        role=clean_role,
        email=address,
        full_name=full_name,
        account_status="invited",
        date_of_birth=birthday,
        created_by=_actor_id(actor),
        now=instant,
    )
    # Everything below reserves a globally unique resource. None of it is one write, so
    # a failure part-way is compensated rather than left holding the address.
    try:
        account_number = _attach_account_number(
            account_id=account_id, role=clean_role, now=instant
        )
        issued = _issue_invitation(
            account_id=account_id,
            role=clean_role,
            email=address,
            full_name=full_name,
            account_number=account_number,
            invited_by=_actor_id(actor),
            invitation_expiry_seconds=invitation_expiry_seconds,
            deliver=deliver,
            now=instant,
        )
    except Exception:
        _release_failed_account(account_id=account_id, now=instant)
        raise
    return {
        "userId": account_id,
        "role": clean_role,
        "accountNumber": account_number,
        "email": address,
        "accountStatus": "invited",
        **issued,
    }


def assign_account(
    *,
    actor: dict[str, Any],
    role: str,
    email: str,
    provider: Any,
    full_name: str = "",
    date_of_birth: str | None = None,
    issuer: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Open one active account and return its initial password exactly once.

    The password is never written to the account row, the invitation store or the
    audit stream, so this response is the only place it exists.
    """
    _require_account_administrator(actor)
    clean_role = _role(role)
    address = _email(email)
    instant = _instant(now)
    birthday = _date_of_birth(date_of_birth, now=instant)
    account_id = _new_account_id(clean_role)
    password = generate_initial_password()
    _create_account_row(
        account_id=account_id,
        role=clean_role,
        email=address,
        full_name=full_name,
        account_status="active",
        date_of_birth=birthday,
        must_change_password=True,
        created_by=_actor_id(actor),
        now=instant,
    )
    # Same compensation as `invite_account`, extended over the identity the provider
    # mints: an assignment that dies half-way must not keep the address hostage, and
    # must not leave a sign-in behind that nothing in this system knows about.
    subject = ""
    try:
        account_number = _attach_account_number(
            account_id=account_id, role=clean_role, now=instant
        )
        subject = _create_provider_account(provider, email=address, password=password)
        _bind_identity(
            provider,
            account_id=account_id,
            role=clean_role,
            email=address,
            issuer=issuer,
            subject=subject,
            created_by=f"account-assignment:{account_id}",
            now=instant,
        )
    except Exception:
        if subject:
            _delete_provider_account(provider, email=address)
        _release_failed_account(account_id=account_id, now=instant)
        raise
    _audit(
        stream_id=account_id,
        event_type="account_assigned",
        actor_id=_actor_id(actor),
        target_id=account_id,
        action="assign_account",
        reason_code=clean_role,
        evidence_reference=f"account-number:{account_number}",
        created_at=instant.isoformat(),
    )
    return {
        "userId": account_id,
        "role": clean_role,
        "accountNumber": account_number,
        "email": address,
        "accountStatus": "active",
        "initialPassword": password,
    }


def claim_invitation(
    *,
    token: str,
    password: str,
    issuer: str,
    provider: Any,
    date_of_birth: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Exchange one single-use token for an active account with a chosen password.

    The role, the address and the account number all come from the invitation, never
    from the caller, so holding a token grants exactly the account that was opened.
    """
    instant = _instant(now)
    # Validated before the burn, for the same reason the password policy is: a
    # malformed field must not cost the invitee their single-use token.
    birthday = _date_of_birth(date_of_birth, now=instant)
    invitation = _consume_invitation(token=token, now=instant)
    digest = str(invitation.get("token_digest") or "")
    role = str(invitation.get("role") or "")
    account_id = str(invitation.get("account_id") or "")
    address = str(invitation.get("email") or "")
    # The burn has to come first - it is the single-use guard two racing claims are
    # decided by - so the way to survive a failure after it is to give the token back.
    # The account row is still `invited`, which is exactly where a retry resumes from.
    subject = ""
    try:
        if role not in PROVISIONABLE_ROLES or not account_id or not address:
            raise HTTPException(
                status_code=409, detail={"code": "invitation_state_invalid"}
            )
        subject = _create_provider_account(provider, email=address, password=password)
        _bind_identity(
            provider,
            account_id=account_id,
            role=role,
            email=address,
            issuer=issuer,
            subject=subject,
            created_by=str(invitation.get("invitation_id") or account_id),
            now=instant,
        )
        # Written while the row is still `invited`: a failure here is compensated by
        # giving the token back, and the retry resumes from exactly this state.
        if birthday:
            _record_date_of_birth(
                account_id=account_id, date_of_birth=birthday, now=instant
            )
        _transition_account_status(
            account_id=account_id,
            expected_status="invited",
            next_status="active",
            now=instant,
        )
    except Exception:
        if subject:
            _delete_provider_account(provider, email=address)
        account_invitation_repo.restore_invitation(
            digest, restored_at=instant.isoformat()
        )
        raise
    _audit(
        stream_id=account_id,
        event_type="account_invitation_consumed",
        actor_id=account_id,
        target_id=account_id,
        action="claim_invitation",
        reason_code=role,
        evidence_reference=f"account-invitation:{invitation.get('invitation_id')}",
        created_at=instant.isoformat(),
    )
    return {
        "status": "active",
        "userId": account_id,
        "role": role,
        "accountNumber": str(invitation.get("account_number") or ""),
    }


def revoke_invitation(
    *,
    actor: dict[str, Any],
    invitation_id: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Retire one unused invitation without touching the account it was opened for."""
    _require_account_administrator(actor)
    instant = _instant(now)
    invitation = account_invitation_repo.get_invitation_by_id(str(invitation_id).strip())
    if not invitation:
        raise HTTPException(status_code=404, detail={"code": "invitation_not_found"})
    digest = str(invitation.get("token_digest") or "")
    if not account_invitation_repo.revoke_invitation(digest, revoked_at=instant.isoformat()):
        raise HTTPException(status_code=409, detail={"code": "invitation_not_revocable"})
    _audit(
        stream_id=str(invitation.get("account_id") or invitation_id),
        event_type="account_invitation_revoked",
        actor_id=_actor_id(actor),
        target_id=str(invitation.get("account_id") or ""),
        action="revoke_invitation",
        evidence_reference=f"account-invitation:{invitation_id}",
        created_at=instant.isoformat(),
    )
    return {"invitationId": str(invitation_id), "status": account_invitation_repo.REVOKED_STATUS}


def reissue_invitation(
    *,
    actor: dict[str, Any],
    invitation_id: str,
    invitation_expiry_seconds: int = DEFAULT_INVITATION_SECONDS,
    deliver: Callable[..., None] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Replace an undelivered or expired invitation for an account still `invited`.

    A token is readable only at issue time, so a lost invitation cannot be recovered.
    The replacement reuses the account and the number already allocated to it, which
    is why reissuing never becomes a second way to hand out an account number.
    """
    _require_account_administrator(actor)
    instant = _instant(now)
    previous = account_invitation_repo.get_invitation_by_id(str(invitation_id).strip())
    if not previous:
        raise HTTPException(status_code=404, detail={"code": "invitation_not_found"})
    status = str(previous.get("status") or "")
    if status == account_invitation_repo.USED_STATUS:
        raise HTTPException(status_code=409, detail={"code": "invitation_already_used"})
    # A revoked invitation is not a handle on the account any more. Reissuing from one
    # would retire nothing and add a second live token, so the guarantee "reissuing
    # invalidates the previous invitation" would quietly stop holding.
    if status != account_invitation_repo.ISSUED_STATUS:
        raise HTTPException(status_code=409, detail={"code": "invitation_not_reissuable"})
    account_id = str(previous.get("account_id") or "")
    profile = user_repo.get_user(account_id)
    if not profile or str(profile.get("account_status") or "") != "invited":
        raise HTTPException(status_code=409, detail={"code": "account_not_invited"})
    # The conditional retirement is the guard, not the status read above it: a stale
    # read cannot be allowed to leave the previous token live beside the new one.
    digest = str(previous.get("token_digest") or "")
    if not account_invitation_repo.revoke_invitation(digest, revoked_at=instant.isoformat()):
        raise HTTPException(status_code=409, detail={"code": "invitation_not_reissuable"})
    # Retirement and replacement are several writes, so a failure anywhere after the
    # first is compensated: the invitation id the administrator was handed is the only
    # one they have, and leaving it revoked with no replacement strands the account.
    # `replacement` collects the row as soon as it lands, because a replacement that
    # was written but never returned has to be retired before the old one comes back -
    # otherwise the compensation is what creates the second live token.
    replacement: list[dict[str, Any]] = []
    try:
        issued = _issue_invitation(
            account_id=account_id,
            role=str(previous.get("role") or ""),
            email=str(previous.get("email") or ""),
            full_name=str(previous.get("full_name") or ""),
            account_number=str(previous.get("account_number") or ""),
            invited_by=_actor_id(actor),
            invitation_expiry_seconds=invitation_expiry_seconds,
            deliver=deliver,
            now=instant,
            created=replacement,
        )
    except Exception:
        _withdraw_replacement(replacement, now=instant)
        _restore_retired_invitation(
            digest,
            account_id=account_id,
            invitation_id=str(invitation_id),
            actor_id=_actor_id(actor),
            now=instant,
        )
        raise
    return {
        "userId": account_id,
        "role": str(previous.get("role") or ""),
        "accountNumber": str(previous.get("account_number") or ""),
        "replacedInvitationId": str(invitation_id),
        **issued,
    }


def open_account(
    *,
    account_id: str,
    role: str,
    email: str,
    account_status: str,
    full_name: str = "",
    date_of_birth: str | None = None,
    must_change_password: bool = False,
    created_by: str,
    extra_fields: dict[str, Any] | None = None,
    now: Callable[[], datetime] | None = None,
) -> str:
    """Open one account at an id its own flow already decided, and return its number.

    The entry point for a flow that owns its admission rule - teacher review is the
    one that does - and needs only the opening itself. Everything the invitation path
    gets comes from here too: the `(address, role)` claim, the birthday, the
    change-password flag and exactly one account number.

    Resumable rather than idempotent: an opening that died after the row landed is
    finished by calling again, because the row and the number are two commits and the
    gap between them is a state a retry has to be able to stand in.
    """
    clean_role = _role(role)
    address = _email(email)
    instant = _instant(now)
    birthday = _date_of_birth(date_of_birth, now=instant)
    profile = user_repo.get_user(account_id)
    if profile is None:
        _create_account_row(
            account_id=account_id,
            role=clean_role,
            email=address,
            full_name=full_name,
            account_status=account_status,
            date_of_birth=birthday,
            must_change_password=must_change_password,
            created_by=created_by,
            extra_fields=extra_fields,
            now=instant,
        )
    else:
        # Resuming is only ever resuming this account. A row that carries a different
        # address or role is somebody else's, and finishing it here would hand the
        # caller an account it never opened.
        if str(profile.get("email") or "") != address or str(profile.get("role") or "") != clean_role:
            raise HTTPException(status_code=409, detail={"code": "account_state_invalid"})
        existing = str(profile.get("account_number") or "").strip()
        if existing:
            return existing
    return _attach_account_number(account_id=account_id, role=clean_role, now=instant)


def transition_account_status(
    *,
    account_id: str,
    expected_status: str,
    next_status: str,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Move one account row between two states, refusing a stale expectation."""
    _transition_account_status(
        account_id=account_id,
        expected_status=expected_status,
        next_status=next_status,
        now=_instant(now),
    )


def generate_initial_password() -> str:
    """Mint one password that satisfies the pool policy without confusable glyphs."""
    alphabet = PASSWORD_UPPER + PASSWORD_LOWER + PASSWORD_DIGITS
    while True:
        password = "".join(
            secrets.choice(alphabet) for _ in range(INITIAL_PASSWORD_LENGTH)
        )
        if (
            any(char in PASSWORD_UPPER for char in password)
            and any(char in PASSWORD_LOWER for char in password)
            and any(char in PASSWORD_DIGITS for char in password)
        ):
            return password


def _issue_invitation(
    *,
    account_id: str,
    role: str,
    email: str,
    full_name: str,
    account_number: str,
    invited_by: str,
    invitation_expiry_seconds: int,
    deliver: Callable[..., None] | None,
    now: datetime,
    created: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    digest = _token_digest(token)
    invitation_id = f"accountinvite_{uuid4().hex}"
    seconds = min(
        MAX_INVITATION_SECONDS, max(MIN_INVITATION_SECONDS, int(invitation_expiry_seconds))
    )
    expires_at = now + timedelta(seconds=seconds)
    row = account_invitation_repo.create_invitation(
        {
            "invitation_id": invitation_id,
            "token_digest": digest,
            "account_id": account_id,
            "role": role,
            "email": email,
            "full_name": full_name,
            "account_number": account_number,
            "status": account_invitation_repo.ISSUED_STATUS,
            "version": 1,
            "invited_by": invited_by,
            "issued_at": now.isoformat(),
            # Numeric epoch so the table's time-to-live attribute actually expires the
            # row; the readable copy is kept beside it for responses and audits.
            "expires_at": int(expires_at.timestamp()),
            "expires_at_iso": expires_at.isoformat(),
        }
    )
    if created is not None:
        created.append(row)
    _audit(
        stream_id=account_id,
        event_type="account_invitation_issued",
        actor_id=invited_by,
        target_id=account_id,
        action="invite_account",
        reason_code=role,
        evidence_reference=f"account-invitation:{invitation_id}",
        created_at=now.isoformat(),
    )
    delivered = False
    if deliver is not None:
        try:
            deliver(
                email,
                activation_token=token,
                expires_at=expires_at.isoformat(),
                full_name=full_name,
            )
            delivered = True
        except Exception:
            _audit(
                stream_id=account_id,
                event_type="account_invitation_delivery_failed",
                actor_id=invited_by,
                target_id=account_id,
                action="invite_account",
                reason_code="delivery_unavailable",
                evidence_reference=f"account-invitation:{invitation_id}",
                created_at=now.isoformat(),
            )
    return {
        "invitationId": invitation_id,
        "activationToken": token,
        "expiresAt": expires_at.isoformat(),
        "invitationDelivered": delivered,
    }


def _consume_invitation(*, token: str, now: datetime) -> dict[str, Any]:
    """Burn one invitation, refusing every unusable digest with identical bytes.

    Both the digest that was never issued and the digest that was already burned take
    the same path: one read, one constant-time comparison, one expiry parse, one raise.
    """
    digest = _token_digest(token)
    stored = account_invitation_repo.get_invitation(
        digest
    ) or account_invitation_repo.absent_invitation(token_digest=digest)
    matched = secrets.compare_digest(str(stored.get("token_digest") or ""), digest)
    expired = _parse_timestamp(stored.get("expires_at_iso")) <= now
    if not matched or str(stored.get("status") or "") != account_invitation_repo.ISSUED_STATUS:
        raise _invitation_rejected()
    if expired:
        raise HTTPException(status_code=409, detail={"code": "invitation_expired"})
    if not account_invitation_repo.claim_invitation(digest, used_at=now.isoformat()):
        raise _invitation_rejected()
    return {**stored, "used_at": now.isoformat()}


def _create_account_row(
    *,
    account_id: str,
    role: str,
    email: str,
    full_name: str,
    account_status: str,
    date_of_birth: str = "",
    must_change_password: bool = False,
    created_by: str,
    extra_fields: dict[str, Any] | None = None,
    now: datetime,
) -> None:
    # A courtesy, not the guard. GSI-Email is eventually consistent, so two
    # administrators opening the same person in the same second both read it free; the
    # claim row written with the profile below is what actually breaks the tie. Kept
    # because it answers with the right code before an account number is burned.
    if user_repo.get_user_by_email_and_role(email, role):
        raise HTTPException(status_code=409, detail={"code": "account_exists"})
    claim = account_email_claim_repo.claim_operation(
        email=email, role=role, account_id=account_id, created_at=now.isoformat()
    )
    try:
        user_repo.put_user_with_email_claim(
            {
                "user_id": account_id,
                "role": role,
                "account_status": account_status,
                # Absent rather than empty when it was not supplied: "" would read as
                # a stored answer, and the minor rule has to see "not known".
                **({DATE_OF_BIRTH_FIELD: date_of_birth} if date_of_birth else {}),
                # An account the administrator opened carries a password the
                # administrator knows, so it owes the same change a reset does. An
                # invited account sets its own password at claim time and owes nothing.
                MUST_CHANGE_PASSWORD_FIELD: must_change_password,
                "email": email,
                "name": full_name,
                "created_by": created_by,
                # The provenance the sign-in guard checks. Without it a student
                # or parent account opened here is refused at sign-in, which is
                # every one of them: public sign-up is closed.
                "registration_command": public_identity_repo.ADMIN_ASSIGNMENT_COMMAND,
                "registration_role": role,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                # Last so a caller's own fields can never displace the identity the
                # claim above was taken for.
                **{
                    key: value
                    for key, value in (extra_fields or {}).items()
                    if key not in RESERVED_PROFILE_FIELDS
                },
            },
            claim_operation=claim,
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        # The pair was taken between the read above and this commit, or the profile
        # row itself already exists. Nothing was written either way.
        raise HTTPException(status_code=409, detail={"code": "account_exists"}) from exc


def _attach_account_number(*, account_id: str, role: str, now: datetime) -> str:
    """Bind exactly one number to one account row.

    The conditional write is the guard, not the read above it: a second allocation for
    an account that already carries a number is refused by the store itself, so a lost
    or stale read cannot hand the same account two numbers.
    """
    profile = user_repo.get_user(account_id)
    if not profile:
        raise HTTPException(status_code=409, detail={"code": "account_profile_missing"})
    if str(profile.get("account_number") or "").strip():
        raise HTTPException(status_code=409, detail={"code": "account_number_already_assigned"})
    try:
        account_number = account_numbering_service.allocate_account_number(
            role=role, account_id=account_id, created_at=now
        )
    except account_numbering_service.UnknownAccountRole as exc:
        raise HTTPException(status_code=422, detail={"code": "role_not_provisionable"}) from exc
    except (
        account_numbering_service.AccountNumberExhausted,
        account_numbering_service.AccountNumberAllocationFailed,
    ) as exc:
        raise HTTPException(
            status_code=503, detail={"code": "account_number_unavailable"}
        ) from exc
    operation = user_repo.profile_update_operation(
        account_id,
        update_expression=(
            "SET #account_number = :account_number, "
            "account_number_assigned_at = :assigned_at"
        ),
        expression_attribute_names={"#account_number": "account_number"},
        expression_attribute_values={
            ":account_number": account_number,
            ":assigned_at": now.isoformat(),
        },
        expected_version=_profile_version(profile),
        additional_condition_expression="attribute_not_exists(#account_number)",
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(account_id)
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    account_id, _profile_version(fence, field="generation")
                ),
                operation,
            ]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HTTPException(
            status_code=409, detail={"code": "account_number_already_assigned"}
        ) from exc
    return account_number


def _record_date_of_birth(*, account_id: str, date_of_birth: str, now: datetime) -> None:
    """Fill in a birthday the invitation did not carry, once and only once.

    The conditional write is the guard, not the read above it. An administrator who
    recorded the date when they opened the account has the authoritative answer, so
    a self-declared one can only ever fill a gap - it can never overwrite.
    """
    profile = user_repo.get_user(account_id)
    if not profile:
        raise HTTPException(status_code=409, detail={"code": "account_profile_missing"})
    if str(profile.get(DATE_OF_BIRTH_FIELD) or "").strip():
        return
    operation = user_repo.profile_update_operation(
        account_id,
        update_expression="SET #date_of_birth = :date_of_birth, updated_at = :now",
        expression_attribute_names={"#date_of_birth": DATE_OF_BIRTH_FIELD},
        expression_attribute_values={
            ":date_of_birth": date_of_birth,
            ":now": now.isoformat(),
        },
        expected_version=_profile_version(profile),
        additional_condition_expression="attribute_not_exists(#date_of_birth)",
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(account_id)
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    account_id, _profile_version(fence, field="generation")
                ),
                operation,
            ]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HTTPException(
            status_code=409, detail={"code": "account_state_invalid"}
        ) from exc


def _date_of_birth(value: Any, *, now: datetime) -> str:
    """Normalize one optional birthday, refusing it by code and never by value."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return normalize_date_of_birth(text, today=now.date())
    except ValueError:
        # Deliberately unchained: the rejected value must not survive in a traceback.
        raise HTTPException(
            status_code=422, detail={"code": "date_of_birth_invalid"}
        ) from None


def _transition_account_status(
    *, account_id: str, expected_status: str, next_status: str, now: datetime
) -> None:
    profile = user_repo.get_user(account_id)
    if not profile:
        raise HTTPException(status_code=409, detail={"code": "account_profile_missing"})
    if str(profile.get("account_status") or "") != expected_status:
        raise HTTPException(status_code=409, detail={"code": "account_status_unexpected"})
    operation = user_repo.profile_update_operation(
        account_id,
        update_expression=(
            "SET #account_status = :next_status, activated_at = :activated_at, "
            "updated_at = :activated_at"
        ),
        expression_attribute_names={"#account_status": "account_status"},
        expression_attribute_values={
            ":next_status": next_status,
            ":expected_status": expected_status,
            ":activated_at": now.isoformat(),
        },
        expected_version=_profile_version(profile),
        additional_condition_expression="#account_status = :expected_status",
    )
    try:
        fence = account_deletion_repo.require_active_account_fence(account_id)
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    account_id, _profile_version(fence, field="generation")
                ),
                operation,
            ]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "account_status_unexpected"}) from exc


def _withdraw_replacement(replacement: list[dict[str, Any]], *, now: datetime) -> None:
    """Retire a replacement that was written but never handed to anyone.

    Best effort, and ordered before the restore on purpose: the account may hold one
    live invitation, never two.
    """
    for row in replacement:
        try:
            account_invitation_repo.revoke_invitation(
                str(row.get("token_digest") or ""), revoked_at=now.isoformat()
            )
        except Exception:
            continue


def _restore_retired_invitation(
    digest: str, *, account_id: str, invitation_id: str, actor_id: str, now: datetime
) -> None:
    """Give back the invitation a reissue retired for a replacement that never landed.

    Best effort for the same reason as `_release_failed_account`: the caller is already
    raising the error that explains what went wrong, and a failure to tidy up must not
    replace it. A restore the store refuses leaves the row revoked - no worse than
    before - and is recorded so the stranded account can be found.
    """
    restored = False
    try:
        restored = account_invitation_repo.restore_revoked_invitation(
            digest, revoked_at=now.isoformat(), restored_at=now.isoformat()
        )
    except Exception:
        restored = False
    try:
        _audit(
            stream_id=account_id,
            event_type=(
                "account_invitation_reissue_rolled_back"
                if restored
                else "account_invitation_reissue_stranded"
            ),
            actor_id=actor_id,
            target_id=account_id,
            action="reissue_invitation",
            reason_code="replacement_write_failed",
            evidence_reference=f"account-invitation:{invitation_id}",
            created_at=now.isoformat(),
        )
    except Exception:
        return


def _release_failed_account(*, account_id: str, now: datetime) -> None:
    """Park a half-opened account in a terminal state and give its address back.

    Two things hold the pair, and both are released in one commit or neither is: the
    profile row, whose address is overwritten with a value carrying no `@` so it can
    never match a normalized email again, and the claim row, which is what a retry
    actually collides with. Releasing them separately would either strand the pair
    forever, or free it while a live profile still holds it. The number stays where it
    is; numbers are never recycled, and that cost is accepted.

    The invitation row is left alone. It repeats the address in GSI-Email, but
    uniqueness reads only profile rows, so the residue cannot cancel the release.

    Best effort on purpose: the caller is already raising the error that explains what
    went wrong, and a failure to tidy up must not replace it with a different one.
    """
    try:
        profile = user_repo.get_user(account_id)
        if not profile:
            return
        operation = user_repo.profile_update_operation(
            account_id,
            update_expression=(
                "SET #account_status = :failed, #email = :released_email, "
                "provisioning_failed_at = :now, updated_at = :now"
            ),
            expression_attribute_names={
                "#account_status": "account_status",
                "#email": "email",
            },
            expression_attribute_values={
                ":failed": FAILED_ACCOUNT_STATUS,
                ":released_email": f"{FAILED_ACCOUNT_STATUS}:{account_id}",
                ":now": now.isoformat(),
            },
            expected_version=_profile_version(profile),
        )
        fence = account_deletion_repo.require_active_account_fence(account_id)
        operations = [
            account_deletion_repo.active_fence_condition(
                account_id, _profile_version(fence, field="generation")
            ),
            operation,
        ]
        released = _claim_release_operation(profile, account_id=account_id)
        if released:
            operations.append(released)
        account_deletion_repo.transact(operations)
    except Exception:
        return


def _claim_release_operation(
    profile: dict[str, Any], *, account_id: str
) -> dict[str, Any] | None:
    """Give back the `(address, role)` this row still holds, when it still holds one.

    A row parked by an earlier release carries an address with no `@` and owns no
    claim any more, so there is nothing to give back and no operation to append.

    A pair standing in another account's name is read out rather than left for the
    condition: this operation travels in the same commit as the parking, so a refusal
    would cancel that too and the half-opened account would keep both its address and
    its `provisioning` status - the state this release exists to end.
    """
    email = str(profile.get("email") or "")
    role = str(profile.get("role") or "")
    try:
        account_email_claim_repo.claim_key(email=email, role=role)
    except ValueError:
        return None
    try:
        claim = account_email_claim_repo.get_claim(email=email, role=role)
    except Exception:
        # The parking is the half that matters: it is what stops a half-opened
        # account being read as a live one. A claim that cannot be read right now is
        # left where it is rather than taking the parking down with it - an address
        # still held by a parked account is what the backfill's reverse sweep finds.
        return None
    if claim is None or claim.get("account_id") != account_id:
        return None
    return account_email_claim_repo.release_operation(
        email=email, role=role, account_id=account_id
    )


def _delete_provider_account(provider: Any, *, email: str) -> None:
    """Withdraw an identity minted for an opening that then failed.

    Without this the retry meets its own orphan: the provider refuses a second account
    for the same address, so the invitee stays locked out by their own failed attempt.
    Best effort for the same reason as `_release_failed_account`.
    """
    delete = getattr(provider, "delete_account", None) or getattr(
        provider, "delete_teacher_account", None
    )
    if not callable(delete):
        return
    try:
        delete(email=email)
    except Exception:
        return


def _create_provider_account(provider: Any, *, email: str, password: str) -> str:
    create = getattr(provider, "create_account", None) or getattr(
        provider, "create_teacher_account", None
    )
    if not callable(create):
        raise HTTPException(status_code=503, detail={"code": "provisioning_unavailable"})
    try:
        subject = create(email=email, password=password)
    except Exception as exc:
        raise _provider_failure(exc) from exc
    subject = str(subject or "").strip()
    if not subject:
        raise HTTPException(status_code=503, detail={"code": "provisioning_unavailable"})
    return subject


def _bind_identity(
    provider: Any,
    *,
    account_id: str,
    role: str,
    email: str,
    issuer: str,
    subject: str,
    created_by: str,
    now: datetime,
) -> None:
    ensure = getattr(provider, "ensure_account_group", None) or getattr(
        provider, "ensure_teacher_identity", None
    )
    try:
        if callable(ensure):
            ensure(email=email, user_id=account_id, group=ROLE_GROUPS[role])
        identity_repo.create_identity_binding(
            issuer=issuer,
            subject=subject,
            user_id=account_id,
            created_at=now.isoformat(),
            created_by=created_by,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail={"code": "provisioning_temporarily_unavailable"}
        ) from exc


def _provider_failure(exc: Exception) -> HTTPException:
    name = type(exc).__name__
    if "Exists" in name:
        return HTTPException(status_code=409, detail={"code": "account_exists"})
    if "PasswordRejected" in name:
        return HTTPException(status_code=422, detail={"code": "password_rejected"})
    return HTTPException(
        status_code=503, detail={"code": "provisioning_temporarily_unavailable"}
    )


def _invitation_rejected() -> HTTPException:
    return HTTPException(
        status_code=INVITATION_REJECTION_STATUS, detail=dict(INVITATION_REJECTION_DETAIL)
    )


def _require_account_administrator(actor: dict[str, Any]) -> None:
    if actor.get("role") != "admin" or actor.get("account_status") != "active":
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})
    required = capability_repo.ADMIN_IDENTITY_MANAGER
    grants = actor.get("current_grants") or []
    from_grants = any(
        isinstance(grant, dict)
        and grant.get("capability") == required
        and grant.get("status") == "active"
        and int(grant.get("version") or 0) > 0
        for grant in grants
    )
    projected = actor.get("capabilities")
    from_projection = isinstance(projected, dict) and (
        projected.get(required) is True or str(projected.get(required)).lower() == "granted"
    )
    if not from_grants and not from_projection:
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})


def _audit(**event: Any) -> None:
    stream_id = str(event.pop("stream_id"))
    security_audit_repo.append_event(
        stream_id, {"event_id": f"event_{uuid4().hex}", **event}
    )


def _actor_id(actor: dict[str, Any]) -> str:
    value = str(actor.get("user_id") or actor.get("sub") or "").strip()
    if not value:
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})
    return value


def _new_account_id(role: str) -> str:
    return f"{role}_{uuid4().hex[:24]}"


def _role(role: str) -> str:
    clean = str(role or "").strip()
    if clean not in PROVISIONABLE_ROLES:
        raise HTTPException(status_code=422, detail={"code": "role_not_provisionable"})
    return clean


def _email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if not email or "@" not in email or len(email) > 320:
        raise HTTPException(status_code=422, detail={"code": "valid_email_required"})
    return email


def _token_digest(token: str) -> str:
    clean = str(token or "").strip()
    if not clean:
        raise _invitation_rejected()
    return sha256(clean.encode("utf-8")).hexdigest()


def _instant(now: Callable[[], datetime] | None) -> datetime:
    moment = (now or (lambda: datetime.now(UTC)))()
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _parse_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invitation_rejected() from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _profile_version(item: dict[str, Any], field: str = "version") -> int:
    number = stored_int(item.get(field))
    if number is None or number <= 0:
        raise HTTPException(status_code=409, detail={"code": "account_state_invalid"})
    return number
