"""Executable capability classification for every route registered below ``/admin``."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    ResourceRef,
    ResourceType,
    operator_capability_permits,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor


@dataclass(frozen=True, slots=True)
class AdminRoutePolicy:
    capability: str
    purpose: AuthorizationPurpose
    action: AuthorizationAction
    resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE
    target_keys: tuple[str, ...] = ()


def _policy(capability: str, purpose: AuthorizationPurpose, action: AuthorizationAction, *targets: str,
            resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE) -> AdminRoutePolicy:
    return AdminRoutePolicy(capability, purpose, action, resource_type, targets)


def classify_admin_route(method: str, path: str) -> AdminRoutePolicy:
    """Return one exact executable policy for an admin-prefixed registered route."""
    method = method.upper()
    action = {
        "GET": AuthorizationAction.READ,
        "PATCH": AuthorizationAction.UPDATE,
        "DELETE": AuthorizationAction.DELETE,
    }.get(method, AuthorizationAction.CREATE)

    if path == "/admin/notifications":
        return _policy("notification_event_inspector", AuthorizationPurpose.NOTIFICATION_EVENT_INSPECTION,
                       AuthorizationAction.READ, resource_type=ResourceType.NOTIFICATION_EVENT)
    if path == "/admin/notifications/delivery-status":
        return _policy("notification_delivery_health_reader", AuthorizationPurpose.NOTIFICATION_DELIVERY_HEALTH,
                       AuthorizationAction.READ, resource_type=ResourceType.NOTIFICATION_COLLECTION)
    if path.startswith("/admin/privileged-identities"):
        return _policy("admin_identity_manager", AuthorizationPurpose.IDENTITY_MANAGEMENT,
                       AuthorizationAction.MANAGE_PRIVILEGE, "target_id")
    if path.startswith("/admin/moderation"):
        return _policy("student_safety_review", AuthorizationPurpose.MODERATION_OPERATIONS, action, "case_id")
    if path.startswith("/admin/curriculum"):
        if "/analytics/" in path:
            capability = "curriculum_analytics_reader" if "warehouse-export" not in path else "curriculum_analytics_exporter"
            op_action = AuthorizationAction.EXPORT if "warehouse-export" in path else AuthorizationAction.READ
        elif "/migrations/" in path:
            capability = "curriculum_migration_operator"
            op_action = action
        elif method == "GET" or "preview" in path or "diff" in path or "audit" in path or "worklist" in path:
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.READ
        elif any(marker in path for marker in ("/approve", "/request-changes", "/submit-review")):
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
        elif any(marker in path for marker in ("/publish", "/rollback", "/archive")):
            capability = "curriculum_publisher"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
        else:
            capability = "curriculum_author"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
        return _policy(capability, AuthorizationPurpose.CURRICULUM_OPERATIONS, op_action,
                       "public_lesson_id", "version_id", "migration_id")
    if path.startswith("/admin/users"):
        capability = "admin_identity_manager" if method != "GET" else "student_support_lookup"
        op_action = AuthorizationAction.MANAGE_PRIVILEGE if method != "GET" else AuthorizationAction.LOOKUP
        return _policy(capability, AuthorizationPurpose.ACCOUNT_OPERATIONS, op_action, "user_id")
    if path.startswith("/admin/account-verification") or path.startswith("/admin/account-operations"):
        return _policy("student_support_lookup", AuthorizationPurpose.ACCOUNT_OPERATIONS,
                       AuthorizationAction.LOOKUP, "user_id", "parent_id")
    if path.startswith("/admin/parent-bindings"):
        capability = "parent_binding_repairer" if method != "GET" else "student_support_lookup"
        return _policy(capability, AuthorizationPurpose.ACCOUNT_OPERATIONS,
                       AuthorizationAction.UPDATE if method != "GET" else AuthorizationAction.LOOKUP,
                       "parent_id", "student_id", resource_type=ResourceType.PARENT_BINDING)
    if path.startswith("/admin/subscriptions"):
        if "/refunds" in path:
            capability, op_action = "billing_refund_executor", AuthorizationAction.UPDATE
        elif "accounting-export" in path:
            capability, op_action = "billing_accounting_exporter", AuthorizationAction.EXPORT
        elif "rollout-controls" in path and method != "GET":
            capability, op_action = "billing_rollout_manager", AuthorizationAction.UPDATE
        elif method == "GET":
            capability, op_action = "billing_operations_reader", AuthorizationAction.READ
        else:
            capability, op_action = "billing_operations_manager", action
        return _policy(capability, AuthorizationPurpose.BILLING_OPERATIONS, op_action,
                       "parent_id", "request_id")
    if path.startswith("/admin/usage"):
        capability = "usage_reconciliation_operator" if "reconciliation" in path else "usage_event_inspector"
        op_action = AuthorizationAction.UPDATE if "reconciliation" in path else AuthorizationAction.READ
        return _policy(capability, AuthorizationPurpose.USAGE_OPERATIONS, op_action, "student_id")
    if path.startswith("/admin/reports"):
        targets = ("parent_id", "student_id", "week_start", "job_id", "delivery_id", "report_id")
        if any(marker in path for marker in ("support-handoff-delivery", "/messages", "/provider-sync", "/retry")):
            capability = "report_external_handoff_sender" if method != "GET" else "report_handoff_reader"
            op_action = AuthorizationAction.EXTERNAL_SEND if method != "GET" else AuthorizationAction.READ
            purpose = AuthorizationPurpose.SUPPORT_HANDOFF
        elif any(marker in path for marker in ("audit-retention", "immutable-evidence", "retention-governance", "legal-holds")):
            capability = "report_governance_reader" if (method == "GET" or path.endswith("/status")) else "report_governance_manager"
            op_action = AuthorizationAction.READ if capability.endswith("reader") else AuthorizationAction.UPDATE
            purpose = AuthorizationPurpose.AUDIT_GOVERNANCE
        elif any(marker in path for marker in ("recovery-evidence", "support-package", "support-handoff-package", "release-evidence")):
            capability = "report_evidence_exporter"
            op_action = AuthorizationAction.EXPORT
            purpose = AuthorizationPurpose.REPORT_RECOVERY
        elif any(marker in path for marker in ("resend", "retry-generation", "recovery-jobs", "edit-drafts", "artifact-edit", "artifact-rollback")):
            capability = "report_recovery_reader" if method == "GET" else "report_recovery_operator"
            op_action = AuthorizationAction.READ if method == "GET" else AuthorizationAction.UPDATE
            purpose = AuthorizationPurpose.REPORT_RECOVERY
        else:
            capability = "report_metadata_reader"
            op_action = AuthorizationAction.READ
            purpose = AuthorizationPurpose.REPORT_OPERATIONS
        return _policy(capability, purpose, op_action, *targets, resource_type=ResourceType.REPORT)
    if path.startswith("/admin/bi"):
        capability = "bi_exporter" if "warehouse-export" in path else "bi_operations_reader"
        return _policy(capability, AuthorizationPurpose.GLOBAL_OPERATIONS,
                       AuthorizationAction.EXPORT if "warehouse-export" in path else AuthorizationAction.READ)
    if path.startswith("/admin/external-activation"):
        return _policy("production_readiness_reader", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    if path.startswith("/admin/teacher-dispatch"):
        return _policy("teacher_dispatch_operator", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    if path in {"/admin/stats", "/admin/core-smoke"}:
        return _policy("platform_operations_reader", AuthorizationPurpose.GLOBAL_OPERATIONS, AuthorizationAction.READ)
    raise KeyError(f"unclassified admin route: {method} {path}")


async def _target(request: Request, policy: AdminRoutePolicy, actor: Actor) -> tuple[str, str]:
    values = {**request.query_params, **request.path_params}
    try:
        if values.get("job_id"):
            from stoa.db.repositories import report_repo

            job = report_repo.get_recovery_job(str(values["job_id"]))
            if not job:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
                raise HTTPException(error.status_code, detail=error.public_body())
            filters = job.get("filters") or {}
            values.setdefault("student_id", filters.get("student_id"))
            values.setdefault("parent_id", filters.get("parent_id"))
        if values.get("delivery_id"):
            from stoa.db.repositories import report_repo

            delivery = report_repo.get_support_handoff_delivery_record(
                str(values["delivery_id"])
            )
            if not delivery:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
                raise HTTPException(error.status_code, detail=error.public_body())
            values.setdefault("student_id", delivery.get("student_id"))
            values.setdefault("parent_id", delivery.get("parent_id"))
    except HTTPException:
        raise
    except Exception as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            internal_detail=type(exc).__name__,
        )
        raise HTTPException(error.status_code, detail=error.public_body()) from exc
    selected = [(key, str(values[key])) for key in policy.target_keys if values.get(key)]
    if not selected:
        return "global", actor.user_id
    resource_id = ":".join(value for _, value in selected)
    student_id = str(values.get("student_id") or values.get("user_id") or values.get("parent_id") or actor.user_id)
    return resource_id, student_id


async def admin_operation(
    request: Request,
    actor: Actor = Depends(get_actor),
) -> dict[str, object]:
    route = request.scope.get("route")
    path = str(getattr(route, "path", request.url.path))
    try:
        policy = classify_admin_route(request.method, path)
    except KeyError as exc:
        error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED, internal_detail=str(exc))
        raise HTTPException(error.status_code, detail=error.public_body()) from exc
    resource_id, student_id = await _target(request, policy, actor)
    ref = ResourceRef(policy.resource_type, resource_id, student_id, relationship_known=True)
    if not operator_capability_permits(
        actor,
        capability=policy.capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    ):
        error = SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
        raise HTTPException(error.status_code, detail=error.public_body()) from error
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "account_status": actor.account_status.value,
    }


admin_operation.admin_policy_classifier = classify_admin_route  # type: ignore[attr-defined]
