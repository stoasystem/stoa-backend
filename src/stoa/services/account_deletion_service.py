"""Accepting an account deletion: who asked, the command, and where it stands.

`accept_account_deletion` is the one way in, whoever asks: the account itself
(`DELETE /auth/me`) or an operator call. It moves the account's fence to
`deletion_pending` and writes the command in the same commit; the scheduled job
then carries the command through the catalog's three steps
(`stoa.services.account_deletion_flow`, #641). The 17 branches, their sealed
inventories and the scans they read with are gone (#642).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import logging
from typing import Any, Mapping
from uuid import uuid4

from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import account_deletion_flow, owner_registry_sweep


logger = logging.getLogger(__name__)


class DeletionNotReady(account_deletion_repo.AccountDeletionConflict):
    """A new deletion refused for now: the owner registry is not vouched for (#641)."""



@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    command_id: str
    status: str
    accepted_at: str
    completed_at: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status == "deleted" and self.completed_at is not None


def terminal_deletion_receipt(command: Mapping[str, Any]) -> DeletionReceipt:
    """Project only the exact nested receipt persisted by terminalization."""
    if command.get("status") != "complete":
        raise account_deletion_repo.AccountDeletionConflict(
            "deletion command is not terminal"
        )
    receipt = command.get("receipt")
    if not isinstance(receipt, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "terminal deletion receipt is unavailable"
        )
    command_id = receipt.get("command_id")
    completed_at = receipt.get("completed_at")
    if (
        not isinstance(command_id, str)
        or not command_id
        or command_id != command.get("command_id")
        or receipt.get("status") != "deleted"
        or not isinstance(completed_at, str)
        or not completed_at
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid terminal deletion receipt"
        )
    try:
        parsed_completed_at = datetime.fromisoformat(completed_at)
    except ValueError as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid terminal deletion receipt"
        ) from exc
    offset = (
        parsed_completed_at.utcoffset()
        if parsed_completed_at.tzinfo is not None
        else None
    )
    if offset is None or offset.total_seconds() != 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid terminal deletion receipt"
        )
    accepted_at = command.get("accepted_at")
    if not isinstance(accepted_at, str):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid terminal deletion receipt"
        )
    return DeletionReceipt(
        command_id=command_id,
        status="deleted",
        accepted_at=accepted_at,
        completed_at=completed_at,
    )


# How old the owner registry sweep's last clean run may be for a new deletion
# to be accepted: a daily schedule, plus slack. The flow reads only the
# account's derived and registered partitions, so the registry must be whole.
REGISTRY_SWEEP_MAX_AGE = timedelta(hours=36)


def registry_path_ready(*, table: Any | None = None, now: datetime | None = None) -> bool:
    """Whether the last owner registry sweep vouches for the registry (#397).

    Its result row must say the run reached the end of the table, found no
    missing registration, and finished within `REGISTRY_SWEEP_MAX_AGE`. A
    missing, unreadable or stale row is a no.
    """
    try:
        marker = account_deletion_repo.get_row(
            owner_registry_sweep.RUN_MARKER_KEY, table=table
        )
    except Exception:
        return False
    if not marker or marker.get("complete") is not True:
        return False
    if stored_int(marker.get("missing_registrations")) != 0:
        return False
    try:
        completed = datetime.fromisoformat(str(marker.get("completed_at")))
    except ValueError:
        return False
    if completed.tzinfo is None:
        return False
    return (now or datetime.now(UTC)) - completed <= REGISTRY_SWEEP_MAX_AGE


def deletion_command_fingerprint(
    *,
    verified: VerifiedAccessToken,
    user_id: str,
    method: str,
    path: str,
    body: bytes,
    generation: int,
) -> str:
    if not isinstance(body, bytes):
        raise account_deletion_repo.AccountDeletionConflict("request body must be bytes")
    fields = (
        verified.issuer.strip().rstrip("/"),
        verified.subject.strip(),
        user_id.strip(),
        method.strip().upper(),
        path.strip(),
        sha256(body).hexdigest(),
        str(generation),
    )
    if any(not field for field in fields):
        raise account_deletion_repo.AccountDeletionConflict("incomplete deletion identity")
    framed = b"account-delete-command.v1"
    for field in fields:
        encoded = field.encode("utf-8")
        framed += len(encoded).to_bytes(4, "big") + encoded
    return sha256(framed).hexdigest()


