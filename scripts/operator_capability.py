#!/usr/bin/env python3
"""Grant an administrator a capability, or record its grants, from an operator session.

#48: the product refuses an administrator's grant to itself, so a lone
administrator has no second person to ask. The way out lives here, in the AWS
trust domain, behind the same SSO operator guard as the bootstrap script: a
stolen administrator session cannot reach it.

`grant` issues one registered capability to one active administrator and
records it. It first writes the row of any earlier grant of this script that
has none, revoked or not: a grant and its row are two writes, and a run can
stop between them. `baseline` records, one audit row per grant plus a closing
summary, every grant the administrator holds now; the grants issued before
per-grant audit rows existed have none. Neither command touches Cognito.

Like the bootstrap script, the rows name the operator path, not the person:
the SSO session ARN carries the person's address, a plain hash of it is
reversible by guessing, and the keyed audit fingerprint needs a secret an
operator shell does not hold. The free-text reason stays on the grant.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
import os
import sys
import uuid
from typing import Any

from botocore.exceptions import ClientError

from stoa.db.repositories import capability_repo, security_audit_repo
from stoa.security.aws_operator_identity import (
    AwsOperatorIdentityError,
    require_sso_operator_session,
)


DEFAULT_AWS_ACCOUNT_ID = "562923011260"
OPERATOR_ID = "operator:operator_capability"


class OperatorCapabilityError(RuntimeError):
    """Raised when the command cannot be carried out safely."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_active_admin(table: Any, user_id: str) -> None:
    profile = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}).get("Item")
    if (
        not profile
        or profile.get("role") != "admin"
        or profile.get("account_status") != "active"
    ):
        raise OperatorCapabilityError(f"{user_id} is not an active administrator.")


class SessionTable:
    """The table, with every write on the verified operator session.

    The capability store opens its own low-level client for transactions, and
    that client comes from ambient credentials, not from this session. Given a
    table that carries `transact_write_items`, it uses that instead, so the
    grant lands in the account the SSO guard checked, as the reads and the
    audit rows do.
    """

    def __init__(self, table: Any, client: Any) -> None:
        self._table = table
        self._client = client
        self.name = table.name
        self.meta = table.meta

    def get_item(self, **kwargs: Any) -> Any:
        return self._table.get_item(**kwargs)

    def put_item(self, **kwargs: Any) -> Any:
        return self._table.put_item(**kwargs)

    def query(self, **kwargs: Any) -> Any:
        return self._table.query(**kwargs)

    def transact_write_items(self, **kwargs: Any) -> Any:
        return self._client.transact_write_items(**kwargs)


def _append_audit(table: Any, user_id: str, event: dict[str, Any]) -> None:
    security_audit_repo.append_event(user_id, event, table=table)


def _active(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if str(item.get("status") or "") == "active"]


def _grant_event_id(grant_id: str) -> str:
    # Derived from the grant, so a rerun can tell whether this grant's row exists.
    return f"event_operator_grant_{grant_id}"


def _audit_row_exists(table: Any, user_id: str, event_id: str) -> bool:
    key = {"PK": f"SECURITY_AUDIT#{user_id}", "SK": f"EVENT#{event_id}"}
    return bool(table.get_item(Key=key, ConsistentRead=True).get("Item"))


def _repair_missing_grant_rows(table: Any, user_id: str, *, dry_run: bool) -> int:
    """Write the row of every grant this script issued that has none.

    The grant and its row are two writes; a run cut short between them leaves
    a grant with no row. That grant may since have been revoked, so the repair
    reads every grant's first revision, not only the grants still held.
    """
    missing = [
        item
        for item in capability_repo.list_grant_revisions(user_id, table_factory=lambda: table)
        if item.get("grantor_id") == OPERATOR_ID
        and int(item.get("version") or 0) == 1
        and not _audit_row_exists(table, user_id, _grant_event_id(str(item.get("grant_id") or "")))
    ]
    if not dry_run:
        for item in missing:
            # Dated when the grant took effect, not when the gap was noticed.
            _record_grant(table, user_id, item, str(item.get("effective_at") or now_iso()))
    return len(missing)


