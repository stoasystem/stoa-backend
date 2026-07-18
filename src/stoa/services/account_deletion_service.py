"""Deny-first account deletion command and primary branch orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

import boto3

from stoa.config import get_settings
from stoa.db.repositories import (
    account_deletion_repo,
    adaptive_learning_repo,
    ai_teacher_tools_repo,
    attachment_repo,
    curriculum_analytics_repo,
    moderation_repo,
    notification_repo,
    practice_repo,
    report_repo,
    websocket_repo,
)
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import attachment_service


ACCOUNT_DELETION_BRANCH_IDS = (
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
    "moderation",
    "report_records",
    "report_artifacts",
    "support_recovery_feed",
    "conversation_messages",
    "practice_progress",
    "adaptive_assignment",
    "learning_memory",
    "ai_teacher_draft",
    "curriculum_signal",
    "notification_device_realtime",
    "external_delivery_debt",
)
PRIMARY_BRANCH_IDS = {
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
}

DeletionCommandClaim = account_deletion_repo.DeletionCommandClaim
DeletionCommandClaimLost = account_deletion_repo.DeletionCommandClaimLost


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
    legal_retention_blocked: int = 0
    external_receipts: tuple[dict[str, Any], ...] = ()

    def persisted(
        self,
        updated_at: str,
        *,
        generation: int | None = None,
        handler_version: str | None = None,
        subfamilies: tuple[str, ...] | list[str] | None = None,
    ) -> dict[str, Any]:
        value = {**asdict(self), "updated_at": updated_at}
        if generation is not None:
            value["generation"] = generation
        if handler_version is not None:
            value["handler_version"] = handler_version
        if subfamilies is not None:
            value["subfamilies"] = list(subfamilies)
        return value


def _default_inventory_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "security"
        / "phase-473-private-store-inventory.json"
    )


def load_private_store_seal(path: Path | str | None = None) -> dict[str, Any]:
    """Load and strictly validate the immutable runtime branch projection."""
    inventory_path = Path(path) if path is not None else _default_inventory_path()
    try:
        raw = inventory_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise account_deletion_repo.AccountDeletionConflict(
            "private-store inventory unavailable"
        ) from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != (
        "phase-473-private-store-inventory.v1"
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "private-store inventory schema mismatch"
        )
    branch_ids = payload.get("branch_ids")
    registry = payload.get("branch_registry")
    if branch_ids != list(ACCOUNT_DELETION_BRANCH_IDS) or not isinstance(registry, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "private-store branch registry mismatch"
        )
    branches: list[dict[str, Any]] = []
    contracts: dict[str, dict[str, Any]] = {}
    for index, raw_branch in enumerate(registry):
        if not isinstance(raw_branch, Mapping):
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid private-store branch contract"
            )
        branch = dict(raw_branch)
        branch_id = branch.get("branch_id")
        version = branch.get("handler_version")
        roots = branch.get("required_roots")
        subfamilies = branch.get("subfamilies")
        if (
            branch_id != ACCOUNT_DELETION_BRANCH_IDS[index]
            or not isinstance(version, str)
            or not version
            or not isinstance(roots, list)
            or not roots
            or any(not isinstance(value, str) or not value for value in roots)
            or not isinstance(subfamilies, list)
            or not subfamilies
            or any(not isinstance(value, str) or not value for value in subfamilies)
        ):
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid private-store branch contract"
            )
        branches.append(branch)
        contracts[str(branch_id)] = {
            "handler_version": version,
            "required_roots": list(roots),
            "subfamilies": list(subfamilies),
        }
    return {
        "inventory_sha256": sha256(raw).hexdigest(),
        "branches": branches,
        "branch_contracts": contracts,
    }


def _result_debt_is_zero(result: Mapping[str, Any]) -> bool:
    debt = result.get("debt_counts")
    if debt is None:
        return True
    if not isinstance(debt, Mapping):
        return False
    allowed_nonblocking = {
        "external_accepted",
        "external_delivered",
        "external_unknown",
        "processed",
        "pass_dirty",
    }
    for key, value in debt.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        if key not in allowed_nonblocking and value != 0:
            return False
        if key == "pass_dirty" and value != 0:
            return False
    return True


def validate_deletion_seal(
    *, command: Mapping[str, Any], fence: Mapping[str, Any], seal: Mapping[str, Any]
) -> bool:
    """Return true only for one exact current-generation, debt-free seal."""
    try:
        generation = command["generation"]
        command_id = command["command_id"]
        contracts = seal["branch_contracts"]
        branches = seal["branches"]
        results = command["branch_results"]
    except (KeyError, TypeError):
        return False
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
        or command.get("status") not in {"running", "pending"}
        or command.get("inventory_sha256") != seal.get("inventory_sha256")
        or command.get("branch_ids") != list(ACCOUNT_DELETION_BRANCH_IDS)
        or command.get("branch_contracts") != contracts
        or fence.get("status") != "deletion_pending"
        or fence.get("generation") != generation
        or fence.get("command_id") != command_id
        or not isinstance(results, Mapping)
        or set(results) != set(ACCOUNT_DELETION_BRANCH_IDS)
        or not isinstance(branches, list)
    ):
        return False
    for branch in branches:
        if not isinstance(branch, Mapping):
            return False
        branch_id = branch.get("branch_id")
        if branch_id not in results or branch_id not in contracts:
            return False
        result = results[branch_id]
        contract = contracts[branch_id]
        if (
            not isinstance(result, Mapping)
            or result.get("status") != "complete"
            or result.get("quiescent") is not True
            or type(result.get("epoch")) is not int
            or int(result["epoch"]) < 2
            or result.get("generation") != generation
            or result.get("handler_version") != contract["handler_version"]
            or result.get("subfamilies") != contract["subfamilies"]
            or result.get("cursor") not in (None, {})
            or result.get("legal_retention_blocked", 0) != 0
            or not _result_debt_is_zero(result)
        ):
            return False
        receipts = result.get("external_receipts", ())
        if not isinstance(receipts, (list, tuple)):
            return False
        for receipt in receipts:
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("status")
                not in {"accepted", "delivered", "provider_acceptance_unknown"}
                or receipt.get("claim", "outside_backend_purge_authority")
                != "outside_backend_purge_authority"
            ):
                return False
    return True


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
    seal = load_private_store_seal()
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
        "inventory_sha256": seal["inventory_sha256"],
        "branch_ids": list(ACCOUNT_DELETION_BRANCH_IDS),
        "branch_contracts": seal["branch_contracts"],
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
        "inventory_sha256": seal["inventory_sha256"],
        "branch_ids": list(ACCOUNT_DELETION_BRANCH_IDS),
        "branch_contracts": seal["branch_contracts"],
    }
    if any(persisted.get(key) != value for key, value in immutable.items()):
        raise account_deletion_repo.AccountDeletionConflict("deletion replay conflict")
    return DeletionReceipt(
        command_id=str(persisted["command_id"]),
        status=("deleted" if persisted.get("status") == "complete" else "deletion_pending"),
        accepted_at=str(persisted["accepted_at"]),
    )


def can_finalize_account_deletion(
    completed: object,
    *,
    sealed: bool = False,
    command: Mapping[str, Any] | None = None,
    fence: Mapping[str, Any] | None = None,
    seal: Mapping[str, Any] | None = None,
) -> bool:
    """Plan 35 is the only caller allowed to set ``sealed=True``."""
    if not sealed or command is None or fence is None or seal is None:
        return False
    if completed is not command.get("branch_results") and completed != command.get(
        "branch_results"
    ):
        return False
    return validate_deletion_seal(command=command, fence=fence, seal=seal)


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
        try:
            mutate(item)
        except account_deletion_repo.AccountDeletionRowConflict:
            return BranchResult(
                "retryable",
                cursor=cursor,
                debt_counts={"row_conflict": 1, "pass_dirty": 1},
                epoch=0,
            )
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
    selected_rows = 0
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
        selected_rows += 1
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
    dirty = dirty or bool(selected_rows) or bool(debt)
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
    """Delete exact report versions; legal holds and ambiguity remain debt."""
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = report_repo.scan_report_private_rows(
        str(command["user_id"]), cursor=cursor, maximum_pages=1
    )
    s3 = boto3.client("s3", region_name=get_settings().aws_region)
    bucket = get_settings().report_artifacts_bucket
    debt: dict[str, int] = {}
    processed = 0
    selected = 0
    now = datetime.now(UTC).isoformat()
    for item in page.items:
        if not str(item.get("SK") or "").startswith("REPORT_OBJECT#"):
            continue
        selected += 1
        identity = f"{item.get('PK', '')}|{item.get('SK', '')}"
        try:
            candidate = dict(item)
            if not candidate.get("version_id"):
                coordinate = report_repo.reconcile_report_object_version(
                    s3_client=s3,
                    bucket=bucket,
                    object_key=str(candidate["object_key"]),
                    operation_id=str(candidate["operation_id"]),
                    body_sha256=str(candidate["body_sha256"]),
                    body_length=int(candidate["body_length"]),
                )
                candidate.update(coordinate)
            result = report_repo.purge_report_object_intent(
                candidate,
                owner_id=str(command["user_id"]),
                generation=int(command["generation"]),
                bucket=bucket,
                s3_client=s3,
                now_iso=now,
            )
            if result["status"] == "purged":
                processed += 1
            else:
                debt[str(result["status"])] = debt.get(str(result["status"]), 0) + 1
        except Exception:
            debt[identity] = 1
    prior_debt = previous.get("debt_counts")
    dirty = bool(isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty"))
    dirty = dirty or bool(selected) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update({"pass_dirty": int(dirty), "processed": processed})
    if page.cursor is not None:
        return BranchResult("retryable", cursor=page.cursor, debt_counts=debt, epoch=epoch)
    if dirty:
        if any(key not in {"pass_dirty", "processed"} for key in debt):
            return BranchResult("retryable", debt_counts=debt, epoch=0)
        return BranchResult(
            "retryable", debt_counts={"pass_dirty": 0, "processed": processed}, epoch=0
        )
    epoch += 1
    return BranchResult(
        "complete" if epoch >= 2 else "retryable",
        debt_counts={},
        quiescent=epoch >= 2,
        epoch=epoch,
    )


def _support_recovery_feed_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_report_row_branch(command=command, previous=previous, family="support")


def _conversation_messages_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    """Drain commands/references before scrubbing one strong conversation page."""
    owner_id = str(command["user_id"])
    generation = int(command["generation"])
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = attachment_repo.scan_conversation_private_rows(
        owner_id, cursor=cursor, maximum_pages=1
    )
    debt: dict[str, int] = {}
    processed = 0
    now_iso = datetime.now(UTC).isoformat()
    settings = get_settings()
    s3 = boto3.client("s3", region_name=settings.aws_region)
    released_conversations: set[str] = set()
    for item in page.items:
        identity = f"{item.get('PK')}|{item.get('SK')}"
        try:
            if (
                item.get("entity_type") == "message_command"
                and item.get("status") in attachment_repo.CONVERSATION_ACTIVE_COMMAND_STATES
            ):
                attachment_repo.cancel_stale_message_command(
                    item,
                    owner_id=owner_id,
                    deletion_generation=generation,
                    now_iso=now_iso,
                )
            conversation_id = str(item.get("conversation_id") or "")
            if item.get("attachment_ids") and conversation_id not in released_conversations:
                release = attachment_service.release_conversation_attachments(
                    owner_id=owner_id,
                    conversation_id=conversation_id,
                    s3=s3,
                    settings=settings,
                )
                released_conversations.add(conversation_id)
                disposition = (
                    release.get("disposition")
                    if isinstance(release, Mapping)
                    else getattr(release, "disposition", None)
                )
                if disposition is not None and str(disposition) not in {
                    "complete",
                    "RetentionDisposition.COMPLETE",
                }:
                    debt[f"association:{conversation_id}"] = 1
                    continue
            attachment_repo.scrub_conversation_private_row(
                item,
                owner_id=owner_id,
                generation=generation,
                now_iso=now_iso,
            )
            processed += 1
        except Exception:
            debt[identity] = 1

    prior_debt = previous.get("debt_counts")
    dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(page.items) or bool(debt)
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


def _run_learning_scrub_branch(
    *,
    command: Mapping[str, Any],
    previous: Mapping[str, Any],
    scan: Callable[..., Any],
    scrub: Callable[..., Any],
    scan_kwargs: Mapping[str, Any] | None = None,
) -> BranchResult:
    """Advance one learning family with item debt and two later clean scans."""
    owner_id = str(command["user_id"])
    generation = int(command["generation"])
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = scan(
        owner_id,
        cursor=cursor,
        maximum_pages=1,
        **dict(scan_kwargs or {}),
    )
    debt: dict[str, int] = {}
    processed = 0
    now_iso = datetime.now(UTC).isoformat()
    for item in page.items:
        identity = f"{item.get('PK')}|{item.get('SK')}"
        try:
            scrub(
                item,
                owner_id=owner_id,
                generation=generation,
                now_iso=now_iso,
            )
            processed += 1
        except Exception:
            debt[identity] = 1
    prior_debt = previous.get("debt_counts")
    dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(page.items) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update({"pass_dirty": int(dirty), "processed": processed})
    if page.cursor is not None:
        return BranchResult("retryable", cursor=page.cursor, debt_counts=debt, epoch=epoch)
    if debt.keys() - {"pass_dirty", "processed"}:
        return BranchResult("retryable", debt_counts=debt, epoch=0)
    if dirty:
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


def _practice_progress_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_learning_scrub_branch(
        command=command,
        previous=previous,
        scan=practice_repo.scan_practice_private_rows,
        scrub=practice_repo.scrub_practice_private_row,
    )


def _adaptive_assignment_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_learning_scrub_branch(
        command=command,
        previous=previous,
        scan=adaptive_learning_repo.scan_adaptive_private_rows,
        scrub=adaptive_learning_repo.scrub_adaptive_private_row,
        scan_kwargs={"family": "assignment"},
    )


def _learning_memory_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_learning_scrub_branch(
        command=command,
        previous=previous,
        scan=adaptive_learning_repo.scan_adaptive_private_rows,
        scrub=adaptive_learning_repo.scrub_adaptive_private_row,
        scan_kwargs={"family": "learning_memory"},
    )


def _ai_teacher_draft_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    return _run_learning_scrub_branch(
        command=command,
        previous=previous,
        scan=ai_teacher_tools_repo.scan_ai_draft_private_rows,
        scrub=ai_teacher_tools_repo.scrub_ai_draft_private_row,
    )


def _curriculum_signal_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    owner_id = str(command["user_id"])
    generation = int(command["generation"])
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else None
    page = curriculum_analytics_repo.scan_curriculum_signal_manifests(
        owner_id, cursor=cursor, maximum_pages=1
    )
    debt: dict[str, int] = {}
    processed = 0
    now_iso = datetime.now(UTC).isoformat()
    for manifest in page.items:
        signal_id = str(manifest.get("signal_id") or "unknown")
        try:
            curriculum_analytics_repo.reconcile_curriculum_signal(
                manifest,
                owner_id=owner_id,
                generation=generation,
                now_iso=now_iso,
            )
            processed += 1
        except Exception:
            debt[f"signal:{signal_id}"] = 1
    prior_debt = previous.get("debt_counts")
    dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(page.items) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update({"pass_dirty": int(dirty), "processed": processed})
    if page.cursor is not None:
        return BranchResult("retryable", cursor=page.cursor, debt_counts=debt, epoch=epoch)
    if debt.keys() - {"pass_dirty", "processed"}:
        return BranchResult("retryable", debt_counts=debt, epoch=0)
    if dirty:
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


def _notification_device_realtime_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    """Revoke credentials, minimize receipts, and prove two clean strong epochs."""
    owner_id = str(command["user_id"])
    generation = int(command["generation"])
    raw_cursor = previous.get("cursor")
    cursor = dict(raw_cursor) if isinstance(raw_cursor, Mapping) else {}

    def family_cursor(prefix: str) -> dict[str, str] | None:
        pk = cursor.get(f"{prefix}_pk")
        sk = cursor.get(f"{prefix}_sk")
        if pk is None and sk is None:
            return None
        if not isinstance(pk, str) or not pk or not isinstance(sk, str) or not sk:
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid notification branch cursor"
            )
        return {"PK": pk, "SK": sk}

    notification_page = notification_repo.scan_notification_private_rows(
        owner_id,
        cursor=family_cursor("notification"),
        maximum_pages=1,
    )
    connection_page = websocket_repo.scan_account_connections(
        owner_id,
        cursor=family_cursor("connection"),
        maximum_pages=1,
    )
    debt: dict[str, int] = {}
    processed = 0
    external_accepted = 0
    external_unknown = 0
    current_time = datetime.now(UTC).isoformat()
    for item in notification_page.items:
        identity = f"{item.get('PK')}|{item.get('SK')}"
        try:
            if item.get("entity_type") == notification_repo.DELIVERY_INTENT_ENTITY:
                status = str(item.get("status") or "")
                if status == "accepted":
                    external_accepted += 1
                elif status == "provider_acceptance_unknown":
                    external_unknown += 1
            notification_repo.scrub_notification_private_row(
                item,
                owner_id=owner_id,
                generation=generation,
                now_iso=current_time,
            )
            processed += 1
        except Exception:
            debt[f"notification:{identity}"] = 1
    for item in connection_page.items:
        identity = f"{item.get('PK')}|{item.get('SK')}"
        try:
            websocket_repo.revoke_account_connection(
                item,
                owner_id=owner_id,
                generation=generation,
            )
            processed += 1
        except Exception:
            debt[f"connection:{identity}"] = 1

    prior_debt = previous.get("debt_counts")
    dirty = bool(
        isinstance(prior_debt, Mapping) and prior_debt.get("pass_dirty")
    ) or bool(notification_page.items) or bool(connection_page.items) or bool(debt)
    epoch = int(previous.get("epoch") or 0)
    debt.update(
        {
            "pass_dirty": int(dirty),
            "processed": processed,
            # These are policy-fact counts only. Provider/client copies are
            # explicitly outside backend purge authority.
            "external_accepted": external_accepted,
            "external_unknown": external_unknown,
        }
    )
    next_cursor: dict[str, str] = {}
    if notification_page.cursor is not None:
        next_cursor.update(
            {
                "notification_pk": notification_page.cursor["PK"],
                "notification_sk": notification_page.cursor["SK"],
            }
        )
    if connection_page.cursor is not None:
        next_cursor.update(
            {
                "connection_pk": connection_page.cursor["PK"],
                "connection_sk": connection_page.cursor["SK"],
            }
        )
    if next_cursor:
        return BranchResult(
            "retryable", cursor=next_cursor, debt_counts=debt, epoch=epoch
        )
    item_debt = debt.keys() - {
        "pass_dirty",
        "processed",
        "external_accepted",
        "external_unknown",
    }
    if item_debt:
        return BranchResult("retryable", debt_counts=debt, epoch=0)
    if dirty:
        return BranchResult(
            "retryable",
            debt_counts={
                "pass_dirty": 0,
                "processed": processed,
                "external_accepted": external_accepted,
                "external_unknown": external_unknown,
            },
            epoch=0,
        )
    epoch += 1
    return BranchResult(
        "complete" if epoch >= 2 else "retryable",
        debt_counts={
            "external_accepted": external_accepted,
            "external_unknown": external_unknown,
        },
        quiescent=epoch >= 2,
        epoch=epoch,
    )


def _external_delivery_debt_branch(
    *, command: Mapping[str, Any], previous: Mapping[str, Any]
) -> BranchResult:
    """Compose backend delivery debt without claiming provider/client erasure."""
    del previous
    results = command.get("branch_results")
    if not isinstance(results, Mapping):
        return BranchResult("retryable", debt_counts={"missing_branch_results": 1})
    accepted = delivered = unknown = pending = 0
    for branch_id, raw_result in results.items():
        if branch_id == "external_delivery_debt" or not isinstance(raw_result, Mapping):
            continue
        debt = raw_result.get("debt_counts")
        if not isinstance(debt, Mapping):
            continue
        accepted += int(debt.get("external_accepted") or 0)
        delivered += int(debt.get("external_delivered") or 0)
        unknown += int(debt.get("external_unknown") or 0)
        for key, value in debt.items():
            if key in {
                "external_accepted",
                "external_delivered",
                "external_unknown",
                "processed",
                "pass_dirty",
            }:
                continue
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                pending += value
    if pending:
        return BranchResult("retryable", debt_counts={"pending": pending})
    receipts = tuple(
        {
            "channel": channel,
            "status": status,
            "count": count,
            "claim": "outside_backend_purge_authority",
        }
        for channel, status, count in (
            ("provider", "accepted", accepted),
            ("provider", "delivered", delivered),
            ("provider", "provider_acceptance_unknown", unknown),
        )
        if count
    )
    return BranchResult(
        "complete",
        debt_counts={
            "external_accepted": accepted,
            "external_delivered": delivered,
            "external_unknown": unknown,
        },
        quiescent=True,
        epoch=2,
        external_receipts=receipts,
    )


BRANCH_HANDLERS: dict[str, Callable[..., BranchResult]] = {
    "account_profile": _account_profile_branch,
    "identity_cross_account": _identity_cross_account_branch,
    "capability_scope": _capability_scope_branch,
    "question_ocr_session": _question_ocr_session_branch,
    "attachments": _attachments_branch,
    # Derived rows resolve their question owner before the primary question
    # branch can replace that question with a tombstone.
    "moderation": _moderation_support_branch,
    "report_records": _report_records_branch,
    "report_artifacts": _report_artifacts_branch,
    "support_recovery_feed": _support_recovery_feed_branch,
    "conversation_messages": _conversation_messages_branch,
    "practice_progress": _practice_progress_branch,
    "adaptive_assignment": _adaptive_assignment_branch,
    "learning_memory": _learning_memory_branch,
    "ai_teacher_draft": _ai_teacher_draft_branch,
    "curriculum_signal": _curriculum_signal_branch,
    "notification_device_realtime": _notification_device_realtime_branch,
    "external_delivery_debt": _external_delivery_debt_branch,
}


class AccountDeletionService:
    """Resume independent primary branches from one durable command lease."""

    def __init__(
        self,
        *,
        repository: Any = account_deletion_repo,
        branch_handlers: Mapping[str, Callable[..., BranchResult]] | None = None,
        now: Callable[[], str] | None = None,
        now_epoch: Callable[[], int] | None = None,
        lease_seconds: int = 120,
        inventory_path: Path | str | None = None,
    ) -> None:
        self.repository = repository
        self.branch_handlers = dict(branch_handlers or BRANCH_HANDLERS)
        self.now = now or (lambda: datetime.now(UTC).isoformat())
        self.now_epoch = now_epoch or (lambda: int(datetime.now(UTC).timestamp()))
        self.lease_seconds = lease_seconds
        self.seal = load_private_store_seal(inventory_path)
        if tuple(self.branch_handlers) != ACCOUNT_DELETION_BRANCH_IDS:
            raise account_deletion_repo.AccountDeletionConflict(
                "runtime branch handlers do not match sealed registry"
            )

    def continue_command(self, claim: DeletionCommandClaim) -> None:
        if not isinstance(claim, DeletionCommandClaim):
            raise DeletionCommandClaimLost("opaque deletion claim required")
        command = self._load_command(claim.command_id)
        if not command:
            raise DeletionCommandClaimLost("deletion command disappeared")
        if command.get("status") == "complete":
            return
        self._require_current_claim(command, claim)
        if (
            command.get("inventory_sha256") != self.seal["inventory_sha256"]
            or command.get("branch_ids") != list(ACCOUNT_DELETION_BRANCH_IDS)
            or command.get("branch_contracts") != self.seal["branch_contracts"]
        ):
            raise account_deletion_repo.AccountDeletionConflict(
                "deletion command seal drift"
            )
        branch_results = command.setdefault("branch_results", {})
        if not isinstance(branch_results, dict):
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid deletion branch results"
            )
        for branch_id in ACCOUNT_DELETION_BRANCH_IDS:
            command = self._load_command(claim.command_id)
            if not command:
                raise DeletionCommandClaimLost("deletion command disappeared")
            self._require_current_claim(command, claim)
            previous = (command.get("branch_results") or {}).get(branch_id) or {}
            if previous.get("status") == "complete" and previous.get("quiescent") is True:
                continue
            current_epoch = self.now_epoch()
            now_iso = self.now()
            claim = self.repository.renew_deletion_command_claim(
                command,
                claim=claim,
                now_epoch=current_epoch,
                lease_expires_at=current_epoch + self.lease_seconds,
                now_iso=now_iso,
            )
            command = self._load_command(claim.command_id)
            if not command:
                raise DeletionCommandClaimLost("deletion command disappeared")
            self._require_current_claim(command, claim)
            handler = self.branch_handlers[branch_id]
            try:
                result = handler(command=command, previous=previous)
            except Exception:
                result = BranchResult("retryable", debt_counts={"dependency": 1})
            contract = self.seal["branch_contracts"][branch_id]
            persisted = result.persisted(
                self.now(),
                generation=int(command["generation"]),
                handler_version=str(contract["handler_version"]),
                subfamilies=contract["subfamilies"],
            )
            claim = self.repository.persist_branch_result(
                command,
                branch_id,
                persisted,
                claim=claim,
                expected_branch_results_digest=claim.branch_results_digest,
                expected_result_version=int(previous.get("result_version") or 0),
                now_epoch=self.now_epoch(),
            )
        command = self._load_command(claim.command_id)
        if not command:
            raise DeletionCommandClaimLost("deletion command disappeared")
        self._require_current_claim(command, claim)
        fence = self._load_fence(str(command["user_id"]))
        if fence and validate_deletion_seal(
            command=command, fence=fence, seal=self.seal
        ):
            self.repository.finalize_account_deletion(
                command=command,
                fence=fence,
                seal=self.seal,
                claim=claim,
                now_epoch=self.now_epoch(),
                now_iso=self.now(),
            )

    @staticmethod
    def _require_current_claim(
        command: Mapping[str, Any], claim: DeletionCommandClaim
    ) -> None:
        durable_results = command.get("branch_results") or {}
        if (
            command.get("status") != "running"
            or command.get("command_id") != claim.command_id
            or command.get("generation") != claim.generation
            or command.get("lease_owner") != claim.lease_owner
            or command.get("lease_expires_at") != claim.lease_expires_at
            or command.get("command_version") != claim.command_version
            or command.get("branch_results_digest") != claim.branch_results_digest
            or not isinstance(durable_results, Mapping)
            or account_deletion_repo.branch_results_digest(durable_results)
            != claim.branch_results_digest
        ):
            raise DeletionCommandClaimLost("deletion claim lost")

    def _load_command(self, command_id: str) -> dict[str, Any] | None:
        loader = getattr(self.repository, "get_command_by_id", None)
        if callable(loader):
            return loader(command_id)
        if self.repository is account_deletion_repo:
            return account_deletion_repo.get_command_by_id(command_id)
        return None

    def _load_fence(self, user_id: str) -> dict[str, Any] | None:
        loader = getattr(self.repository, "get_account_fence", None)
        if callable(loader):
            value = loader(user_id)
            return dict(value) if value else None
        if self.repository is account_deletion_repo:
            return account_deletion_repo.get_account_fence(user_id)
        return None
