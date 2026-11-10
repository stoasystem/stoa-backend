from fastapi import FastAPI

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.links import LINKED_AT
from stoa.deps import get_actor, get_authorization_audit_sink, get_current_user
from stoa.security.authorization import (
    AuthorizationFacts,
    ParentAuthorizationFacts,
    TeacherAuthorizationFacts,
)
from stoa.security.identity import (
    AccountStatus,
    Actor,
    CanonicalRole,
    CapabilityGrant,
)
from stoa.security.declared_authorization import get_authorization_fact_repository
from stoa.services.current_relationship import SOURCE_LINK, Standing, Verdict


def actor_from_user(user: dict) -> Actor:
    role = CanonicalRole(user["role"])
    capabilities = user.get("grantCapabilities")
    legacy_operator_capabilities = capabilities is None and bool(user.get("capabilities"))
    if capabilities is None and user.get("capabilities"):
        capabilities = tuple(user["capabilities"])
    if capabilities is None and role is CanonicalRole.ADMIN:
        capabilities = (
            "learning_assignment_manager",
            "assignment_automation_preview",
            "assignment_automation_execute",
            "student_content_review",
            "admin_identity_manager",
            "student_support_lookup",
            "student_safety_review",
            "parent_binding_repairer",
            "billing_operations_reader",
            "billing_operations_manager",
            "billing_accounting_exporter",
            "billing_rollout_manager",
            "billing_refund_executor",
            "usage_event_inspector",
            "usage_reconciliation_operator",
            "report_metadata_reader",
            "report_recovery_reader",
            "report_recovery_operator",
            "report_evidence_exporter",
            "report_handoff_reader",
            "report_external_handoff_sender",
            "report_governance_reader",
            "report_governance_manager",
            "bi_operations_reader",
            "bi_exporter",
            "production_readiness_reader",
            "platform_operations_reader",
            "teacher_dispatch_operator",
            "teacher_support_allowance_manager",
            "notification_event_inspector",
            "notification_delivery_health_reader",
        )
    capabilities = capabilities or ()
    explicit_scope = user.get("grantScope")
    scopes = (
        (str(explicit_scope),)
        if explicit_scope
        else (
            ("global", "student:student-1")
            if role is CanonicalRole.ADMIN
            else (("global",) if legacy_operator_capabilities else ("student:student-1",))
        )
    )
    grants = tuple(
        CapabilityGrant(name, scope, 1)
        for name in capabilities
        for scope in scopes
    )
    return Actor(
        str(user["sub"]),
        "https://identity.test",
        f"{user['sub']}-subject",
        role,
        AccountStatus(user.get("accountStatus") or "active"),
        role.value,
        grants,
        tuple(
            (key, str(value))
            for key, value in user.items()
            if key in {"preferredLocale", "preferred_locale", "language", "email"}
        ),
    )


def install_actor_overrides(app: FastAPI, user: dict) -> Actor:
    actor = actor_from_user(user)

    class Facts:
        async def facts_for(self, current_actor, resource, action, purpose, _value):
            student = {
                "user_id": resource.student_id,
                "role": "student",
                "account_status": "active",
            }
            if current_actor.role is CanonicalRole.PARENT and user.get("bound", True):
                return AuthorizationFacts(
                    parent=ParentAuthorizationFacts(
                        Verdict(
                            Standing.CURRENT,
                            current_actor.user_id,
                            resource.student_id,
                            relationship="child",
                            status="active",
                            source=SOURCE_LINK,
                            version=LINKED_AT,
                        ),
                        {
                            "user_id": current_actor.user_id,
                            "role": "parent",
                            "account_status": "active",
                        },
                        student,
                    )
                )
            if current_actor.role is CanonicalRole.TEACHER and user.get("assigned", True):
                request = (
                    _value
                    if resource.resource_type.value
                    in {"question", "teacher_help_request"}
                    else None
                )
                if (
                    resource.resource_type.value == "ai_teacher_draft"
                    and _value.get("question_id")
                ):
                    # The help request the draft was made from (#234).
                    request_id = _value.get("question_id")
                    task_teachers = user.get("taskTeacherByQuestion") or {}
                    request = {
                        "conversation_id": request_id,
                        "escalation_request_id": request_id,
                        "student_id": resource.student_id,
                        "teacher_id": task_teachers.get(
                            request_id,
                            user.get("taskTeacherId", current_actor.user_id),
                        ),
                        "escalation_status": user.get("taskStatus", "in_progress"),
                        "dispatch_status": user.get("taskDispatchStatus", "accepted"),
                    }
                return AuthorizationFacts(
                    teacher=TeacherAuthorizationFacts(
                        request=request,
                        assignment=None
                        if request
                        else {
                            "teacher_id": current_actor.user_id,
                            "student_id": resource.student_id,
                            "status": "active",
                            "resource_types": [resource.resource_type.value],
                            "actions": [action.value],
                            "purposes": [purpose.value],
                        },
                        teacher_account={
                            "user_id": current_actor.user_id,
                            "role": "teacher",
                            "account_status": current_actor.account_status.value,
                        },
                        student_account=student,
                    )
                )
            return AuthorizationFacts()

    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_authorization_fact_repository] = Facts
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return actor
