"""Explicit, relationship-fenced beneficiary grants for paid access."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, billing_fact_repo, user_repo
from stoa.models.billing import BillingPlanId


GRANT_SCHEMA_VERSION = "paid_beneficiary_grant.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLAN_RANK = {
    BillingPlanId.FREE_TRIAL: 0,
    BillingPlanId.STUDENT: 1,
    BillingPlanId.TEACHER_SUPPORTED: 2,
    BillingPlanId.FAMILY: 3,
}


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


class PaidGrantConflict(RuntimeError):
    """Current relationship or monotonic grant conditions do not authorize a write."""


class PaidGrantDisposition(StrEnum):
    UPGRADED = "upgraded"
    ALREADY_APPLIED = "already_applied"
    CONFLICT = "conditional_conflict"
    RETRYABLE = "retryable_dependency"


@dataclass(frozen=True, slots=True)
class PaidGrantBuild:
    grant_items: tuple[dict[str, object], ...]
    grant_operations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class PaidGrantResult:
    disposition: PaidGrantDisposition
    operations: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class _RelationshipProof:
    parent_profile_version: int
    parent_fence_generation: int
    student_profile_version: int
    student_fence_generation: int
    forward_version: int
    reverse_version: int


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


def _digest(value: object, field: str) -> str:
    text = _required_text(value, field, maximum=64)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{field} is invalid")
    return text


def _aware_timestamp(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} is invalid")
    return value.isoformat()


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return dict(value)


def _strong_get(table: object, key: Mapping[str, str]) -> dict[str, object] | None:
    if not isinstance(table, _GetTable):
        raise TypeError("table does not support get_item")
    response = table.get_item(Key=dict(key), ConsistentRead=True)
    response_map = _mapping(response)
    return _mapping((response_map or {}).get("Item"))


def _grant_key(parent_id: str, beneficiary_id: str) -> dict[str, str]:
    return {
        "PK": f"PAID_GRANT#{_required_text(parent_id, 'parent_id')}",
        "SK": f"BENEFICIARY#{_required_text(beneficiary_id, 'beneficiary_id')}",
    }


def validate_beneficiary_selection(
    plan_id: BillingPlanId,
    beneficiary_ids: Sequence[str],
) -> tuple[str, ...]:
    """Return one immutable sorted selection within the plan's exact cardinality."""
    if not isinstance(plan_id, BillingPlanId) or plan_id is BillingPlanId.FREE_TRIAL:
        raise ValueError("plan_id is not a paid plan")
    if not isinstance(beneficiary_ids, Sequence) or isinstance(
        beneficiary_ids, (str, bytes)
    ):
        raise ValueError("beneficiary_ids are invalid")
    selected = tuple(
        _required_text(value, "beneficiary_id") for value in beneficiary_ids
    )
    if len(selected) != len(set(selected)):
        raise ValueError("beneficiary_ids must be unique")
    if plan_id in {BillingPlanId.STUDENT, BillingPlanId.TEACHER_SUPPORTED}:
        valid = len(selected) == 1
    else:
        valid = 1 <= len(selected) <= 3
    if not valid:
        raise ValueError("beneficiary selection does not match the paid plan")
    return tuple(sorted(selected))


