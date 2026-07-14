"""Limited production pilot readiness and launch decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stoa.services import release_evidence_service


RELEASE_STATE = "limited-pilot-ready-local-contracts"
FORBIDDEN_EVIDENCE_FIELDS = {
    "answer",
    "authorization",
    "cookie",
    "id_token",
    "object_key",
    "password",
    "prompt",
    "provider_payload",
    "raw_student_content",
    "refresh_token",
    "s3_key",
    "secret",
    "student_work",
    "token",
}
READINESS_STATES = {"live_ready", "read_only_verified", "local_only", "blocked", "failed", "deferred"}
PILOT_COMPONENTS = {
    "backend",
    "frontend",
    "mobile",
    "cognito_email",
    "payment",
    "notifications",
    "support_crm",
    "ai",
    "bi_apm",
    "data_lifecycle",
    "incident_operations",
}
PILOT_REQUIRED_COMPONENTS = {
    "backend",
    "frontend",
    "mobile",
    "cognito_email",
    "payment",
    "notifications",
    "support_crm",
    "ai",
    "bi_apm",
    "data_lifecycle",
    "incident_operations",
}
PROVIDER_COMPONENTS = {"payment", "notifications", "support_crm", "bi_apm", "mobile", "data_lifecycle", "incident_operations"}
PILOT_OUTCOME_SIGNALS = {
    "activation",
    "retention",
    "usage",
    "teacher_help",
    "ai_quality",
    "notifications",
    "support_load",
    "mobile_stability",
    "account_billing",
    "satisfaction",
}
LAUNCH_SURFACES = {
    "self_serve_signup",
    "email_verification",
    "parent_student_setup",
    "entitlement",
    "payment_subscription",
    "mobile_install",
    "first_learning_action",
    "support_fallback",
}
LIVE_APPROVAL_ROLES = {
    "decision_owner",
    "product_owner",
    "support_owner",
    "incident_owner",
    "finance_billing_owner",
    "mobile_release_owner",
    "provider_owner",
}
LIVE_ACTIVATION_DEPENDENCIES = {
    "payment",
    "notifications",
    "support_crm",
    "bi_apm",
    "mobile_testflight",
    "production_restore",
    "launch_room_tabletop",
}
LIVE_OPERATIONS_SIGNALS = {
    "onboarding",
    "login",
    "entitlement",
    "first_learning_action",
    "support_intake",
    "teacher_sla",
    "billing",
    "notifications",
    "ai_quality",
    "mobile_stability",
}
REVENUE_GROWTH_SURFACES = {
    "package_copy",
    "checkout",
    "payment_methods",
    "failed_payment_states",
    "entitlement_activation",
    "usage_display",
    "invoice_refund_support",
    "lifecycle_messages",
    "referral_waitlist",
}
LEARNING_QUALITY_AREAS = {
    "learning_progress",
    "weak_topics",
    "curriculum_coverage",
    "exercise_bank",
    "ai_summaries",
    "teacher_tools",
    "adaptive_recommendations",
    "parent_progress_reporting",
}
OPERATIONS_SCALE_AREAS = {
    "incident_review",
    "data_quality",
    "queue_health",
    "admin_workflows",
    "teacher_dispatch",
    "support_handoff",
    "observability",
    "release_rollback",
}
V6_REAL_EVIDENCE_ACCESS_PATHS = {
    "admin",
    "parent",
    "student",
    "teacher_support",
    "provider",
    "mobile",
    "monitoring",
    "deployment",
}
V6_ACCOUNT_PAYMENT_USAGE_SURFACES = {
    "login",
    "email_verification",
    "login_code_passwordless",
    "account_recovery",
    "role_visibility",
    "paid_access",
    "checkout_paywall",
    "entitlement_activation",
    "subscription_state",
    "usage_ledger",
    "quota_display",
    "admin_support_explanations",
}
V6_NOTIFICATION_SUPPORT_PROVIDER_SURFACES = {
    "email_notifications",
    "push_notifications",
    "realtime_notifications",
    "support_crm_handoff",
    "support_queue",
    "teacher_dispatch_sla",
    "mobile_testflight_install",
    "payment_provider",
    "bi_apm",
    "ai_provider",
}
V6_PILOT_LAUNCH_PACKET_AREAS = {
    "cohort_scope",
    "account_aliases",
    "communication_plan",
    "consent_state",
    "support_staffing",
    "teacher_owner",
    "launch_room",
    "dashboards",
    "rollback_authority",
    "pause_criteria",
}
V6_REMEDIATION_SURFACES = {
    "activation",
    "support",
    "teacher",
    "notification",
    "usage",
    "entitlement",
    "mobile",
    "learning",
}
V6_ACCOUNT_FIX_SURFACES = {
    "login",
    "email_verification",
    "resend_confirm",
    "login_code_passwordless_policy",
    "account_recovery",
    "session_expiry",
    "role_visibility",
    "admin_support_state",
}
V6_ENTITLEMENT_SUPPORT_FIX_SURFACES = {
    "paid_entitlement",
    "checkout_paywall",
    "subscription_state",
    "usage_ledger",
    "quota_reconciliation",
    "notification_delivery",
    "support_handoff",
    "teacher_dispatch_sla",
}
V6_LEARNING_MOBILE_FIX_SURFACES = {
    "onboarding",
    "first_assignment",
    "first_practice_action",
    "curriculum_access",
    "ai_help_flow",
    "parent_progress_view",
    "mobile_install_access",
}
V6_PAID_CONVERSION_SURFACES = {
    "package",
    "checkout",
    "payment_method",
    "paywall",
    "entitlement_activation",
    "renewal",
    "cancellation",
    "failed_payment",
    "invoice",
    "refund",
}
V6_USAGE_QUOTA_SURFACES = {
    "question_submission",
    "chat_message",
    "teacher_help",
    "practice_action",
    "assignment_action",
    "generation_action",
    "quota_display",
    "quota_block",
    "reconciliation",
}
V6_VERIFICATION_RECOVERY_SURFACES = {
    "email_verification",
    "login_code_policy",
    "resend_confirm",
    "expiry",
    "account_recovery",
    "support_override",
    "role_transition",
}
V6_BILLING_LIFECYCLE_SURFACES = {
    "failed_payment",
    "refund",
    "invoice",
    "subscription_change",
    "entitlement_mismatch",
    "usage_dispute",
    "onboarding",
    "activation",
    "renewal",
    "reminder",
    "cancellation",
    "win_back",
}
V6_LEARNING_EVIDENCE_SIGNALS = {
    "completion",
    "retry",
    "mastery_progress",
    "weak_topics",
    "teacher_help",
    "ai_draft_review",
    "parent_report_engagement",
    "support_contacts",
}
V6_CURRICULUM_QUALITY_SURFACES = {
    "priority_lessons",
    "exercise_bank",
    "explanations",
    "metadata",
    "validation",
    "preview",
    "rollback",
    "analytics_tags",
    "sequencing",
    "progress_reporting",
}
V6_AI_TEACHER_QUALITY_SURFACES = {
    "summaries",
    "explanations",
    "exercise_drafts",
    "teacher_tools",
    "refusal_fallback",
    "safety_review",
    "cost_latency_observability",
    "provider_error_observability",
}
V6_ADAPTIVE_PROGRESS_SURFACES = {
    "recent_learning",
    "weak_topics",
    "completed_assignments",
    "content_availability",
    "freshness",
    "duplicate_suppression",
    "explanation_copy",
    "teacher_admin_correction",
    "parent_progress_report",
}
V6_OPERATIONS_RISK_AREAS = {
    "incidents",
    "near_misses",
    "manual_toil",
    "data_drift",
    "provider_degradation",
    "support_bottlenecks",
    "teacher_queue_issues",
    "release_regressions",
}
V6_OPERATOR_WORKFLOW_SURFACES = {
    "account_operations",
    "billing_support",
    "teacher_dispatch",
    "support_handoff",
    "content_operations",
    "curriculum_qa",
    "escalation_workflows",
}
V6_OBSERVABILITY_SURFACES = {
    "auth",
    "entitlement",
    "usage",
    "billing",
    "notification",
    "support_sla",
    "teacher_dispatch",
    "ai_provider_health",
    "mobile",
    "curriculum_content",
    "incidents",
    "revenue",
}
V6_RELEASE_DISCIPLINE_SURFACES = {
    "backend",
    "frontend",
    "mobile",
    "provider",
    "migration",
    "configuration",
    "smoke_tests",
    "fixture_hygiene",
    "owner_handoff",
}
V65_PRODUCTION_ACCESS_PATHS = {
    "admin",
    "parent",
    "student",
    "teacher_support",
    "provider",
    "mobile",
    "monitoring",
    "deploy",
    "support",
}
V65_ACCOUNT_PAYMENT_USAGE_SURFACES = {
    "login",
    "email_verification",
    "login_code_passwordless_policy",
    "account_recovery",
    "role_visibility",
    "admin_support_visibility",
    "paid_access",
    "checkout_paywall",
    "entitlement_activation",
    "subscription_state",
    "usage_ledger",
    "quota_display",
    "support_explanations",
}
V65_NOTIFICATION_SUPPORT_MOBILE_LEARNING_SURFACES = {
    "notification_delivery",
    "support_handoff",
    "teacher_dispatch_sla",
    "mobile_testflight_install",
    "ai_provider_health",
    "provider_health",
    "first_learning_action",
    "learning_path",
}
V65_COHORT_LAUNCH_PACKET_AREAS = {
    "account_aliases",
    "communication_plan",
    "consent_state",
    "support_staffing",
    "teacher_owner",
    "launch_room",
    "dashboards",
    "rollback_authority",
    "pause_criteria",
    "support_macros",
    "known_disabled_features",
    "day_one_operating_plan",
}
V66_COHORT_OPERATION_SIGNALS = {
    "activation",
    "support",
    "teacher",
    "billing",
    "notification",
    "mobile",
    "usage",
    "learning",
}
V66_ACCOUNT_ENTITLEMENT_FIX_SURFACES = {
    "login",
    "verification",
    "recovery",
    "role_visibility",
    "entitlement_activation",
    "subscription_state",
    "usage_writes",
    "quota_display",
    "admin_support_explanations",
}
V66_SUPPORT_TEACHER_MOBILE_FIX_SURFACES = {
    "support_handoff",
    "support_queue",
    "teacher_dispatch_sla",
    "escalation",
    "notification_delivery",
    "mobile_access_install",
    "incident_handling",
}
V66_LEARNING_PARENT_FIX_SURFACES = {
    "onboarding",
    "first_practice_assignment",
    "curriculum_access",
    "ai_help_flow",
    "recommendations",
    "parent_progress_reporting",
}
V67_PAID_BILLING_REVIEW_SURFACES = {
    "checkout",
    "paywall",
    "payment_methods",
    "entitlement_activation",
    "renewal",
    "cancellation",
    "failed_payment",
    "invoice",
    "refund",
    "manual_correction",
}
V67_USAGE_ACCOUNT_RELIABILITY_SURFACES = {
    "usage_ledger",
    "idempotency",
    "quota_display",
    "quota_blocking",
    "support_explanations",
    "reconciliation_reports",
    "verification_state",
    "subscription_state",
    "child_access",
    "recovery_state",
}
V67_LIFECYCLE_RETENTION_SURFACES = {
    "onboarding",
    "activation",
    "reminder",
    "renewal",
    "failed_payment",
    "cancellation",
    "win_back",
    "support_capacity",
    "retention_signals",
}
V67_CONTROLLED_INTAKE_SURFACES = {
    "referral",
    "waitlist",
    "invite",
    "eligibility_copy",
    "availability_copy",
    "abuse_handling",
    "cohort_planning",
    "support_staffing",
}
V68_REAL_LEARNING_OUTCOME_SIGNALS = {
    "completion",
    "retry",
    "mastery_progress",
    "weak_topics",
    "teacher_help",
    "ai_draft_review",
    "parent_report_engagement",
    "support_contacts",
}
V68_CURRICULUM_RELEASE_SURFACES = {
    "priority_lessons",
    "exercises",
    "explanations",
    "metadata",
    "sequencing",
    "validation",
    "preview",
    "rollback",
    "analytics_tags",
    "progress_integrity",
    "recommendation_integrity",
}
V68_AI_TEACHER_RELEASE_SURFACES = {
    "summaries",
    "explanations",
    "exercise_drafts",
    "teacher_tools",
    "review_workflows",
    "refusal_fallback",
    "safety_review",
    "cost_latency_observability",
    "provider_error_observability",
}
V68_ADAPTIVE_PROGRESS_RELEASE_SURFACES = {
    "recent_learning",
    "weak_topics",
    "completed_assignments",
    "content_availability",
    "freshness",
    "duplicate_suppression",
    "student_explanations",
    "parent_explanations",
    "teacher_admin_correction",
    "parent_progress_reporting",
}
V69_MARKET_EVIDENCE_AREAS = {
    "cohort_operations",
    "activation",
    "account_reliability",
    "revenue",
    "retention",
    "learning_quality",
    "support",
    "teacher_operations",
    "mobile",
    "provider_health",
    "incidents",
    "observability",
    "release_discipline",
}
V69_LAUNCH_SCOPE_RISK_AREAS = {
    "rollout_scope",
    "audience",
    "pricing_package",
    "lifecycle_messaging",
    "support_staffing",
    "teacher_capacity",
    "disabled_features",
    "known_limitations",
    "support_macros",
    "incident_communications",
}
V69_PRODUCTION_PROVIDER_READINESS_AREAS = {
    "backend",
    "frontend_web",
    "mobile_app_store",
    "providers",
    "monitoring",
    "alerting",
    "rollback",
    "migration",
    "incident_readiness",
}
V69_ROLLOUT_PLAN_AREAS = {
    "cohort_market_scope",
    "growth_limits",
    "support_staffing",
    "dashboards",
    "freeze",
    "rollback",
    "owner_approvals",
    "communications",
    "known_limitations",
    "disabled_features",
}


@dataclass(frozen=True)
class ReadinessItem:
    component: str
    state: str
    owner: str
    blocker: str
    evidence: str

    def row(self) -> dict[str, str]:
        return {
            "component": self.component,
            "state": self.state,
            "owner": self.owner,
            "blocker": self.blocker,
            "evidence": self.evidence,
        }


DEFAULT_READINESS = [
    ReadinessItem("backend", "live_ready", "backend", "none", "backend smoke and release contracts"),
    ReadinessItem("frontend", "read_only_verified", "frontend", "production CDN smoke pending", "focused e2e/build evidence"),
    ReadinessItem("mobile", "local_only", "mobile", "store/TestFlight activation pending", "native distribution contracts"),
    ReadinessItem("cognito_email", "read_only_verified", "backend", "live email smoke pending", "verification contracts"),
    ReadinessItem("payment", "blocked", "operations", "live Stripe/TWINT approval pending", "billing readiness contracts"),
    ReadinessItem("notifications", "blocked", "operations", "provider activation pending", "notification/mobile contracts"),
    ReadinessItem("support_crm", "blocked", "operations", "CRM credentials/templates/destinations pending", "customer lifecycle contracts"),
    ReadinessItem("ai", "read_only_verified", "backend", "live cost feed pending", "AI operations contracts"),
    ReadinessItem("bi_apm", "blocked", "operations", "warehouse/APM activation pending", "BI/APM readiness contracts"),
    ReadinessItem("data_lifecycle", "local_only", "operations", "production restore fixture pending", "enterprise hardening contracts"),
    ReadinessItem("incident_operations", "local_only", "operations", "live tabletop approval pending", "enterprise hardening contracts"),
]


def activation_blocker_reality_audit(
    *,
    readiness_items: list[dict[str, Any]] | None = None,
    disabled_components: set[str] | None = None,
) -> dict[str, Any]:
    """Classify every limited-pilot dependency before any real-user activation."""
    disabled = disabled_components or set()
    audit = launch_scope_audit(readiness_items)
    blockers = []
    rows = []
    for item in audit["readiness"]:
        classification = _pilot_dependency_classification(item, disabled)
        action = _pilot_dependency_action(item, classification)
        row = {
            "component": item["component"],
            "owner": item["owner"],
            "currentState": item["state"],
            "pilotClassification": classification,
            "requiredForPilot": item["component"] in PILOT_REQUIRED_COMPONENTS,
            "blocker": item["blocker"],
            "requiredAction": action,
            "pilotImpact": _pilot_dependency_impact(item["component"], classification),
            "fallbackOrDisableOption": _fallback_or_disable_option(item["component"]),
            "evidenceSource": item["evidence"],
            "decisionDeadline": "before_real_user_enablement",
        }
        rows.append(row)
        if classification == "blocked":
            blockers.append(row)

    result = {
        "auditState": "blocked" if blockers else "ready",
        "scope": "limited_parent_student_pilot",
        "dependencies": rows,
        "blockers": blockers,
        "stateCounts": _count_by(rows, "pilotClassification"),
        "realUserStartRecommended": not blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def provider_activation_or_disablement(
    *,
    disabled_components: set[str] | None = None,
    approved_evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Document which pilot dependencies are activated, read-only, disabled, or blocking."""
    disabled = disabled_components or set()
    evidence = approved_evidence or {}
    audit = activation_blocker_reality_audit(disabled_components=disabled)
    rows = []
    unresolved = []
    for dependency in audit["dependencies"]:
        component = dependency["component"]
        if component not in PROVIDER_COMPONENTS:
            continue
        if component in disabled:
            state = "explicitly_disabled_for_pilot"
        elif component in evidence:
            state = "approved_evidence_recorded"
        elif dependency["pilotClassification"] == "cleared":
            state = "read_only_or_live_evidence_available"
        else:
            state = "launch_blocking"
            unresolved.append(component)
        rows.append(
            {
                "component": component,
                "pilotState": state,
                "evidence": evidence.get(component) or dependency["evidenceSource"],
                "operatorImpact": _operator_impact(component, state),
                "participantCopy": _participant_copy(component, state),
                "rollbackControl": _provider_rollback_control(component),
            }
        )

    result = {
        "activationState": "blocked" if unresolved else "ready",
        "components": rows,
        "unresolvedComponents": unresolved,
        "disabledComponents": sorted(disabled),
        "evidencePolicy": {
            "recordsRequestIds": True,
            "recordsTimestamps": True,
            "recordsOwners": True,
            "sensitiveMaterialExcluded": True,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_environment_cohort_dry_run() -> dict[str, Any]:
    """Return safe-fixture pilot setup checks for account, support, and rollback readiness."""
    plan = cohort_onboarding_plan()
    result = {
        "dryRunState": "safe_fixture_ready",
        "fixtureAccounts": {
            "parent": "pilot-parent-fixture",
            "student": "pilot-student-fixture",
            "admin": "pilot-admin-fixture",
            "support": "pilot-support-fixture",
            "customerMutationAllowed": False,
        },
        "checks": [
            "parent_email_verification",
            "student_child_binding",
            "entitlement_visibility",
            "curriculum_placement",
            "mobile_install_path",
            "notification_preference_review",
            "support_contact_path",
            "account_recovery_path",
            "rollback_communication",
            "exit_path",
        ],
        "onboardingChecklist": plan["onboardingChecklist"],
        "unsupportedPilotFeatures": launch_scope_audit()["excludedFeatures"],
        "fixtureRetention": "metadata-only dry-run evidence retained with milestone artifacts",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def launch_room_rehearsal_safe_start_package() -> dict[str, Any]:
    """Assemble launch-room rehearsal and safe-start package evidence."""
    controls = launch_controls_monitoring()
    result = {
        "rehearsalState": "local_ready",
        "launchRoom": {
            "owner": "operations",
            "schedule": "daily during limited pilot",
            "dashboard": controls["dashboard"],
            "alertRouting": controls["alertRouting"],
            "supportStaffing": "business-hours support with escalation owner",
            "dailyReporting": "activation, incidents, support, blockers, and next action",
        },
        "scenarios": [
            "auth_failure",
            "payment_blocker",
            "notification_blocker",
            "ai_provider_issue",
            "support_spike",
            "mobile_crash",
            "rollback",
        ],
        "safeStartPackage": {
            "cohortList": "approved cohort identifiers only, stored outside public evidence",
            "enablementChecklist": cohort_onboarding_plan()["onboardingChecklist"],
            "disabledFeatureList": launch_scope_audit()["excludedFeatures"],
            "supportPlan": "support contact, escalation, and rollback copy ready before enablement",
            "monitoringPlan": controls["dashboard"],
            "rollbackPlan": controls["freezeAndRollback"],
            "communicationsPlan": "start, blocker, rollback, and hold messages prepared",
        },
        "findings": ["live provider blockers must be cleared or explicitly disabled before start"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_safe_start_gate(
    *,
    disabled_components: set[str] | None = None,
    accepted_risks: list[str] | None = None,
) -> dict[str, Any]:
    """Decide whether the limited pilot can start from activation evidence."""
    blocker_audit = activation_blocker_reality_audit(disabled_components=disabled_components)
    provider_state = provider_activation_or_disablement(disabled_components=disabled_components)
    dry_run = pilot_environment_cohort_dry_run()
    rehearsal = launch_room_rehearsal_safe_start_package()
    blockers = _unique([row["component"] for row in blocker_audit["blockers"]] + provider_state["unresolvedComponents"])
    decision = "start_limited_pilot" if not blockers else "hold"
    result = {
        "decision": decision,
        "safeToStart": decision == "start_limited_pilot",
        "blockers": blockers,
        "acceptedRisks": accepted_risks or [],
        "evidence": {
            "blockerAudit": blocker_audit["auditState"],
            "providerActivation": provider_state["activationState"],
            "dryRun": dry_run["dryRunState"],
            "launchRoomRehearsal": rehearsal["rehearsalState"],
        },
        "nextMilestoneRecommendation": "v5.26 may execute only if decision is start_limited_pilot",
        "notApproved": ["public_launch", "paid_marketing", "unapproved_provider_writes"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_cohort_enablement_first_use_tracking(
    *,
    safe_start_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = safe_start_gate or pilot_safe_start_gate()
    blocked = not gate.get("safeToStart")
    result = {
        "executionState": "blocked_by_safe_start_gate" if blocked else "ready_for_controlled_enablement",
        "gateDecision": gate.get("decision"),
        "cohortEnablement": {
            "rolloutFlags": ["pilot_enabled", "provider_writes_enabled"],
            "stageOrder": ["admin_fixture", "staff_family", "approved_pilot_family"],
            "customerMutationAllowed": not blocked,
        },
        "tracking": [
            "onboarding_started",
            "email_verified",
            "entitlement_visible",
            "child_bound",
            "curriculum_placed",
            "mobile_or_web_accessed",
            "first_learning_action",
            "support_path_confirmed",
        ],
        "failedStateSupportActions": ["show_blocker_reason", "assign_owner", "retry_after_clearance"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def daily_pilot_monitoring_incident_operations() -> dict[str, Any]:
    result = {
        "monitoringState": "ready",
        "dailyChecklist": [
            "auth",
            "billing_entitlement",
            "usage_quota",
            "ai",
            "notifications",
            "support",
            "mobile",
            "providers",
            "incidents",
        ],
        "incidentActions": {
            "pauseCohortEnablement": True,
            "rollbackSupported": True,
            "providerDisablementSupported": True,
            "supportEscalationRequired": True,
        },
        "reviewOutputs": ["blocker_state", "incident_state", "rollback_readiness", "daily_owner_action"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_support_feedback_learning_quality_evidence() -> dict[str, Any]:
    result = {
        "feedbackState": "ready",
        "channels": ["parent", "student", "teacher", "admin", "support_operator"],
        "qualityEvidence": [
            "ai_summary_quality",
            "exercise_generation_quality",
            "assignment_relevance",
            "teacher_help_response_quality",
            "curriculum_placement",
            "progress_explanation",
        ],
        "rubricSource": "v5.21 AI operations rubrics and approved synthetic fixtures",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_metrics_outcome_analysis(signals: dict[str, str] | None = None) -> dict[str, Any]:
    observed = signals or {}
    rows = []
    blockers = []
    for signal in sorted(PILOT_OUTCOME_SIGNALS):
        state = observed.get(signal, "not_observed")
        if state in {"failed", "blocked"}:
            blockers.append(signal)
        rows.append({"signal": signal, "state": state, "supportAction": _pilot_signal_action(signal, state)})
    result = {
        "analysisState": "blocked" if blockers else "insufficient_evidence" if not observed else "reviewed",
        "signals": rows,
        "expansionBlockers": blockers,
        "decisionBuckets": ["expansion_blockers", "remediation_backlog", "accepted_risks", "future_improvements"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_outcome_decision_gate(
    *,
    safe_start_gate: dict[str, Any] | None = None,
    signals: dict[str, str] | None = None,
) -> dict[str, Any]:
    gate = safe_start_gate or pilot_safe_start_gate()
    analysis = pilot_metrics_outcome_analysis(signals)
    if not gate.get("safeToStart"):
        decision = "pause"
    elif analysis["expansionBlockers"]:
        decision = "remediate_before_continuing"
    elif signals:
        decision = "continue_pilot"
    else:
        decision = "remediate_before_continuing"
    result = {
        "decision": decision,
        "gateDecision": gate.get("decision"),
        "outcomeAnalysis": analysis["analysisState"],
        "expansionBlocked": decision != "continue_pilot",
        "v5_27ScopeBasis": "real pilot signals if observed; otherwise safe-start blockers",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_issue_triage_remediation_backlog(
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert pilot issues into an expansion-oriented remediation backlog."""
    source_issues = issues or [
        {
            "issue": "safe_start_gate_blocked",
            "severity": "critical",
            "frequency": "current",
            "owner": "operations",
            "surface": "provider_activation",
            "affectedRole": "operator",
            "expansionImpact": "blocks_expansion",
        }
    ]
    rows = []
    must_fix = []
    for issue in source_issues:
        severity = str(issue.get("severity") or "medium")
        impact = str(issue.get("expansionImpact") or "unknown")
        must_fix_item = severity in {"critical", "high"} or impact == "blocks_expansion"
        row = {
            "issue": str(issue.get("issue") or "unknown_issue"),
            "severity": severity,
            "frequency": str(issue.get("frequency") or "unknown"),
            "owner": str(issue.get("owner") or "unassigned"),
            "affectedRole": str(issue.get("affectedRole") or "unknown"),
            "surface": str(issue.get("surface") or "unknown"),
            "expansionImpact": impact,
            "bucket": "must_fix_expansion_blocker" if must_fix_item else "known_limitation",
            "verificationPlan": "focused regression, smoke check, or support-safe evidence snapshot",
            "participantCopy": "Known pilot limitation under remediation.",
        }
        rows.append(row)
        if must_fix_item:
            must_fix.append(row["issue"])
    result = {
        "backlogState": "blocked" if must_fix else "ready",
        "items": rows,
        "mustFixExpansionBlockers": must_fix,
        "futureEnhancements": [row["issue"] for row in rows if row["bucket"] == "known_limitation"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def account_billing_mobile_notification_remediation() -> dict[str, Any]:
    result = {
        "remediationState": "scoped",
        "surfaces": [
            "account_verification",
            "entitlement_visibility",
            "billing_state",
            "mobile_install_session",
            "offline_cache",
            "notification_delivery",
        ],
        "fixPolicy": {
            "noDemoFallback": True,
            "explicitDisablementAllowed": True,
            "supportSafeStateExplanations": True,
            "regressionCoverageRequired": True,
        },
        "supportVisibility": ["parent_account_operations", "admin_account_operations", "provider_blocker_state"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def learning_ai_curriculum_teacher_help_remediation() -> dict[str, Any]:
    result = {
        "remediationState": "scoped",
        "surfaces": [
            "ai_quality",
            "exercise_generation",
            "assignment_relevance",
            "curriculum_placement",
            "teacher_help_routing",
            "parent_student_explanations",
        ],
        "safety": {
            "teacherOversightRetained": True,
            "safetyEscalationRetained": True,
            "rawStudentWorkExcluded": True,
        },
        "validation": ["v5.21_rubric_fixtures", "approved_synthetic_pilot_examples", "support_safe_snapshots"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_regression_reliability_evidence(
    *,
    blockers_resolved: bool = False,
) -> dict[str, Any]:
    result = {
        "evidenceState": "ready" if blockers_resolved else "blocked",
        "coverage": [
            "fixed_pilot_issue_regressions",
            "impacted_api_smoke",
            "mobile_flow_smoke",
            "provider_state_review",
            "support_operations_review",
            "reopen_rate_dashboard",
        ],
        "releaseNotes": {
            "parentStudentLanguage": True,
            "operatorLanguage": True,
            "knownLimitationsIncluded": True,
        },
        "remainingBlockers": [] if blockers_resolved else ["safe_start_gate_blocked"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def remediation_release_gate(
    *,
    blockers_resolved: bool = False,
    accepted_blockers: list[str] | None = None,
) -> dict[str, Any]:
    backlog = pilot_issue_triage_remediation_backlog()
    reliability = pilot_regression_reliability_evidence(blockers_resolved=blockers_resolved)
    unresolved = [] if blockers_resolved else backlog["mustFixExpansionBlockers"]
    accepted = accepted_blockers or []
    decision = "ready_for_controlled_expansion" if not unresolved or set(unresolved).issubset(accepted) else "another_remediation_cycle"
    result = {
        "decision": decision,
        "mustFixResolved": decision == "ready_for_controlled_expansion",
        "acceptedBlockers": accepted,
        "unresolvedBlockers": unresolved,
        "evidenceState": reliability["evidenceState"],
        "v5_28ScopeBasis": "resolved or explicitly accepted pilot remediation evidence",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def expansion_cohort_capacity_plan(
    *,
    remediation_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = remediation_gate or remediation_release_gate()
    blocked = gate["decision"] != "ready_for_controlled_expansion"
    result = {
        "planState": "blocked_by_remediation_gate" if blocked else "ready",
        "cohort": {
            "size": "25-50 families",
            "stages": ["10_family_cap", "25_family_cap", "50_family_cap"],
            "rollbackThresholds": ["critical_incident", "support_sla_breach", "provider_blocker", "mobile_crash_spike"],
        },
        "capacityAssumptions": [
            "api",
            "mobile",
            "providers",
            "ai",
            "teacher_help",
            "support",
            "billing",
            "bi_apm",
            "incident_response",
        ],
        "communicationAndConsentPrepared": True,
        "expansionAllowed": not blocked,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def revenue_billing_subscription_operations_scale() -> dict[str, Any]:
    result = {
        "scaleState": "ready_for_controlled_review",
        "flows": ["payment", "entitlement", "refunds", "failed_payments", "dunning", "accounting_handoff", "billing_support"],
        "supportViews": {
            "providerStateVisible": True,
            "providerPayloadsExcluded": True,
            "financeOwnershipDocumented": True,
            "reconciliationCadence": "daily during expansion",
        },
        "metrics": ["mrr", "conversion", "failed_payment_rate", "refund_count", "entitlement_mismatch_count"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def teacher_support_customer_operations_scale() -> dict[str, Any]:
    result = {
        "scaleState": "ready_for_controlled_review",
        "operations": [
            "teacher_help_queue",
            "sla_dispatch",
            "escalation",
            "support_crm",
            "lifecycle_messaging",
            "feedback_workflows",
        ],
        "staffingPlan": {
            "normalHoursCovered": True,
            "spikeHandlingOwner": "operations",
            "escalationOwner": "support",
        },
        "measurements": ["support_load", "teacher_response_time", "resolution_time", "satisfaction"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def mobile_provider_infrastructure_scale_smoke() -> dict[str, Any]:
    result = {
        "smokeState": "ready_for_controlled_review",
        "checks": [
            "mobile_release_channel",
            "push_delivery",
            "offline_cache",
            "auth_session",
            "crash_performance",
            "provider_capacity",
            "bi_apm_dashboards",
            "infrastructure_runbooks",
        ],
        "runbooks": ["scale_up", "rollback", "provider_degradation"],
        "redactedEvidenceOnly": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def controlled_expansion_gate(
    *,
    expansion_metrics_met: bool = False,
    support_capacity_met: bool = False,
) -> dict[str, Any]:
    if expansion_metrics_met and support_capacity_met:
        decision = "prepare_public_launch_readiness"
    elif expansion_metrics_met:
        decision = "hold"
    else:
        decision = "remediate"
    result = {
        "decision": decision,
        "publicLaunchBlocked": decision != "prepare_public_launch_readiness",
        "metricsMet": expansion_metrics_met,
        "supportCapacityMet": support_capacity_met,
        "v5_29ScopeBasis": "controlled expansion outcomes and remaining capacity blockers",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def self_serve_onboarding_account_conversion() -> dict[str, Any]:
    result = {
        "onboardingState": "contract_ready",
        "surfaces": sorted(LAUNCH_SURFACES),
        "conversionEvents": [
            "signup_started",
            "email_verified",
            "parent_student_created",
            "subscription_selected",
            "mobile_install_started",
            "first_learning_action",
        ],
        "supportFallback": ["verification_recovery", "billing_support", "entitlement_blocker", "mobile_install_help"],
        "noDemoFallback": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pricing_packaging_growth_lifecycle_readiness() -> dict[str, Any]:
    result = {
        "growthState": "contract_ready",
        "pricing": ["plan_comparison", "subscription_state", "upgrade", "downgrade", "cancel", "billing_support_copy"],
        "growthLoops": ["waitlist", "referral", "lifecycle_nudges", "trial_conversion"],
        "controls": {
            "optOutRequired": True,
            "preferenceControlsRequired": True,
            "privacyGateRequired": True,
            "supportCapacityGateRequired": True,
        },
        "retentionReporting": ["onboarding", "learning_activity", "notifications", "support", "billing_state"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def public_support_knowledge_base_launch_communications() -> dict[str, Any]:
    result = {
        "supportContentState": "contract_ready",
        "topics": [
            "onboarding",
            "billing",
            "verification",
            "mobile_install",
            "notifications",
            "ai_limits",
            "teacher_help",
            "privacy",
            "incident_status",
        ],
        "communications": ["release_notes", "known_limitations", "escalation_paths", "rollback_or_hold_message"],
        "supportTeamAssets": ["macros", "templates", "escalation_ownership"],
        "disabledFeaturesDisclosed": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def app_store_public_release_production_launch_controls() -> dict[str, Any]:
    result = {
        "launchControlState": "contract_ready",
        "appStore": ["release_assets", "review_notes", "privacy_declarations", "notification_usage", "screenshots", "version_metadata"],
        "dashboard": launch_controls_monitoring()["dashboard"] + ["revenue"],
        "controls": ["launch_freeze", "staged_rollout", "rollback", "provider_disablement", "support_staffing"],
        "currentChecks": ["provider_capacity", "data_lifecycle", "incident_response"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def public_launch_readiness_gate(
    *,
    expansion_gate: dict[str, Any] | None = None,
    final_approval: bool = False,
) -> dict[str, Any]:
    gate = expansion_gate or controlled_expansion_gate()
    if final_approval and gate["decision"] == "prepare_public_launch_readiness":
        decision = "public_launch"
    elif gate["decision"] == "prepare_public_launch_readiness":
        decision = "continue_controlled_expansion"
    elif gate["decision"] == "hold":
        decision = "hold"
    else:
        decision = "harden_further"
    result = {
        "decision": decision,
        "acceptedRisks": [],
        "launchBlockers": [] if decision == "public_launch" else ["final_public_launch_approval_missing"],
        "v5_30Recommendation": "launch execution and post-launch operations" if decision == "public_launch" else "address blocking category before public launch",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_approval_ownership_audit(
    *,
    approvals: dict[str, bool] | None = None,
    dependency_states: dict[str, str] | None = None,
    disabled_features: list[str] | None = None,
) -> dict[str, Any]:
    """Record live pilot owners, approvals, dependency states, and authority."""
    approvals = approvals or {}
    dependency_states = dependency_states or {}
    owners = [
        {
            "role": role,
            "approved": bool(approvals.get(role)),
            "decisionAuthority": role in {"decision_owner", "product_owner"},
        }
        for role in sorted(LIVE_APPROVAL_ROLES)
    ]
    dependencies = [
        {
            "dependency": dependency,
            "state": dependency_states.get(dependency, "missing"),
            "allowedStates": ["approved", "disabled", "blocked", "missing"],
        }
        for dependency in sorted(LIVE_ACTIVATION_DEPENDENCIES)
    ]
    blockers = [
        *[f"approval_missing:{owner['role']}" for owner in owners if not owner["approved"]],
        *[
            f"dependency_not_ready:{dependency['dependency']}"
            for dependency in dependencies
            if dependency["state"] not in {"approved", "disabled"}
        ],
    ]
    result = {
        "approvalState": "approved" if not blockers else "blocked",
        "owners": owners,
        "pilotScope": {
            "cohort": "approved_limited_pilot_only",
            "disabledFeatures": disabled_features or [],
            "rollbackAuthority": "decision_owner",
            "supportHoursApproved": bool(approvals.get("support_owner")),
        },
        "dependencies": dependencies,
        "blockers": blockers,
        "realUserActionAllowed": not blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_provider_mobile_activation_evidence(
    *,
    evidence_states: dict[str, str] | None = None,
    disabled_components: set[str] | None = None,
) -> dict[str, Any]:
    """Capture redacted live/read-only provider, BI/APM, and mobile activation evidence."""
    evidence_states = evidence_states or {}
    disabled = disabled_components or set()
    components = ["payment", "notifications", "support_crm", "bi_apm", "mobile_testflight"]
    rows = []
    blockers = []
    for component in components:
        state = "disabled" if component in disabled else evidence_states.get(component, "missing")
        if state not in {"live_verified", "read_only_verified", "disabled"}:
            blockers.append(component)
        rows.append(
            {
                "component": component,
                "state": state,
                "timestampRequired": True,
                "ownerRequired": True,
                "requestOrBuildIdRequired": component == "mobile_testflight",
                "rollbackControl": _live_rollback_control(component),
                "participantCopy": _participant_copy(component, "explicitly_disabled_for_pilot")
                if state == "disabled"
                else _participant_copy(component, "launch_blocking" if component in blockers else "ready"),
            }
        )
    result = {
        "activationState": "ready" if not blockers else "blocked",
        "components": rows,
        "blockers": blockers,
        "disabledComponents": sorted(disabled),
        "evidencePolicy": {
            "redactedOnly": True,
            "supportSafe": True,
            "customerMutationDefault": "disabled_until_gate_start",
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def production_restore_tabletop_launch_room_evidence(
    *,
    restore_state: str = "missing",
    tabletop_state: str = "missing",
    launch_room_state: str = "missing",
    accepted_gaps: list[str] | None = None,
) -> dict[str, Any]:
    """Record restore/tabletop/launch-room evidence required before live pilot start."""
    accepted = accepted_gaps or []
    checks = {
        "production_restore": restore_state,
        "tabletop": tabletop_state,
        "launch_room": launch_room_state,
    }
    blockers = [
        name
        for name, state in checks.items()
        if state not in {"approved", "recorded"} and name not in accepted
    ]
    result = {
        "operationsState": "ready" if not blockers else "blocked",
        "checks": checks,
        "scenarios": [
            "auth_failure",
            "billing_blocker",
            "notification_blocker",
            "support_spike",
            "ai_provider_issue",
            "mobile_incident",
            "rollback",
        ],
        "incidentPolicy": {
            "severityApproved": not blockers,
            "escalationPathApproved": not blockers,
            "pauseCriteriaApproved": not blockers,
            "rollbackCriteriaApproved": not blockers,
        },
        "acceptedGaps": accepted,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_safe_start_gate_execution(
    *,
    approval: dict[str, Any] | None = None,
    provider_evidence: dict[str, Any] | None = None,
    operations_evidence: dict[str, Any] | None = None,
    accepted_risks: list[str] | None = None,
) -> dict[str, Any]:
    """Execute the live safe-start gate from current approved evidence state."""
    approval = approval or live_approval_ownership_audit()
    provider_evidence = provider_evidence or live_provider_mobile_activation_evidence()
    operations_evidence = operations_evidence or production_restore_tabletop_launch_room_evidence()
    blockers = _unique(
        [
            *approval.get("blockers", []),
            *[f"provider:{blocker}" for blocker in provider_evidence.get("blockers", [])],
            *[f"operations:{blocker}" for blocker in operations_evidence.get("blockers", [])],
        ]
    )
    decision = "start_limited_pilot" if not blockers else "hold"
    result = {
        "decision": decision,
        "safeToStart": decision == "start_limited_pilot",
        "blockers": blockers,
        "acceptedRisks": accepted_risks or [],
        "evidence": {
            "approval": approval.get("approvalState"),
            "providers": provider_evidence.get("activationState"),
            "operations": operations_evidence.get("operationsState"),
        },
        "ownerSignoffRequired": decision != "start_limited_pilot",
        "v5_31Allowed": decision == "start_limited_pilot",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_activation_gate(
    *,
    gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close v5.30 with a real-pilot execution or continued hold decision."""
    gate = gate or live_pilot_safe_start_gate_execution()
    result = {
        "decision": "real_pilot_execution" if gate.get("safeToStart") else "continued_hold_remediation",
        "safeStartDecision": gate.get("decision"),
        "v5_31Scope": "real_limited_pilot" if gate.get("safeToStart") else "blocked_until_live_gate_start",
        "outOfScope": ["public_launch", "paid_marketing", "uncontrolled_provider_writes"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_cohort_enablement_onboarding_operations(
    *,
    live_gate: dict[str, Any] | None = None,
    approved_user_count: int = 0,
) -> dict[str, Any]:
    gate = live_gate or live_pilot_safe_start_gate_execution()
    allowed = bool(gate.get("safeToStart") and approved_user_count > 0)
    result = {
        "executionState": "ready" if allowed else "blocked_by_live_gate",
        "approvedUserCount": approved_user_count,
        "checks": [
            "account_verification",
            "entitlement",
            "child_binding",
            "curriculum_placement",
            "mobile_or_web_access",
            "notification_preference",
            "support_path",
            "first_learning_action",
        ],
        "failedStatePolicy": {"ownerRequired": True, "supportVisibleNextAction": True},
        "pauseSupported": True,
        "customerMutationAllowed": allowed,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def daily_live_pilot_operations_incident_review() -> dict[str, Any]:
    result = {
        "reviewState": "ready",
        "dailyChecks": [
            "auth",
            "billing",
            "usage_quota",
            "ai",
            "notifications",
            "support",
            "mobile",
            "providers",
            "incidents",
        ],
        "incidentPolicy": {
            "rollbackThresholdReviewed": True,
            "pauseOnSeriousIncident": True,
            "supportTaxonomyRequired": True,
            "ownerRequired": True,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_learning_feedback_support_quality_capture() -> dict[str, Any]:
    result = {
        "captureState": "ready",
        "channels": ["parent", "student", "teacher", "support"],
        "qualityAreas": [
            "ai_quality",
            "curriculum_placement",
            "teacher_help_response",
            "parent_explanations",
        ],
        "findingBuckets": ["remediation", "accepted_limitation"],
        "privateContentExcluded": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_outcome_analysis(signals: dict[str, str] | None = None) -> dict[str, Any]:
    observed = signals or {}
    rows = []
    blockers = []
    for signal in sorted(PILOT_OUTCOME_SIGNALS):
        state = observed.get(signal, "not_observed")
        if state in {"failed", "blocked"}:
            blockers.append(signal)
        rows.append({"signal": signal, "state": state, "nextAction": _pilot_signal_action(signal, state)})
    result = {
        "analysisState": "reviewed" if observed else "insufficient_live_evidence",
        "signals": rows,
        "expansionBlockers": blockers,
        "buckets": ["expansion_blockers", "remediation_backlog", "accepted_risks", "future_improvements"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_decision_gate(
    *,
    live_gate: dict[str, Any] | None = None,
    signals: dict[str, str] | None = None,
) -> dict[str, Any]:
    gate = live_gate or live_pilot_safe_start_gate_execution()
    analysis = live_pilot_outcome_analysis(signals)
    if not gate.get("safeToStart"):
        decision = "pause"
    elif analysis["expansionBlockers"]:
        decision = "remediate_before_continuing"
    elif signals:
        decision = "expansion_candidate"
    else:
        decision = "continue_pilot"
    result = {
        "decision": decision,
        "expansionBlocked": decision != "expansion_candidate",
        "v5_32ScopeBasis": "live evidence if available; otherwise live gate blockers",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_issue_triage_fix_plan(
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issues = issues or [
        {
            "issue": "live_pilot_not_started",
            "severity": "critical",
            "frequency": "current",
            "owner": "operations",
            "affectedRole": "operator",
            "surface": "live_gate",
            "expansionImpact": "blocks_expansion",
        }
    ]
    backlog = pilot_issue_triage_remediation_backlog(issues)
    return {
        **backlog,
        "source": "live_pilot_issue_triage",
        "deferredExplanationRequired": True,
    }


def account_mobile_billing_notification_fixes() -> dict[str, Any]:
    result = account_billing_mobile_notification_remediation()
    result["source"] = "live_pilot_fix_plan"
    assert_pilot_evidence_safe(result)
    return result


def learning_ai_curriculum_teacher_help_fixes() -> dict[str, Any]:
    result = learning_ai_curriculum_teacher_help_remediation()
    result["validationSource"] = "live_examples_or_approved_synthetic_fixtures"
    assert_pilot_evidence_safe(result)
    return result


def regression_release_support_evidence(*, blockers_resolved: bool = False) -> dict[str, Any]:
    result = pilot_regression_reliability_evidence(blockers_resolved=blockers_resolved)
    result["releaseEvidenceSource"] = "live_pilot_remediation"
    assert_pilot_evidence_safe(result)
    return result


def live_remediation_gate(
    *,
    blockers_resolved: bool = False,
    accepted_blockers: list[str] | None = None,
) -> dict[str, Any]:
    accepted = accepted_blockers or []
    unresolved = [] if blockers_resolved else live_pilot_issue_triage_fix_plan()[
        "mustFixExpansionBlockers"
    ]
    if not unresolved or set(unresolved).issubset(accepted):
        decision = "expansion_ready"
    elif accepted:
        decision = "continue_pilot"
    else:
        decision = "another_remediation_cycle"
    result = {
        "decision": decision,
        "unresolvedBlockers": unresolved,
        "acceptedBlockers": accepted,
        "v5_33Allowed": decision == "expansion_ready",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_expansion_cohort_capacity_enablement(
    *,
    remediation_gate: dict[str, Any] | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    gate = remediation_gate or live_remediation_gate()
    allowed = approved and gate.get("v5_33Allowed")
    result = {
        "enablementState": "ready" if allowed else "blocked_by_remediation_or_approval",
        "cohort": {
            "size": "controlled_expansion",
            "stages": ["initial_expansion", "capacity_review", "expanded_cap"],
            "rollbackThresholds": ["critical_incident", "support_sla_breach", "provider_blocker"],
        },
        "capacityAreas": [
            "api",
            "mobile",
            "providers",
            "ai",
            "teacher_help",
            "support",
            "billing",
            "bi_apm",
            "incident_response",
        ],
        "expansionAllowed": allowed,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_revenue_billing_subscription_validation() -> dict[str, Any]:
    result = revenue_billing_subscription_operations_scale()
    result["validationState"] = "ready_for_live_expansion_review"
    assert_pilot_evidence_safe(result)
    return result


def live_teacher_support_customer_operations_scale() -> dict[str, Any]:
    result = teacher_support_customer_operations_scale()
    result["validationState"] = "ready_for_live_expansion_review"
    assert_pilot_evidence_safe(result)
    return result


def live_mobile_provider_infrastructure_scale_evidence() -> dict[str, Any]:
    result = mobile_provider_infrastructure_scale_smoke()
    result["evidenceState"] = "ready_for_live_expansion_review"
    assert_pilot_evidence_safe(result)
    return result


def controlled_expansion_decision_gate(
    *,
    metrics_met: bool = False,
    support_capacity_met: bool = False,
    rollback_needed: bool = False,
) -> dict[str, Any]:
    if rollback_needed:
        decision = "rollback"
    elif metrics_met and support_capacity_met:
        decision = "public_launch_prep"
    elif metrics_met:
        decision = "hold"
    else:
        decision = "remediate"
    result = {
        "decision": decision,
        "publicLaunchBlocked": decision != "public_launch_prep",
        "v5_34Scope": "launch_execution" if decision == "public_launch_prep" else "hold_or_remediate",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def final_launch_approval_public_rollout_plan(
    *,
    final_approval: bool = False,
    expansion_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expansion_gate = expansion_gate or controlled_expansion_decision_gate()
    approved = final_approval and expansion_gate.get("decision") == "public_launch_prep"
    result = {
        "decision": "public_launch" if approved else "continued_controlled_expansion_or_hold",
        "rolloutPlanApproved": approved,
        "scope": "public_launch" if approved else "controlled_or_held",
        "requiredApprovals": ["owner_signoff", "support_staffing", "provider_capacity", "billing_readiness"],
        "knownLimitationsDocumented": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def self_serve_onboarding_growth_support_launch(
    *,
    launch_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    launch_plan = launch_plan or final_launch_approval_public_rollout_plan()
    enabled = launch_plan.get("decision") == "public_launch"
    result = {
        "launchState": "enabled" if enabled else "blocked_by_launch_approval",
        "surfaces": sorted(LAUNCH_SURFACES),
        "growthLoops": ["pricing", "waitlist", "referral", "lifecycle", "retention_reporting"],
        "supportAssetsCurrent": True,
        "consentPreferencePrivacyGated": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def app_store_production_release_launch_monitoring(
    *,
    launch_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    launch_plan = launch_plan or final_launch_approval_public_rollout_plan()
    active = launch_plan.get("decision") == "public_launch"
    result = {
        "monitoringState": "active" if active else "prepared_not_active",
        "appStoreAssetsApproved": active,
        "dashboard": launch_controls_monitoring()["dashboard"] + ["revenue"],
        "controls": ["launch_freeze", "staged_rollout", "rollback", "provider_disablement"],
        "monitoringEvidencePolicy": {
            "redactedOnly": True,
            "supportSafe": True,
            "privateContentExcluded": True,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def post_launch_incident_revenue_learning_operations() -> dict[str, Any]:
    result = {
        "operationsState": "ready",
        "cadence": [
            "incidents",
            "revenue_reconciliation",
            "support_load",
            "teacher_response",
            "ai_quality",
            "curriculum_issues",
            "mobile_crashes",
            "provider_health",
            "retention",
        ],
        "issueBuckets": ["hotfix", "support_action", "product_backlog", "growth_learning", "accepted_limitation"],
        "reconciliationSource": "provider_and_account_operations_state",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def launch_outcome_next_strategy_gate(
    *,
    launch_plan: dict[str, Any] | None = None,
    outcome_healthy: bool = False,
    rollback_needed: bool = False,
) -> dict[str, Any]:
    launch_plan = launch_plan or final_launch_approval_public_rollout_plan()
    if rollback_needed:
        decision = "rollback"
    elif launch_plan.get("decision") == "public_launch" and outcome_healthy:
        decision = "scale"
    elif launch_plan.get("decision") == "public_launch":
        decision = "hold"
    else:
        decision = "next_focused_product_or_growth_milestone"
    result = {
        "decision": decision,
        "outcomeReportRecorded": True,
        "v5_35Recommendation": decision,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def real_pilot_blocker_inventory_owner_assignment(
    *,
    approval: dict[str, Any] | None = None,
    provider_evidence: dict[str, Any] | None = None,
    operations_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert current live-gate blockers into owner/action rows for v5.35."""
    gate = live_pilot_safe_start_gate_execution(
        approval=approval,
        provider_evidence=provider_evidence,
        operations_evidence=operations_evidence,
    )
    rows = [
        {
            "blocker": blocker,
            "owner": _blocker_owner(blocker),
            "requiredAction": _blocker_action(blocker),
            "deadline": "before_real_pilot_start",
            "decisionImpact": "blocks_start",
        }
        for blocker in gate["blockers"]
    ]
    result = {
        "inventoryState": "ready" if not rows else "blocked",
        "gateDecision": gate["decision"],
        "ownerActionTable": rows,
        "blockers": gate["blockers"],
        "dailyReviewRequired": bool(rows),
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def provider_or_disablement_activation_closeout(
    *,
    evidence_states: dict[str, str] | None = None,
    disabled_components: set[str] | None = None,
) -> dict[str, Any]:
    """Close each provider/mobile dependency as verified, disabled, or still blocking."""
    provider = live_provider_mobile_activation_evidence(
        evidence_states=evidence_states,
        disabled_components=disabled_components,
    )
    rows = []
    for row in provider["components"]:
        component = row["component"]
        state = row["state"]
        rows.append(
            {
                "component": component,
                "closeoutState": "closed" if state in {"live_verified", "read_only_verified", "disabled"} else "open",
                "pilotUse": "enabled" if state == "live_verified" else "disabled_or_read_only",
                "supportCopyReady": state in {"read_only_verified", "disabled"},
                "fallback": _fallback_or_disable_option(component),
                "rollbackControl": row["rollbackControl"],
            }
        )
    result = {
        "closeoutState": "ready" if not provider["blockers"] else "blocked",
        "components": rows,
        "blockers": provider["blockers"],
        "disabledComponents": provider["disabledComponents"],
        "evidencePolicy": provider["evidencePolicy"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_cohort_account_support_dry_run(
    *,
    live_gate: dict[str, Any] | None = None,
    approved_account_count: int = 0,
    support_staffed: bool = False,
) -> dict[str, Any]:
    """Run account and support readiness checks without enabling real-user writes."""
    gate = live_gate or live_pilot_safe_start_gate_execution()
    ready = bool(gate.get("safeToStart") and approved_account_count > 0 and support_staffed)
    result = {
        "dryRunState": "ready" if ready else "blocked",
        "approvedAccountCount": approved_account_count,
        "checks": [
            "account_verification",
            "child_binding",
            "entitlement_visibility",
            "support_contact_path",
            "billing_or_disabled_payment_copy",
            "mobile_or_web_access_path",
            "rollback_message",
        ],
        "supportStaffed": support_staffed,
        "customerMutationAllowed": False,
        "realEnablementRequiresStartGate": True,
        "blockers": []
        if ready
        else ["live_gate", "approved_accounts", "support_staffing"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def launch_room_restore_incident_readiness_closeout(
    *,
    operations_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close restore, tabletop, monitoring, rollback, and incident-room evidence."""
    operations = operations_evidence or production_restore_tabletop_launch_room_evidence()
    controls = launch_controls_monitoring()
    result = {
        "readinessState": "ready" if operations["operationsState"] == "ready" else "blocked",
        "operationsState": operations["operationsState"],
        "checks": operations["checks"],
        "blockers": operations["blockers"],
        "launchRoom": {
            "dashboard": controls["dashboard"],
            "alertRouting": controls["alertRouting"],
            "pauseSupported": True,
            "rollbackSupported": True,
            "providerDisablementSupported": True,
        },
        "incidentPolicy": operations["incidentPolicy"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def real_pilot_start_decision_gate(
    *,
    inventory: dict[str, Any] | None = None,
    provider_closeout: dict[str, Any] | None = None,
    dry_run: dict[str, Any] | None = None,
    launch_room: dict[str, Any] | None = None,
    accepted_risks: list[str] | None = None,
) -> dict[str, Any]:
    """Close v5.35 with the only decision that may unlock v5.36 operations."""
    inventory = inventory or real_pilot_blocker_inventory_owner_assignment()
    provider_closeout = provider_closeout or provider_or_disablement_activation_closeout()
    dry_run = dry_run or pilot_cohort_account_support_dry_run()
    launch_room = launch_room or launch_room_restore_incident_readiness_closeout()
    blockers = _unique(
        [
            *(["inventory_state"] if inventory.get("inventoryState") != "ready" else []),
            *(["provider_closeout_state"] if provider_closeout.get("closeoutState") != "ready" else []),
            *(["dry_run_state"] if dry_run.get("dryRunState") != "ready" else []),
            *(["launch_room_state"] if launch_room.get("readinessState") != "ready" else []),
            *inventory.get("blockers", []),
            *[f"provider:{blocker}" for blocker in provider_closeout.get("blockers", [])],
            *[f"dry_run:{blocker}" for blocker in dry_run.get("blockers", [])],
            *[f"launch_room:{blocker}" for blocker in launch_room.get("blockers", [])],
        ]
    )
    decision = "start_limited_pilot" if not blockers else "hold"
    result = {
        "decision": decision,
        "safeToStart": decision == "start_limited_pilot",
        "blockers": blockers,
        "acceptedRisks": accepted_risks or [],
        "v5_36Allowed": decision == "start_limited_pilot",
        "outOfScope": ["public_launch", "paid_marketing", "unapproved_provider_writes"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_operations_feedback_capture(
    *,
    start_gate: dict[str, Any] | None = None,
    approved_user_count: int = 0,
) -> dict[str, Any]:
    """Capture v5.36 live operations signals only after the v5.35 start gate."""
    gate = start_gate or real_pilot_start_decision_gate()
    active = bool(gate.get("safeToStart") and approved_user_count > 0)
    result = {
        "operationsState": "active" if active else "blocked_by_start_gate",
        "approvedUserCount": approved_user_count,
        "signals": sorted(LIVE_OPERATIONS_SIGNALS),
        "dailyReview": daily_live_pilot_operations_incident_review()["dailyChecks"],
        "feedbackChannels": live_learning_feedback_support_quality_capture()["channels"],
        "customerMutationAllowed": active,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_product_fix_plan(
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prioritize pilot findings into hotfix, product, support, copy, or accepted buckets."""
    source_findings = findings or [
        {
            "finding": "real_pilot_not_started",
            "severity": "critical",
            "surface": "start_gate",
            "owner": "operations",
            "frequency": "current",
        }
    ]
    rows = []
    must_fix = []
    for finding in source_findings:
        severity = str(finding.get("severity") or "medium")
        surface = str(finding.get("surface") or "unknown")
        bucket = "hotfix" if severity in {"critical", "high"} else "product_backlog"
        row = {
            "finding": str(finding.get("finding") or "unknown_finding"),
            "severity": severity,
            "surface": surface,
            "owner": str(finding.get("owner") or "unassigned"),
            "frequency": str(finding.get("frequency") or "unknown"),
            "bucket": bucket,
            "verificationPlan": "focused regression plus support-visible release note",
        }
        rows.append(row)
        if bucket == "hotfix":
            must_fix.append(row["finding"])
    result = {
        "planState": "blocked" if must_fix else "ready",
        "items": rows,
        "mustFixBeforeExpansion": must_fix,
        "releaseNotesRequired": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_product_fix_release_evidence(
    *,
    fixes_closed: bool = False,
    regressions_passed: bool = False,
) -> dict[str, Any]:
    """Record release evidence for the v5.36 high-impact pilot fixes."""
    ready = fixes_closed and regressions_passed
    result = {
        "releaseState": "ready" if ready else "blocked",
        "fixesClosed": fixes_closed,
        "regressionsPassed": regressions_passed,
        "coverage": [
            "activation_flow",
            "support_path",
            "billing_entitlement",
            "mobile_access",
            "notification_delivery",
            "ai_quality",
        ],
        "supportVisibleReleaseNotes": ready,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_feedback_decision_gate(
    *,
    start_gate: dict[str, Any] | None = None,
    signals: dict[str, str] | None = None,
    fixes_released: bool = False,
) -> dict[str, Any]:
    """Decide whether live pilot evidence supports revenue and growth completion."""
    gate = start_gate or real_pilot_start_decision_gate()
    analysis = live_pilot_outcome_analysis(signals)
    if not gate.get("safeToStart"):
        decision = "hold"
    elif analysis["expansionBlockers"]:
        decision = "remediate"
    elif signals and fixes_released:
        decision = "revenue_growth_candidate"
    else:
        decision = "continue_pilot"
    result = {
        "decision": decision,
        "outcomeAnalysis": analysis["analysisState"],
        "v5_37Allowed": decision == "revenue_growth_candidate",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def revenue_conversion_checkout_completion(
    evidence_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate v5.37 paid conversion, entitlement, and billing support surfaces."""
    evidence_states = evidence_states or {}
    rows = []
    blockers = []
    for surface in sorted(REVENUE_GROWTH_SURFACES):
        state = evidence_states.get(surface, "missing")
        if state not in {"passed", "disabled", "support_ready"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "supportVisible": surface in {"failed_payment_states", "invoice_refund_support"},
                "reconciliationRequired": surface
                in {"entitlement_activation", "checkout", "payment_methods"},
            }
        )
    result = {
        "completionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def self_serve_growth_lifecycle_completion(
    evidence_states: dict[str, str] | None = None,
    *,
    support_capacity_ready: bool = False,
) -> dict[str, Any]:
    """Complete self-serve onboarding, lifecycle, referral, and capacity gates."""
    evidence_states = evidence_states or {}
    required = ["self_serve_onboarding", "lifecycle_messages", "referral_waitlist", "support_capacity"]
    rows = []
    blockers = []
    for surface in required:
        state = "passed" if surface == "support_capacity" and support_capacity_ready else evidence_states.get(surface, "missing")
        if state not in {"passed", "disabled"}:
            blockers.append(surface)
        rows.append({"surface": surface, "state": state, "preferenceAware": surface == "lifecycle_messages"})
    result = {
        "completionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "capacityGateReady": support_capacity_ready,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def revenue_growth_decision_gate(
    *,
    revenue: dict[str, Any] | None = None,
    growth: dict[str, Any] | None = None,
    reconciliation_approved: bool = False,
) -> dict[str, Any]:
    """Close v5.37 with controlled growth, paid marketing prep, or remediation."""
    revenue = revenue or revenue_conversion_checkout_completion()
    growth = growth or self_serve_growth_lifecycle_completion()
    blockers = _unique(
        [
            *[f"revenue:{blocker}" for blocker in revenue.get("blockers", [])],
            *[f"growth:{blocker}" for blocker in growth.get("blockers", [])],
            *(["reconciliation"] if not reconciliation_approved else []),
        ]
    )
    decision = "controlled_growth_ready" if not blockers else "remediate"
    result = {
        "decision": decision,
        "blockers": blockers,
        "reconciliationApproved": reconciliation_approved,
        "v5_38Allowed": decision == "controlled_growth_ready",
        "paidMarketingApproved": False,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def learning_outcomes_curriculum_quality_scale(
    evidence_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Turn pilot learning evidence into curriculum and outcome quality rows."""
    evidence_states = evidence_states or {}
    rows = []
    blockers = []
    for area in sorted(LEARNING_QUALITY_AREAS):
        state = evidence_states.get(area, "missing")
        if state not in {"passed", "accepted_gap"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "teacherReviewed": area in {"ai_summaries", "teacher_tools", "adaptive_recommendations"},
                "familyVisible": area in {"learning_progress", "parent_progress_reporting"},
            }
        )
    result = {
        "qualityState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "privateContentExcluded": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def ai_quality_teacher_help_scale(
    *,
    evaluations_passed: bool = False,
    teacher_capacity_ready: bool = False,
) -> dict[str, Any]:
    """Record AI, teacher-help, and automation quality evidence for v5.38."""
    ready = evaluations_passed and teacher_capacity_ready
    result = {
        "qualityState": "ready" if ready else "blocked",
        "evaluationsPassed": evaluations_passed,
        "teacherCapacityReady": teacher_capacity_ready,
        "controls": {
            "teacherReviewRetained": True,
            "safetyEscalationRetained": True,
            "automationLimitationsDisclosed": True,
        },
        "coverage": ["summaries", "explanations", "exercise_drafts", "teacher_review_tools"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def learning_quality_decision_gate(
    *,
    outcomes: dict[str, Any] | None = None,
    ai_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close v5.38 with expansion support, remediation, or content/AI hold."""
    outcomes = outcomes or learning_outcomes_curriculum_quality_scale()
    ai_quality = ai_quality or ai_quality_teacher_help_scale()
    blockers = _unique(
        [
            *[f"learning:{blocker}" for blocker in outcomes.get("blockers", [])],
            *(["ai_teacher_quality"] if ai_quality.get("qualityState") != "ready" else []),
        ]
    )
    decision = "learning_quality_scale_ready" if not blockers else "remediate"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v5_39Allowed": decision == "learning_quality_scale_ready",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def platform_reliability_operations_scale(
    evidence_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Audit reliability, observability, data quality, and release operations for scale."""
    evidence_states = evidence_states or {}
    rows = []
    blockers = []
    for area in sorted(OPERATIONS_SCALE_AREAS):
        state = evidence_states.get(area, "missing")
        if state not in {"passed", "accepted_gap"}:
            blockers.append(area)
        rows.append({"area": area, "state": state, "owner": _operations_area_owner(area)})
    result = {
        "scaleState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "incidentPolicyReviewed": not blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def internal_operations_admin_teacher_scale(
    evidence_states: dict[str, str] | None = None,
    *,
    staffing_ready: bool = False,
) -> dict[str, Any]:
    """Scale admin, teacher, support, billing, and content workflows."""
    evidence_states = evidence_states or {}
    workflows = ["account_operations", "teacher_dispatch", "support_handoff", "billing_fixes", "content_operations"]
    rows = []
    blockers = []
    for workflow in workflows:
        state = evidence_states.get(workflow, "missing")
        if state not in {"passed", "accepted_gap"}:
            blockers.append(workflow)
        rows.append({"workflow": workflow, "state": state, "repeatable": state == "passed"})
    if not staffing_ready:
        blockers.append("staffing")
    result = {
        "scaleState": "ready" if not blockers else "blocked",
        "workflows": rows,
        "blockers": blockers,
        "staffingReady": staffing_ready,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def platform_scale_decision_gate(
    *,
    reliability: dict[str, Any] | None = None,
    internal_ops: dict[str, Any] | None = None,
    release_discipline_ready: bool = False,
) -> dict[str, Any]:
    """Close v5.39 with larger expansion readiness or another hardening cycle."""
    reliability = reliability or platform_reliability_operations_scale()
    internal_ops = internal_ops or internal_operations_admin_teacher_scale()
    blockers = _unique(
        [
            *[f"reliability:{blocker}" for blocker in reliability.get("blockers", [])],
            *[f"operations:{blocker}" for blocker in internal_ops.get("blockers", [])],
            *(["release_discipline"] if not release_discipline_ready else []),
        ]
    )
    decision = "larger_expansion_ready" if not blockers else "operations_hardening_cycle"
    result = {
        "decision": decision,
        "blockers": blockers,
        "releaseDisciplineReady": release_discipline_ready,
        "expansionAllowed": decision == "larger_expansion_ready",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def real_evidence_inventory_access_readiness(
    evidence_states: dict[str, str] | None = None,
    *,
    approved_credential_path: bool = False,
) -> dict[str, Any]:
    """Inventory current real evidence sources before v6 pilot execution."""
    evidence_states = evidence_states or {}
    rows = []
    blockers = []
    for path in sorted(V6_REAL_EVIDENCE_ACCESS_PATHS):
        state = evidence_states.get(path, "missing")
        if state not in {"available", "disabled_for_pilot", "not_required"}:
            blockers.append(path)
        rows.append(
            {
                "accessPath": path,
                "state": state,
                "owner": _v6_access_owner(path),
                "approvalRequired": state not in {"not_required"},
                "nextAction": _v6_access_next_action(path, state),
            }
        )
    if not approved_credential_path:
        blockers.append("approved_credential_path")
    result = {
        "inventoryState": "ready" if not blockers else "blocked",
        "accessPaths": rows,
        "approvedCredentialPath": approved_credential_path,
        "blockers": blockers,
        "evidencePolicy": {
            "metadataOnly": True,
            "recordOwners": True,
            "recordRequestIds": True,
            "recordAccountAliasesOnly": True,
            "productionMutationAllowed": False,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def account_payment_usage_verification_smoke(
    evidence_states: dict[str, str] | None = None,
    *,
    production_mutation_approved: bool = False,
) -> dict[str, Any]:
    """Verify account, billing, entitlement, usage, quota, and support surfaces."""
    evidence_states = evidence_states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_ACCOUNT_PAYMENT_USAGE_SURFACES):
        state = evidence_states.get(surface, "missing")
        if state not in {"passed", "disabled_for_pilot", "read_only_verified"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_account_surface_owner(surface),
                "requestIdRequired": True,
                "accountAliasRequired": True,
                "nextAction": _v6_surface_next_action(surface, state),
            }
        )
    result = {
        "smokeState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "productionMutationApproved": production_mutation_approved,
        "mutationPolicy": {
            "allowed": production_mutation_approved,
            "scope": "pilot_safe_account_only" if production_mutation_approved else "read_only_or_disabled",
            "reversible": True,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def notification_support_mobile_provider_evidence(
    evidence_states: dict[str, str] | None = None,
    *,
    disabled_surfaces: set[str] | None = None,
) -> dict[str, Any]:
    """Verify or explicitly disable notification, support, mobile, and provider surfaces."""
    evidence_states = evidence_states or {}
    disabled = disabled_surfaces or set()
    rows = []
    blockers = []
    for surface in sorted(V6_NOTIFICATION_SUPPORT_PROVIDER_SURFACES):
        state = "disabled_for_pilot" if surface in disabled else evidence_states.get(surface, "missing")
        if state not in {"passed", "disabled_for_pilot", "read_only_verified"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_provider_surface_owner(surface),
                "fallback": _v6_provider_fallback(surface),
                "rollbackControl": _v6_provider_rollback(surface),
                "supportCopyReady": state == "disabled_for_pilot",
            }
        )
    result = {
        "evidenceState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "disabledSurfaces": sorted(disabled),
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def pilot_cohort_launch_packet_dry_run(
    packet_states: dict[str, str] | None = None,
    *,
    dry_run_passed: bool = False,
) -> dict[str, Any]:
    """Assemble the v6.0 launch packet and dry-run evidence before cohort start."""
    packet_states = packet_states or {}
    rows = []
    blockers = []
    for area in sorted(V6_PILOT_LAUNCH_PACKET_AREAS):
        state = packet_states.get(area, "missing")
        if state not in {"ready", "accepted_gap", "disabled_for_pilot"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "owner": _v6_launch_packet_owner(area),
                "startBlocking": state == "missing",
            }
        )
    if not dry_run_passed:
        blockers.append("dry_run")
    result = {
        "packetState": "ready" if not blockers else "blocked",
        "areas": rows,
        "dryRunPassed": dry_run_passed,
        "dryRunCoverage": [
            "login",
            "onboarding",
            "entitlement",
            "usage",
            "first_learning_action",
            "notification_support_touchpoints",
            "mobile_path",
            "admin_visibility",
        ],
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v6_pilot_start_or_blocker_decision_gate(
    *,
    inventory: dict[str, Any] | None = None,
    account_smoke: dict[str, Any] | None = None,
    provider_evidence: dict[str, Any] | None = None,
    launch_packet: dict[str, Any] | None = None,
    accepted_blockers: list[str] | None = None,
) -> dict[str, Any]:
    """Close v6.0 with a start, hold, or harden decision from current evidence."""
    inventory = inventory or real_evidence_inventory_access_readiness()
    account_smoke = account_smoke or account_payment_usage_verification_smoke()
    provider_evidence = provider_evidence or notification_support_mobile_provider_evidence()
    launch_packet = launch_packet or pilot_cohort_launch_packet_dry_run()
    accepted = accepted_blockers or []
    blockers = _unique(
        [
            *(["inventory"] if inventory.get("inventoryState") != "ready" else []),
            *(["account_smoke"] if account_smoke.get("smokeState") != "ready" else []),
            *(["provider_evidence"] if provider_evidence.get("evidenceState") != "ready" else []),
            *(["launch_packet"] if launch_packet.get("packetState") != "ready" else []),
            *[f"inventory:{blocker}" for blocker in inventory.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_smoke.get("blockers", [])],
            *[f"provider:{blocker}" for blocker in provider_evidence.get("blockers", [])],
            *[f"launch:{blocker}" for blocker in launch_packet.get("blockers", [])],
        ]
    )
    unresolved = [blocker for blocker in blockers if blocker not in accepted]
    if not unresolved:
        decision = "start_limited_pilot"
    elif accepted:
        decision = "harden_further"
    else:
        decision = "hold"
    result = {
        "decision": decision,
        "safeToStart": decision == "start_limited_pilot",
        "blockers": unresolved,
        "acceptedBlockers": accepted,
        "v6_1Allowed": decision == "start_limited_pilot",
        "nextAction": "handoff_to_v6_1" if decision == "start_limited_pilot" else "execute_blocker_package",
        "outOfScope": ["public_launch", "paid_marketing", "broad_expansion", "uncontrolled_provider_writes"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def cohort_day_one_operations_or_blocker_fix_kickoff(
    *,
    v6_start_gate: dict[str, Any] | None = None,
    observed_signals: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start day-one review or convert v6.0 blockers into fix rows."""
    gate = v6_start_gate or v6_pilot_start_or_blocker_decision_gate()
    observed_signals = observed_signals or {}
    start_allowed = bool(gate.get("safeToStart"))
    rows = []
    blockers = []
    for surface in sorted(V6_REMEDIATION_SURFACES):
        state = observed_signals.get(surface, "not_observed" if start_allowed else "blocked")
        if state in {"blocked", "failed"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_remediation_owner(surface),
                "severity": "critical" if state in {"blocked", "failed"} else "monitor",
                "expectedOutcome": _v6_remediation_outcome(surface),
                "verificationPath": "focused regression plus support-visible evidence",
            }
        )
    result = {
        "kickoffState": "cohort_review" if start_allowed else "blocker_fix_board",
        "startDecision": gate.get("decision"),
        "items": rows,
        "blockers": blockers or gate.get("blockers", []),
        "scope": "pilot_critical_product_behavior",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def account_login_verification_role_fixes(
    fix_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track account/login/verification fixes and explicit deferrals."""
    fix_states = fix_states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_ACCOUNT_FIX_SURFACES):
        state = fix_states.get(surface, "missing")
        if state not in {"fixed", "explicitly_deferred", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_account_surface_owner(surface),
                "testsRequired": surface
                in {"login", "email_verification", "role_visibility", "admin_support_state"},
                "privateCodesExposed": False,
                "userCopy": _v6_account_copy(surface, state),
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "rolesCovered": ["parent", "student", "teacher_support", "admin"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def entitlement_usage_notification_support_fixes(
    fix_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track entitlement, usage, notification, support, and dispatch fixes."""
    fix_states = fix_states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_ENTITLEMENT_SUPPORT_FIX_SURFACES):
        state = fix_states.get(surface, "missing")
        if state not in {"fixed", "fallback_ready", "disabled_for_pilot", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_entitlement_support_owner(surface),
                "supportVisible": surface
                in {"support_handoff", "teacher_dispatch_sla", "quota_reconciliation"},
                "evidenceRequired": ["code_sha", "focused_test", "operator_note"],
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def first_learning_action_mobile_friction_fixes(
    fix_states: dict[str, str] | None = None,
    *,
    mobile_local_tests_available: bool = True,
) -> dict[str, Any]:
    """Track first-learning-action and mobile friction fixes."""
    fix_states = fix_states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_LEARNING_MOBILE_FIX_SURFACES):
        state = fix_states.get(surface, "missing")
        if state not in {"fixed", "explicitly_deferred", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v6_learning_mobile_owner(surface),
                "userNextStepClear": state == "fixed",
                "mobileTested": mobile_local_tests_available if "mobile" in surface else None,
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "aiAutonomyBroadened": False,
        "curriculumEditPermissionBroadened": False,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v6_1_remediation_release_gate(
    *,
    kickoff: dict[str, Any] | None = None,
    account_fixes: dict[str, Any] | None = None,
    entitlement_support_fixes: dict[str, Any] | None = None,
    learning_mobile_fixes: dict[str, Any] | None = None,
    rollback_needed: bool = False,
) -> dict[str, Any]:
    """Close v6.1 with continue, hold, rollback, or another blocker sprint."""
    kickoff = kickoff or cohort_day_one_operations_or_blocker_fix_kickoff()
    account_fixes = account_fixes or account_login_verification_role_fixes()
    entitlement_support_fixes = (
        entitlement_support_fixes or entitlement_usage_notification_support_fixes()
    )
    learning_mobile_fixes = learning_mobile_fixes or first_learning_action_mobile_friction_fixes()
    blockers = _unique(
        [
            *[f"kickoff:{blocker}" for blocker in kickoff.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_fixes.get("blockers", [])],
            *[
                f"entitlement_support:{blocker}"
                for blocker in entitlement_support_fixes.get("blockers", [])
            ],
            *[f"learning_mobile:{blocker}" for blocker in learning_mobile_fixes.get("blockers", [])],
        ]
    )
    if rollback_needed:
        decision = "roll_back"
    elif not blockers:
        decision = "continue_pilot"
    elif any(blocker.startswith(("account:", "entitlement_support:")) for blocker in blockers):
        decision = "hold"
    else:
        decision = "another_blocker_sprint"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_2Allowed": decision == "continue_pilot",
        "releaseEvidence": ["focused_tests", "operator_notes", "user_support_copy"],
        "nextAction": "start_v6_2" if decision == "continue_pilot" else "execute_remaining_blockers",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def paid_conversion_flow_completion(states: dict[str, str] | None = None) -> dict[str, Any]:
    """Complete parent paid conversion and entitlement-facing states for pilot scope."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_PAID_CONVERSION_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"working", "support_ready", "disabled_for_pilot"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "parentCopyReady": state in {"working", "disabled_for_pilot"},
                "providerPayloadStored": False,
                "supportExplainable": state != "missing",
            }
        )
    result = {
        "completionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "revenueImpactAuditable": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def usage_ledger_quota_reliability_completion(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Close usage recording, idempotency, quota display, and reconciliation."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_USAGE_QUOTA_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"covered", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "idempotent": surface not in {"quota_display", "quota_block"} and state == "covered",
                "parentAdminExplanation": state == "covered",
            }
        )
    result = {
        "reliabilityState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "reconciliationCovers": ["missing", "duplicate", "stale", "manual_adjusted"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def verification_lifecycle_account_recovery_completion(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Complete verification, recovery, support override, and role transition states."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_VERIFICATION_RECOVERY_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"tested", "explicitly_deferred"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "userCopyReady": state == "tested",
                "supportStatusReady": state in {"tested", "explicitly_deferred"},
                "privateMaterialExposed": False,
                "auditable": state == "tested",
            }
        )
    result = {
        "completionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def billing_support_lifecycle_messaging_completion(
    states: dict[str, str] | None = None,
    *,
    support_capacity_ready: bool = False,
) -> dict[str, Any]:
    """Complete billing support workflows and approved lifecycle messaging."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_BILLING_LIFECYCLE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"ready", "not_approved", "disabled_for_pilot"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "preferencesRespected": surface
                in {"onboarding", "activation", "renewal", "reminder", "win_back"},
                "supportVisible": True,
            }
        )
    if not support_capacity_ready:
        blockers.append("support_capacity")
    result = {
        "completionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "supportCapacityReady": support_capacity_ready,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v6_2_revenue_reliability_gate(
    *,
    paid_conversion: dict[str, Any] | None = None,
    usage_quota: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    billing_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide controlled growth, hold, or further account/revenue remediation."""
    paid_conversion = paid_conversion or paid_conversion_flow_completion()
    usage_quota = usage_quota or usage_ledger_quota_reliability_completion()
    verification = verification or verification_lifecycle_account_recovery_completion()
    billing_lifecycle = billing_lifecycle or billing_support_lifecycle_messaging_completion()
    blockers = _unique(
        [
            *[f"paid:{blocker}" for blocker in paid_conversion.get("blockers", [])],
            *[f"usage:{blocker}" for blocker in usage_quota.get("blockers", [])],
            *[f"verification:{blocker}" for blocker in verification.get("blockers", [])],
            *[f"billing:{blocker}" for blocker in billing_lifecycle.get("blockers", [])],
        ]
    )
    decision = "controlled_growth" if not blockers else "hold"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_3Allowed": decision == "controlled_growth",
        "learningRisksSeparated": True,
        "evidenceInputs": [
            "billing_drift",
            "entitlement_mismatch",
            "usage_accuracy",
            "verification_success",
            "support_load",
            "parent_comprehension",
        ],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def learning_outcome_evidence_review(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Review learning outcome evidence without mixing account or billing risks."""
    states = states or {}
    rows = []
    blockers = []
    for signal in sorted(V6_LEARNING_EVIDENCE_SIGNALS):
        state = states.get(signal, "missing")
        if state not in {"reviewed", "accepted_gap"}:
            blockers.append(signal)
        rows.append(
            {
                "signal": signal,
                "state": state,
                "learningRiskOnly": True,
                "supportSafe": True,
                "rankingInputs": ["student_impact", "frequency", "severity", "effort"],
            }
        )
    result = {
        "reviewState": "ready" if not blockers else "blocked",
        "signals": rows,
        "blockers": blockers,
        "accountPaymentNotificationOnboardingSeparated": True,
        "rawPrivateLearningArtifactsIncluded": False,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def curriculum_exercise_explanation_quality_fixes(
    states: dict[str, str] | None = None,
    *,
    authorized_content_workflow: bool = False,
) -> dict[str, Any]:
    """Track authorized curriculum, exercise, explanation, and metadata fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_CURRICULUM_QUALITY_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"improved", "accepted_gap", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "specialOperatorOnly": True,
                "validationReady": state == "improved",
                "rollbackMetadataReady": state == "improved",
                "analyticsTagged": state == "improved",
            }
        )
    if not authorized_content_workflow:
        blockers.append("authorized_content_workflow")
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "authorizedContentWorkflow": authorized_content_workflow,
        "curriculumEditPermissionsBroadened": False,
        "sequencingProtected": "sequencing" not in blockers,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def ai_teacher_summary_practice_quality_fixes(
    states: dict[str, str] | None = None,
    *,
    evaluation_fixtures_updated: bool = False,
    teacher_review_ready: bool = False,
) -> dict[str, Any]:
    """Track AI summary, explanation, exercise draft, and teacher review quality."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_AI_TEACHER_QUALITY_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"covered", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "reviewOrFallbackReady": state == "covered",
                "providerObservable": surface
                in {"cost_latency_observability", "provider_error_observability"},
            }
        )
    if not evaluation_fixtures_updated:
        blockers.append("evaluation_fixtures")
    if not teacher_review_ready:
        blockers.append("teacher_review")
    result = {
        "qualityState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "evaluationFixturesUpdated": evaluation_fixtures_updated,
        "teacherReviewReady": teacher_review_ready,
        "teacherReviewModes": ["accept", "edit", "reject", "explain", "follow_up"],
        "unreviewedAutonomyExpanded": False,
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def adaptive_recommendation_parent_progress_clarity(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track recommendation freshness, dedupe, correction, and progress clarity."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_ADAPTIVE_PROGRESS_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"improved", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "internalScoringExposed": False,
                "teacherAdminCorrectionReady": surface == "teacher_admin_correction"
                and state == "improved",
                "familyExplanationReady": surface
                in {"explanation_copy", "parent_progress_report"}
                and state == "improved",
            }
        )
    result = {
        "clarityState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "parentProgressConnects": ["activity", "outcome", "next_step", "support_recommendation"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v6_3_learning_quality_gate(
    *,
    outcome_review: dict[str, Any] | None = None,
    curriculum_fixes: dict[str, Any] | None = None,
    ai_quality: dict[str, Any] | None = None,
    adaptive_progress: dict[str, Any] | None = None,
    automation_hold: bool = False,
) -> dict[str, Any]:
    """Close v6.3 with learning scale, automation hold, or remediation."""
    outcome_review = outcome_review or learning_outcome_evidence_review()
    curriculum_fixes = curriculum_fixes or curriculum_exercise_explanation_quality_fixes()
    ai_quality = ai_quality or ai_teacher_summary_practice_quality_fixes()
    adaptive_progress = adaptive_progress or adaptive_recommendation_parent_progress_clarity()
    blockers = _unique(
        [
            *[f"outcome:{blocker}" for blocker in outcome_review.get("blockers", [])],
            *[f"curriculum:{blocker}" for blocker in curriculum_fixes.get("blockers", [])],
            *[f"ai:{blocker}" for blocker in ai_quality.get("blockers", [])],
            *[f"adaptive:{blocker}" for blocker in adaptive_progress.get("blockers", [])],
        ]
    )
    if automation_hold:
        decision = "hold_automation"
    elif not blockers:
        decision = "prepare_larger_cohort"
    else:
        decision = "continue_learning_quality_remediation"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_4Allowed": decision == "prepare_larger_cohort",
        "automationHold": automation_hold,
        "largerCohortApproved": False,
        "remainingRisksForV6_4": ["observability", "release_discipline", "incident_operations"],
        "evidenceInputs": [
            "learning_outcome",
            "parent_comprehension",
            "teacher_review",
            "ai_quality",
            "support_evidence",
        ],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def operations_risk_incident_review(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Review operational risks, incidents, toil, drift, and bottlenecks."""
    states = states or {}
    rows = []
    blockers = []
    selected_findings = []
    for area in sorted(V6_OPERATIONS_RISK_AREAS):
        state = states.get(area, "missing")
        if state not in {"reviewed", "selected_for_fix", "accepted_gap"}:
            blockers.append(area)
        if state == "selected_for_fix":
            selected_findings.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "severityAssigned": state != "missing",
                "ownerAssigned": state != "missing",
                "userImpactCaptured": state != "missing",
                "detectionPathCaptured": state != "missing",
                "gapTypeSeparated": True,
            }
        )
    if not selected_findings:
        blockers.append("highest_risk_selection")
    result = {
        "reviewState": "ready" if not blockers else "blocked",
        "areas": rows,
        "selectedFindings": selected_findings,
        "blockers": blockers,
        "gapTypes": ["product", "reliability", "support", "process"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def admin_support_teacher_workflow_scale_fixes(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track admin, support, teacher, content, QA, and escalation workflow fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_OPERATOR_WORKFLOW_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"improved", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "sensitiveOperationProtected": True,
                "operatorStateVisible": state == "improved",
                "ownerNextActionEscalationVisible": state == "improved",
                "manualToilReduced": state == "improved",
            }
        )
    result = {
        "workflowState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "privateContentLeakage": False,
        "permissionBroadening": False,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def observability_alert_dashboard_hardening(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track dashboards, alerts, owners, thresholds, runbooks, and traffic labels."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_OBSERVABILITY_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"hardened", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "ownerReady": state == "hardened",
                "thresholdReady": state == "hardened",
                "severityReady": state == "hardened",
                "escalationReady": state == "hardened",
                "runbookReady": state == "hardened",
                "trafficClassSeparated": True,
            }
        )
    result = {
        "observabilityState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "trafficClasses": ["test", "dry_run", "pilot", "real_customer"],
        "privateEvidenceExcluded": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def release_migration_rollback_smoke_discipline(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track release checklist, rollout, rollback, smoke, fixture, and owner evidence."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V6_RELEASE_DISCIPLINE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"hardened", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "currentChecklistReady": state == "hardened",
                "stagedRolloutReady": state == "hardened",
                "featureFlagReady": state == "hardened",
                "rollbackExecutable": state == "hardened",
                "smokeCoverageReady": state == "hardened",
                "ownerHandoffReady": state == "hardened",
            }
        )
    result = {
        "releaseState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "evidenceLinks": ["code_sha", "deploy_build_id", "request_id", "timestamp", "owner"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v6_4_controlled_expansion_readiness_gate(
    *,
    risk_review: dict[str, Any] | None = None,
    workflow_fixes: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    release_discipline: dict[str, Any] | None = None,
    hold_requested: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    """Close v6.4 with larger cohort readiness, hold, rollback, or hardening."""
    risk_review = risk_review or operations_risk_incident_review()
    workflow_fixes = workflow_fixes or admin_support_teacher_workflow_scale_fixes()
    observability = observability or observability_alert_dashboard_hardening()
    release_discipline = release_discipline or release_migration_rollback_smoke_discipline()
    blockers = _unique(
        [
            *[f"risk:{blocker}" for blocker in risk_review.get("blockers", [])],
            *[f"workflow:{blocker}" for blocker in workflow_fixes.get("blockers", [])],
            *[f"observability:{blocker}" for blocker in observability.get("blockers", [])],
            *[f"release:{blocker}" for blocker in release_discipline.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif hold_requested:
        decision = "hold"
    elif blockers:
        decision = "operations_hardening_cycle"
    else:
        decision = "larger_controlled_cohort"
    result = {
        "decision": decision,
        "blockers": blockers,
        "largerCohortAllowed": decision == "larger_controlled_cohort",
        "publicLaunchApproved": False,
        "paidMarketingApproved": False,
        "evidenceInputs": [
            "incident",
            "support",
            "teacher",
            "billing",
            "data_quality",
            "mobile",
            "provider",
            "learning",
            "release",
        ],
        "nextVersionRecommendation": "plan_from_real_bottlenecks_and_customer_outcomes",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def production_evidence_access_approval_refresh(
    states: dict[str, str] | None = None,
    *,
    owner_signoffs: dict[str, str] | None = None,
    approved_credential_path: bool = False,
) -> dict[str, Any]:
    """Refresh current production access, approvals, and owner signoff evidence."""
    states = states or {}
    owner_signoffs = owner_signoffs or {}
    rows = []
    blockers = []
    for path in sorted(V65_PRODUCTION_ACCESS_PATHS):
        state = states.get(path, "missing")
        signoff = owner_signoffs.get(path, "missing")
        if state not in {"available", "disabled_for_pilot", "not_required"}:
            blockers.append(path)
        if state in {"available", "disabled_for_pilot"} and signoff != "approved":
            blockers.append(f"owner_signoff:{path}")
        rows.append(
            {
                "accessPath": path,
                "state": state,
                "owner": _v65_access_owner(path),
                "ownerSignoff": signoff,
                "sourceType": "real_production_or_approved_credential",
                "redactedMetadataOnly": True,
            }
        )
    if not approved_credential_path:
        blockers.append("approved_credential_path")
    result = {
        "accessState": "ready" if not blockers else "blocked",
        "accessPaths": rows,
        "approvedCredentialPath": approved_credential_path,
        "blockers": blockers,
        "evidencePolicy": {
            "realEvidenceRequired": True,
            "localContractsAreNotProof": True,
            "recordRequestIds": True,
            "recordAccountAliasesOnly": True,
            "productionMutationAllowed": False,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def production_account_payment_usage_smoke(
    states: dict[str, str] | None = None,
    *,
    production_mutation_approved: bool = False,
) -> dict[str, Any]:
    """Check account, payment, entitlement, usage, quota, and support states."""
    states = states or {}
    rows = []
    blockers = []
    blocker_package = []
    for surface in sorted(V65_ACCOUNT_PAYMENT_USAGE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"passed", "read_only_verified", "disabled_for_pilot"}:
            blockers.append(surface)
            blocker_package.append(_v65_blocker(surface, "account_payment_usage"))
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v65_account_owner(surface),
                "requestIdRequired": state != "disabled_for_pilot",
                "accountAliasRequired": state != "disabled_for_pilot",
                "fallback": _v65_account_fallback(surface),
            }
        )
    result = {
        "smokeState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "blockerPackage": blocker_package,
        "productionMutationApproved": production_mutation_approved,
        "mutationPolicy": {
            "allowed": production_mutation_approved,
            "scope": "pilot_safe_account_only" if production_mutation_approved else "read_only",
            "reversible": True,
            "recorded": production_mutation_approved,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def production_notification_support_mobile_learning_smoke(
    states: dict[str, str] | None = None,
    *,
    disabled_surfaces: set[str] | None = None,
    evidence_modes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Check production notification, support, mobile, provider, and learning paths."""
    states = states or {}
    disabled = disabled_surfaces or set()
    evidence_modes = evidence_modes or {}
    rows = []
    blockers = []
    for surface in sorted(V65_NOTIFICATION_SUPPORT_MOBILE_LEARNING_SURFACES):
        state = "disabled_for_pilot" if surface in disabled else states.get(surface, "missing")
        mode = "disabled" if surface in disabled else evidence_modes.get(surface, "missing")
        if state not in {"passed", "read_only_verified", "disabled_for_pilot"}:
            blockers.append(surface)
        if state in {"passed", "read_only_verified"} and mode != "production":
            blockers.append(f"evidence_mode:{surface}")
        rows.append(
            {
                "surface": surface,
                "state": state,
                "evidenceMode": mode,
                "owner": _v65_provider_learning_owner(surface),
                "fallback": _v65_provider_learning_fallback(surface),
                "supportCopyReady": state == "disabled_for_pilot",
                "requestOrBuildIdRequired": state != "disabled_for_pilot",
            }
        )
    result = {
        "smokeState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "disabledSurfaces": sorted(disabled),
        "blockers": blockers,
        "dryRunOrLocalFixtureIsNotProductionEvidence": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def first_cohort_launch_packet_execution(
    packet_states: dict[str, str] | None = None,
    *,
    dry_run_passed: bool = False,
) -> dict[str, Any]:
    """Finalize first-cohort launch packet and dry-run handoff evidence."""
    packet_states = packet_states or {}
    rows = []
    blockers = []
    for area in sorted(V65_COHORT_LAUNCH_PACKET_AREAS):
        state = packet_states.get(area, "missing")
        if state not in {"finalized", "accepted_gap", "disabled_for_pilot"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "owner": _v65_launch_packet_owner(area),
                "startBlocking": state == "missing",
            }
        )
    if not dry_run_passed:
        blockers.append("dry_run")
    result = {
        "packetState": "ready" if not blockers else "blocked",
        "areas": rows,
        "dryRunPassed": dry_run_passed,
        "dryRunCoverage": [
            "login",
            "onboarding",
            "entitlement",
            "usage",
            "first_learning_action",
            "notification_support_touchpoints",
            "mobile_path",
            "admin_visibility",
        ],
        "blockers": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def live_pilot_start_decision_handoff(
    *,
    access_refresh: dict[str, Any] | None = None,
    account_smoke: dict[str, Any] | None = None,
    support_mobile_learning_smoke: dict[str, Any] | None = None,
    launch_packet: dict[str, Any] | None = None,
    accepted_blockers: list[str] | None = None,
) -> dict[str, Any]:
    """Run the current v6.5 start decision and prepare v6.6 handoff or blockers."""
    access_refresh = access_refresh or production_evidence_access_approval_refresh()
    account_smoke = account_smoke or production_account_payment_usage_smoke()
    support_mobile_learning_smoke = (
        support_mobile_learning_smoke or production_notification_support_mobile_learning_smoke()
    )
    launch_packet = launch_packet or first_cohort_launch_packet_execution()
    accepted = accepted_blockers or []
    blockers = _unique(
        [
            *(["access_refresh"] if access_refresh.get("accessState") != "ready" else []),
            *(["account_smoke"] if account_smoke.get("smokeState") != "ready" else []),
            *(
                ["support_mobile_learning_smoke"]
                if support_mobile_learning_smoke.get("smokeState") != "ready"
                else []
            ),
            *(["launch_packet"] if launch_packet.get("packetState") != "ready" else []),
            *[f"access:{blocker}" for blocker in access_refresh.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_smoke.get("blockers", [])],
            *[
                f"support_mobile_learning:{blocker}"
                for blocker in support_mobile_learning_smoke.get("blockers", [])
            ],
            *[f"launch:{blocker}" for blocker in launch_packet.get("blockers", [])],
        ]
    )
    unresolved = [blocker for blocker in blockers if blocker not in accepted]
    if not unresolved:
        decision = "start_limited_pilot"
    elif accepted:
        decision = "harden_further"
    else:
        decision = "hold"
    result = {
        "decision": decision,
        "safeToStart": decision == "start_limited_pilot",
        "realUserOperationsAllowed": decision == "start_limited_pilot",
        "blockers": unresolved,
        "acceptedBlockers": accepted,
        "v6_6Allowed": decision == "start_limited_pilot",
        "handoff": (
            {
                "cohortScope": "approved_limited_pilot",
                "dailyOperatingCadence": "daily_pilot_review",
                "owners": ["product_owner", "support_owner", "teacher_owner", "incident_owner"],
                "dashboards": ["activation", "usage", "support", "learning", "provider"],
                "rollbackControls": ["pause_cohort", "disable_provider", "support_macro"],
            }
            if decision == "start_limited_pilot"
            else {"blockerPackageTarget": "v6_6_blocker_burn_down"}
        ),
        "outOfScope": ["public_launch", "paid_marketing", "broad_expansion", "uncontrolled_provider_writes"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def cohort_day_one_operations_or_blocker_sprint_start(
    *,
    v65_start_gate: dict[str, Any] | None = None,
    observed_signals: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Start live cohort operations or convert v6.5 blockers into a fix board."""
    v65_start_gate = v65_start_gate or live_pilot_start_decision_handoff()
    observed_signals = observed_signals or {}
    rows = []
    blockers = []
    if v65_start_gate.get("decision") == "start_limited_pilot":
        mode = "cohort_operations"
        for signal in sorted(V66_COHORT_OPERATION_SIGNALS):
            state = observed_signals.get(signal, "missing")
            if state not in {"healthy", "watch", "accepted_gap"}:
                blockers.append(signal)
            rows.append(
                {
                    "signal": signal,
                    "state": state,
                    "owner": _v66_signal_owner(signal),
                    "trafficClass": "real_cohort",
                    "dailyReviewRequired": True,
                }
            )
    else:
        mode = "blocker_sprint"
        for blocker in v65_start_gate.get("blockers", ["v6_5_start_gate_not_started"]):
            rows.append(_v66_fix_board_row(blocker))
            blockers.append(blocker)
    result = {
        "operationsState": "ready" if not blockers else "blocked",
        "mode": mode,
        "rows": rows,
        "blockers": blockers,
        "cadence": "daily_pilot_review",
        "pauseCriteriaActive": True,
        "rollbackAuthorityActive": True,
        "supportCoverageActive": True,
        "trafficClassesSeparated": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def activation_account_verification_entitlement_fixes(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track activation, account, verification, entitlement, usage, and quota fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V66_ACCOUNT_ENTITLEMENT_FIX_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"fixed", "explicitly_deferred"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "focusedTestsCovered": state == "fixed",
                "userCopyStates": ["pending", "failed", "expired", "blocked", "disabled", "recovered"],
                "revenueImpactAuditable": surface
                in {"entitlement_activation", "subscription_state", "usage_writes", "quota_display"},
                "reversible": True,
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "rolesCovered": ["parent", "student", "admin_support"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def support_teacher_notification_mobile_fixes(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track support, teacher, notification, mobile, and incident fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V66_SUPPORT_TEACHER_MOBILE_FIX_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"fixed", "disabled_for_pilot", "explicitly_deferred"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "owner": _v66_support_owner(surface),
                "operatorVisible": state in {"fixed", "disabled_for_pilot"},
                "fallbackCopyReady": state == "disabled_for_pilot",
                "requestOrBuildIdRequired": state == "fixed",
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "escalationVisible": "escalation" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def first_learning_action_parent_clarity_fixes(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track first learning action, recommendation, and parent clarity fixes."""
    states = states or {}
    rows = []
    blockers = []
    known_gaps = []
    for surface in sorted(V66_LEARNING_PARENT_FIX_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"fixed", "accepted_gap", "explicitly_deferred"}:
            blockers.append(surface)
        if state == "accepted_gap":
            known_gaps.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "nextStepClear": state == "fixed",
                "operatorInterventionRequired": state != "fixed",
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "curriculumAuthorizationPreserved": True,
        "aiBoundariesPreserved": True,
        "knownLearningGapsForV6_8": known_gaps,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v66_live_cohort_outcome_gate(
    *,
    operations: dict[str, Any] | None = None,
    account_fixes: dict[str, Any] | None = None,
    support_fixes: dict[str, Any] | None = None,
    learning_fixes: dict[str, Any] | None = None,
    rollback_required: bool = False,
) -> dict[str, Any]:
    """Close v6.6 with continue, hold, rollback, or revenue/retention execution."""
    operations = operations or cohort_day_one_operations_or_blocker_sprint_start()
    account_fixes = account_fixes or activation_account_verification_entitlement_fixes()
    support_fixes = support_fixes or support_teacher_notification_mobile_fixes()
    learning_fixes = learning_fixes or first_learning_action_parent_clarity_fixes()
    blockers = _unique(
        [
            *[f"operations:{blocker}" for blocker in operations.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_fixes.get("blockers", [])],
            *[f"support:{blocker}" for blocker in support_fixes.get("blockers", [])],
            *[f"learning:{blocker}" for blocker in learning_fixes.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "hold"
    else:
        decision = "proceed_to_revenue_retention"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_7Allowed": decision == "proceed_to_revenue_retention",
        "evidenceInputs": [
            "activation",
            "support",
            "teacher",
            "billing",
            "usage",
            "mobile",
            "notification",
            "learning",
            "parent_clarity",
            "incident",
        ],
        "remainingRisksForV6_7": blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def paid_conversion_billing_reality_review(
    states: dict[str, str] | None = None,
    *,
    owner_approved_corrections: bool = False,
) -> dict[str, Any]:
    """Review paid conversion, billing, entitlement, invoice, refund, and correction evidence."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V67_PAID_BILLING_REVIEW_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"reviewed", "reconciled", "disabled_for_pilot", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "providerReconciled": state == "reconciled",
                "supportVisible": surface in {"failed_payment", "invoice", "refund", "manual_correction"},
                "parentCopyReady": state in {"reviewed", "reconciled", "disabled_for_pilot"},
                "revenueImpacting": surface
                in {
                    "checkout",
                    "payment_methods",
                    "entitlement_activation",
                    "renewal",
                    "failed_payment",
                    "refund",
                    "manual_correction",
                },
            }
        )
    if not owner_approved_corrections:
        blockers.append("owner_approved_corrections")
    result = {
        "reviewState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": _unique(blockers),
        "parentCopyReady": all(row["parentCopyReady"] for row in rows),
        "revenueCorrectionsAuditable": owner_approved_corrections,
        "reversible": owner_approved_corrections,
        "reconciliationInputs": ["billing_provider", "entitlement", "usage", "admin_support"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def usage_quota_parent_account_reliability_fixes(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Track usage, quota, account, support explanation, and reconciliation reliability fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V67_USAGE_ACCOUNT_RELIABILITY_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"reliable", "fixed", "accepted_gap", "explicitly_deferred"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "supportSafe": True,
                "privateLearningContentIncluded": False,
                "driftVisible": surface
                in {"usage_ledger", "idempotency", "reconciliation_reports", "quota_display"},
                "parentSelfServeCovered": surface
                in {
                    "verification_state",
                    "subscription_state",
                    "child_access",
                    "quota_display",
                    "support_explanations",
                    "recovery_state",
                },
            }
        )
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "supportCanExplainWithoutPrivateLearningContent": True,
        "driftStaleDuplicateManualOverrideVisible": "reconciliation_reports" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def lifecycle_retention_support_capacity_execution(
    states: dict[str, str] | None = None,
    *,
    support_capacity_measured: bool = False,
) -> dict[str, Any]:
    """Execute retention lifecycle surfaces or explicitly disable them for the pilot."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V67_LIFECYCLE_RETENTION_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"executed", "disabled_for_pilot", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "preferencesHandled": surface
                in {"onboarding", "activation", "reminder", "renewal", "failed_payment", "win_back"},
                "supportVisible": surface in {"failed_payment", "cancellation", "support_capacity"},
                "realUserSignal": surface == "retention_signals" and state == "executed",
            }
        )
    if not support_capacity_measured:
        blockers.append("support_capacity_measured")
    result = {
        "executionState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": _unique(blockers),
        "supportCapacityMeasured": support_capacity_measured,
        "retentionSignalsDistinguishRealUsers": states.get("retention_signals") == "executed",
        "testTrafficExcludedFromRetention": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def referral_waitlist_controlled_intake_execution(
    states: dict[str, str] | None = None,
    *,
    capacity_gate_ready: bool = False,
    support_gate_ready: bool = False,
) -> dict[str, Any]:
    """Run referral, waitlist, invite, and intake flows only behind capacity gates."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V67_CONTROLLED_INTAKE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"ready", "disabled_for_pilot", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "featureGateRequired": surface in {"referral", "waitlist", "invite"},
                "supportVisible": surface in {"cohort_planning", "support_staffing"},
                "publicLaunchSurface": False,
            }
        )
    if not capacity_gate_ready:
        blockers.append("capacity_gate")
    if not support_gate_ready:
        blockers.append("support_gate")
    result = {
        "intakeState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": _unique(blockers),
        "capacityGateReady": capacity_gate_ready,
        "supportGateReady": support_gate_ready,
        "publicLaunchApproved": False,
        "paidMarketingApproved": False,
        "feedsCohortPlanning": "cohort_planning" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v67_revenue_growth_decision_gate(
    *,
    revenue_review: dict[str, Any] | None = None,
    usage_account: dict[str, Any] | None = None,
    lifecycle: dict[str, Any] | None = None,
    intake: dict[str, Any] | None = None,
    rollback_required: bool = False,
) -> dict[str, Any]:
    """Close v6.7 with controlled growth, hold, rollback, or revenue remediation."""
    revenue_review = revenue_review or paid_conversion_billing_reality_review()
    usage_account = usage_account or usage_quota_parent_account_reliability_fixes()
    lifecycle = lifecycle or lifecycle_retention_support_capacity_execution()
    intake = intake or referral_waitlist_controlled_intake_execution()
    blockers = _unique(
        [
            *[f"revenue:{blocker}" for blocker in revenue_review.get("blockers", [])],
            *[f"usage_account:{blocker}" for blocker in usage_account.get("blockers", [])],
            *[f"lifecycle:{blocker}" for blocker in lifecycle.get("blockers", [])],
            *[f"intake:{blocker}" for blocker in intake.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "revenue_remediation"
    else:
        decision = "controlled_growth"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_8Allowed": decision == "controlled_growth",
        "paidMarketingApproved": False,
        "publicLaunchApproved": False,
        "learningRisksSeparated": True,
        "decisionInputs": [
            "conversion",
            "revenue_drift",
            "usage_accuracy",
            "retention",
            "support_load",
            "parent_comprehension",
            "incidents",
        ],
        "nextMilestoneRiskHandoff": {
            "learningQualityRisks": [],
            "revenueAccountRisks": blockers,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def real_learning_outcome_weak_topic_analysis(
    states: dict[str, str] | None = None,
    *,
    top_issues_ranked: bool = False,
) -> dict[str, Any]:
    """Analyze real learning outcome signals without mixing operational account risks."""
    states = states or {}
    rows = []
    blockers = []
    for signal in sorted(V68_REAL_LEARNING_OUTCOME_SIGNALS):
        state = states.get(signal, "missing")
        if state not in {"analyzed", "accepted_gap", "insufficient_data"}:
            blockers.append(signal)
        rows.append(
            {
                "signal": signal,
                "state": state,
                "learningProblemOnly": True,
                "supportSafe": True,
                "rawPrivateStudentContentIncluded": False,
                "rankingInputs": ["student_impact", "frequency", "severity", "effort"],
            }
        )
    if not top_issues_ranked:
        blockers.append("top_issues_ranked")
    result = {
        "analysisState": "ready" if not blockers else "blocked",
        "signals": rows,
        "blockers": _unique(blockers),
        "accountBillingNotificationSupportOnboardingSeparated": True,
        "topIssuesRanked": top_issues_ranked,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def curriculum_exercise_explanation_quality_release(
    states: dict[str, str] | None = None,
    *,
    authorized_content_workflow: bool = False,
) -> dict[str, Any]:
    """Release authorized curriculum, exercise, explanation, metadata, and sequencing fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V68_CURRICULUM_RELEASE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"released", "validated", "accepted_gap", "not_applicable"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "specialAuthorizationRequired": True,
                "validationReady": state in {"released", "validated"},
                "previewReady": state in {"released", "validated"},
                "rollbackMetadataReady": state in {"released", "validated"},
                "analyticsTagged": surface == "analytics_tags" and state in {"released", "validated"},
            }
        )
    if not authorized_content_workflow:
        blockers.append("authorized_content_workflow")
    result = {
        "releaseState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": _unique(blockers),
        "authorizedContentWorkflow": authorized_content_workflow,
        "curriculumEditPermissionsBroadened": False,
        "progressIntegrityPreserved": "progress_integrity" not in blockers,
        "recommendationIntegrityPreserved": "recommendation_integrity" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def ai_teacher_summary_practice_quality_release(
    states: dict[str, str] | None = None,
    *,
    evaluation_fixtures_updated: bool = False,
    teacher_review_ready: bool = False,
) -> dict[str, Any]:
    """Release AI teacher summary, explanation, exercise draft, review, and fallback quality fixes."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V68_AI_TEACHER_RELEASE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"released", "reviewed", "fallback_ready", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "reviewOrFallbackReady": state in {"released", "reviewed", "fallback_ready"},
                "providerObservable": surface
                in {"cost_latency_observability", "provider_error_observability"},
                "unreviewedAutonomyExpanded": False,
            }
        )
    if not evaluation_fixtures_updated:
        blockers.append("evaluation_fixtures")
    if not teacher_review_ready:
        blockers.append("teacher_review")
    result = {
        "qualityState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": _unique(blockers),
        "evaluationFixturesUpdated": evaluation_fixtures_updated,
        "teacherReviewReady": teacher_review_ready,
        "teacherReviewModes": ["accept", "edit", "reject", "explain", "follow_up"],
        "unsafeOffTopicOverconfidentCaught": "safety_review" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def adaptive_recommendation_parent_progress_release(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Release adaptive recommendation and parent progress explanation improvements."""
    states = states or {}
    rows = []
    blockers = []
    for surface in sorted(V68_ADAPTIVE_PROGRESS_RELEASE_SURFACES):
        state = states.get(surface, "missing")
        if state not in {"released", "improved", "accepted_gap"}:
            blockers.append(surface)
        rows.append(
            {
                "surface": surface,
                "state": state,
                "internalScoringExposed": False,
                "promptExposed": False,
                "correctionReady": surface == "teacher_admin_correction" and state in {"released", "improved"},
                "familyExplanationReady": surface
                in {"student_explanations", "parent_explanations", "parent_progress_reporting"}
                and state in {"released", "improved"},
            }
        )
    result = {
        "releaseState": "ready" if not blockers else "blocked",
        "surfaces": rows,
        "blockers": blockers,
        "recommendationInputs": [
            "recent_learning",
            "weak_topics",
            "completed_assignments",
            "content_availability",
            "freshness",
            "duplicate_suppression",
        ],
        "parentProgressConnects": ["activity", "outcome", "next_step", "support_recommendation"],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v68_learning_expansion_decision_gate(
    *,
    outcome_analysis: dict[str, Any] | None = None,
    curriculum_release: dict[str, Any] | None = None,
    ai_quality: dict[str, Any] | None = None,
    adaptive_progress: dict[str, Any] | None = None,
    content_ai_freeze: bool = False,
) -> dict[str, Any]:
    """Close v6.8 with learning scale, remediation, hold, or content/AI freeze."""
    outcome_analysis = outcome_analysis or real_learning_outcome_weak_topic_analysis()
    curriculum_release = curriculum_release or curriculum_exercise_explanation_quality_release()
    ai_quality = ai_quality or ai_teacher_summary_practice_quality_release()
    adaptive_progress = adaptive_progress or adaptive_recommendation_parent_progress_release()
    blockers = _unique(
        [
            *[f"outcome:{blocker}" for blocker in outcome_analysis.get("blockers", [])],
            *[f"curriculum:{blocker}" for blocker in curriculum_release.get("blockers", [])],
            *[f"ai:{blocker}" for blocker in ai_quality.get("blockers", [])],
            *[f"adaptive:{blocker}" for blocker in adaptive_progress.get("blockers", [])],
        ]
    )
    if content_ai_freeze:
        decision = "content_ai_freeze"
    elif blockers:
        decision = "learning_remediation"
    else:
        decision = "learning_scale"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v6_9Allowed": decision == "learning_scale",
        "publicLaunchApproved": False,
        "paidMarketingApproved": False,
        "marketReadinessRisksSeparated": True,
        "decisionInputs": [
            "learning_outcome",
            "parent_comprehension",
            "teacher_review",
            "ai_quality",
            "support_load",
            "retention",
        ],
        "nextMilestoneRiskHandoff": {
            "marketReadinessRisks": [],
            "learningQualityRisks": blockers,
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def market_readiness_evidence_consolidation(
    states: dict[str, str] | None = None,
    *,
    real_traffic_separated: bool = False,
) -> dict[str, Any]:
    """Consolidate market readiness evidence across customer, revenue, learning, support, and operations."""
    states = states or {}
    rows = []
    blockers = []
    for area in sorted(V69_MARKET_EVIDENCE_AREAS):
        state = states.get(area, "missing")
        if state not in {"consolidated", "accepted_gap", "not_applicable"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "ownerAssigned": state != "missing",
                "severityAssigned": state != "missing",
                "userImpactCaptured": state != "missing",
                "mitigationCaptured": state != "missing",
                "rollbackCaptured": state != "missing",
                "supportSafe": True,
            }
        )
    if not real_traffic_separated:
        blockers.append("real_traffic_separated")
    result = {
        "evidenceState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "realTrafficSeparated": real_traffic_separated,
        "forbiddenEvidenceExcluded": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def launch_scope_pricing_support_risk_review(
    states: dict[str, str] | None = None,
    *,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    """Review launch scope, pricing, support, disabled features, known limits, and communications."""
    states = states or {}
    rows = []
    blockers = []
    for area in sorted(V69_LAUNCH_SCOPE_RISK_AREAS):
        state = states.get(area, "missing")
        if state not in {"reviewed", "ready", "accepted_gap"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "copyReady": area in {"disabled_features", "known_limitations"} and state in {"reviewed", "ready"},
                "supportReady": area in {"support_staffing", "support_macros", "incident_communications"}
                and state in {"reviewed", "ready"},
            }
        )
    result = {
        "reviewState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "roleCopyReady": "disabled_features" not in blockers and "known_limitations" not in blockers,
        "paidMarketingApproved": paid_marketing_approved,
        "paidMarketingSeparateApprovalRequired": not paid_marketing_approved,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def app_store_web_production_provider_readiness_review(
    states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Review app, web, backend, provider, monitoring, rollback, migration, and incident readiness."""
    states = states or {}
    rows = []
    blockers = []
    for area in sorted(V69_PRODUCTION_PROVIDER_READINESS_AREAS):
        state = states.get(area, "missing")
        if state not in {"reviewed", "ready", "partial_with_constraints", "accepted_gap"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "releaseEvidenceLinks": ["code_sha", "deploy_or_build_id", "timestamp", "owner"],
                "requestIdWhereApplicable": True,
                "disablementOrFallbackReady": area in {"providers", "mobile_app_store"}
                and state in {"ready", "partial_with_constraints"},
                "constraintsExplicit": state == "partial_with_constraints",
            }
        )
    result = {
        "readinessState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "providerFailuresHaveControls": "providers" not in blockers,
        "mobileConstraintsExplicit": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def public_launch_or_controlled_expansion_plan(
    states: dict[str, str] | None = None,
    *,
    final_owner_approval: bool = False,
    healthy_evidence: bool = False,
    requested_path: str = "controlled_expansion",
) -> dict[str, Any]:
    """Prepare staged public-launch-prep or controlled-expansion plan without approving launch by default."""
    states = states or {}
    rows = []
    blockers = []
    for area in sorted(V69_ROLLOUT_PLAN_AREAS):
        state = states.get(area, "missing")
        if state not in {"ready", "reviewed", "accepted_gap"}:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "userVisibleWhenNeeded": area in {"known_limitations", "disabled_features"}
                and state in {"ready", "reviewed"},
                "rollbackRelevant": area in {"freeze", "rollback", "dashboards", "owner_approvals"},
            }
        )
    if requested_path == "public_launch_prep" and not final_owner_approval:
        blockers.append("final_owner_approval")
    if requested_path == "public_launch_prep" and not healthy_evidence:
        blockers.append("healthy_evidence")
    plan_state = "ready" if not blockers else "blocked"
    result = {
        "planState": plan_state,
        "rolloutPath": requested_path if plan_state == "ready" else "hold_or_remediation",
        "areas": rows,
        "blockers": _unique(blockers),
        "finalOwnerApproval": final_owner_approval,
        "healthyEvidence": healthy_evidence,
        "publicLaunchApproved": requested_path == "public_launch_prep" and plan_state == "ready",
        "knownLimitationsUserVisible": "known_limitations" not in blockers,
        "disabledFeaturesUserVisible": "disabled_features" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v69_market_readiness_decision_gate(
    *,
    evidence: dict[str, Any] | None = None,
    scope_review: dict[str, Any] | None = None,
    production_readiness: dict[str, Any] | None = None,
    rollout_plan: dict[str, Any] | None = None,
    rollback_required: bool = False,
    recommend_next_version: bool = False,
) -> dict[str, Any]:
    """Close v6.9 with launch prep, controlled expansion, hold, rollback, or next-version focus."""
    evidence = evidence or market_readiness_evidence_consolidation()
    scope_review = scope_review or launch_scope_pricing_support_risk_review()
    production_readiness = production_readiness or app_store_web_production_provider_readiness_review()
    rollout_plan = rollout_plan or public_launch_or_controlled_expansion_plan()
    blockers = _unique(
        [
            *[f"evidence:{blocker}" for blocker in evidence.get("blockers", [])],
            *[f"scope:{blocker}" for blocker in scope_review.get("blockers", [])],
            *[f"production:{blocker}" for blocker in production_readiness.get("blockers", [])],
            *[f"rollout:{blocker}" for blocker in rollout_plan.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif recommend_next_version:
        decision = "next_version_focus"
    elif blockers:
        decision = "hold"
    elif rollout_plan.get("rolloutPath") == "public_launch_prep":
        decision = "launch_prep"
    else:
        decision = "controlled_expansion"
    result = {
        "decision": decision,
        "blockers": blockers,
        "publicLaunchApproved": decision == "launch_prep" and rollout_plan.get("publicLaunchApproved") is True,
        "paidMarketingApproved": scope_review.get("paidMarketingApproved") is True,
        "decisionInputs": [
            "customer",
            "revenue",
            "learning",
            "support",
            "operations",
            "provider",
            "mobile",
            "release",
        ],
        "v7RecommendationBasedOnRemainingRisks": recommend_next_version,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


V70_APPROVAL_SCOPE_AREAS = {
    "decision_owner",
    "product_owner",
    "support_owner",
    "teacher_owner",
    "finance_billing_owner",
    "mobile_release_owner",
    "provider_owner",
    "incident_owner",
    "rollout_scope",
    "cohort_cap",
    "disabled_features",
    "pricing_posture",
    "support_hours",
    "risk_acceptance",
    "rollback_authority",
}
V70_PROVIDER_EVIDENCE_AREAS = {
    "payment",
    "notifications",
    "support_crm",
    "bi_apm",
    "ai_provider",
    "mobile_app_store",
    "monitoring",
    "restore_tabletop",
    "incident_readiness",
}
V70_COHORT_SETUP_AREAS = {
    "cohort_aliases",
    "eligibility",
    "consent_state",
    "communications",
    "feature_flags",
    "dashboards",
    "support_staffing",
    "teacher_coverage",
    "pause_criteria",
    "rollback_plan",
    "traffic_separation",
}
V70_SMOKE_AREAS = {
    "login",
    "verification",
    "onboarding",
    "entitlement",
    "usage_ledger",
    "quota",
    "notification",
    "support",
    "mobile",
    "learning",
    "ai_help",
    "revenue",
}
V71_DAY_ONE_AREAS = {
    "cohort_enablement",
    "support_coverage",
    "teacher_coverage",
    "dashboards",
    "incident_checks",
    "pause_criteria",
    "rollback_controls",
    "real_user_separation",
}
V71_ACCOUNT_REVENUE_SUPPORT_AREAS = {
    "account",
    "verification",
    "entitlement",
    "subscription",
    "usage_quota",
    "billing",
    "lifecycle",
    "support",
    "parent_clarity",
}
V71_LEARNING_MOBILE_PROVIDER_AREAS = {
    "learning",
    "ai_provider",
    "teacher_dispatch",
    "mobile",
    "notification",
    "curriculum",
    "recommendation",
    "parent_progress",
}
V71_RELEASE_EVIDENCE_AREAS = {
    "regression_tests",
    "smoke_evidence",
    "release_notes",
    "rollback_notes",
    "operator_runbook",
    "traffic_dashboards",
    "residual_risks",
}
V72_LAUNCH_SCOPE_AREAS = {
    "audience",
    "rollout_scope",
    "pricing_package",
    "plan_limits",
    "disabled_features",
    "known_limitations",
    "eligibility",
    "support_policy",
    "billing_copy",
}
V72_PROVIDER_READINESS_AREAS = {
    "frontend_web",
    "mobile_app_store",
    "backend",
    "payment",
    "notification",
    "support",
    "bi_apm",
    "ai_provider",
    "monitoring",
}
V72_SUPPORT_ACQUISITION_AREAS = {
    "support_staffing",
    "incident_coverage",
    "lifecycle_messages",
    "referral_waitlist",
    "acquisition_limits",
    "retention_reporting",
    "escalation_paths",
    "support_macros",
}
V72_EVIDENCE_PACKAGE_AREAS = {
    "launch_freeze",
    "staged_rollout",
    "rollback",
    "dashboards",
    "alerts",
    "incident_runbooks",
    "owner_approvals",
    "evidence_package",
    "residual_risks",
}
V73_APPROVAL_FREEZE_AREAS = {
    "final_launch_approval",
    "rollout_scope",
    "release_freeze",
    "release_artifacts",
    "support_staffing",
    "teacher_capacity",
    "provider_readiness",
    "mobile_readiness",
    "rollback_authority",
}
V73_PRODUCTION_SMOKE_AREAS = {
    "login",
    "verification",
    "onboarding",
    "entitlement",
    "usage",
    "notification",
    "support",
    "mobile",
    "learning",
    "ai_help",
    "revenue",
    "rollback",
}
V73_MONITORING_AREAS = {
    "auth",
    "billing",
    "usage",
    "notifications",
    "support_sla",
    "teacher_operations",
    "learning_quality",
    "ai_provider",
    "mobile",
    "incidents",
    "revenue",
    "retention",
    "acquisition_intake",
}
V73_REMEDIATION_AREAS = {
    "hotfixes",
    "support_actions",
    "incident_communications",
    "rollback",
    "disablement",
    "user_copy",
    "release_evidence",
    "support_macros",
    "residual_risks",
}
V74_CUSTOMER_SUCCESS_AREAS = {
    "customer_success",
    "support",
    "onboarding",
    "lifecycle",
    "incident_communications",
    "feedback_loops",
    "teacher_workload",
    "parent_satisfaction",
    "student_friction",
}
V74_REVENUE_GROWTH_AREAS = {
    "revenue",
    "retention",
    "churn",
    "refunds",
    "failed_payments",
    "usage_quota",
    "pricing",
    "lifecycle",
    "referral_waitlist",
    "acquisition_quality",
    "paid_marketing_gate",
}
V74_QUALITY_RELIABILITY_AREAS = {
    "learning_outcomes",
    "curriculum_quality",
    "ai_teacher_quality",
    "recommendations",
    "parent_progress",
    "teacher_workload",
    "mobile_reliability",
    "provider_health",
    "support_burden",
}
V74_INCIDENT_FEEDBACK_AREAS = {
    "incidents",
    "releases",
    "dashboards",
    "alerts",
    "rollback",
    "migrations",
    "data_quality",
    "support_load",
    "roadmap_feedback",
}
V7_READY_STATES = {"approved", "ready", "verified", "active", "fixed", "healthy", "accepted_gap", "disabled_for_scope", "not_required"}


def _v7_contract_rows(
    areas: set[str],
    states: dict[str, str] | None,
    *,
    ready_states: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    states = states or {}
    ready_states = ready_states or V7_READY_STATES
    rows = []
    blockers = []
    for area in sorted(areas):
        state = states.get(area, "missing")
        if state not in ready_states:
            blockers.append(area)
        rows.append(
            {
                "area": area,
                "state": state,
                "ownerAssigned": state != "missing",
                "evidenceFields": ["timestamp", "owner", "environment", "request_or_build_id", "result", "blocker_state"],
                "rollbackOrDisableControl": area not in blockers,
                "supportVisible": area in {"disabled_features", "known_limitations", "support", "support_policy", "support_macros"}
                and area not in blockers,
            }
        )
    return rows, blockers


def v70_final_owner_approval_scope_refresh(
    states: dict[str, str] | None = None,
    *,
    controlled_expansion_approved: bool = False,
    public_launch_approved: bool = False,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    """Record final controlled-expansion approval without approving launch or marketing by default."""
    rows, blockers = _v7_contract_rows(V70_APPROVAL_SCOPE_AREAS, states)
    if not controlled_expansion_approved:
        blockers.append("controlled_expansion_approval")
    result = {
        "approvalState": "approved" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "controlledExpansionApproved": controlled_expansion_approved and not blockers,
        "publicLaunchApproved": public_launch_approved,
        "paidMarketingApproved": paid_marketing_approved,
        "separateLaunchAndMarketingApprovalRequired": not public_launch_approved or not paid_marketing_approved,
        "knownLimitationsVisible": "known_limitations" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v70_production_provider_mobile_support_evidence_refresh(states: dict[str, str] | None = None) -> dict[str, Any]:
    """Refresh provider, mobile, support, restore, monitoring, and incident evidence for controlled expansion."""
    rows, blockers = _v7_contract_rows(V70_PROVIDER_EVIDENCE_AREAS, states)
    result = {
        "evidenceState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "missingDependenciesClassified": all(row["state"] != "missing" for row in rows),
        "forbiddenEvidenceExcluded": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v70_controlled_expansion_cohort_rollout_setup(states: dict[str, str] | None = None) -> dict[str, Any]:
    """Prepare cohort aliases, flags, support, dashboards, pause criteria, and rollback controls."""
    rows, blockers = _v7_contract_rows(V70_COHORT_SETUP_AREAS, states)
    result = {
        "setupState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "growthIntakeCapped": "cohort_aliases" not in blockers and "eligibility" not in blockers,
        "trafficSeparated": "traffic_separation" not in blockers,
        "customerMutationAllowed": False,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v70_expansion_start_smoke_day_zero_verification(
    states: dict[str, str] | None = None,
    *,
    mutation_approved: bool = False,
) -> dict[str, Any]:
    """Verify day-zero expansion paths while requiring explicit approval for any production mutation."""
    rows, blockers = _v7_contract_rows(V70_SMOKE_AREAS, states, ready_states={"verified", "disabled_for_scope", "not_required"})
    if not mutation_approved:
        blockers.append("production_mutation_approval")
    result = {
        "smokeState": "passed" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "mutationApproved": mutation_approved,
        "startBlockersConvertedToOwnerActions": True,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v70_controlled_expansion_start_gate(
    *,
    approval: dict[str, Any] | None = None,
    provider_evidence: dict[str, Any] | None = None,
    cohort_setup: dict[str, Any] | None = None,
    smoke: dict[str, Any] | None = None,
    rollback_required: bool = False,
    remediate: bool = False,
) -> dict[str, Any]:
    """Decide whether controlled expansion starts, holds, rolls back, or enters remediation."""
    approval = approval or v70_final_owner_approval_scope_refresh()
    provider_evidence = provider_evidence or v70_production_provider_mobile_support_evidence_refresh()
    cohort_setup = cohort_setup or v70_controlled_expansion_cohort_rollout_setup()
    smoke = smoke or v70_expansion_start_smoke_day_zero_verification()
    blockers = _unique(
        [
            *[f"approval:{blocker}" for blocker in approval.get("blockers", [])],
            *[f"provider:{blocker}" for blocker in provider_evidence.get("blockers", [])],
            *[f"cohort:{blocker}" for blocker in cohort_setup.get("blockers", [])],
            *[f"smoke:{blocker}" for blocker in smoke.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif remediate:
        decision = "remediate"
    elif blockers:
        decision = "hold"
    else:
        decision = "start_controlled_expansion"
    result = {
        "decision": decision,
        "blockers": blockers,
        "v7_1Allowed": decision == "start_controlled_expansion",
        "publicLaunchApproved": False,
        "paidMarketingApproved": False,
        "handoff": "cohort scope, cadence, dashboards, owners, support coverage, and rollback controls"
        if decision == "start_controlled_expansion"
        else "hold v7.1 until controlled-expansion start evidence is approved",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v71_controlled_expansion_day_one_operations(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V71_DAY_ONE_AREAS, states, ready_states={"active", "verified", "ready"})
    result = {"operationsState": "active" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v71_expansion_account_revenue_support_fixes(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V71_ACCOUNT_REVENUE_SUPPORT_AREAS, states, ready_states={"fixed", "accepted_gap", "not_required"})
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "revenueFixesAuditable": "billing" not in blockers and "subscription" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v71_expansion_learning_mobile_teacher_provider_fixes(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V71_LEARNING_MOBILE_PROVIDER_AREAS, states, ready_states={"fixed", "accepted_gap", "not_required"})
    result = {
        "fixState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "curriculumSpecialAuthorizationRequired": True,
        "aiPolicyBound": "ai_provider" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v71_expansion_reliability_release_evidence(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V71_RELEASE_EVIDENCE_AREAS, states, ready_states={"ready", "verified", "accepted_gap"})
    result = {"releaseState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v71_expansion_outcome_gate(
    *,
    day_one: dict[str, Any] | None = None,
    account_fixes: dict[str, Any] | None = None,
    learning_fixes: dict[str, Any] | None = None,
    release_evidence: dict[str, Any] | None = None,
    launch_prep_candidate: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    day_one = day_one or v71_controlled_expansion_day_one_operations()
    account_fixes = account_fixes or v71_expansion_account_revenue_support_fixes()
    learning_fixes = learning_fixes or v71_expansion_learning_mobile_teacher_provider_fixes()
    release_evidence = release_evidence or v71_expansion_reliability_release_evidence()
    blockers = _unique(
        [
            *[f"operations:{blocker}" for blocker in day_one.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_fixes.get("blockers", [])],
            *[f"learning:{blocker}" for blocker in learning_fixes.get("blockers", [])],
            *[f"release:{blocker}" for blocker in release_evidence.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "remediation"
    elif launch_prep_candidate:
        decision = "public_launch_prep"
    else:
        decision = "continue_expansion"
    result = {"decision": decision, "blockers": blockers, "v7_2Allowed": decision == "public_launch_prep", "publicLaunchApproved": False, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v72_launch_scope_pricing_package_copy_readiness(
    states: dict[str, str] | None = None,
    *,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V72_LAUNCH_SCOPE_AREAS, states)
    result = {
        "scopeState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": blockers,
        "paidMarketingApproved": paid_marketing_approved,
        "paidMarketingSeparateGateRequired": not paid_marketing_approved,
        "copyReady": "known_limitations" not in blockers and "disabled_features" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v72_web_mobile_app_store_provider_launch_readiness(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V72_PROVIDER_READINESS_AREAS, states)
    result = {"readinessState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "providerFallbacksReady": "ai_provider" not in blockers and "payment" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v72_support_lifecycle_acquisition_capacity_readiness(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V72_SUPPORT_ACQUISITION_AREAS, states)
    result = {"capacityState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "growthIntakeCapacityGated": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v72_launch_freeze_rollback_dashboard_evidence_package(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V72_EVIDENCE_PACKAGE_AREAS, states)
    result = {"packageState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "forbiddenEvidenceExcluded": sorted(FORBIDDEN_EVIDENCE_FIELDS), "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v72_launch_preparation_gate(
    *,
    scope: dict[str, Any] | None = None,
    provider_readiness: dict[str, Any] | None = None,
    capacity: dict[str, Any] | None = None,
    evidence_package: dict[str, Any] | None = None,
    final_launch_approval: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    scope = scope or v72_launch_scope_pricing_package_copy_readiness()
    provider_readiness = provider_readiness or v72_web_mobile_app_store_provider_launch_readiness()
    capacity = capacity or v72_support_lifecycle_acquisition_capacity_readiness()
    evidence_package = evidence_package or v72_launch_freeze_rollback_dashboard_evidence_package()
    blockers = _unique(
        [
            *[f"scope:{blocker}" for blocker in scope.get("blockers", [])],
            *[f"provider:{blocker}" for blocker in provider_readiness.get("blockers", [])],
            *[f"capacity:{blocker}" for blocker in capacity.get("blockers", [])],
            *[f"package:{blocker}" for blocker in evidence_package.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "hold"
    elif final_launch_approval:
        decision = "launch_ready"
    else:
        decision = "controlled_expansion_only"
    result = {"decision": decision, "blockers": blockers, "v7_3Allowed": decision == "launch_ready", "publicLaunchApproved": final_launch_approval and decision == "launch_ready", "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v73_final_launch_approval_freeze_execution(
    states: dict[str, str] | None = None,
    *,
    public_launch_approved: bool = False,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V73_APPROVAL_FREEZE_AREAS, states)
    if not public_launch_approved:
        blockers.append("public_launch_approval")
    result = {
        "approvalState": "approved" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "publicLaunchApproved": public_launch_approved and not blockers,
        "paidMarketingApproved": paid_marketing_approved,
        "paidMarketingSeparateGateRequired": not paid_marketing_approved,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v73_staged_launch_enablement_production_smoke(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V73_PRODUCTION_SMOKE_AREAS, states, ready_states={"verified", "disabled_for_scope", "not_required"})
    result = {"smokeState": "passed" if not blockers else "blocked", "areas": rows, "blockers": blockers, "mutationsScopedAndReversible": not blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v73_launch_room_support_revenue_learning_monitoring(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V73_MONITORING_AREAS, states, ready_states={"active", "healthy", "verified"})
    result = {"monitoringState": "active" if not blockers else "blocked", "areas": rows, "blockers": blockers, "realUserTrafficSeparated": "acquisition_intake" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v73_launch_incident_remediation_user_communication(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V73_REMEDIATION_AREAS, states, ready_states={"ready", "fixed", "accepted_gap", "not_required"})
    result = {"remediationState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "limitationsVisible": "user_copy" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v73_launch_outcome_gate(
    *,
    approval: dict[str, Any] | None = None,
    smoke: dict[str, Any] | None = None,
    monitoring: dict[str, Any] | None = None,
    remediation: dict[str, Any] | None = None,
    outcome_healthy: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    approval = approval or v73_final_launch_approval_freeze_execution()
    smoke = smoke or v73_staged_launch_enablement_production_smoke()
    monitoring = monitoring or v73_launch_room_support_revenue_learning_monitoring()
    remediation = remediation or v73_launch_incident_remediation_user_communication()
    blockers = _unique(
        [
            *[f"approval:{blocker}" for blocker in approval.get("blockers", [])],
            *[f"smoke:{blocker}" for blocker in smoke.get("blockers", [])],
            *[f"monitoring:{blocker}" for blocker in monitoring.get("blockers", [])],
            *[f"remediation:{blocker}" for blocker in remediation.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "hold"
    elif approval.get("publicLaunchApproved") and outcome_healthy:
        decision = "launched"
    else:
        decision = "continue_controlled_expansion"
    result = {"decision": decision, "blockers": blockers, "v7_4Mode": "launched" if decision == "launched" else "controlled_or_hold", "paidMarketingApproved": approval.get("paidMarketingApproved") is True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v74_post_launch_customer_success_support_operations(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V74_CUSTOMER_SUCCESS_AREAS, states, ready_states={"active", "healthy", "accepted_gap"})
    result = {"operationsState": "healthy" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v74_revenue_retention_growth_governance(
    states: dict[str, str] | None = None,
    *,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V74_REVENUE_GROWTH_AREAS, states, ready_states={"healthy", "reconciled", "accepted_gap", "not_required"})
    result = {"governanceState": "healthy" if not blockers else "blocked", "areas": rows, "blockers": blockers, "paidMarketingApproved": paid_marketing_approved, "paidMarketingCapacityGateRequired": not paid_marketing_approved, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v74_learning_quality_mobile_provider_reliability_review(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V74_QUALITY_RELIABILITY_AREAS, states, ready_states={"healthy", "reviewed", "accepted_gap"})
    result = {"qualityState": "healthy" if not blockers else "blocked", "areas": rows, "blockers": blockers, "aiAutonomyPolicyBound": "ai_teacher_quality" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v74_scale_incident_release_roadmap_feedback_loop(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V74_INCIDENT_FEEDBACK_AREAS, states, ready_states={"reviewed", "healthy", "accepted_gap"})
    result = {"feedbackState": "healthy" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v74_scale_next_strategy_gate(
    *,
    customer_success: dict[str, Any] | None = None,
    revenue_growth: dict[str, Any] | None = None,
    quality_reliability: dict[str, Any] | None = None,
    incident_feedback: dict[str, Any] | None = None,
    scale_approved: bool = False,
    recommend_v8: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    customer_success = customer_success or v74_post_launch_customer_success_support_operations()
    revenue_growth = revenue_growth or v74_revenue_retention_growth_governance()
    quality_reliability = quality_reliability or v74_learning_quality_mobile_provider_reliability_review()
    incident_feedback = incident_feedback or v74_scale_incident_release_roadmap_feedback_loop()
    blockers = _unique(
        [
            *[f"customer:{blocker}" for blocker in customer_success.get("blockers", [])],
            *[f"revenue:{blocker}" for blocker in revenue_growth.get("blockers", [])],
            *[f"quality:{blocker}" for blocker in quality_reliability.get("blockers", [])],
            *[f"incident:{blocker}" for blocker in incident_feedback.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "remediation"
    elif recommend_v8:
        decision = "next_strategic_version"
    elif scale_approved:
        decision = "scale_growth"
    else:
        decision = "hold"
    result = {"decision": decision, "blockers": blockers, "v8Recommended": decision == "next_strategic_version", "paidMarketingApproved": revenue_growth.get("paidMarketingApproved") is True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


V80_APPROVAL_SCOPE_AREAS = {
    "decision_owner",
    "product_owner",
    "support_owner",
    "teacher_owner",
    "finance_owner",
    "mobile_owner",
    "provider_owner",
    "incident_owner",
    "release_owner",
    "rollout_type",
    "account_scope",
    "support_coverage",
    "disabled_features",
    "pricing_posture",
    "growth_limits",
    "risk_acceptance",
    "rollback_authority",
}
V80_LIVE_EVIDENCE_AREAS = {
    "login",
    "verification",
    "onboarding",
    "entitlement",
    "usage_ledger",
    "quota",
    "checkout_paywall",
    "notification",
    "support",
    "teacher_operations",
    "mobile_app_store",
    "ai_provider",
    "learning",
    "monitoring",
    "revenue",
    "incident_readiness",
}
V80_COMMUNICATION_AREAS = {
    "user_communications",
    "support_macros",
    "lifecycle_messages",
    "incident_communications",
    "disabled_feature_copy",
    "known_limitation_copy",
    "support_staffing",
    "teacher_coverage",
    "billing_support",
    "escalation_paths",
}
V80_SMOKE_ROLLBACK_AREAS = {
    "rollout_flags",
    "auth",
    "billing",
    "usage",
    "notification",
    "support",
    "mobile",
    "learning",
    "ai_help",
    "monitoring",
    "incident",
    "rollback",
    "launch_room",
}
V81_DAY_ONE_AREAS = {
    "rollout_dashboard",
    "support_room",
    "teacher_coverage",
    "incident_watch",
    "revenue_watch",
    "learning_watch",
    "mobile_provider_watch",
    "rollback_readiness",
    "real_user_separation",
    "daily_cadence",
}
V81_ACCOUNT_REVENUE_INCIDENT_AREAS = {
    "auth",
    "verification",
    "entitlement",
    "usage_quota",
    "billing",
    "lifecycle",
    "support",
    "refund",
    "account_clarity",
}
V81_LEARNING_MOBILE_PROVIDER_INCIDENT_AREAS = {
    "learning",
    "ai_provider",
    "mobile",
    "notification",
    "curriculum",
    "teacher",
    "recommendation",
    "parent_progress",
}
V81_RELEASE_COMMUNICATION_AREAS = {
    "tests",
    "release_notes",
    "support_macros",
    "incident_communications",
    "rollback_notes",
    "dashboard_evidence",
    "residual_risks",
}
V82_REVENUE_EVIDENCE_AREAS = {
    "conversion",
    "retention",
    "churn",
    "refunds",
    "payment_failures",
    "usage_quota",
    "pricing",
    "lifecycle",
    "support_corrections",
    "revenue_reconciliation",
}
V82_ACQUISITION_QUALITY_AREAS = {
    "referral",
    "waitlist",
    "invite",
    "acquisition_source_quality",
    "cohort_fit",
    "fraud_abuse_signals",
    "capacity_gate",
    "source_reporting",
}
V82_SUPPORT_LIFECYCLE_AREAS = {
    "support_capacity",
    "lifecycle_messaging",
    "billing_support",
    "onboarding",
    "activation",
    "reminder",
    "renewal",
    "failed_payment",
    "cancellation",
    "win_back",
    "teacher_capacity",
}
V82_PAID_MARKETING_EXPERIMENT_AREAS = {
    "owner_approval",
    "budget",
    "target_audience",
    "capacity_gate",
    "success_metrics",
    "stop_criteria",
    "rollback_controls",
    "support_ready",
    "copy_limitations",
    "audit_evidence",
}
V83_LEARNING_OUTCOME_AREAS = {
    "progress",
    "mastery",
    "weak_topics",
    "completion",
    "retry",
    "support_contacts",
    "teacher_help",
    "parent_report_engagement",
    "retention",
    "cohort_source_differences",
}
V83_CURRICULUM_QUALITY_AREAS = {
    "curriculum",
    "exercises",
    "explanations",
    "sequencing",
    "recommendations",
    "parent_progress_reporting",
    "validation",
    "preview",
    "rollback_metadata",
    "analytics_tags",
}
V83_AI_QUALITY_AREAS = {
    "summaries",
    "practice_generation",
    "explanations",
    "teacher_tools",
    "refusal_fallback",
    "safety",
    "cost",
    "latency",
    "provider_errors",
    "teacher_review",
}
V83_WORKLOAD_CLARITY_AREAS = {
    "teacher_workload",
    "parent_confusion",
    "support_contacts",
    "next_steps",
    "learning_friction",
    "student_copy",
    "teacher_copy",
    "support_macros",
    "outcome_evidence",
}
V84_STRATEGIC_REVIEW_AREAS = {
    "customer_success",
    "revenue",
    "retention",
    "learning_outcomes",
    "support_load",
    "teacher_workload",
    "mobile_reliability",
    "provider_health",
    "acquisition_quality",
    "incidents",
    "roadmap_feedback",
}
V84_RELIABILITY_SCALE_AREAS = {
    "reliability",
    "data_quality",
    "dashboards",
    "alerts",
    "migrations",
    "rollback",
    "release_cadence",
    "incident_response",
    "operational_ownership",
}
V84_MARKET_ENTERPRISE_AREAS = {
    "market_expansion",
    "language_expansion",
    "enterprise_readiness",
    "school_partnerships",
    "localization",
    "support_staffing",
    "pricing",
    "billing",
    "compliance",
}
V84_AI_GROWTH_GOVERNANCE_AREAS = {
    "ai_autonomy",
    "paid_marketing_scale",
    "growth_loops",
    "compliance",
    "privacy",
    "audit",
    "governance",
    "teacher_oversight",
    "owner_approval",
}


def v80_final_external_rollout_approval_scope_lock(
    states: dict[str, str] | None = None,
    *,
    external_rollout_approved: bool = False,
    paid_marketing_approved: bool = False,
    broad_expansion_approved: bool = False,
) -> dict[str, Any]:
    """Lock external rollout approval and scope without approving marketing or broad expansion by default."""
    rows, blockers = _v7_contract_rows(V80_APPROVAL_SCOPE_AREAS, states)
    if not external_rollout_approved:
        blockers.append("external_rollout_approval")
    result = {
        "approvalState": "approved" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "externalRolloutApproved": external_rollout_approved and not blockers,
        "paidMarketingApproved": paid_marketing_approved,
        "broadExpansionApproved": broad_expansion_approved,
        "separateGrowthApprovalRequired": not paid_marketing_approved or not broad_expansion_approved,
        "limitationsVisible": "disabled_features" not in blockers,
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v80_live_product_provider_mobile_evidence_execution(
    states: dict[str, str] | None = None,
    *,
    mutation_approved: bool = False,
) -> dict[str, Any]:
    """Execute live evidence checks while requiring explicit approval for any production mutation."""
    rows, blockers = _v7_contract_rows(V80_LIVE_EVIDENCE_AREAS, states, ready_states={"verified", "disabled_for_scope", "not_required"})
    if not mutation_approved:
        blockers.append("production_mutation_approval")
    result = {
        "evidenceState": "ready" if not blockers else "blocked",
        "areas": rows,
        "blockers": _unique(blockers),
        "mutationApproved": mutation_approved,
        "forbiddenEvidenceExcluded": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def v80_rollout_communications_support_limitation_readiness(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V80_COMMUNICATION_AREAS, states, ready_states={"ready", "active", "approved"})
    result = {"readinessState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "statesDistinguished": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v80_external_rollout_smoke_rollback_rehearsal(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V80_SMOKE_ROLLBACK_AREAS, states, ready_states={"verified", "ready", "active"})
    result = {"smokeState": "passed" if not blockers else "blocked", "areas": rows, "blockers": blockers, "rollbackCurrent": "rollback" not in blockers, "startBlockersConverted": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v80_external_rollout_start_gate(
    *,
    approval: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    communications: dict[str, Any] | None = None,
    smoke: dict[str, Any] | None = None,
    rollback_required: bool = False,
    remediate: bool = False,
) -> dict[str, Any]:
    approval = approval or v80_final_external_rollout_approval_scope_lock()
    evidence = evidence or v80_live_product_provider_mobile_evidence_execution()
    communications = communications or v80_rollout_communications_support_limitation_readiness()
    smoke = smoke or v80_external_rollout_smoke_rollback_rehearsal()
    blockers = _unique(
        [
            *[f"approval:{blocker}" for blocker in approval.get("blockers", [])],
            *[f"evidence:{blocker}" for blocker in evidence.get("blockers", [])],
            *[f"communications:{blocker}" for blocker in communications.get("blockers", [])],
            *[f"smoke:{blocker}" for blocker in smoke.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif remediate:
        decision = "remediation"
    elif blockers:
        decision = "hold"
    else:
        decision = "rollout_start"
    result = {"decision": decision, "blockers": blockers, "v8_1Allowed": decision == "rollout_start", "paidMarketingApproved": False, "broadExpansionApproved": False, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v81_live_rollout_day_one_operations(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V81_DAY_ONE_AREAS, states, ready_states={"active", "verified", "ready"})
    result = {"operationsState": "active" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v81_live_account_revenue_support_incident_fixes(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V81_ACCOUNT_REVENUE_INCIDENT_AREAS, states, ready_states={"fixed", "accepted_gap", "not_required"})
    result = {"fixState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "revenueAuditable": "billing" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v81_live_learning_mobile_provider_incident_fixes(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V81_LEARNING_MOBILE_PROVIDER_INCIDENT_AREAS, states, ready_states={"fixed", "accepted_gap", "not_required"})
    result = {"fixState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "aiPolicyBound": "ai_provider" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v81_rollout_hotfix_release_communication_evidence(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V81_RELEASE_COMMUNICATION_AREAS, states, ready_states={"ready", "verified", "accepted_gap"})
    result = {"releaseState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "limitationsVisible": "support_macros" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v81_rollout_operations_decision_gate(
    *,
    day_one: dict[str, Any] | None = None,
    account_fixes: dict[str, Any] | None = None,
    learning_fixes: dict[str, Any] | None = None,
    release_evidence: dict[str, Any] | None = None,
    growth_ready: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    day_one = day_one or v81_live_rollout_day_one_operations()
    account_fixes = account_fixes or v81_live_account_revenue_support_incident_fixes()
    learning_fixes = learning_fixes or v81_live_learning_mobile_provider_incident_fixes()
    release_evidence = release_evidence or v81_rollout_hotfix_release_communication_evidence()
    blockers = _unique(
        [
            *[f"operations:{blocker}" for blocker in day_one.get("blockers", [])],
            *[f"account:{blocker}" for blocker in account_fixes.get("blockers", [])],
            *[f"learning:{blocker}" for blocker in learning_fixes.get("blockers", [])],
            *[f"release:{blocker}" for blocker in release_evidence.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "remediation"
    elif growth_ready:
        decision = "growth_readiness"
    else:
        decision = "continue_rollout"
    result = {"decision": decision, "blockers": blockers, "v8_2Allowed": decision == "growth_readiness", "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v82_revenue_conversion_retention_evidence_review(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V82_REVENUE_EVIDENCE_AREAS, states, ready_states={"reviewed", "reconciled", "healthy", "accepted_gap"})
    result = {"reviewState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "realCustomerSeparated": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v82_acquisition_referral_waitlist_quality_review(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V82_ACQUISITION_QUALITY_AREAS, states, ready_states={"reviewed", "healthy", "accepted_gap"})
    result = {"reviewState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "intakeCapacityGated": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v82_growth_support_capacity_lifecycle_fixes(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V82_SUPPORT_LIFECYCLE_AREAS, states, ready_states={"fixed", "accepted_gap", "not_required"})
    result = {"fixState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "supportVisible": "support_capacity" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v82_paid_marketing_approval_experiment_design_gate(
    states: dict[str, str] | None = None,
    *,
    paid_marketing_approved: bool = False,
) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V82_PAID_MARKETING_EXPERIMENT_AREAS, states)
    if not paid_marketing_approved:
        blockers.append("paid_marketing_approval")
    result = {"approvalState": "approved" if not blockers else "blocked", "areas": rows, "blockers": _unique(blockers), "paidMarketingApproved": paid_marketing_approved and not blockers, "spendBlocked": bool(blockers), "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v82_growth_decision_gate(
    *,
    revenue: dict[str, Any] | None = None,
    acquisition: dict[str, Any] | None = None,
    lifecycle: dict[str, Any] | None = None,
    marketing: dict[str, Any] | None = None,
    growth_scale_approved: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    revenue = revenue or v82_revenue_conversion_retention_evidence_review()
    acquisition = acquisition or v82_acquisition_referral_waitlist_quality_review()
    lifecycle = lifecycle or v82_growth_support_capacity_lifecycle_fixes()
    marketing = marketing or v82_paid_marketing_approval_experiment_design_gate()
    blockers = _unique(
        [
            *[f"revenue:{blocker}" for blocker in revenue.get("blockers", [])],
            *[f"acquisition:{blocker}" for blocker in acquisition.get("blockers", [])],
            *[f"lifecycle:{blocker}" for blocker in lifecycle.get("blockers", [])],
            *[f"marketing:{blocker}" for blocker in marketing.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "remediation"
    elif marketing.get("paidMarketingApproved"):
        decision = "paid_marketing_prep"
    elif growth_scale_approved:
        decision = "growth_scale"
    else:
        decision = "organic_only_growth"
    result = {"decision": decision, "blockers": blockers, "v8_3Allowed": decision in {"growth_scale", "organic_only_growth", "paid_marketing_prep"}, "paidMarketingApproved": marketing.get("paidMarketingApproved") is True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v83_scaled_learning_outcome_cohort_analysis(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V83_LEARNING_OUTCOME_AREAS, states, ready_states={"analyzed", "reviewed", "healthy", "accepted_gap"})
    result = {"analysisState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "privateContentExcluded": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v83_curriculum_exercise_recommendation_quality_release(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V83_CURRICULUM_QUALITY_AREAS, states, ready_states={"improved", "validated", "accepted_gap"})
    result = {"releaseState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "specialAuthorizationRequired": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v83_ai_teacher_quality_safety_cost_release(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V83_AI_QUALITY_AREAS, states, ready_states={"improved", "reviewed", "accepted_gap"})
    result = {"releaseState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "aiAutonomyPolicyBound": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v83_teacher_workload_parent_clarity_support_reduction(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V83_WORKLOAD_CLARITY_AREAS, states, ready_states={"improved", "reduced", "updated", "accepted_gap"})
    result = {"improvementState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "supportBurdenReduced": "support_contacts" not in blockers, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v83_learning_scale_decision_gate(
    *,
    outcomes: dict[str, Any] | None = None,
    curriculum: dict[str, Any] | None = None,
    ai_quality: dict[str, Any] | None = None,
    workload: dict[str, Any] | None = None,
    learning_scale_approved: bool = False,
    content_ai_freeze: bool = False,
    strategic_pivot: bool = False,
) -> dict[str, Any]:
    outcomes = outcomes or v83_scaled_learning_outcome_cohort_analysis()
    curriculum = curriculum or v83_curriculum_exercise_recommendation_quality_release()
    ai_quality = ai_quality or v83_ai_teacher_quality_safety_cost_release()
    workload = workload or v83_teacher_workload_parent_clarity_support_reduction()
    blockers = _unique(
        [
            *[f"outcomes:{blocker}" for blocker in outcomes.get("blockers", [])],
            *[f"curriculum:{blocker}" for blocker in curriculum.get("blockers", [])],
            *[f"ai:{blocker}" for blocker in ai_quality.get("blockers", [])],
            *[f"workload:{blocker}" for blocker in workload.get("blockers", [])],
        ]
    )
    if content_ai_freeze:
        decision = "content_ai_freeze"
    elif strategic_pivot:
        decision = "strategic_pivot"
    elif blockers:
        decision = "remediation"
    elif learning_scale_approved:
        decision = "learning_scale"
    else:
        decision = "hold"
    result = {"decision": decision, "blockers": blockers, "v8_4Allowed": decision == "learning_scale", "aiAutonomyApproved": False, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v84_strategic_product_business_operations_review(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V84_STRATEGIC_REVIEW_AREAS, states, ready_states={"reviewed", "healthy", "accepted_gap"})
    result = {"reviewState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "trafficSeparated": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v84_reliability_data_quality_release_scale_review(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V84_RELIABILITY_SCALE_AREAS, states, ready_states={"reviewed", "healthy", "accepted_gap"})
    result = {"reviewState": "ready" if not blockers else "blocked", "areas": rows, "blockers": blockers, "scaleBlockersSeparated": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v84_market_expansion_enterprise_localization_options(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V84_MARKET_ENTERPRISE_AREAS, states, ready_states={"evaluated", "approved", "blocked", "accepted_gap"})
    result = {"optionState": "evaluated" if not blockers else "blocked", "areas": rows, "blockers": blockers, "unsupportedExpansionBlocked": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v84_ai_autonomy_growth_governance_options(states: dict[str, str] | None = None) -> dict[str, Any]:
    rows, blockers = _v7_contract_rows(V84_AI_GROWTH_GOVERNANCE_AREAS, states, ready_states={"evaluated", "approved", "blocked", "accepted_gap"})
    result = {"optionState": "evaluated" if not blockers else "blocked", "areas": rows, "blockers": blockers, "aiAutonomyBlockedByDefault": True, "paidMarketingScaleBlockedByDefault": True, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def v84_strategic_scale_v9_decision_gate(
    *,
    strategic_review: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    market_options: dict[str, Any] | None = None,
    governance_options: dict[str, Any] | None = None,
    scale_approved: bool = False,
    market_expansion_approved: bool = False,
    enterprise_ready: bool = False,
    recommend_v9: bool = False,
    rollback_required: bool = False,
) -> dict[str, Any]:
    strategic_review = strategic_review or v84_strategic_product_business_operations_review()
    reliability = reliability or v84_reliability_data_quality_release_scale_review()
    market_options = market_options or v84_market_expansion_enterprise_localization_options()
    governance_options = governance_options or v84_ai_autonomy_growth_governance_options()
    blockers = _unique(
        [
            *[f"strategy:{blocker}" for blocker in strategic_review.get("blockers", [])],
            *[f"reliability:{blocker}" for blocker in reliability.get("blockers", [])],
            *[f"market:{blocker}" for blocker in market_options.get("blockers", [])],
            *[f"governance:{blocker}" for blocker in governance_options.get("blockers", [])],
        ]
    )
    if rollback_required:
        decision = "rollback"
    elif blockers:
        decision = "remediation"
    elif market_expansion_approved:
        decision = "market_expansion"
    elif enterprise_ready:
        decision = "enterprise_readiness"
    elif recommend_v9:
        decision = "v9_focus"
    elif scale_approved:
        decision = "scale_growth"
    else:
        decision = "hold"
    result = {"decision": decision, "blockers": blockers, "v9Recommended": decision == "v9_focus", "paidMarketingScaleApproved": False, "aiAutonomyApproved": False, "privacy": _privacy_contract()}
    assert_pilot_evidence_safe(result)
    return result


def launch_scope_audit(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    readiness = [_normalize_item(item) for item in (items or [entry.row() for entry in DEFAULT_READINESS])]
    result = {
        "options": [
            {
                "option": "internal_hold",
                "rolloutSize": 0,
                "recommendation": "available if provider blockers remain unresolved",
                "successCriteria": ["no production user exposure"],
            },
            {
                "option": "limited_parent_student_pilot",
                "rolloutSize": "5-10 families",
                "recommendation": "recommended only after payment, notification, support CRM, and BI/APM blockers are cleared or explicitly disabled",
                "successCriteria": ["verified onboarding", "one simple conversation", "support response path", "rollback tested"],
            },
            {
                "option": "public_launch",
                "rolloutSize": "unbounded",
                "recommendation": "not recommended",
                "successCriteria": ["all critical providers live_ready", "support staffing confirmed", "mobile store path ready"],
            },
        ],
        "recommendedScope": "limited_parent_student_pilot",
        "excludedFeatures": ["broad public signup", "paid marketing", "unsupervised AI teaching", "unapproved provider writes"],
        "readiness": readiness,
        "stateCounts": _count_by(readiness, "state"),
        "launchBlockers": [row for row in readiness if row["state"] in {"blocked", "failed"}],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(result)
    return result


def cohort_onboarding_plan() -> dict[str, Any]:
    plan = {
        "cohort": {
            "size": "5-10 families",
            "roles": ["parent", "student", "admin", "support_operator"],
            "entryCriteria": ["verified parent email", "linked child account", "support contact acknowledged"],
            "exitCriteria": ["pilot completed", "rollback requested", "safety/support blocker"],
        },
        "onboardingChecklist": [
            "account_verification",
            "entitlement_grant",
            "child_binding",
            "mobile_install_or_web_access",
            "notification_preference_review",
            "initial_curriculum_placement",
            "first_simple_conversation",
        ],
        "consentAndComms": {
            "privacyNotice": "pilot scope, data handling, and support path explained before activation",
            "supportHours": "business-hours support with incident escalation owner",
            "billingExpectation": "no broad paid rollout until payment provider blockers are cleared",
            "rollbackCommunication": "prepared before activation",
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(plan)
    return plan


def launch_controls_monitoring() -> dict[str, Any]:
    controls = {
        "rolloutFlags": ["pilot_enabled", "provider_writes_enabled", "ai_autonomy_disabled", "payment_live_enabled"],
        "stagedEnablement": ["admin_fixture", "staff_family", "5_family_pilot", "10_family_cap"],
        "freezeAndRollback": {
            "backend": "rollback last Lambda/CDK release",
            "frontend": "rollback static deployment",
            "mobile": "halt phased rollout or keep previous build channel",
            "providers": "disable provider writes and surface blocker states",
            "scheduledJobs": "pause schedules and replay safe jobs only",
        },
        "dashboard": [
            "auth",
            "billing",
            "usage_quota",
            "ai",
            "notifications",
            "support",
            "mobile",
            "provider_blockers",
            "incident_state",
        ],
        "alertRouting": {
            "launchRoomOwner": "operations",
            "backendOwner": "backend",
            "mobileOwner": "mobile",
            "supportOwner": "support",
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(controls)
    return controls


def pilot_acceptance_metrics() -> dict[str, Any]:
    metrics = {
        "successMetrics": [
            "activation_rate",
            "verified_accounts",
            "paid_or_entitled_access",
            "question_practice_usage",
            "teacher_help_response",
            "ai_quality_review",
            "notification_delivery_visibility",
            "support_load",
            "mobile_stability",
            "parent_student_satisfaction",
        ],
        "issueTaxonomy": [
            "product_bug",
            "provider_blocker",
            "content_issue",
            "ai_quality_issue",
            "support_process_issue",
            "billing_account_issue",
            "training_onboarding_issue",
        ],
        "feedbackCapture": ["parent", "student", "teacher", "admin", "support_operator"],
        "decisionCriteria": {
            "expand": "success metrics met and no unresolved critical blockers",
            "hold": "provider/support/stability blockers remain but product core is useful",
            "rollback": "safety, privacy, billing, or stability incident",
            "hardenMore": "restore/monitoring/support evidence remains insufficient",
        },
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(metrics)
    return metrics


def go_no_go_decision(
    *,
    owner: str = "operations",
    timestamp: str = "2026-07-06T00:00:00Z",
    accepted_risks: list[str] | None = None,
) -> dict[str, Any]:
    audit = launch_scope_audit()
    blockers = [item["component"] for item in audit["launchBlockers"]]
    decision = {
        "decision": "conditional_go_for_limited_pilot_readiness",
        "owner": owner,
        "timestamp": timestamp,
        "blockers": blockers,
        "acceptedRisks": accepted_risks or ["local-only readiness evidence must be rechecked before activating real users"],
        "notApproved": ["broad_public_launch", "paid_marketing", "unapproved_provider_writes"],
        "requiredBeforeActivation": [
            "clear_or_disable_payment_blocker",
            "clear_or_disable_notification_blocker",
            "clear_support_crm_blocker",
            "confirm_support_staffing",
            "run launch-room checklist",
        ],
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(decision)
    return decision


def release_gate_evidence() -> dict[str, Any]:
    evidence = {
        "releaseState": RELEASE_STATE,
        "readinessAudit": launch_scope_audit(),
        "cohortPlan": cohort_onboarding_plan(),
        "launchControls": launch_controls_monitoring(),
        "acceptanceMetrics": pilot_acceptance_metrics(),
        "goNoGo": go_no_go_decision(),
        "v5_25Recommendation": "execute the approved limited pilot only after clearing required activation blockers; otherwise hold and harden",
        "privacy": _privacy_contract(),
    }
    assert_pilot_evidence_safe(evidence)
    return evidence


def assert_pilot_evidence_safe(payload: dict[str, Any]) -> None:
    _assert_no_forbidden_keys(payload)
    hits = release_evidence_service.private_marker_hits(payload)
    if hits:
        raise ValueError(f"pilot readiness evidence contains private markers: {hits}")


def _normalize_item(item: dict[str, Any]) -> dict[str, str]:
    state = str(item.get("state") or "blocked")
    if state not in READINESS_STATES:
        state = "blocked"
    return {
        "component": str(item.get("component") or "unknown"),
        "state": state,
        "owner": str(item.get("owner") or "unknown"),
        "blocker": str(item.get("blocker") or "unknown"),
        "evidence": str(item.get("evidence") or "none"),
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _pilot_dependency_classification(item: dict[str, str], disabled_components: set[str]) -> str:
    component = item["component"]
    if component in disabled_components:
        return "explicitly_disabled_for_pilot"
    if component not in PILOT_REQUIRED_COMPONENTS:
        return "optional"
    if item["state"] in {"live_ready", "read_only_verified"}:
        return "cleared"
    return "blocked"


def _pilot_dependency_action(item: dict[str, str], classification: str) -> str:
    if classification == "cleared":
        return "record owner, timestamp, request id, and rollback control"
    if classification == "explicitly_disabled_for_pilot":
        return "confirm disabled-feature copy and operator support path"
    if classification == "optional":
        return "monitor only"
    return f"clear or explicitly disable {item['component']} before pilot start"


def _pilot_dependency_impact(component: str, classification: str) -> str:
    if classification == "cleared":
        return "pilot may proceed for this dependency"
    if classification == "explicitly_disabled_for_pilot":
        return "pilot may proceed only with the feature visibly disabled"
    impacts = {
        "payment": "paid subscription and entitlement activation cannot be trusted",
        "notifications": "push or email messages cannot be relied on for pilot operations",
        "support_crm": "external support handoff cannot be relied on",
        "bi_apm": "operator dashboards and alerting are incomplete",
        "mobile": "native distribution path is not approved for pilot users",
        "data_lifecycle": "restore evidence is insufficient for real-user exposure",
        "incident_operations": "launch-room escalation has not been rehearsed live",
    }
    return impacts.get(component, "required pilot evidence is incomplete")


def _fallback_or_disable_option(component: str) -> str:
    options = {
        "payment": "disable paid checkout and use approved manual entitlement for pilot only",
        "notifications": "disable outbound provider sends and use in-app/manual communication",
        "support_crm": "disable external CRM write and use internal support queue",
        "bi_apm": "use local release evidence and daily manual dashboard until live BI/APM is approved",
        "mobile": "limit pilot to approved internal build or web access",
        "data_lifecycle": "hold real-user pilot until production restore/tabletop evidence is recorded",
        "incident_operations": "hold real-user pilot until launch-room rehearsal is complete",
    }
    return options.get(component, "hold or narrow pilot scope until evidence is ready")


def _operator_impact(component: str, state: str) -> str:
    if state == "launch_blocking":
        return f"{component} owner must clear blocker before enablement"
    if state == "explicitly_disabled_for_pilot":
        return f"{component} remains visible as disabled with support fallback"
    return f"{component} evidence must be reviewed during launch-room checks"


def _participant_copy(component: str, state: str) -> str:
    if state == "explicitly_disabled_for_pilot":
        return f"{component} is not available during the limited pilot; support will provide a fallback."
    if state == "launch_blocking":
        return f"{component} is not ready; pilot access is held until this is resolved."
    return f"{component} is available for the limited pilot."


def _provider_rollback_control(component: str) -> str:
    controls = {
        "payment": "disable payment_live_enabled and stop checkout entry points",
        "notifications": "disable provider_writes_enabled and keep in-app state",
        "support_crm": "disable CRM destination and keep internal queue",
        "bi_apm": "fall back to local release evidence",
        "mobile": "halt rollout channel or retain previous internal build",
        "data_lifecycle": "freeze pilot and run restore owner escalation",
        "incident_operations": "pause cohort enablement and enter launch-room incident mode",
    }
    return controls.get(component, "disable pilot flag and escalate to owner")


def _live_rollback_control(component: str) -> str:
    controls = {
        "payment": "disable live checkout and revoke pilot billing rollout",
        "notifications": "disable outbound provider delivery and use manual support copy",
        "support_crm": "disable CRM destination and keep internal queue ownership",
        "bi_apm": "fall back to daily local evidence and manual launch-room review",
        "mobile_testflight": "halt pilot build channel and return users to approved access path",
    }
    return controls.get(component, "pause live pilot enablement and escalate to owner")


def _pilot_signal_action(signal: str, state: str) -> str:
    if state in {"passed", "healthy", "met"}:
        return "continue monitoring"
    if state in {"failed", "blocked"}:
        return f"open remediation for {signal}"
    return f"collect {signal} evidence before expansion"


def _blocker_owner(blocker: str) -> str:
    if blocker.startswith("approval_missing:"):
        return blocker.removeprefix("approval_missing:")
    if blocker.startswith("dependency_not_ready:"):
        return "operations"
    if blocker.startswith("provider:"):
        return "provider_owner"
    if blocker.startswith("operations:"):
        return "incident_owner"
    return "operations"


def _blocker_action(blocker: str) -> str:
    if blocker.startswith("approval_missing:"):
        return "record owner approval or hold pilot scope"
    if blocker.startswith("dependency_not_ready:"):
        dependency = blocker.removeprefix("dependency_not_ready:")
        return f"clear, disable, or explicitly hold {dependency}"
    if blocker.startswith("provider:"):
        dependency = blocker.removeprefix("provider:")
        return f"verify or disable {dependency} before start"
    if blocker.startswith("operations:"):
        dependency = blocker.removeprefix("operations:")
        return f"record operations evidence for {dependency}"
    return "assign owner and close blocker before start"


def _operations_area_owner(area: str) -> str:
    owners = {
        "incident_review": "incident_owner",
        "data_quality": "backend",
        "queue_health": "backend",
        "admin_workflows": "operations",
        "teacher_dispatch": "teacher_operations",
        "support_handoff": "support",
        "observability": "backend",
        "release_rollback": "release_manager",
    }
    return owners.get(area, "operations")


def _v6_access_owner(path: str) -> str:
    owners = {
        "admin": "operations",
        "parent": "support",
        "student": "support",
        "teacher_support": "teacher_operations",
        "provider": "provider_owner",
        "mobile": "mobile_release_owner",
        "monitoring": "backend",
        "deployment": "release_manager",
    }
    return owners.get(path, "operations")


def _v6_access_next_action(path: str, state: str) -> str:
    if state in {"available", "not_required"}:
        return "record owner, timestamp, and request/build id where applicable"
    if state == "disabled_for_pilot":
        return "record disabled-pilot copy, fallback, and owner approval"
    return f"collect approved {path} evidence or mark explicitly disabled for pilot"


def _v6_account_surface_owner(surface: str) -> str:
    if surface in {"checkout_paywall", "paid_access", "subscription_state"}:
        return "finance_billing_owner"
    if surface in {"usage_ledger", "quota_display", "entitlement_activation"}:
        return "backend"
    if surface == "admin_support_explanations":
        return "support"
    return "account_owner"


def _v6_surface_next_action(surface: str, state: str) -> str:
    if state in {"passed", "read_only_verified"}:
        return "retain request id, account alias, timestamp, and observed state"
    if state == "disabled_for_pilot":
        return "publish support-safe disabled-state explanation"
    return f"run approved smoke or document blocker for {surface}"


def _v6_provider_surface_owner(surface: str) -> str:
    if surface.startswith("support"):
        return "support"
    if surface.startswith("teacher"):
        return "teacher_operations"
    if "mobile" in surface:
        return "mobile_release_owner"
    if surface in {"bi_apm", "ai_provider"}:
        return "backend"
    return "provider_owner"


def _v6_provider_fallback(surface: str) -> str:
    fallbacks = {
        "email_notifications": "manual email or in-app-only communication",
        "push_notifications": "disable push and use in-app/manual support communication",
        "realtime_notifications": "fall back to refreshable notification center",
        "support_crm_handoff": "use internal support queue",
        "support_queue": "manual support owner assignment",
        "teacher_dispatch_sla": "manual teacher owner assignment",
        "mobile_testflight_install": "use approved web path or internal build only",
        "payment_provider": "manual pilot entitlement without live checkout",
        "bi_apm": "daily manual dashboard review",
        "ai_provider": "reviewed deterministic fallback or teacher-supervised flow",
    }
    return fallbacks.get(surface, "hold pilot dependency until evidence is current")


def _v6_provider_rollback(surface: str) -> str:
    if "notification" in surface:
        return "disable outbound delivery and keep support-visible state"
    if surface == "payment_provider":
        return "disable live checkout and revert to manual entitlement"
    if surface == "mobile_testflight_install":
        return "halt pilot build channel"
    return "disable pilot dependency and escalate to owner"


def _v6_launch_packet_owner(area: str) -> str:
    owners = {
        "cohort_scope": "product_owner",
        "account_aliases": "support",
        "communication_plan": "support",
        "consent_state": "operations",
        "support_staffing": "support",
        "teacher_owner": "teacher_operations",
        "launch_room": "incident_owner",
        "dashboards": "backend",
        "rollback_authority": "decision_owner",
        "pause_criteria": "incident_owner",
    }
    return owners.get(area, "operations")


def _v6_remediation_owner(surface: str) -> str:
    if surface in {"activation", "usage", "entitlement", "learning"}:
        return "backend"
    if surface in {"support", "notification"}:
        return "support"
    if surface == "teacher":
        return "teacher_operations"
    if surface == "mobile":
        return "mobile_release_owner"
    return "operations"


def _v6_remediation_outcome(surface: str) -> str:
    outcomes = {
        "activation": "pilot user can reach an activated account state",
        "support": "support can see blocker and next action",
        "teacher": "teacher/support owner can respond inside SLA",
        "notification": "message path is delivered or visibly disabled",
        "usage": "usage event is recorded and visible",
        "entitlement": "paid/manual entitlement is understandable",
        "mobile": "approved mobile or web access path is clear",
        "learning": "student can complete first useful learning action",
    }
    return outcomes.get(surface, "pilot-critical behavior is remediated")


def _v6_account_copy(surface: str, state: str) -> str:
    if state == "fixed":
        return f"{surface} is available."
    if state == "explicitly_deferred":
        return f"{surface} is unavailable during pilot; support has the fallback."
    return f"{surface} is blocked pending remediation."


def _v6_entitlement_support_owner(surface: str) -> str:
    if surface in {"paid_entitlement", "checkout_paywall", "subscription_state"}:
        return "finance_billing_owner"
    if surface in {"usage_ledger", "quota_reconciliation"}:
        return "backend"
    if surface in {"notification_delivery", "support_handoff"}:
        return "support"
    if surface == "teacher_dispatch_sla":
        return "teacher_operations"
    return "operations"


def _v6_learning_mobile_owner(surface: str) -> str:
    if surface == "mobile_install_access":
        return "mobile_release_owner"
    if surface in {"ai_help_flow", "curriculum_access"}:
        return "learning_quality_owner"
    return "product_owner"


def _v65_access_owner(path: str) -> str:
    owners = {
        "admin": "operations",
        "parent": "product_owner",
        "student": "product_owner",
        "teacher_support": "teacher_operations",
        "provider": "provider_owner",
        "mobile": "mobile_release_owner",
        "monitoring": "backend",
        "deploy": "release_owner",
        "support": "support_owner",
    }
    return owners.get(path, "operations")


def _v65_account_owner(surface: str) -> str:
    if surface in {"paid_access", "checkout_paywall", "entitlement_activation", "subscription_state"}:
        return "finance_billing_owner"
    if surface in {"usage_ledger", "quota_display"}:
        return "backend"
    if surface in {"admin_support_visibility", "support_explanations"}:
        return "support_owner"
    return "account_owner"


def _v65_account_fallback(surface: str) -> str:
    fallbacks = {
        "login_code_passwordless_policy": "disable passwordless pilot path and use verified email login",
        "checkout_paywall": "manual pilot entitlement with parent-facing disabled checkout copy",
        "usage_ledger": "pause learning actions that cannot record support-visible usage",
        "quota_display": "support-visible manual quota explanation",
        "support_explanations": "manual owner-authored support note",
    }
    return fallbacks.get(surface, f"block pilot start until {surface} evidence is current")


def _v65_provider_learning_owner(surface: str) -> str:
    if surface in {"notification_delivery", "support_handoff"}:
        return "support_owner"
    if surface == "teacher_dispatch_sla":
        return "teacher_operations"
    if surface == "mobile_testflight_install":
        return "mobile_release_owner"
    if surface in {"ai_provider_health", "provider_health"}:
        return "provider_owner"
    return "learning_quality_owner"


def _v65_provider_learning_fallback(surface: str) -> str:
    fallbacks = {
        "notification_delivery": "disable outbound notifications and use manual support communication",
        "support_handoff": "use internal support queue with manual owner assignment",
        "teacher_dispatch_sla": "manual teacher owner assignment",
        "mobile_testflight_install": "use approved web path or hold mobile access",
        "ai_provider_health": "teacher-reviewed deterministic fallback",
        "provider_health": "disable provider-dependent path until owner approves",
        "first_learning_action": "route to reviewed static learning action",
        "learning_path": "hold cohort start until first learning path is verified",
    }
    return fallbacks.get(surface, "hold or disable for pilot with support copy")


def _v65_launch_packet_owner(area: str) -> str:
    owners = {
        "account_aliases": "support_owner",
        "communication_plan": "support_owner",
        "consent_state": "operations",
        "support_staffing": "support_owner",
        "teacher_owner": "teacher_operations",
        "launch_room": "incident_owner",
        "dashboards": "backend",
        "rollback_authority": "decision_owner",
        "pause_criteria": "incident_owner",
        "support_macros": "support_owner",
        "known_disabled_features": "product_owner",
        "day_one_operating_plan": "operations",
    }
    return owners.get(area, "operations")


def _v65_blocker(surface: str, category: str) -> dict[str, str]:
    return {
        "surface": surface,
        "category": category,
        "owner": _v65_account_owner(surface),
        "severity": "start_blocking",
        "userImpact": f"{surface} is not proven for the approved pilot",
        "fallback": _v65_account_fallback(surface),
        "nextAction": f"capture current production evidence or disable {surface} for pilot",
    }


def _v66_signal_owner(signal: str) -> str:
    owners = {
        "activation": "product_owner",
        "support": "support_owner",
        "teacher": "teacher_operations",
        "billing": "finance_billing_owner",
        "notification": "support_owner",
        "mobile": "mobile_release_owner",
        "usage": "backend",
        "learning": "learning_quality_owner",
    }
    return owners.get(signal, "operations")


def _v66_fix_board_row(blocker: str) -> dict[str, str]:
    owner = _v66_signal_owner(blocker.split(":", 1)[0])
    return {
        "blocker": blocker,
        "owner": owner,
        "severity": "start_blocking",
        "fixPath": f"close or explicitly disable {blocker}",
        "testPath": "focused production-pilot contract test plus owner evidence",
        "releasePath": "small reversible release with rollback note",
        "targetOutcome": "rerun v6.5 start gate with current evidence",
    }


def _v66_support_owner(surface: str) -> str:
    if surface in {"support_handoff", "support_queue", "escalation", "incident_handling"}:
        return "support_owner"
    if surface == "teacher_dispatch_sla":
        return "teacher_operations"
    if surface == "mobile_access_install":
        return "mobile_release_owner"
    return "support_owner"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _privacy_contract() -> dict[str, Any]:
    return {
        "metadataOnly": True,
        "excludedFields": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        "rawProviderPayloadsIncluded": False,
        "rawStudentContentIncluded": False,
        "privateObjectKeysIncluded": False,
    }


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_FIELDS:
                raise ValueError(f"forbidden pilot evidence field: {key}")
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(child)