def _record_grant(table: Any, user_id: str, item: dict[str, Any], timestamp: str) -> None:
    grant_id = str(item.get("grant_id") or "")
    _append_audit(
        table,
        user_id,
        {
            "event_id": _grant_event_id(grant_id),
            "event_type": "capability_granted",
            "actor_id": OPERATOR_ID,
            "actor_role": "operator",
            "target_id": user_id,
            "target_type": "capability_grant",
            "action": "grant_capability",
            "version": item.get("version"),
            "reason_code": "operator_capability_grant",
            "evidence_reference": f"capability-grant:{grant_id}",
            "command_id": item.get("command_id"),
            "created_at": timestamp,
        },
    )


def grant(
    table: Any,
    *,
    user_id: str,
    capability: str,
    scope: str,
    incident_reason: str,
    dry_run: bool,
    expires_at: str | None = None,
    now: Callable[[], str] = now_iso,
) -> tuple[str, int]:
    """Issue the capability once, after repairing any row an earlier run left out.

    Returns the grant's status (`issued`, `present`, or `pending` on a dry run)
    and how many missing audit rows were, or on a dry run would be, written.
    """
    if capability not in capability_repo.KNOWN_CAPABILITIES:
        raise OperatorCapabilityError(f"{capability!r} is not a registered capability.")
    scope = scope.strip()
    if not scope:
        raise OperatorCapabilityError("A non-empty --scope is required.")
    expires_at = (expires_at or "").strip() or None
    # Checked here, not left to the store, so a dry run cannot say `pending`
    # for a grant the store would refuse.
    if capability == capability_repo.STUDENT_DATA_BREAK_GLASS and not expires_at:
        raise OperatorCapabilityError("A break-glass grant needs --expires-at.")
    if expires_at is not None:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise OperatorCapabilityError("--expires-at is not an ISO 8601 time.") from exc
        if expiry.tzinfo is None:
            raise OperatorCapabilityError("--expires-at needs a timezone.")
        if expiry <= datetime.fromisoformat(now()):
            raise OperatorCapabilityError("--expires-at is not in the future.")
    _require_active_admin(table, user_id)
    repaired = _repair_missing_grant_rows(table, user_id, dry_run=dry_run)
    held = _active(capability_repo.get_current_grants(user_id, table_factory=lambda: table))
    if any(
        item.get("capability") == capability and str(item.get("scope") or "").strip() == scope
        for item in held
    ):
        return "present", repaired
    if dry_run:
        return "pending", repaired

    command_id = f"operator-{uuid.uuid4().hex[:16]}"
    timestamp = now()
    item = capability_repo.grant_capability(
        user_id=user_id,
        command_id=command_id,
        grant_id=f"grant-{uuid.uuid4().hex[:16]}",
        capability=capability,
        scope=scope,
        grantor_id=OPERATOR_ID,
        reason=incident_reason,
        effective_at=timestamp,
        expires_at=expires_at,
        expected_generation=capability_repo.current_lineage_generation(
            user_id, capability, scope, table_factory=lambda: table
        ),
        table_factory=lambda: table,
    )
    _record_grant(table, user_id, {**item, "command_id": command_id}, timestamp)
    return "issued", repaired


