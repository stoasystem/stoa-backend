import pytest

from stoa.services import production_pilot_service


def test_launch_scope_audit_compares_options_and_records_blockers():
    audit = production_pilot_service.launch_scope_audit()
    options = {item["option"] for item in audit["options"]}
    assert {"internal_hold", "limited_parent_student_pilot", "public_launch"}.issubset(options)
    components = {item["component"] for item in audit["readiness"]}
    assert production_pilot_service.PILOT_COMPONENTS.issubset(components)
    assert audit["recommendedScope"] == "limited_parent_student_pilot"
    assert audit["launchBlockers"]
    assert "broad public signup" in audit["excludedFeatures"]


def test_cohort_onboarding_plan_covers_consent_support_and_setup():
    plan = production_pilot_service.cohort_onboarding_plan()
    assert plan["cohort"]["size"] == "5-10 families"
    assert "account_verification" in plan["onboardingChecklist"]
    assert "entitlement_grant" in plan["onboardingChecklist"]
    assert "rollbackCommunication" in plan["consentAndComms"]
    assert "supportHours" in plan["consentAndComms"]


def test_launch_controls_monitoring_covers_flags_dashboard_and_rollback():
    controls = production_pilot_service.launch_controls_monitoring()
    assert "pilot_enabled" in controls["rolloutFlags"]
    assert "provider_writes_enabled" in controls["rolloutFlags"]
    assert {"backend", "frontend", "mobile", "providers", "scheduledJobs"}.issubset(controls["freezeAndRollback"])
    assert {"auth", "billing", "usage_quota", "ai", "notifications", "support", "mobile", "provider_blockers", "incident_state"}.issubset(set(controls["dashboard"]))


def test_pilot_acceptance_metrics_define_success_taxonomy_and_decisions():
    metrics = production_pilot_service.pilot_acceptance_metrics()
    assert "activation_rate" in metrics["successMetrics"]
    assert "teacher_help_response" in metrics["successMetrics"]
    assert "provider_blocker" in metrics["issueTaxonomy"]
    assert {"expand", "hold", "rollback", "hardenMore"}.issubset(metrics["decisionCriteria"])
    assert {"parent", "student", "admin", "support_operator"}.issubset(set(metrics["feedbackCapture"]))


def test_go_no_go_and_release_gate_are_conditional_not_public_launch():
    decision = production_pilot_service.go_no_go_decision(owner="ops", timestamp="2026-07-06T12:00:00Z")
    assert decision["decision"] == "conditional_go_for_limited_pilot_readiness"
    assert "broad_public_launch" in decision["notApproved"]
    assert "clear_support_crm_blocker" in decision["requiredBeforeActivation"]
    evidence = production_pilot_service.release_gate_evidence()
    assert evidence["releaseState"] == "limited-pilot-ready-local-contracts"
    assert "v5_25Recommendation" in evidence


def test_pilot_evidence_rejects_private_fields():
    with pytest.raises(ValueError):
        production_pilot_service.assert_pilot_evidence_safe({"prompt": "not allowed"})
    with pytest.raises(ValueError):
        production_pilot_service.assert_pilot_evidence_safe({"nested": {"s3_key": "private"}})


def test_activation_blocker_audit_classifies_required_blockers_and_disablements():
    audit = production_pilot_service.activation_blocker_reality_audit(
        disabled_components={"payment", "notifications"}
    )

    states = {item["component"]: item["pilotClassification"] for item in audit["dependencies"]}
    assert states["payment"] == "explicitly_disabled_for_pilot"
    assert states["notifications"] == "explicitly_disabled_for_pilot"
    assert states["support_crm"] == "blocked"
    assert audit["realUserStartRecommended"] is False


def test_safe_start_gate_holds_by_default_and_can_start_when_blockers_disabled():
    default_gate = production_pilot_service.pilot_safe_start_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["safeToStart"] is False
    assert "payment" in default_gate["blockers"]

    disabled = {
        "mobile",
        "payment",
        "notifications",
        "support_crm",
        "bi_apm",
        "data_lifecycle",
        "incident_operations",
    }
    start_gate = production_pilot_service.pilot_safe_start_gate(disabled_components=disabled)
    assert start_gate["decision"] == "start_limited_pilot"
    assert start_gate["safeToStart"] is True


def test_pilot_execution_is_blocked_until_safe_start_gate_allows_it():
    enablement = production_pilot_service.pilot_cohort_enablement_first_use_tracking()
    assert enablement["executionState"] == "blocked_by_safe_start_gate"
    assert enablement["cohortEnablement"]["customerMutationAllowed"] is False

    allowed = production_pilot_service.pilot_cohort_enablement_first_use_tracking(
        safe_start_gate={"decision": "start_limited_pilot", "safeToStart": True}
    )
    assert allowed["executionState"] == "ready_for_controlled_enablement"
    assert allowed["cohortEnablement"]["customerMutationAllowed"] is True


def test_pilot_outcome_and_remediation_gates_preserve_expansion_controls():
    outcome = production_pilot_service.pilot_outcome_decision_gate()
    assert outcome["decision"] == "pause"
    assert outcome["expansionBlocked"] is True

    remediation = production_pilot_service.remediation_release_gate()
    assert remediation["decision"] == "another_remediation_cycle"

    accepted = production_pilot_service.remediation_release_gate(
        accepted_blockers=["safe_start_gate_blocked"]
    )
    assert accepted["decision"] == "ready_for_controlled_expansion"


def test_controlled_expansion_and_public_launch_gates_require_evidence_and_approval():
    expansion = production_pilot_service.controlled_expansion_gate(
        expansion_metrics_met=True,
        support_capacity_met=True,
    )
    assert expansion["decision"] == "prepare_public_launch_readiness"
    assert expansion["publicLaunchBlocked"] is False

    launch_gate = production_pilot_service.public_launch_readiness_gate(expansion_gate=expansion)
    assert launch_gate["decision"] == "continue_controlled_expansion"

    approved = production_pilot_service.public_launch_readiness_gate(
        expansion_gate=expansion,
        final_approval=True,
    )
    assert approved["decision"] == "public_launch"


def test_launch_readiness_contracts_cover_self_serve_growth_support_and_app_store():
    onboarding = production_pilot_service.self_serve_onboarding_account_conversion()
    assert production_pilot_service.LAUNCH_SURFACES.issubset(set(onboarding["surfaces"]))
    assert onboarding["noDemoFallback"] is True

    growth = production_pilot_service.pricing_packaging_growth_lifecycle_readiness()
    assert "trial_conversion" in growth["growthLoops"]
    assert growth["controls"]["supportCapacityGateRequired"] is True

    support = production_pilot_service.public_support_knowledge_base_launch_communications()
    assert "known_limitations" in support["communications"]

    controls = production_pilot_service.app_store_public_release_production_launch_controls()
    assert "revenue" in controls["dashboard"]
