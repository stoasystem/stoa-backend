"""Answer one operator call: verify the caller, run one listed operation, record it (#383).

`stoa.main.handler` hands a direct invocation here when its top level carries
`catalog.OPERATOR_CALL_KEY`. The call is

    {"operation": str, "arguments": {...}, "callerIdentity": {signed headers},
     "agent": "claude-code"}

and the answer is `{"ok": true, "result": ...}` or
`{"ok": false, "error": {"code": ..., "message": ...}}`. Nothing a caller sends
is echoed back, and an error message carries no stored value beyond account
numbers and states.

Order matters. The caller is verified before anything else, so an unverified
caller learns nothing, not even which operations exist. Every verified call then
leaves exactly one row in the security audit stream of `operator:agent_mcp`,
refusals included; a read's result is only handed back once its row is written.
An operation that cannot be recorded does not answer.

An operation that changes data (#384) takes `dryRun`. Its rehearsal only reads; its
real run writes, and its row is written after it, so a real run whose row then fails
has happened all the same, and the answer says so instead of claiming nothing ran.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from stoa import config
from stoa.db.repositories import security_audit_repo
from stoa.operator_calls import accounts, caller_identity, catalog, deletions, invitations
from stoa.operator_calls import curriculum, overview
from stoa.operator_calls import usage_periods
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.rule_violation import RuleViolation


logger = logging.getLogger(__name__)

Runner = Callable[[Any], Outcome]

RUNNERS: Mapping[str, Runner] = {
    "find_accounts": accounts.find_accounts,
    "get_account": accounts.get_account,
    "invite_account": invitations.invite_account,
    "reissue_invitation": invitations.reissue_invitation,
    "revoke_invitation": invitations.revoke_invitation,
    "delete_account": deletions.delete_account,
    "list_teacher_applications": overview.list_teacher_applications,
    "count_review_queues": overview.count_review_queues,
    "report_email_stats": overview.report_email_stats,
    "get_usage_period": usage_periods.get_usage_period,
    "extend_usage_period": usage_periods.extend_usage_period,
    "set_usage_period": usage_periods.set_usage_period,
    "get_lesson_state": curriculum.get_lesson_state,
    "get_migration": curriculum.get_migration,
    "dry_run_curriculum_migration": curriculum.dry_run_curriculum_migration,
    "apply_curriculum_migration": curriculum.apply_curriculum_migration,
    "publish_curriculum_drafts": curriculum.publish_curriculum_drafts,
    "rollback_lesson": curriculum.rollback_lesson,
}

_AGENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]")
_FUNCTION_ARN = re.compile(r"^arn:aws[a-z-]*:lambda:[a-z0-9-]+:(\d{12}):function:")


def _error(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "error": {"code": code, "message": message}}


def account_of_function(invoked_function_arn: object) -> str:
    """The AWS account the function runs in: the only account an operator may call from."""
    match = _FUNCTION_ARN.match(str(invoked_function_arn or ""))
    return match.group(1) if match else ""


def _agent(value: object) -> str:
    name = _AGENT_PATTERN.sub("", str(value or ""))[:64]
    return name or "unknown"


def _audit_key() -> security_audit_repo.AuthorizationAuditKey:
    from stoa.deps import get_authorization_audit_sink

    sink = get_authorization_audit_sink(config.settings())
    keys = getattr(sink, "keys", ())
    if not keys:
        raise OperatorCallRefused(
            "audit_unavailable", "The audit trail is unavailable, so nothing was run."
        )
    return keys[0]


def _record(
    *,
    key: security_audit_repo.AuthorizationAuditKey,
    principal_arn: str,
    agent: str,
    action: str,
    dry_run: bool,
    result_code: str,
    target_type: str = "",
    target_id: str = "",
    evidence: str = "",
    correlation_id: str,
    now: datetime,
) -> None:
    event: dict[str, object] = {
        "event_id": f"event_operator_{uuid4().hex}",
        "event_type": "operator_call",
        "actor_id": catalog.OPERATOR_ACTOR_ID,
        "actor_role": "operator",
        "actor_fingerprint": security_audit_repo.operator_principal_fingerprint(
            key, principal_arn
        ),
        "audit_key_id": key.key_id,
        "agent_client": agent,
        "dry_run": dry_run,
        "action": action,
        "result_code": result_code,
        "correlation_id": correlation_id,
        "created_at": now.replace(microsecond=0).isoformat(),
    }
    if target_type:
        event["target_type"] = target_type
    if target_id:
        event["target_id"] = target_id
    if evidence:
        event["evidence_reference"] = evidence[:400]
    security_audit_repo.append_event(catalog.OPERATOR_ACTOR_ID, event)


def _arguments(spec: catalog.OperationSpec, value: object) -> BaseModel:
    try:
        return spec.arguments.model_validate(value if value is not None else {})
    except ValidationError as exc:
        # Field names and rule types only: the input values stay out of the answer.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['type']}"
            for error in exc.errors()
        )
        raise OperatorCallRefused("invalid_arguments", problems[:500]) from exc


def handle(
    call: object,
    *,
    invoked_function_arn: object,
    region: str | None = None,
    verify: Callable[..., str] = caller_identity.verify,
    audit_key: Callable[[], security_audit_repo.AuthorizationAuditKey] = _audit_key,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    if not isinstance(call, Mapping):
        return _error("malformed_call", "An operator call is an object.")
    try:
        principal_arn = verify(
            call.get("callerIdentity"),
            region=region or config.settings().aws_region,
            expected_account_id=account_of_function(invoked_function_arn),
        )
    except caller_identity.CallerNotVerified as exc:
        return _error("caller_not_verified", str(exc))

    agent = _agent(call.get("agent"))
    correlation_id = f"operator-{uuid4().hex}"
    name = str(call.get("operation") or "")
    spec = catalog.OPERATIONS_BY_NAME.get(name)
    action = name if spec else "unknown_operation"
    raw_arguments = call.get("arguments")
    dry_run = bool(isinstance(raw_arguments, Mapping) and raw_arguments.get("dryRun") is True)

    try:
        key = audit_key()
    except OperatorCallRefused as refused:
        return _error(refused.code, refused.message)

    def record(
        result_code: str,
        outcome: Outcome | None = None,
        refused: OperatorCallRefused | None = None,
    ) -> None:
        _record(
            key=key,
            principal_arn=principal_arn,
            agent=agent,
            action=action,
            dry_run=dry_run,
            result_code=result_code,
            target_type=outcome.target_type if outcome else (refused.target_type if refused else ""),
            target_id=outcome.target_id if outcome else (refused.target_id if refused else ""),
            evidence=outcome.evidence if outcome else (refused.evidence if refused else ""),
            correlation_id=correlation_id,
            now=now(),
        )

    refusal: OperatorCallRefused | None = None
    try:
        if spec is None or name not in RUNNERS:
            raise OperatorCallRefused(
                "unknown_operation",
                "No such operator operation. Known: "
                + ", ".join(spec.name for spec in catalog.OPERATIONS)
                + ".",
            )
        arguments = _arguments(spec, raw_arguments)
        # The validated switch is what the operation obeys, so it is what is recorded.
        dry_run = getattr(arguments, "dryRun", False) is True
        outcome = RUNNERS[name](arguments)
    except OperatorCallRefused as declined:
        code, message, refusal = declined.code, declined.message, declined
    except accounts.AmbiguousAccount as exc:
        code, message = "ambiguous_account", str(exc)
    except RuleViolation as violation:
        code = str(violation.code.value)
        message = f"Refused: {code}."
    except Exception:  # noqa: BLE001 - the answer must not carry the failure's detail
        logger.exception("operator call %s failed (%s)", action, correlation_id)
        code, message = "failed", f"The operation failed; see logs for {correlation_id}."
    else:
        try:
            record("ok", outcome)
        except Exception:  # noqa: BLE001
            logger.exception("operator call %s not recorded (%s)", action, correlation_id)
            if spec is not None and spec.effect is catalog.Effect.WRITE and not dry_run:
                return _error(
                    "audit_unavailable",
                    "The operation ran but could not be recorded, so no result is given; "
                    "check the account with get_account before trying again.",
                )
            return _error("audit_unavailable", "The call could not be recorded, so no result is given.")
        return {"ok": True, "result": outcome.result, "correlationId": correlation_id}

    try:
        record(code, refused=refusal)
    except Exception:  # noqa: BLE001
        logger.exception("operator refusal %s not recorded (%s)", action, correlation_id)
    return _error(code, message)