def operator_deletion_command_fingerprint(
    *, initiated_by: str, user_id: str, generation: int
) -> str:
    """The fingerprint of a deletion an operator accepted (#396).

    Framed under its own tag, so it can never equal a self-deletion's
    fingerprint: a token-bound replay of `DELETE /auth/me` and an operator's
    command for the same account and generation stay two different commands,
    and whichever came second is refused by `begin_account_deletion`. The reason
    is not part of it - it says why, not what - so a second acceptance racing the
    first for the same account and generation replays the first.
    """
    fields = (initiated_by.strip(), user_id.strip(), str(generation))
    if any(not field for field in fields):
        raise account_deletion_repo.AccountDeletionConflict("incomplete deletion identity")
    framed = b"account-delete-command.operator.v1"
    for field in fields:
        encoded = field.encode("utf-8")
        framed += len(encoded).to_bytes(4, "big") + encoded
    return sha256(framed).hexdigest()


@dataclass(frozen=True, slots=True)
class SelfInitiated:
    """The account closing itself: `DELETE /auth/me`, bound to its verified token.

    The command carries the token's issuer and subject hashes, so the route can
    replay it after the account's binding is gone (`deps.get_deletion_command`).
    """

    verified: VerifiedAccessToken
    method: str = "DELETE"
    path: str = "/auth/me"
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class OperatorInitiated:
    """An operator closing someone else's account through an operator call (#396).

    `initiated_by` is the operator's audit id (`operator:agent_mcp`), never a web
    account; `reason` is the one sentence the operator gave, kept on the command.
    """

    initiated_by: str
    reason: str


DeletionInitiator = SelfInitiated | OperatorInitiated


def _initiator_fields(
    initiator: DeletionInitiator, *, user_id: str, generation: int
) -> dict[str, Any]:
    """The command fields that say who asked; also what a replay must match."""
    if isinstance(initiator, SelfInitiated):
        verified, body = initiator.verified, initiator.body
        return {
            "issuer_hash": account_deletion_repo.normalized_identity_hash(
                verified.issuer.strip().rstrip("/")
            ),
            "subject_hash": account_deletion_repo.normalized_identity_hash(
                verified.subject.strip()
            ),
            "fingerprint": deletion_command_fingerprint(
                verified=verified,
                user_id=user_id,
                method=initiator.method,
                path=initiator.path,
                body=body,
                generation=generation,
            ),
            "method": initiator.method.strip().upper(),
            "path": initiator.path.strip(),
            "request_body_sha256": sha256(body).hexdigest(),
        }
    if isinstance(initiator, OperatorInitiated):
        initiated_by = initiator.initiated_by.strip()
        reason = initiator.reason.strip()
        if not initiated_by or not reason or initiated_by == user_id:
            raise account_deletion_repo.AccountDeletionConflict("incomplete deletion initiator")
        return {
            "fingerprint": operator_deletion_command_fingerprint(
                initiated_by=initiated_by, user_id=user_id, generation=generation
            ),
            "initiated_by": initiated_by,
        }
    raise account_deletion_repo.AccountDeletionConflict("unknown deletion initiator")


