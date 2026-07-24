"""Exact-once teacher-support case admission under Zurich-week scopes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import struct
from typing import Any

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.models.allowance import TeacherSupportScope, ZurichWeek
from stoa.models.billing import BillingPlanId
from stoa.services import allowance_service, paid_entitlement_service


ADMISSION_SCHEMA_VERSION = "teacher_support_admission.v1"
COUNTER_SCHEMA_VERSION = "teacher_support_counter.v1"
_CASE_KINDS = frozenset({"question", "conversation"})

type AdmissionOperation = dict[str, Any]
type PersistCase = Callable[[tuple[AdmissionOperation, ...]], bool]


class TeacherSupportAdmissionDisposition(StrEnum):
    ADMITTED = "admitted"
    REPLAYED = "replayed"
    PLAN_DENIED = "plan_denied"
    LIMIT_EXCEEDED = "limit_exceeded"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class TeacherSupportCaseAdmission:
    support_case_id: str
    support_scope_id: str
    beneficiary_id: str
    plan_id: BillingPlanId
    week_identity: str
    window_start: datetime
    window_end: datetime
    post_admission_count: int
    limit: int
    admitted_at: datetime


@dataclass(frozen=True, slots=True)
class TeacherSupportAdmissionResult:
    disposition: TeacherSupportAdmissionDisposition
    admission: TeacherSupportCaseAdmission | None = None


@dataclass(frozen=True, slots=True)
class _ResolvedScope:
    beneficiary_id: str
    parent_id: str
    plan_id: BillingPlanId
    plan_version: int
    allowance_version: int
    grant_version: int
    subscription_id_digest: str
    grant_id: str
    support_scope: TeacherSupportScope
    support_scope_id: str
    limit: int
    grant: dict[str, object]


class _DependencyFailure(RuntimeError):
    pass


def _required_text(value: object, field: str, *, maximum: int = 200) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= maximum
    ):
        raise ValueError(f"{field} is invalid")
    return value


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} is invalid")
    return value


def _stored_nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _DependencyFailure(f"{field} is malformed")
    return value


def _digest(value: object, field: str) -> str:
    text = _required_text(value, field, maximum=64)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} is invalid")
    return text


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _domain_digest(domain: bytes, *values: str) -> str:
    framed = bytearray(domain)
    for value in values:
        framed.extend(_frame(value))
    return hashlib.sha256(bytes(framed)).hexdigest()


def _mapping(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise _DependencyFailure("teacher-support dependency returned malformed data")
    return dict(value)


def _strong_get(table: object, key: Mapping[str, str]) -> dict[str, object] | None:
    getter = getattr(table, "get_item", None)
    if not callable(getter):
        raise _DependencyFailure("teacher-support persistence is unavailable")
    try:
        response = getter(Key=dict(key), ConsistentRead=True)
    except Exception:
        raise _DependencyFailure("teacher-support persistence is unavailable") from None
    response_map = _mapping(response)
    return _mapping((response_map or {}).get("Item"))


def _aware(value: datetime | None, field: str) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return observed


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: object, field: str) -> datetime:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _DependencyFailure(f"{field} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _DependencyFailure(f"{field} is malformed")
    return parsed


def _week_identity(week: ZurichWeek) -> str:
    return f"{week.iso_year:04d}-W{week.iso_week:02d}"


def _case_key(case_kind: str, support_case_id: str) -> dict[str, str]:
    identity = _domain_digest(
        b"stoa.teacher-support.case.v1",
        case_kind,
        support_case_id,
    )
    return {"PK": f"TEACHER_SUPPORT_CASE#{identity}", "SK": "ADMISSION"}


def _counter_key(scope_id: str, week_identity: str) -> dict[str, str]:
    return {
        "PK": f"TEACHER_SUPPORT#{scope_id}",
        "SK": f"WEEK#{week_identity}",
    }


def _resolve_scope(
    beneficiary_id: str,
    *,
    table: object,
) -> _ResolvedScope | None:
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    try:
        student = _mapping(user_repo.get_user(beneficiary))
    except Exception:
        raise _DependencyFailure("student entitlement is unavailable") from None
    if student is None:
        return None
    parent_id = student.get("parent_id")
    if (
        student.get("user_id") != beneficiary
        or student.get("role") != "student"
        or student.get("account_status") != "active"
        or student.get("parent_binding_status") != "active"
        or not isinstance(parent_id, str)
        or not parent_id
    ):
        return None
    try:
        grant = _mapping(
            paid_entitlement_service.get_active_beneficiary_grant(
                parent_id,
                beneficiary,
                table=table,
            )
        )
    except Exception:
        raise _DependencyFailure("paid grant resolution is unavailable") from None
    if grant is None:
        return None
    try:
        plan_id = BillingPlanId(_required_text(grant.get("plan_id"), "plan_id"))
        plan_version = _positive_integer(grant.get("plan_version"), "plan_version")
        allowance_version = _positive_integer(
            grant.get("allowance_version"), "allowance_version"
        )
        grant_version = _positive_integer(grant.get("grant_version"), "grant_version")
        subscription_digest = _digest(
            grant.get("subscription_id_digest"), "subscription_id_digest"
        )
        if (
            grant.get("parent_id") != parent_id
            or grant.get("beneficiary_id") != beneficiary
            or grant.get("grant_status") != "active"
        ):
            return None
        budget = allowance_service.plan_allowance_budget(
            plan_id,
            allowance_version=allowance_version,
        )
    except ValueError:
        return None
    if budget.teacher_support_scope is TeacherSupportScope.NONE:
        return None

    grant_values: tuple[str, ...]
    scope_values: tuple[str, ...]
    if budget.teacher_support_scope is TeacherSupportScope.PER_BENEFICIARY:
        grant_values = (
            parent_id,
            beneficiary,
            subscription_digest,
            str(grant_version),
            str(plan_version),
        )
        scope_values = grant_values
    else:
        grant_values = (parent_id, subscription_digest, str(plan_version))
        scope_values = grant_values
    grant_id = _domain_digest(
        b"stoa.teacher-support.grant.v1",
        *grant_values,
    )
    support_scope_id = _domain_digest(
        b"stoa.teacher-support.scope.v1",
        budget.teacher_support_scope.value,
        *scope_values,
    )
    return _ResolvedScope(
        beneficiary_id=beneficiary,
        parent_id=parent_id,
        plan_id=plan_id,
        plan_version=plan_version,
        allowance_version=allowance_version,
        grant_version=grant_version,
        subscription_id_digest=subscription_digest,
        grant_id=grant_id,
        support_scope=budget.teacher_support_scope,
        support_scope_id=support_scope_id,
        limit=budget.teacher_support_cases,
        grant=grant,
    )


def _grant_condition_operations(scope: _ResolvedScope) -> tuple[AdmissionOperation, ...]:
    grant = scope.grant
    parent_generation = _positive_integer(
        grant.get("parent_account_fence_generation"),
        "parent_account_fence_generation",
    )
    _positive_integer(
        grant.get("student_account_fence_generation"),
        "student_account_fence_generation",
    )
    parent_profile_version = _positive_integer(
        grant.get("parent_profile_version"), "parent_profile_version"
    )
    student_profile_version = _positive_integer(
        grant.get("student_profile_version"), "student_profile_version"
    )
    forward_version = _positive_integer(
        grant.get("forward_relationship_version"), "forward_relationship_version"
    )
    reverse_version = _positive_integer(
        grant.get("reverse_relationship_version"), "reverse_relationship_version"
    )
    common_values: dict[str, object] = {
        ":active": "active",
        ":parent_id": scope.parent_id,
        ":beneficiary_id": scope.beneficiary_id,
        ":plan_id": str(scope.plan_id),
        ":plan_version": scope.plan_version,
        ":allowance_version": scope.allowance_version,
        ":grant_version": scope.grant_version,
        ":subscription_id_digest": scope.subscription_id_digest,
    }
    return (
        # The case repository contributes the beneficiary fence because DynamoDB
        # transactions cannot target the same fence row twice.
        account_deletion_repo.active_fence_condition(scope.parent_id, parent_generation),
        {
            "ConditionCheck": {
                "Key": {
                    "PK": f"PAID_GRANT#{scope.parent_id}",
                    "SK": f"BENEFICIARY#{scope.beneficiary_id}",
                },
                "ConditionExpression": (
                    "grant_status=:active AND parent_id=:parent_id "
                    "AND beneficiary_id=:beneficiary_id AND plan_id=:plan_id "
                    "AND plan_version=:plan_version "
                    "AND allowance_version=:allowance_version "
                    "AND grant_version=:grant_version "
                    "AND subscription_id_digest=:subscription_id_digest"
                ),
                "ExpressionAttributeValues": common_values,
            }
        },
        {
            "ConditionCheck": {
                "Key": {"PK": f"USER#{scope.parent_id}", "SK": "PROFILE"},
                "ConditionExpression": (
                    "#role=:parent_role AND #status=:active AND #version=:version"
                ),
                "ExpressionAttributeNames": {
                    "#role": "role",
                    "#status": "account_status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":parent_role": "parent",
                    ":active": "active",
                    ":version": parent_profile_version,
                },
            }
        },
        {
            "ConditionCheck": {
                "Key": {"PK": f"USER#{scope.beneficiary_id}", "SK": "PROFILE"},
                "ConditionExpression": (
                    "#role=:student_role AND #status=:active AND #version=:version "
                    "AND parent_id=:parent_id AND parent_binding_status=:active"
                ),
                "ExpressionAttributeNames": {
                    "#role": "role",
                    "#status": "account_status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":student_role": "student",
                    ":active": "active",
                    ":version": student_profile_version,
                    ":parent_id": scope.parent_id,
                },
            }
        },
        _relationship_condition(
            key={
                "PK": f"USER#{scope.parent_id}",
                "SK": f"CHILD#{scope.beneficiary_id}",
            },
            scope=scope,
            version=forward_version,
        ),
        _relationship_condition(
            key={
                "PK": f"USER#{scope.beneficiary_id}",
                "SK": f"PARENT#{scope.parent_id}",
            },
            scope=scope,
            version=reverse_version,
        ),
    )


def _relationship_condition(
    *,
    key: dict[str, str],
    scope: _ResolvedScope,
    version: int,
) -> AdmissionOperation:
    return {
        "ConditionCheck": {
            "Key": key,
            "ConditionExpression": (
                "parent_id=:parent_id AND student_id=:student_id "
                "AND relationship=:relationship AND #status=:active "
                "AND #version=:version"
            ),
            "ExpressionAttributeNames": {
                "#status": "status",
                "#version": "version",
            },
            "ExpressionAttributeValues": {
                ":parent_id": scope.parent_id,
                ":student_id": scope.beneficiary_id,
                ":relationship": "child",
                ":active": "active",
                ":version": version,
            },
        }
    }


def _admission_from_item(item: Mapping[str, object]) -> TeacherSupportCaseAdmission:
    try:
        if (
            item.get("entity_type") != "teacher_support_admission"
            or item.get("schema_version") != ADMISSION_SCHEMA_VERSION
        ):
            raise _DependencyFailure("teacher-support admission is malformed")
        return TeacherSupportCaseAdmission(
            support_case_id=_required_text(
                item.get("support_case_id"), "support_case_id"
            ),
            support_scope_id=_digest(
                item.get("support_scope_id"), "support_scope_id"
            ),
            beneficiary_id=_required_text(
                item.get("beneficiary_id"), "beneficiary_id"
            ),
            plan_id=BillingPlanId(
                _required_text(item.get("plan_id"), "plan_id")
            ),
            week_identity=_required_text(
                item.get("week_identity"), "week_identity", maximum=8
            ),
            window_start=_parse_timestamp(item.get("window_start"), "window_start"),
            window_end=_parse_timestamp(item.get("window_end"), "window_end"),
            post_admission_count=_stored_nonnegative_integer(
                item.get("post_admission_count"), "post_admission_count"
            ),
            limit=_positive_integer(item.get("limit"), "limit"),
            admitted_at=_parse_timestamp(item.get("admitted_at"), "admitted_at"),
        )
    except ValueError as exc:
        raise _DependencyFailure("teacher-support admission is malformed") from exc


def _classify_existing(
    item: Mapping[str, object],
    *,
    support_case_id: str,
    case_kind: str,
    beneficiary_id: str,
) -> TeacherSupportAdmissionResult:
    try:
        admission = _admission_from_item(item)
        exact = (
            admission.support_case_id == support_case_id
            and admission.beneficiary_id == beneficiary_id
            and item.get("case_kind") == case_kind
        )
    except _DependencyFailure:
        return TeacherSupportAdmissionResult(
            TeacherSupportAdmissionDisposition.RETRYABLE
        )
    return TeacherSupportAdmissionResult(
        (
            TeacherSupportAdmissionDisposition.REPLAYED
            if exact
            else TeacherSupportAdmissionDisposition.IDEMPOTENCY_CONFLICT
        ),
        admission if exact else None,
    )


def _validated_counter(
    item: Mapping[str, object],
    *,
    scope: _ResolvedScope,
    week: ZurichWeek,
) -> tuple[int, int]:
    identity = _week_identity(week)
    if (
        item.get("entity_type") != "teacher_support_counter"
        or item.get("schema_version") != COUNTER_SCHEMA_VERSION
        or item.get("support_scope_id") != scope.support_scope_id
        or item.get("support_scope") != scope.support_scope.value
        or item.get("week_identity") != identity
        or item.get("plan_id") != str(scope.plan_id)
        or item.get("plan_version") != scope.plan_version
        or item.get("allowance_version") != scope.allowance_version
        or item.get("limit") != scope.limit
    ):
        raise _DependencyFailure("teacher-support counter is malformed")
    admitted_cases = _stored_nonnegative_integer(
        item.get("admitted_cases"), "admitted_cases"
    )
    state_version = _positive_integer(
        item.get("state_version"), "state_version"
    )
    if admitted_cases > scope.limit:
        raise _DependencyFailure("teacher-support counter is malformed")
    return admitted_cases, state_version


def admit_teacher_support_case(
    *,
    support_case_id: str,
    case_kind: str,
    beneficiary_id: str,
    persist_case: PersistCase,
    observed_at: datetime | None = None,
    table: object | None = None,
) -> TeacherSupportAdmissionResult:
    """Persist the first durable case and its weekly debit in one transaction.

    ``persist_case`` must prepend the beneficiary's active-account fence and
    append the durable case mutation to the supplied allowance operations.
    """
    case_id = _required_text(support_case_id, "support_case_id")
    kind = _required_text(case_kind, "case_kind", maximum=20)
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    if kind not in _CASE_KINDS:
        raise ValueError("case_kind is invalid")
    if not callable(persist_case):
        raise ValueError("persist_case is required")
    observed = _aware(observed_at, "observed_at")
    target = table or get_table()
    receipt_key = _case_key(kind, case_id)

    try:
        existing = _strong_get(target, receipt_key)
    except _DependencyFailure:
        return TeacherSupportAdmissionResult(
            TeacherSupportAdmissionDisposition.RETRYABLE
        )
    if existing is not None:
        return _classify_existing(
            existing,
            support_case_id=case_id,
            case_kind=kind,
            beneficiary_id=beneficiary,
        )
    try:
        scope = _resolve_scope(beneficiary, table=target)
    except _DependencyFailure:
        return TeacherSupportAdmissionResult(
            TeacherSupportAdmissionDisposition.RETRYABLE
        )
    if scope is None:
        return TeacherSupportAdmissionResult(
            TeacherSupportAdmissionDisposition.PLAN_DENIED
        )

    week = allowance_service.zurich_week(observed)
    identity = _week_identity(week)
    counter_key = _counter_key(scope.support_scope_id, identity)
    for _ in range(4):
        try:
            existing = _strong_get(target, receipt_key)
            if existing is not None:
                return _classify_existing(
                    existing,
                    support_case_id=case_id,
                    case_kind=kind,
                    beneficiary_id=beneficiary,
                )
            raw_counter = _strong_get(target, counter_key)
            if raw_counter is None:
                admitted_cases = 0
                state_version = 0
                counter_exists = False
            else:
                admitted_cases, state_version = _validated_counter(
                    raw_counter,
                    scope=scope,
                    week=week,
                )
                counter_exists = True
        except _DependencyFailure:
            return TeacherSupportAdmissionResult(
                TeacherSupportAdmissionDisposition.RETRYABLE
            )
        if admitted_cases >= scope.limit:
            return TeacherSupportAdmissionResult(
                TeacherSupportAdmissionDisposition.LIMIT_EXCEEDED
            )

        post_count = admitted_cases + 1
        effect_id = _domain_digest(
            b"stoa.teacher-support.effect.v1",
            kind,
            case_id,
            beneficiary,
        )
        receipt = {
            **receipt_key,
            "entity_type": "teacher_support_admission",
            "schema_version": ADMISSION_SCHEMA_VERSION,
            "support_case_id": case_id,
            "case_kind": kind,
            "effect_id": effect_id,
            "beneficiary_id": beneficiary,
            "parent_id": scope.parent_id,
            "plan_id": str(scope.plan_id),
            "plan_version": scope.plan_version,
            "allowance_version": scope.allowance_version,
            "grant_id": scope.grant_id,
            "support_scope": scope.support_scope.value,
            "support_scope_id": scope.support_scope_id,
            "week_identity": identity,
            "window_start": _timestamp(week.window_start),
            "window_end": _timestamp(week.window_end),
            "post_admission_count": post_count,
            "limit": scope.limit,
            "state_version": 1,
            "admitted_at": _timestamp(observed),
        }
        counter = {
            **counter_key,
            "entity_type": "teacher_support_counter",
            "schema_version": COUNTER_SCHEMA_VERSION,
            "support_scope": scope.support_scope.value,
            "support_scope_id": scope.support_scope_id,
            "plan_id": str(scope.plan_id),
            "plan_version": scope.plan_version,
            "allowance_version": scope.allowance_version,
            "grant_id": scope.grant_id,
            "week_identity": identity,
            "window_start": _timestamp(week.window_start),
            "window_end": _timestamp(week.window_end),
            "admitted_cases": post_count,
            "limit": scope.limit,
            "state_version": state_version + 1,
            "updated_at": _timestamp(observed),
        }
        if not counter_exists:
            counter["created_at"] = _timestamp(observed)
        counter_condition: AdmissionOperation = {
            "Put": {
                "Item": counter,
                "ConditionExpression": (
                    "state_version=:expected_state_version"
                    if counter_exists
                    else "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
                **(
                    {
                        "ExpressionAttributeValues": {
                            ":expected_state_version": state_version
                        }
                    }
                    if counter_exists
                    else {}
                ),
            }
        }
        operations = (
            *_grant_condition_operations(scope),
            {
                "Put": {
                    "Item": receipt,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            counter_condition,
        )
        try:
            committed = bool(persist_case(tuple(operations)))
        except Exception:
            committed = False
        if committed:
            return TeacherSupportAdmissionResult(
                TeacherSupportAdmissionDisposition.ADMITTED,
                _admission_from_item(receipt),
            )
    return TeacherSupportAdmissionResult(TeacherSupportAdmissionDisposition.RETRYABLE)


def get_teacher_support_projection(
    *,
    beneficiary_id: str,
    observed_at: datetime | None = None,
    table: object | None = None,
) -> dict[str, object]:
    """Return the current exact case count for the beneficiary's active grant scope."""
    observed = _aware(observed_at, "observed_at")
    target = table or get_table()
    try:
        scope = _resolve_scope(beneficiary_id, table=target)
    except _DependencyFailure:
        raise ValueError("teacher-support projection is temporarily unavailable") from None
    if scope is None:
        raise ValueError("teacher support is not included in the active plan")
    week = allowance_service.zurich_week(observed)
    identity = _week_identity(week)
    try:
        item = _strong_get(target, _counter_key(scope.support_scope_id, identity))
        admitted = (
            0
            if item is None
            else _validated_counter(item, scope=scope, week=week)[0]
        )
    except _DependencyFailure:
        raise ValueError("teacher-support projection is temporarily unavailable") from None
    return {
        "schemaVersion": "teacher_support_projection.v1",
        "planId": str(scope.plan_id),
        "supportScope": scope.support_scope.value,
        "weekIdentity": identity,
        "admittedCases": admitted,
        "remainingCases": scope.limit - admitted,
        "limit": scope.limit,
    }


__all__ = [
    "TeacherSupportAdmissionDisposition",
    "TeacherSupportAdmissionResult",
    "TeacherSupportCaseAdmission",
    "admit_teacher_support_case",
    "get_teacher_support_projection",
]
