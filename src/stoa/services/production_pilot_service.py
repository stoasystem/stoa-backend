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
        "channels": ["parent", "student", "teacher_tutor", "admin", "support_operator"],
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
        "excludedFeatures": ["broad public signup", "paid marketing", "unsupervised AI tutoring", "unapproved provider writes"],
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
        "feedbackCapture": ["parent", "student", "teacher_tutor", "admin", "support_operator"],
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