def baseline(
    table: Any,
    *,
    user_id: str,
    dry_run: bool,
    now: Callable[[], str] = now_iso,
    snapshot_id: str | None = None,
) -> tuple[str, int]:
    """Record every active grant, then a summary; append-only, grants untouched.

    An audit row holds scalars only, so the list is one row per grant, and the
    summary written last carries the count and a digest of those rows. A
    snapshot cut short has no summary, which is how it can be told apart.
    """
    _require_active_admin(table, user_id)
    snapshot_id = snapshot_id or f"baseline-{uuid.uuid4().hex[:16]}"
    timestamp = now()
    held = _active(capability_repo.get_current_grants(user_id, table_factory=lambda: table))
    # The scope as stored, not its hash: a reader of the trail has to see it.
    references = sorted(
        f"capability-baseline:{snapshot_id}:{item.get('capability')}:"
        f"{str(item.get('scope') or '').strip()}:v{item.get('version')}:{item.get('grant_id')}"
        for item in held
    )
    if dry_run:
        return snapshot_id, len(references)

    common = {
        "actor_id": OPERATOR_ID,
        "actor_role": "operator",
        "target_id": user_id,
        "target_type": "capability_grant",
        "action": "record_capability_baseline",
        "reason_code": "operator_capability_baseline",
        "command_id": snapshot_id,
        "created_at": timestamp,
    }
    for index, reference in enumerate(references):
        _append_audit(
            table,
            user_id,
            {
                **common,
                "event_id": f"{snapshot_id}_{index:03d}",
                "event_type": "capability_baseline_recorded",
                "evidence_reference": reference,
            },
        )
    digest = sha256("\n".join(references).encode()).hexdigest()
    _append_audit(
        table,
        user_id,
        {
            **common,
            "event_id": f"{snapshot_id}_summary",
            "event_type": "capability_baseline_snapshot",
            "evidence_reference": (
                f"capability-baseline:{snapshot_id}:count={len(references)}:sha256={digest}"
            ),
        },
    )
    return snapshot_id, len(references)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("grant", "baseline"))
    parser.add_argument("--user-id", required=True, help="The administrator's user_id.")
    parser.add_argument("--capability", default="", help="grant: a registered capability.")
    parser.add_argument("--scope", default="global", help="grant: the grant scope.")
    parser.add_argument(
        "--expires-at", default="", help="grant: ISO 8601 expiry; required for break-glass."
    )
    parser.add_argument(
        "--incident-reason", default="", help="grant: why; stored on the grant, not the audit row."
    )
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "eu-central-2"))
    parser.add_argument(
        "--profile",
        default=os.environ.get("AWS_PROFILE", "stoa"),
        help="AWS IAM Identity Center profile; IAM User credentials are refused.",
    )
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    parser.add_argument(
        "--table-name", default=os.environ.get("DYNAMODB_TABLE_NAME", "stoa-main")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required guard acknowledging this changes production authority.",
    )
    return parser.parse_args()


def validate_inputs(args: argparse.Namespace) -> None:
    if not args.confirm_production:
        raise OperatorCapabilityError("Refusing to run without --confirm-production.")
    if args.command == "grant":
        if not str(args.capability or "").strip():
            raise OperatorCapabilityError("grant needs --capability.")
        if not str(args.incident_reason or "").strip():
            raise OperatorCapabilityError("grant needs a non-empty --incident-reason.")


def main() -> int:
    args = parse_args()
    try:
        validate_inputs(args)
        session = require_sso_operator_session(
            profile_name=args.profile,
            region_name=args.region,
            expected_account_id=args.account_id,
        )
        table = SessionTable(
            session.resource("dynamodb", region_name=args.region).Table(args.table_name),
            session.client("dynamodb", region_name=args.region),
        )
        if args.command == "grant":
            status, repaired = grant(
                table,
                user_id=args.user_id,
                capability=args.capability.strip(),
                scope=args.scope,
                incident_reason=args.incident_reason.strip(),
                dry_run=args.dry_run,
                expires_at=args.expires_at,
            )
            print(
                f"capability={args.capability.strip()} scope={args.scope.strip()} "
                f"status={status} missing_audit_rows={'would_write' if args.dry_run else 'wrote'}"
                f":{repaired}"
            )
        else:
            snapshot_id, count = baseline(
                table,
                user_id=args.user_id,
                dry_run=args.dry_run,
            )
            state = "would_record" if args.dry_run else "recorded"
            print(f"baseline={snapshot_id} grants={count} status={state}")
    except ClientError:
        print("ERROR: provider operation failed safely.", file=sys.stderr)
        return 1
    except (AwsOperatorIdentityError, OperatorCapabilityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:
        # Refusals from the grant store (a missing expiry, a stale generation, a
        # closed account fence) end the run cleanly rather than in a traceback.
        print(f"ERROR: the grant store refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
