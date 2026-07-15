"""Executable capability classification for every route registered below ``/admin``."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    ResourceRef,
    ResourceType,
    PolicyDecision,
    operator_capability_decision,
    record_authorization_decision,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id


async def _record_admin_decision(**kwargs) -> PolicyDecision:
    try:
        return await record_authorization_decision(**kwargs)
    except SecurityDecisionError as error:
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": str(error.correlation_id)},
        ) from error


@dataclass(frozen=True, slots=True)
class AdminRoutePolicy:
    capability: str
    purpose: AuthorizationPurpose
    action: AuthorizationAction
    resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE
    target_keys: tuple[str, ...] = ()
    alternate_capabilities: tuple[str, ...] = ()

    @property
    def capabilities(self) -> tuple[str, ...]:
        return (self.capability, *self.alternate_capabilities)


def _policy(capability: str, purpose: AuthorizationPurpose, action: AuthorizationAction, *targets: str,
            resource_type: ResourceType = ResourceType.OPERATOR_RESOURCE,
            alternate_capabilities: tuple[str, ...] = ()) -> AdminRoutePolicy:
    return AdminRoutePolicy(capability, purpose, action, resource_type, targets, alternate_capabilities)


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
        alternates: tuple[str, ...] = ()
        if "/analytics/" in path:
            capability = "curriculum_analytics_reader" if "warehouse-export" not in path else "curriculum_analytics_exporter"
            op_action = AuthorizationAction.EXPORT if "warehouse-export" in path else AuthorizationAction.READ
        elif "/migrations/" in path:
            capability = "migration_operator"
            op_action = action
            alternates = ("curriculum_publisher",)
        elif "validation-preview" in path or path.endswith("/preview"):
            capability = "curriculum_author"
            op_action = AuthorizationAction.READ
            alternates = ("curriculum_reviewer", "curriculum_publisher")
        elif "diff" in path or "audit" in path or "worklist" in path or method == "GET":
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.READ
            alternates = ("curriculum_publisher",)
        elif "/submit-review" in path:
            capability = "curriculum_author"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        elif any(marker in path for marker in ("/approve", "/request-changes", "/submit-review")):
            capability = "curriculum_reviewer"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ("curriculum_publisher",)
        elif any(marker in path for marker in ("/publish", "/rollback", "/archive")):
            capability = "curriculum_publisher"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        else:
            capability = "curriculum_author"
            op_action = AuthorizationAction.CURRICULUM_MUTATION
            alternates = ()
        return _policy(capability, AuthorizationPurpose.CURRICULUM_OPERATIONS, op_action,
                       "public_lesson_id", "version_id", "migration_id",
                       alternate_capabilities=alternates)
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


async def _target(
    request: Request,
    policy: AdminRoutePolicy,
    actor: Actor,
    correlation_id: str,
) -> tuple[str, str]:
    values = {**request.query_params, **request.path_params}
    try:
        if values.get("job_id"):
            from stoa.db.repositories import report_repo

            job = report_repo.get_recovery_job(str(values["job_id"]))
            if not job:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
                raise HTTPException(
                    error.status_code,
                    detail=error.public_body(),
                    headers={"X-Correlation-ID": correlation_id},
                )
            filters = job.get("filters") or {}
            values.setdefault("student_id", filters.get("student_id"))
            values.setdefault("parent_id", filters.get("parent_id"))
        if values.get("delivery_id"):
            from stoa.db.repositories import report_repo

            delivery = report_repo.get_support_handoff_delivery_record(
                str(values["delivery_id"])
            )
            if not delivery:
                error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
                raise HTTPException(
                    error.status_code,
                    detail=error.public_body(),
                    headers={"X-Correlation-ID": correlation_id},
                )
            values.setdefault("student_id", delivery.get("student_id"))
            values.setdefault("parent_id", delivery.get("parent_id"))
    except HTTPException:
        raise
    except Exception as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
            correlation_id,
            internal_detail=type(exc).__name__,
        )
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from exc
    selected = [(key, str(values[key])) for key in policy.target_keys if values.get(key)]
    if not selected:
        return "global", actor.user_id
    resource_id = ":".join(value for _, value in selected)
    student_id = str(values.get("student_id") or values.get("user_id") or values.get("parent_id") or actor.user_id)
    return resource_id, student_id


async def admin_operation(
    request: Request,
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> dict[str, object]:
    route = request.scope.get("route")
    path = str(getattr(route, "path", request.url.path))
    try:
        policy = classify_admin_route(request.method, path)
    except KeyError as exc:
        error = SecurityDecisionError(
            SecurityErrorCode.ACTION_NOT_ALLOWED,
            correlation_id,
            internal_detail=str(exc),
        )
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from exc
    provisional_ref = ResourceRef(
        policy.resource_type,
        path,
        actor.user_id,
        relationship_known=True,
    )
    eligible_role = actor.role.value == "admin" or (
        actor.role.value == "teacher"
        and any(
            capability.startswith("curriculum_") or capability == "migration_operator"
            for capability in policy.capabilities
        )
    )
    if (
        not actor.can_authorize
        or not eligible_role
        or not any(grant.capability in policy.capabilities for grant in actor.current_grants)
    ):
        decision = await _record_admin_decision(
            actor=actor,
            resource=provisional_ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=PolicyDecision(False, SecurityErrorCode.ACTION_NOT_ALLOWED),
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_precheck",
        )
        error = SecurityDecisionError(decision.result_code, correlation_id)
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from error
    try:
        resource_id, student_id = await _target(request, policy, actor, correlation_id)
    except HTTPException as exc:
        await _record_admin_decision(
            actor=actor,
            resource=provisional_ref,
            action=policy.action,
            purpose=policy.purpose,
            decision=PolicyDecision(False, SecurityErrorCode.RESOURCE_NOT_FOUND),
            correlation_id=correlation_id,
            audit_sink=audit_sink,
            decision_kind="admin_target",
        )
        raise exc
    ref = ResourceRef(policy.resource_type, resource_id, student_id, relationship_known=True)
    selected_capability = next(
        capability
        for capability in policy.capabilities
        if any(grant.capability == capability for grant in actor.current_grants)
    )
    decision = operator_capability_decision(
        actor,
        capability=selected_capability,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
    )
    decision = await _record_admin_decision(
        actor=actor,
        resource=ref,
        action=policy.action,
        purpose=policy.purpose,
        decision=decision,
        correlation_id=correlation_id,
        audit_sink=audit_sink,
        decision_kind="admin_capability",
    )
    if not decision.allowed:
        error = SecurityDecisionError(decision.result_code, correlation_id)
        raise HTTPException(
            error.status_code,
            detail=error.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from error
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "account_status": actor.account_status.value,
        "capabilities": {
            grant.capability: "granted" for grant in actor.current_grants
        },
    }


admin_operation.admin_policy_classifier = classify_admin_route  # type: ignore[attr-defined]