def _profile_condition(
    user_id: str,
    *,
    role: str,
    version: int,
    parent_id: str | None = None,
) -> dict[str, Any]:
    names = {
        "#user_id": "user_id",
        "#role": "role",
        "#account_status": "account_status",
        "#version": "version",
    }
    values: dict[str, object] = {
        ":user_id": user_id,
        ":role": role,
        ":active": "active",
        ":version": version,
    }
    expression = (
        "#user_id=:user_id AND #role=:role "
        "AND #account_status=:active AND #version=:version"
    )
    if parent_id is not None:
        names.update(
            {
                "#parent_id": "parent_id",
                "#parent_binding_status": "parent_binding_status",
            }
        )
        values[":parent_id"] = parent_id
        expression += (
            " AND #parent_id=:parent_id AND #parent_binding_status=:active"
        )
    return {
        "ConditionCheck": {
            "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
            "ConditionExpression": expression,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def _relationship_condition(
    *,
    key: dict[str, str],
    parent_id: str,
    student_id: str,
    version: int,
) -> dict[str, Any]:
    return {
        "ConditionCheck": {
            "Key": key,
            "ConditionExpression": (
                "#parent_id=:parent_id AND #student_id=:student_id "
                "AND #relationship=:relationship AND #status=:active "
                "AND #version=:version"
            ),
            "ExpressionAttributeNames": {
                "#parent_id": "parent_id",
                "#student_id": "student_id",
                "#relationship": "relationship",
                "#status": "status",
                "#version": "version",
            },
            "ExpressionAttributeValues": {
                ":parent_id": parent_id,
                ":student_id": student_id,
                ":relationship": "child",
                ":active": "active",
                ":version": version,
            },
        }
    }


def _relationship_proof(
    parent_id: str,
    student_id: str,
    *,
    table: object,
) -> _RelationshipProof:
    parent = _mapping(user_repo.get_user(parent_id))
    student = _mapping(user_repo.get_user(student_id))
    forward = _mapping(user_repo.get_parent_student_binding(parent_id, student_id))
    reverse = _mapping(user_repo.get_student_parent_binding(student_id, parent_id))
    if (
        parent is None
        or parent.get("user_id") != parent_id
        or parent.get("role") != "parent"
        or parent.get("account_status") != "active"
        or student is None
        or student.get("user_id") != student_id
        or student.get("role") != "student"
        or student.get("account_status") != "active"
        or student.get("parent_id") != parent_id
        or student.get("parent_binding_status") != "active"
        or forward is None
        or reverse is None
    ):
        raise PaidGrantConflict("beneficiary relationship is not active")
    for row in (forward, reverse):
        if (
            row.get("parent_id") != parent_id
            or row.get("student_id") != student_id
            or row.get("relationship") != "child"
            or row.get("status") != "active"
        ):
            raise PaidGrantConflict("beneficiary relationship is not bidirectional")
    try:
        parent_version = _positive_integer(parent.get("version"), "parent profile version")
        student_version = _positive_integer(student.get("version"), "student profile version")
        forward_version = _positive_integer(forward.get("version"), "forward version")
        reverse_version = _positive_integer(reverse.get("version"), "reverse version")
        parent_fence = account_deletion_repo.require_active_account_fence(
            parent_id, table=table
        )
        student_fence = account_deletion_repo.require_active_account_fence(
            student_id, table=table
        )
        parent_generation = _positive_integer(
            parent_fence.get("generation"), "parent fence generation"
        )
        student_generation = _positive_integer(
            student_fence.get("generation"), "student fence generation"
        )
    except (ValueError, account_deletion_repo.AccountDeletionConflict) as exc:
        raise PaidGrantConflict("beneficiary relationship proof is invalid") from exc
    return _RelationshipProof(
        parent_profile_version=parent_version,
        parent_fence_generation=parent_generation,
        student_profile_version=student_version,
        student_fence_generation=student_generation,
        forward_version=forward_version,
        reverse_version=reverse_version,
    )


def _proof_operations(
    parent_id: str,
    student_id: str,
    proof: _RelationshipProof,
    *,
    include_parent: bool,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    if include_parent:
        operations.extend(
            (
                _profile_condition(
                    parent_id,
                    role="parent",
                    version=proof.parent_profile_version,
                ),
                account_deletion_repo.active_fence_condition(
                    parent_id, proof.parent_fence_generation
                ),
            )
        )
    operations.extend(
        (
            _profile_condition(
                student_id,
                role="student",
                version=proof.student_profile_version,
                parent_id=parent_id,
            ),
            _relationship_condition(
                key={"PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}"},
                parent_id=parent_id,
                student_id=student_id,
                version=proof.forward_version,
            ),
            _relationship_condition(
                key={"PK": f"USER#{student_id}", "SK": f"PARENT#{parent_id}"},
                parent_id=parent_id,
                student_id=student_id,
                version=proof.reverse_version,
            ),
            account_deletion_repo.active_fence_condition(
                student_id, proof.student_fence_generation
            ),
        )
    )
    return operations


def build_paid_activation_operations(
    request: billing_fact_repo.PaidActivationRequest,
    *,
    command: Mapping[str, object],
    table: object | None = None,
) -> PaidGrantBuild:
    """Revalidate immutable beneficiaries and build exact transaction conditions."""
    if not isinstance(request, billing_fact_repo.PaidActivationRequest):
        raise ValueError("PaidActivationRequest is required")
    target = table or get_table()
    command_item = _mapping(command)
    if command_item is None:
        raise ValueError("command is invalid")
    beneficiary_values = command_item.get("beneficiary_ids")
    if not isinstance(beneficiary_values, Sequence) or isinstance(
        beneficiary_values, (str, bytes)
    ) or not all(isinstance(value, str) for value in beneficiary_values):
        raise ValueError("command beneficiary_ids are invalid")
    selected = validate_beneficiary_selection(
        request.plan_id,
        beneficiary_values,
    )
    subscription_digest = _digest(
        request.provider_subscription_id_digest
        or command_item.get("provider_subscription_id_digest"),
        "provider_subscription_id_digest",
    )
    expected = {
        "command_id": request.command_id,
        "parent_id": request.parent_id,
        "plan_id": str(request.plan_id),
        "plan_version": request.plan_version,
        "provider_subscription_id_digest": subscription_digest,
    }
    if any(command_item.get(field) != value for field, value in expected.items()):
        raise PaidGrantConflict("activation does not match the checkout command")

    grants: list[dict[str, object]] = []
    operations: list[dict[str, Any]] = []
    for index, student_id in enumerate(selected):
        proof = _relationship_proof(request.parent_id, student_id, table=target)
        operations.extend(
            _proof_operations(
                request.parent_id,
                student_id,
                proof,
                include_parent=index == 0,
            )
        )
        grants.append(
            {
                **_grant_key(request.parent_id, student_id),
                "entity_type": "beneficiary_grant",
                "schema_version": GRANT_SCHEMA_VERSION,
                "parent_id": request.parent_id,
                "beneficiary_id": student_id,
                "grant_status": "active",
                "command_id": request.command_id,
                "subscription_id_digest": subscription_digest,
                "grant_version": request.activation_version,
                "plan_id": str(request.plan_id),
                "plan_version": request.plan_version,
                "allowance_version": request.allowance_version,
                "activation_version": request.activation_version,
                "activated_at": request.activated_at,
                "parent_profile_version": proof.parent_profile_version,
                "parent_account_fence_generation": proof.parent_fence_generation,
                "student_profile_version": proof.student_profile_version,
                "student_account_fence_generation": proof.student_fence_generation,
                "forward_relationship_version": proof.forward_version,
                "reverse_relationship_version": proof.reverse_version,
            }
        )
    return PaidGrantBuild(tuple(grants), tuple(operations))


def commit_paid_activation(
    request: billing_fact_repo.PaidActivationRequest,
    *,
    command: Mapping[str, object],
    billing_projection: Mapping[str, object],
    allowance_item: Mapping[str, object],
    table: object | None = None,
) -> billing_fact_repo.ActivationResult:
    """Publish activation and relationship-fenced grants in Plan 10's transaction."""
    target = table or get_table()
    try:
        built = build_paid_activation_operations(
            request,
            command=command,
            table=target,
        )
    except PaidGrantConflict:
        return billing_fact_repo.ActivationResult(
            billing_fact_repo.ActivationDisposition.CONFLICT
        )
    return billing_fact_repo.commit_paid_activation(
        request,
        billing_projection=billing_projection,
        grant_items=built.grant_items,
        allowance_item=allowance_item,
        grant_operations=built.grant_operations,
        table=target,
    )


def _active_grant(
    item: Mapping[str, object] | None,
    *,
    parent_id: str,
    beneficiary_id: str,
) -> dict[str, object] | None:
    grant = _mapping(item)
    if (
        grant is None
        or grant.get("PK") != f"PAID_GRANT#{parent_id}"
        or grant.get("SK") != f"BENEFICIARY#{beneficiary_id}"
        or grant.get("entity_type") != "beneficiary_grant"
        or grant.get("schema_version") != GRANT_SCHEMA_VERSION
        or grant.get("parent_id") != parent_id
        or grant.get("beneficiary_id") != beneficiary_id
        or grant.get("grant_status") != "active"
    ):
        return None
    try:
        plan = BillingPlanId(_required_text(grant.get("plan_id"), "plan_id"))
        if plan is BillingPlanId.FREE_TRIAL:
            return None
        _positive_integer(grant.get("grant_version"), "grant_version")
        _positive_integer(grant.get("plan_version"), "plan_version")
        _positive_integer(grant.get("allowance_version"), "allowance_version")
        _positive_integer(grant.get("activation_version"), "activation_version")
        _digest(grant.get("subscription_id_digest"), "subscription_id_digest")
    except ValueError:
        return None
    return grant


def get_active_beneficiary_grant(
    parent_id: str,
    beneficiary_id: str,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    """Return only an exact owner-scoped grant with a current strict relationship."""
    target = table or get_table()
    try:
        grant = _active_grant(
            _strong_get(target, _grant_key(parent_id, beneficiary_id)),
            parent_id=parent_id,
            beneficiary_id=beneficiary_id,
        )
        if grant is None:
            return None
        _relationship_proof(parent_id, beneficiary_id, table=target)
    except (PaidGrantConflict, TypeError, ValueError):
        return None
    return grant


def _upgrade_matches(
    grant: Mapping[str, object],
    *,
    command_id: str,
    subscription_id_digest: str,
    plan_id: BillingPlanId,
    plan_version: int,
    allowance_version: int,
    activation_version: int,
) -> bool:
    return all(
        (
            grant.get("command_id") == command_id,
            grant.get("subscription_id_digest") == subscription_id_digest,
            grant.get("plan_id") == str(plan_id),
            grant.get("plan_version") == plan_version,
            grant.get("allowance_version") == allowance_version,
            grant.get("grant_version") == activation_version,
            grant.get("activation_version") == activation_version,
        )
    )


def apply_paid_upgrade(
    *,
    parent_id: str,
    beneficiary_ids: Sequence[str],
    subscription_id_digest: str,
    command_id: str,
    plan_id: BillingPlanId,
    plan_version: int,
    allowance_version: int,
    activation_version: int,
    activated_at: datetime,
    table: object | None = None,
) -> PaidGrantResult:
    """Raise grant limits monotonically without writing weekly or storage aggregates."""
    parent = _required_text(parent_id, "parent_id")
    command = _required_text(command_id, "command_id")
    digest = _digest(subscription_id_digest, "subscription_id_digest")
    selected = validate_beneficiary_selection(plan_id, beneficiary_ids)
    plan_version = _positive_integer(plan_version, "plan_version")
    allowance_version = _positive_integer(allowance_version, "allowance_version")
    activation_version = _positive_integer(activation_version, "activation_version")
    activated_text = _aware_timestamp(activated_at, "activated_at")
    target = table or get_table()

    current: list[dict[str, object]] = []
    for student_id in selected:
        grant = _active_grant(
            _strong_get(target, _grant_key(parent, student_id)),
            parent_id=parent,
            beneficiary_id=student_id,
        )
        if grant is None:
            return PaidGrantResult(PaidGrantDisposition.CONFLICT)
        current.append(grant)
    if all(
        _upgrade_matches(
            grant,
            command_id=command,
            subscription_id_digest=digest,
            plan_id=plan_id,
            plan_version=plan_version,
            allowance_version=allowance_version,
            activation_version=activation_version,
        )
        for grant in current
    ):
        return PaidGrantResult(PaidGrantDisposition.ALREADY_APPLIED)

    operations: list[dict[str, Any]] = []
    for index, (student_id, grant) in enumerate(zip(selected, current, strict=True)):
        try:
            old_plan = BillingPlanId(_required_text(grant.get("plan_id"), "plan_id"))
            old_plan_version = _positive_integer(grant.get("plan_version"), "plan_version")
            old_allowance_version = _positive_integer(
                grant.get("allowance_version"), "allowance_version"
            )
            old_grant_version = _positive_integer(
                grant.get("grant_version"), "grant_version"
            )
            if (
                grant.get("subscription_id_digest") != digest
                or _PLAN_RANK[plan_id] <= _PLAN_RANK[old_plan]
                or plan_version <= old_plan_version
                or allowance_version <= old_allowance_version
                or activation_version <= old_grant_version
            ):
                return PaidGrantResult(PaidGrantDisposition.CONFLICT)
            proof = _relationship_proof(parent, student_id, table=target)
        except (KeyError, PaidGrantConflict, ValueError):
            return PaidGrantResult(PaidGrantDisposition.CONFLICT)
        operations.extend(
            _proof_operations(parent, student_id, proof, include_parent=index == 0)
        )
        upgraded = {
            **grant,
            "command_id": command,
            "grant_version": activation_version,
            "plan_id": str(plan_id),
            "plan_version": plan_version,
            "allowance_version": allowance_version,
            "activation_version": activation_version,
            "activated_at": activated_text,
            "parent_profile_version": proof.parent_profile_version,
            "parent_account_fence_generation": proof.parent_fence_generation,
            "student_profile_version": proof.student_profile_version,
            "student_account_fence_generation": proof.student_fence_generation,
            "forward_relationship_version": proof.forward_version,
            "reverse_relationship_version": proof.reverse_version,
        }
        operations.append(
            {
                "Put": {
                    "Item": upgraded,
                    "ConditionExpression": (
                        "grant_status=:active AND grant_version=:grant_version "
                        "AND plan_version=:plan_version "
                        "AND allowance_version=:allowance_version "
                        "AND subscription_id_digest=:subscription_id_digest"
                    ),
                    "ExpressionAttributeValues": {
                        ":active": "active",
                        ":grant_version": old_grant_version,
                        ":plan_version": old_plan_version,
                        ":allowance_version": old_allowance_version,
                        ":subscription_id_digest": digest,
                    },
                }
            }
        )
    try:
        account_deletion_repo.transact(operations, table=target)
    except Exception:
        try:
            replayed = [
                _active_grant(
                    _strong_get(target, _grant_key(parent, student_id)),
                    parent_id=parent,
                    beneficiary_id=student_id,
                )
                for student_id in selected
            ]
        except Exception:
            return PaidGrantResult(PaidGrantDisposition.RETRYABLE)
        if all(
            grant is not None
            and _upgrade_matches(
                grant,
                command_id=command,
                subscription_id_digest=digest,
                plan_id=plan_id,
                plan_version=plan_version,
                allowance_version=allowance_version,
                activation_version=activation_version,
            )
            for grant in replayed
        ):
            return PaidGrantResult(PaidGrantDisposition.ALREADY_APPLIED)
        return PaidGrantResult(PaidGrantDisposition.RETRYABLE)
    return PaidGrantResult(PaidGrantDisposition.UPGRADED, tuple(operations))


__all__ = [
    "PaidGrantBuild",
    "PaidGrantConflict",
    "PaidGrantDisposition",
    "PaidGrantResult",
    "apply_paid_upgrade",
    "build_paid_activation_operations",
    "commit_paid_activation",
    "get_active_beneficiary_grant",
    "validate_beneficiary_selection",
]