def accept_account_deletion(
    *,
    user_id: str,
    initiator: DeletionInitiator,
    now_iso: str,
    table: Any | None = None,
    command_id: str | None = None,
) -> DeletionReceipt:
    """Accept one deletion of `user_id`, or replay the one already accepted.

    The one way into the deletion pipeline, whoever asks (#396): the account
    itself through `DELETE /auth/me`, or an operator call. Either way the same
    fence moves to `deletion_pending` in the same transaction that writes the
    same `DELETE_COMMAND` row, and the same scheduled sweep and continuation
    carry it to the end. Only the fields saying who asked differ: a
    self-deletion's command is bound to its token (`SelfInitiated`), an
    operator's names the operator and its reason (`OperatorInitiated`). Each
    command records `initiated_by`; for a self-deletion that is the account.

    Constructs no Actor. Deciding whether this account may be closed by this
    initiator is the caller's: the route lets an account close itself, the
    operator call checks its own rules first.

    A command accepted now runs the catalog's three steps
    (`account_deletion_flow`, #641): it carries that flow and the catalog's
    hash, and is refused while the owner registry is not vouched for
    (`registry_path_ready`), since that flow reads only the account's
    registered partitions. Replaying a command already accepted asks neither.
    """
    fence = account_deletion_repo.get_account_fence(user_id, table=table)
    if not fence or stored_int(fence.get("generation")) is None:
        raise account_deletion_repo.AccountDeletionConflict("missing account fence")
    generation = int(fence["generation"])
    identity = _initiator_fields(initiator, user_id=user_id, generation=generation)
    if fence.get("status") not in {"deletion_pending", "deleted"} and not registry_path_ready(
        table=table
    ):
        logger.warning("account_deletion_refused reason=registry_not_ready")
        raise DeletionNotReady("owner registry is not vouched for")
    command: dict[str, Any] = {
        "command_id": command_id or str(uuid4()),
        **identity,
        "flow": account_deletion_flow.CATALOG_FLOW,
        "catalog_sha256": account_deletion_flow.current_catalog_sha256(),
    }
    if isinstance(initiator, OperatorInitiated):
        command["reason"] = initiator.reason.strip()
    else:
        command["initiated_by"] = user_id
    _fence, persisted = account_deletion_repo.begin_account_deletion(
        user_id=user_id,
        command=command,
        now_iso=now_iso,
        table=table,
    )
    # Who asked and for what: a replay must match. How it is carried out (the
    # flow, the catalog it was sealed with) is the command's own and is not
    # compared - a replay after a deploy still answers with the same receipt.
    immutable = {**identity, "user_id": user_id, "generation": generation}
    if any(persisted.get(key) != value for key, value in immutable.items()):
        raise account_deletion_repo.AccountDeletionConflict("deletion replay conflict")
    # A self-deletion accepted before #396 carries no initiator; it is the account's own.
    if persisted.get("initiated_by", user_id) != command.get("initiated_by", user_id):
        raise account_deletion_repo.AccountDeletionConflict("deletion replay conflict")
    if persisted.get("status") == "complete":
        return terminal_deletion_receipt(persisted)
    return DeletionReceipt(
        command_id=str(persisted["command_id"]),
        status="deletion_pending",
        accepted_at=str(persisted["accepted_at"]),
    )


def begin_or_replay_deletion(
    *,
    verified: VerifiedAccessToken,
    user_id: str,
    method: str,
    path: str,
    body: bytes,
    now_iso: str,
    table: Any | None = None,
    command_id: str | None = None,
) -> DeletionReceipt:
    """Create or replay one token-bound self-deletion command without an Actor."""
    return accept_account_deletion(
        user_id=user_id,
        initiator=SelfInitiated(verified=verified, method=method, path=path, body=body),
        now_iso=now_iso,
        table=table,
        command_id=command_id,
    )


@dataclass(frozen=True, slots=True)
class DeletionStatus:
    """Where an account stands in the deletion pipeline, from its fence and command.

    `state` is `none` (no deletion accepted), `in_progress` (accepted, not yet
    complete) or `completed`. `initiated_by` is `self` for an account that closed
    itself, otherwise the operator id the command names.
    """

    state: str
    command_id: str | None = None
    accepted_at: str | None = None
    completed_at: str | None = None
    initiated_by: str | None = None


def deletion_status(user_id: str, *, table: Any | None = None) -> DeletionStatus:
    """Read the fence, and the command it names, for `user_id` (two strong reads)."""
    fence = account_deletion_repo.get_account_fence(user_id, table=table)
    status = str((fence or {}).get("status") or "")
    if status not in {"deletion_pending", "deleted"}:
        return DeletionStatus("none")
    command_id = str((fence or {}).get("command_id") or "") or None
    command = (
        account_deletion_repo.get_deletion_command(user_id, command_id, table=table)
        if command_id
        else None
    ) or {}
    initiated_by = str(command.get("initiated_by") or "") or (
        user_id if command.get("path") == "/auth/me" else ""
    )
    accepted_at = str(
        (fence or {}).get("deletion_accepted_at") or command.get("accepted_at") or ""
    )
    completed = status == "deleted"
    return DeletionStatus(
        state="completed" if completed else "in_progress",
        command_id=command_id,
        accepted_at=accepted_at or None,
        completed_at=(
            str((fence or {}).get("deleted_at") or command.get("completed_at") or "") or None
        )
        if completed
        else None,
        initiated_by=("self" if initiated_by == user_id else initiated_by) or None,
    )
