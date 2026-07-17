"""Deny-first account deletion command and primary branch orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable, Mapping
from uuid import uuid4

import boto3

from stoa.config import get_settings
from stoa.db.repositories import account_deletion_repo, moderation_repo, report_repo
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import attachment_service


ACCOUNT_DELETION_BRANCH_IDS = (
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
    "conversations_messages",
    "practice_attempts",
    "learning_profiles",
    "usage_ledgers",
    "subscriptions_billing",
    "notifications_reports",
    "moderation_support",
    "teacher_ai_drafts",
    "curriculum_personalization",
    "provider_objects",
    "analytics_evidence",
    "final_identity_accounting",
)
PRIMARY_BRANCH_IDS = {
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
}


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    command_id: str
    status: str
    accepted_at: str


@dataclass(frozen=True, slots=True)
class BranchResult:
    status: str
    cursor: dict[str, str] | None = None
    debt_counts: dict[str, int] | None = None
    quiescent: bool = False
    epoch: int = 0

    def persisted(self, updated_at: str) -> dict[str, Any]:
        return {**asdict(self), "updated_at": updated_at}


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
    """Create or replay one immutable command without constructing an Actor."""
    fence = account_deletion_repo.get_account_fence(user_id, table=table)
    if not fence or type(fence.get("generation")) is not int:
        raise account_deletion_repo.AccountDeletionConflict("missing account fence")
    fingerprint = deletion_command_fingerprint(
        verified=verified,
        user_id=user_id,
        method=method,
        path=path,
        body=body,
        generation=int(fence["generation"]),
    )
    command = {
        "command_id": command_id or str(uuid4()),
        "issuer_hash": account_deletion_repo.normalized_identity_hash(
            verified.issuer.strip().rstrip("/")
        ),
        "subject_hash": account_deletion_repo.normalized_identity_hash(
            verified.subject.strip()
        ),
        "fingerprint": fingerprint,
        "method": method.strip().upper(),
        "path": path.strip(),
        "request_body_sha256": sha256(body).hexdigest(),
    }
    _fence, persisted = account_deletion_repo.begin_account_deletion(
        user_id=user_id,
        command=command,
        now_iso=now_iso,
        table=table,
    )
    immutable = {
        "issuer_hash": command["issuer_hash"],
        "subject_hash": command["subject_hash"],
        "fingerprint": fingerprint,
        "user_id": user_id,
        "generation": int(fence["generation"]),
        "method": method.strip().upper(),
        "path": path.strip(),
        "request_body_sha256": command["request_body_sha256"],
    }
    if any(persisted.get(key) != value for key, value in immutable.items()):
        raise account_deletion_repo.AccountDeletionConflict("deletion replay conflict")
    return DeletionReceipt(
        command_id=str(persisted["command_id"]),
        status="deletion_pending",
        accepted_at=str(persisted["accepted_at"]),
    )


def can_finalize_account_deletion(completed: object, *, sealed: bool = False) -> bool:
    """Plan 35 is the only caller allowed to set ``sealed=True``."""
    return bool(
        sealed
        and isinstance(completed, (set, frozenset, tuple, list))
        and set(completed) == set(ACCOUNT_DELETION_BRANCH_IDS)
    )


def _run_base_branch(
    *,
    command: Mapping[str, Any],
    previous: Mapping[str, Any],
    predicate: Callable[[Mapping[str, Any]], bool],
    mutate: Callable[[dict[str, Any]], None],
) -> BranchResult:
    """Advance one bounded strong page and require two clean full-table epochs."""
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = account_deletion_repo.scan_owned_private_rows(
        str(command["user_id"]), cursor=cursor, maximum_pages=1
    )
    matching = [dict(item) for item in page.items if predicate(item)]
    for item in matching:
        mutate(item)
    prior_debt = previous.get("debt_counts")
    pass_dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(matching)
    epoch = int(previous.get("epoch") or 0)
    if page.cursor is not None:
        return BranchResult(
            "retryable",
            cursor=page.cursor,
            debt_counts={"pass_dirty": int(pass_dirty), "processed": len(matching)},
            epoch=epoch,
        )
    if pass_dirty:
        return BranchResult(
            "retryable",
            debt_counts={"pass_dirty": 0, "processed": len(matching)},
            epoch=0,
        )
    epoch += 1
    return BranchResult(
        "complete" if epoch >= 2 else "retryable",
        debt_counts={},
        quiescent=epoch >= 2,
        epoch=epoch,
    )


def _account_profile_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    now = datetime.now(UTC).isoformat()

    def mutate(item: dict[str, Any]) -> None:
        if item.get("SK") == "PROFILE" and item.get("user_id") == command["user_id"]:
            account_deletion_repo.replace_with_deletion_tombstone(
                item,
                user_id=str(command["user_id"]),
                generation=int(command["generation"]),
                now_iso=now,
            )
        elif item.get("SK") == "PROFILE":
            account_deletion_repo.scrub_parent_profile_child(
                item,
                child_user_id=str(command["user_id"]),
                generation=int(command["generation"]),
            )
        else:
            account_deletion_repo.delete_owned_row(
                item,
                user_id=str(command["user_id"]),
                generation=int(command["generation"]),
            )

    return _run_base_branch(
        command=command,
        previous=previous,
        predicate=lambda item: item.get("SK") == "PROFILE"
        or item.get("entity_type") == "parent_student_binding",
        mutate=mutate,
    )


def _identity_cross_account_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    now = datetime.now(UTC).isoformat()
    account_deletion_repo.create_provider_revoke_debt(
        user_id=str(command["user_id"]),
        generation=int(command["generation"]),
        now_iso=now,
    )

    provider_revoked = False

    def predicate(item: Mapping[str, Any]) -> bool:
        return item.get("entity_type") in {
            "identity_binding",
            "user_identity_inventory",
            "public_identity_command",
        }

    def mutate(item: dict[str, Any]) -> None:
        nonlocal provider_revoked
        provider_username = next(
            (
                str(item.get(field)).strip()
                for field in ("normalized_email", "email", "subject")
                if isinstance(item.get(field), str) and str(item.get(field)).strip()
            ),
            None,
        )
        if provider_username and not provider_revoked:
            _revoke_provider_identity(
                str(command["user_id"]),
                int(command["generation"]),
                provider_username,
            )
            account_deletion_repo.complete_provider_revoke_debt(
                user_id=str(command["user_id"]),
                generation=int(command["generation"]),
                now_iso=now,
            )
            provider_revoked = True
        account_deletion_repo.terminalize_identity_row(
            item,
            user_id=str(command["user_id"]),
            generation=int(command["generation"]),
            now_iso=now,
        )
    return _run_base_branch(
        command=command, previous=previous, predicate=predicate, mutate=mutate
    )


def _revoke_provider_identity(user_id: str, generation: int, username: str) -> None:
    settings = get_settings()
    provider = boto3.client("cognito-idp", region_name=settings.aws_region)
    account_deletion_repo.require_deletion_account_fence(user_id, generation)
    try:
        provider.admin_user_global_sign_out(
            UserPoolId=settings.cognito_user_pool_id, Username=username
        )
        account_deletion_repo.require_deletion_account_fence(user_id, generation)
        provider.admin_delete_user(
            UserPoolId=settings.cognito_user_pool_id, Username=username
        )
    except provider.exceptions.UserNotFoundException:
        return


def _capability_scope_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    now = datetime.now(UTC).isoformat()

    def mutate(item: dict[str, Any]) -> None:
        account_deletion_repo.terminalize_identity_row(
            item,
            user_id=str(command["user_id"]),
            generation=int(command["generation"]),
            now_iso=now,
        )

    return _run_base_branch(
        command=command,
        previous=previous,
        predicate=lambda item: str(item.get("entity_type") or "").startswith(
            "capability_"
        ),
        mutate=mutate,
    )


def _question_ocr_session_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    now = datetime.now(UTC).isoformat()

    def mutate(item: dict[str, Any]) -> None:
        account_deletion_repo.replace_with_deletion_tombstone(
            item,
            user_id=str(command["user_id"]),
            generation=int(command["generation"]),
            now_iso=now,
        )

    return _run_base_branch(
        command=command,
        previous=previous,
        predicate=lambda item: item.get("entity_type")
        in {"question", "teacher_session", "teacher_escalation_intent"}
        or str(item.get("PK") or "").startswith(("QUESTION#", "SESSION#")),
        mutate=mutate,
    )


def _attachments_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    settings = get_settings()
    result = attachment_service.purge_student_attachments(
        str(command["user_id"]),
        account_fence_generation=int(command["generation"]),
        cursors=previous.get("cursor") if isinstance(previous, Mapping) else None,
        s3=boto3.client("s3", region_name=settings.aws_region),
        settings=settings,
    )
    return BranchResult(
        str(result.status),
        cursor=dict(result.cursors),
        debt_counts=dict(result.debt_counts),
        quiescent=bool(result.quiescent),
        epoch=int(previous.get("epoch") or 0) + (1 if result.quiescent else 0),
    )


def _moderation_support_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    """Scrub one strong moderation page and require two later zero epochs."""
    raw_cursor = previous.get("cursor")
    cursor = None
    if isinstance(raw_cursor, Mapping):
        if set(raw_cursor) == {"PK", "SK"}:
            cursor = {"PK": str(raw_cursor["PK"]), "SK": str(raw_cursor["SK"])}
        elif set(raw_cursor) == {
            "summary_pk",
            "summary_sk",
            "event_pk",
            "event_sk",
        }:
            summary_cursor = (
                str(raw_cursor["summary_pk"]),
                str(raw_cursor["summary_sk"]),
            )
            event_cursor = (
                str(raw_cursor["event_pk"]),
                str(raw_cursor["event_sk"]),
            )
            if summary_cursor != event_cursor or not all(summary_cursor):
                raise account_deletion_repo.AccountDeletionConflict(
                    "moderation family cursors diverged"
                )
            cursor = {"PK": summary_cursor[0], "SK": summary_cursor[1]}
        else:
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid moderation branch cursor"
            )
    page = moderation_repo.scan_moderation_private_rows(
        str(command["user_id"]), cursor=cursor, maximum_pages=1
    )
    now = datetime.now(UTC).isoformat()
    debt: dict[str, int] = {}
    processed = 0
    for item in page.items:
        identity = f"{item.get('PK', '')}|{item.get('SK', '')}"
        try:
            moderation_repo.scrub_moderation_row(
                item,
                user_id=str(command["user_id"]),
                generation=int(command["generation"]),
                now_iso=now,
            )
            processed += 1
        except Exception:
            debt[identity] = 1
    if page.unresolved:
        debt["unresolved_lineage"] = int(page.unresolved)

    prior_debt = previous.get("debt_counts")
    pass_dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(page.items) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update({"pass_dirty": int(pass_dirty), "processed": processed})
    if page.cursor is not None:
        family_cursor = {
            "summary_pk": page.cursor["PK"],
            "summary_sk": page.cursor["SK"],
            "event_pk": page.cursor["PK"],
            "event_sk": page.cursor["SK"],
        }
        return BranchResult(
            "retryable", cursor=family_cursor, debt_counts=debt, epoch=epoch
        )
    if pass_dirty:
        if any(key not in {"pass_dirty", "processed"} for key in debt):
            return BranchResult("retryable", debt_counts=debt, epoch=0)
        return BranchResult(
            "retryable",
            debt_counts={"pass_dirty": 0, "processed": processed},
            epoch=0,
        )
    epoch += 1
    return BranchResult(
        "complete" if epoch >= 2 else "retryable",
        debt_counts={},
        quiescent=epoch >= 2,
        epoch=epoch,
    )


def _run_report_row_branch(
    *,
    command: Mapping[str, Any],
    previous: Mapping[str, Any],
    family: str,
) -> BranchResult:
    """Advance one strong report-family page and require two clean epochs."""
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = report_repo.scan_report_private_rows(
        str(command["user_id"]), cursor=cursor, maximum_pages=1
    )
    now = datetime.now(UTC).isoformat()
    debt: dict[str, int] = {}
    processed = 0
    for item in page.items:
        pk = str(item.get("PK") or "")
        selected = (
            family == "all"
            or (family == "support" and pk.startswith("SUPPORT_"))
            or (
                family == "records"
                and not pk.startswith("SUPPORT_")
                and not str(item.get("SK") or "").startswith("REPORT_OBJECT#")
            )
        )
        if not selected:
            continue
        identity = f"{pk}|{item.get('SK', '')}"
        try:
            report_repo.scrub_report_private_row(
                item,
                owner_id=str(command["user_id"]),
                generation=int(command["generation"]),
                now_iso=now,
            )
            processed += 1
        except Exception:
            debt[identity] = 1
    if page.unresolved:
        debt["unresolved_lineage"] = int(page.unresolved)
    prior_debt = previous.get("debt_counts")
    dirty = bool(isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty"))
    dirty = dirty or bool(page.items) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update({"pass_dirty": int(dirty), "processed": processed})
    if page.cursor is not None:
        return BranchResult("retryable", cursor=page.cursor, debt_counts=debt, epoch=epoch)
    if dirty:
        if any(key not in {"pass_dirty", "processed"} for key in debt):
            return BranchResult("retryable", debt_counts=debt, epoch=0)
        return BranchResult(
            "retryable",
            debt_counts={"pass_dirty": 0, "processed": processed},
            epoch=0,
        )
    epoch += 1
    return BranchResult(
        "complete" if epoch >= 2 else "retryable",
        debt_counts={},
        quiescent=epoch >= 2,
        epoch=epoch,
    )


def _report_records_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_report_row_branch(command=command, previous=previous, family="records")


def _report_artifacts_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    """Persist independent artifact discovery progress; provider debt blocks clean epochs."""
    return _run_report_row_branch(command=command, previous=previous, family="all")


def _support_recovery_feed_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_report_row_branch(command=command, previous=previous, family="support")


BRANCH_HANDLERS: dict[str, Callable[..., BranchResult]] = {
    # Derived rows must resolve their authoritative question owner before the
    # primary question branch can replace that question with a tombstone.
    "moderation_support": _moderation_support_branch,
    "account_profile": _account_profile_branch,
    "identity_cross_account": _identity_cross_account_branch,
    "capability_scope": _capability_scope_branch,
    "question_ocr_session": _question_ocr_session_branch,
    "attachments": _attachments_branch,
    # The exact Plan 35 registry retains the aggregate notifications_reports
    # branch. These independently persisted sub-results close its report stores.
    "report_records": _report_records_branch,
    "report_artifacts": _report_artifacts_branch,
    "support_recovery_feed": _support_recovery_feed_branch,
}


class AccountDeletionService:
    """Resume independent primary branches from one durable command lease."""

    def __init__(
        self,
        *,
        repository: Any = account_deletion_repo,
        branch_handlers: Mapping[str, Callable[..., BranchResult]] | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.branch_handlers = dict(branch_handlers or BRANCH_HANDLERS)
        self.now = now or (lambda: "")

    def continue_command(self, command_id: str) -> None:
        command = self._load_command(command_id)
        if not command:
            return
        for branch_id in self.branch_handlers:
            previous = (command.get("branch_results") or {}).get(branch_id) or {}
            if previous.get("status") == "complete" and previous.get("quiescent") is True:
                continue
            handler = self.branch_handlers[branch_id]
            try:
                result = handler(command=command, previous=previous)
            except Exception:
                result = BranchResult("retryable", debt_counts={"dependency": 1})
            self.repository.persist_branch_result(
                command, branch_id, result.persisted(self.now())
            )
        # Deliberately no aggregate finalizer. Plans 30-34 add the remaining
        # branches and Plan 35 alone seals the exact registry.

    def _load_command(self, command_id: str) -> dict[str, Any] | None:
        loader = getattr(self.repository, "get_command_by_id", None)
        if callable(loader):
            return loader(command_id)
        if self.repository is account_deletion_repo:
            return account_deletion_repo.get_command_by_id(command_id)
        return None
