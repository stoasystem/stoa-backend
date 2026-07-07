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


def _pilot_signal_action(signal: str, state: str) -> str:
    if state in {"passed", "healthy", "met"}:
        return "continue monitoring"
    if state in {"failed", "blocked"}:
        return f"open remediation for {signal}"
    return f"collect {signal} evidence before expansion"


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
