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
