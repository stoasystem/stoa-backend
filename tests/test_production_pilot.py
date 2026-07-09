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


def test_live_approval_and_provider_evidence_block_without_owner_signoff():
    approval = production_pilot_service.live_approval_ownership_audit()
    assert approval["approvalState"] == "blocked"
    assert approval["realUserActionAllowed"] is False
    assert any(item.startswith("approval_missing:") for item in approval["blockers"])

    provider = production_pilot_service.live_provider_mobile_activation_evidence()
    assert provider["activationState"] == "blocked"
    assert "payment" in provider["blockers"]


def test_live_safe_start_gate_can_start_only_with_complete_live_evidence():
    default_gate = production_pilot_service.live_pilot_safe_start_gate_execution()
    assert default_gate["decision"] == "hold"
    assert default_gate["v5_31Allowed"] is False

    approvals = {role: True for role in production_pilot_service.LIVE_APPROVAL_ROLES}
    dependency_states = {
        dependency: "approved" for dependency in production_pilot_service.LIVE_ACTIVATION_DEPENDENCIES
    }
    approval = production_pilot_service.live_approval_ownership_audit(
        approvals=approvals,
        dependency_states=dependency_states,
    )
    provider = production_pilot_service.live_provider_mobile_activation_evidence(
        evidence_states={
            "payment": "live_verified",
            "notifications": "live_verified",
            "support_crm": "read_only_verified",
            "bi_apm": "read_only_verified",
            "mobile_testflight": "live_verified",
        }
    )
    operations = production_pilot_service.production_restore_tabletop_launch_room_evidence(
        restore_state="approved",
        tabletop_state="approved",
        launch_room_state="recorded",
    )
    start_gate = production_pilot_service.live_pilot_safe_start_gate_execution(
        approval=approval,
        provider_evidence=provider,
        operations_evidence=operations,
    )
    assert start_gate["decision"] == "start_limited_pilot"
    assert start_gate["safeToStart"] is True


def test_real_pilot_execution_stays_blocked_until_live_gate_and_users_exist():
    blocked = production_pilot_service.live_cohort_enablement_onboarding_operations()
    assert blocked["executionState"] == "blocked_by_live_gate"
    assert blocked["customerMutationAllowed"] is False

    ready = production_pilot_service.live_cohort_enablement_onboarding_operations(
        live_gate={"safeToStart": True},
        approved_user_count=5,
    )
    assert ready["executionState"] == "ready"
    assert ready["customerMutationAllowed"] is True


def test_live_pilot_decision_and_remediation_gates_preserve_expansion_controls():
    decision = production_pilot_service.live_pilot_decision_gate()
    assert decision["decision"] == "pause"
    assert decision["expansionBlocked"] is True

    remediation = production_pilot_service.live_remediation_gate()
    assert remediation["decision"] == "another_remediation_cycle"
    assert remediation["v5_33Allowed"] is False

    resolved = production_pilot_service.live_remediation_gate(blockers_resolved=True)
    assert resolved["decision"] == "expansion_ready"
    assert resolved["v5_33Allowed"] is True


def test_live_expansion_and_public_launch_execution_require_final_approval():
    expansion = production_pilot_service.controlled_expansion_decision_gate(
        metrics_met=True,
        support_capacity_met=True,
    )
    assert expansion["decision"] == "public_launch_prep"
    assert expansion["publicLaunchBlocked"] is False

    launch_plan = production_pilot_service.final_launch_approval_public_rollout_plan(
        expansion_gate=expansion
    )
    assert launch_plan["decision"] == "continued_controlled_expansion_or_hold"

    approved_launch = production_pilot_service.final_launch_approval_public_rollout_plan(
        final_approval=True,
        expansion_gate=expansion,
    )
    assert approved_launch["decision"] == "public_launch"

    monitoring = production_pilot_service.app_store_production_release_launch_monitoring(
        launch_plan=approved_launch
    )
    assert monitoring["monitoringState"] == "active"

    outcome = production_pilot_service.launch_outcome_next_strategy_gate(
        launch_plan=approved_launch,
        outcome_healthy=True,
    )
    assert outcome["decision"] == "scale"


def test_real_pilot_start_gate_requires_closed_blockers_and_dry_run():
    default_gate = production_pilot_service.real_pilot_start_decision_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["v5_36Allowed"] is False

    inventory = {"inventoryState": "ready", "gateDecision": "start_limited_pilot", "blockers": []}
    provider = {"closeoutState": "ready", "blockers": []}
    dry_run = {"dryRunState": "ready", "blockers": []}
    launch_room = {"readinessState": "ready", "blockers": []}
    start_gate = production_pilot_service.real_pilot_start_decision_gate(
        inventory=inventory,
        provider_closeout=provider,
        dry_run=dry_run,
        launch_room=launch_room,
    )
    assert start_gate["decision"] == "start_limited_pilot"
    assert start_gate["safeToStart"] is True


def test_v35_closeout_contracts_keep_real_writes_gated():
    inventory = production_pilot_service.real_pilot_blocker_inventory_owner_assignment()
    assert inventory["inventoryState"] == "blocked"
    assert inventory["ownerActionTable"]

    closeout = production_pilot_service.provider_or_disablement_activation_closeout(
        disabled_components={"payment", "notifications", "support_crm", "bi_apm", "mobile_testflight"}
    )
    assert closeout["closeoutState"] == "ready"
    assert closeout["disabledComponents"]

    dry_run = production_pilot_service.pilot_cohort_account_support_dry_run(
        live_gate={"safeToStart": True},
        approved_account_count=5,
        support_staffed=True,
    )
    assert dry_run["dryRunState"] == "ready"
    assert dry_run["customerMutationAllowed"] is False

    launch_room = production_pilot_service.launch_room_restore_incident_readiness_closeout(
        operations_evidence={
            "operationsState": "ready",
            "checks": {},
            "blockers": [],
            "incidentPolicy": {},
        }
    )
    assert launch_room["readinessState"] == "ready"
    assert launch_room["launchRoom"]["rollbackSupported"] is True


def test_live_pilot_operations_feedback_gate_controls_v37_progression():
    blocked = production_pilot_service.live_pilot_operations_feedback_capture()
    assert blocked["operationsState"] == "blocked_by_start_gate"
    assert blocked["customerMutationAllowed"] is False

    active = production_pilot_service.live_pilot_operations_feedback_capture(
        start_gate={"safeToStart": True},
        approved_user_count=5,
    )
    assert active["operationsState"] == "active"
    assert active["customerMutationAllowed"] is True

    decision = production_pilot_service.live_pilot_feedback_decision_gate()
    assert decision["decision"] == "hold"
    assert decision["v5_37Allowed"] is False

    healthy_signals = {signal: "passed" for signal in production_pilot_service.PILOT_OUTCOME_SIGNALS}
    ready = production_pilot_service.live_pilot_feedback_decision_gate(
        start_gate={"safeToStart": True},
        signals=healthy_signals,
        fixes_released=True,
    )
    assert ready["decision"] == "revenue_growth_candidate"
    assert ready["v5_37Allowed"] is True


def test_revenue_growth_gate_requires_reconciliation_and_capacity():
    default_gate = production_pilot_service.revenue_growth_decision_gate()
    assert default_gate["decision"] == "remediate"
    assert default_gate["v5_38Allowed"] is False

    revenue_states = {
        surface: "passed" for surface in production_pilot_service.REVENUE_GROWTH_SURFACES
    }
    revenue = production_pilot_service.revenue_conversion_checkout_completion(revenue_states)
    growth = production_pilot_service.self_serve_growth_lifecycle_completion(
        {
            "self_serve_onboarding": "passed",
            "lifecycle_messages": "passed",
            "referral_waitlist": "passed",
        },
        support_capacity_ready=True,
    )
    ready = production_pilot_service.revenue_growth_decision_gate(
        revenue=revenue,
        growth=growth,
        reconciliation_approved=True,
    )
    assert ready["decision"] == "controlled_growth_ready"
    assert ready["paidMarketingApproved"] is False


def test_learning_quality_gate_requires_outcome_and_ai_evidence():
    default_gate = production_pilot_service.learning_quality_decision_gate()
    assert default_gate["decision"] == "remediate"
    assert default_gate["v5_39Allowed"] is False

    states = {area: "passed" for area in production_pilot_service.LEARNING_QUALITY_AREAS}
    outcomes = production_pilot_service.learning_outcomes_curriculum_quality_scale(states)
    ai_quality = production_pilot_service.ai_quality_teacher_help_scale(
        evaluations_passed=True,
        teacher_capacity_ready=True,
    )
    ready = production_pilot_service.learning_quality_decision_gate(
        outcomes=outcomes,
        ai_quality=ai_quality,
    )
    assert ready["decision"] == "learning_quality_scale_ready"
    assert ready["v5_39Allowed"] is True


def test_platform_scale_gate_requires_reliability_internal_ops_and_release_discipline():
    default_gate = production_pilot_service.platform_scale_decision_gate()
    assert default_gate["decision"] == "operations_hardening_cycle"
    assert default_gate["expansionAllowed"] is False

    reliability_states = {
        area: "passed" for area in production_pilot_service.OPERATIONS_SCALE_AREAS
    }
    reliability = production_pilot_service.platform_reliability_operations_scale(
        reliability_states
    )
    internal_ops = production_pilot_service.internal_operations_admin_teacher_scale(
        {
            "account_operations": "passed",
            "teacher_dispatch": "passed",
            "support_handoff": "passed",
            "billing_fixes": "passed",
            "content_operations": "passed",
        },
        staffing_ready=True,
    )
    ready = production_pilot_service.platform_scale_decision_gate(
        reliability=reliability,
        internal_ops=internal_ops,
        release_discipline_ready=True,
    )
    assert ready["decision"] == "larger_expansion_ready"
    assert ready["expansionAllowed"] is True


def test_v6_real_evidence_inventory_blocks_until_access_and_credentials_are_ready():
    default_inventory = production_pilot_service.real_evidence_inventory_access_readiness()
    assert default_inventory["inventoryState"] == "blocked"
    assert "approved_credential_path" in default_inventory["blockers"]

    states = {
        path: "available"
        for path in production_pilot_service.V6_REAL_EVIDENCE_ACCESS_PATHS
    }
    ready = production_pilot_service.real_evidence_inventory_access_readiness(
        states,
        approved_credential_path=True,
    )
    assert ready["inventoryState"] == "ready"
    assert ready["blockers"] == []
    assert ready["evidencePolicy"]["productionMutationAllowed"] is False


def test_v6_account_payment_usage_smoke_is_metadata_only_and_fail_closed():
    default_smoke = production_pilot_service.account_payment_usage_verification_smoke()
    assert default_smoke["smokeState"] == "blocked"
    assert "usage_ledger" in default_smoke["blockers"]
    assert default_smoke["mutationPolicy"]["allowed"] is False

    states = {
        surface: "passed"
        for surface in production_pilot_service.V6_ACCOUNT_PAYMENT_USAGE_SURFACES
    }
    ready = production_pilot_service.account_payment_usage_verification_smoke(
        states,
        production_mutation_approved=True,
    )
    assert ready["smokeState"] == "ready"
    assert ready["mutationPolicy"]["scope"] == "pilot_safe_account_only"


def test_v6_notification_support_mobile_provider_evidence_allows_disablement():
    disabled = {
        "email_notifications",
        "push_notifications",
        "support_crm_handoff",
        "mobile_testflight_install",
        "payment_provider",
        "bi_apm",
        "ai_provider",
    }
    states = {
        "realtime_notifications": "passed",
        "support_queue": "passed",
        "teacher_dispatch_sla": "read_only_verified",
    }
    evidence = production_pilot_service.notification_support_mobile_provider_evidence(
        states,
        disabled_surfaces=disabled,
    )
    assert evidence["evidenceState"] == "ready"
    assert set(evidence["disabledSurfaces"]) == disabled
    assert all(row["fallback"] for row in evidence["surfaces"])


def test_v6_launch_packet_requires_packet_and_dry_run():
    default_packet = production_pilot_service.pilot_cohort_launch_packet_dry_run()
    assert default_packet["packetState"] == "blocked"
    assert "dry_run" in default_packet["blockers"]

    states = {
        area: "ready"
        for area in production_pilot_service.V6_PILOT_LAUNCH_PACKET_AREAS
    }
    ready = production_pilot_service.pilot_cohort_launch_packet_dry_run(
        states,
        dry_run_passed=True,
    )
    assert ready["packetState"] == "ready"
    assert "first_learning_action" in ready["dryRunCoverage"]


def test_v6_pilot_start_gate_holds_by_default_and_can_start_with_complete_evidence():
    default_gate = production_pilot_service.v6_pilot_start_or_blocker_decision_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["v6_1Allowed"] is False

    inventory = {"inventoryState": "ready", "blockers": []}
    account_smoke = {"smokeState": "ready", "blockers": []}
    provider_evidence = {"evidenceState": "ready", "blockers": []}
    launch_packet = {"packetState": "ready", "blockers": []}
    start = production_pilot_service.v6_pilot_start_or_blocker_decision_gate(
        inventory=inventory,
        account_smoke=account_smoke,
        provider_evidence=provider_evidence,
        launch_packet=launch_packet,
    )
    assert start["decision"] == "start_limited_pilot"
    assert start["safeToStart"] is True
    assert "public_launch" in start["outOfScope"]


def test_v61_kickoff_converts_hold_into_blocker_board():
    kickoff = production_pilot_service.cohort_day_one_operations_or_blocker_fix_kickoff()
    assert kickoff["kickoffState"] == "blocker_fix_board"
    assert kickoff["scope"] == "pilot_critical_product_behavior"
    assert kickoff["blockers"]

    observed = {surface: "healthy" for surface in production_pilot_service.V6_REMEDIATION_SURFACES}
    cohort = production_pilot_service.cohort_day_one_operations_or_blocker_fix_kickoff(
        v6_start_gate={"decision": "start_limited_pilot", "safeToStart": True, "blockers": []},
        observed_signals=observed,
    )
    assert cohort["kickoffState"] == "cohort_review"
    assert cohort["blockers"] == []


def test_v61_account_login_verification_role_fixes_require_resolution_or_deferral():
    default_fixes = production_pilot_service.account_login_verification_role_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "login" in default_fixes["blockers"]

    states = {
        surface: "fixed"
        for surface in production_pilot_service.V6_ACCOUNT_FIX_SURFACES
    }
    ready = production_pilot_service.account_login_verification_role_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["rolesCovered"] == ["parent", "student", "teacher_support", "admin"]
    assert all(row["privateCodesExposed"] is False for row in ready["surfaces"])


def test_v61_entitlement_usage_notification_support_fixes_allow_fallbacks():
    states = {
        surface: "fixed"
        for surface in production_pilot_service.V6_ENTITLEMENT_SUPPORT_FIX_SURFACES
    }
    states["notification_delivery"] = "disabled_for_pilot"
    states["support_handoff"] = "fallback_ready"
    ready = production_pilot_service.entitlement_usage_notification_support_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["blockers"] == []


def test_v61_learning_mobile_fixes_preserve_ai_and_curriculum_boundaries():
    states = {
        surface: "fixed"
        for surface in production_pilot_service.V6_LEARNING_MOBILE_FIX_SURFACES
    }
    ready = production_pilot_service.first_learning_action_mobile_friction_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["aiAutonomyBroadened"] is False
    assert ready["curriculumEditPermissionBroadened"] is False


def test_v61_release_gate_allows_v62_only_when_all_risks_are_controlled():
    default_gate = production_pilot_service.v6_1_remediation_release_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["v6_2Allowed"] is False

    kickoff = {"blockers": []}
    account = {"blockers": []}
    entitlement = {"blockers": []}
    learning = {"blockers": []}
    ready = production_pilot_service.v6_1_remediation_release_gate(
        kickoff=kickoff,
        account_fixes=account,
        entitlement_support_fixes=entitlement,
        learning_mobile_fixes=learning,
    )
    assert ready["decision"] == "continue_pilot"
    assert ready["v6_2Allowed"] is True


def test_v62_paid_conversion_flow_blocks_until_parent_states_are_complete():
    default_completion = production_pilot_service.paid_conversion_flow_completion()
    assert default_completion["completionState"] == "blocked"
    assert "checkout" in default_completion["blockers"]

    states = {
        surface: "working"
        for surface in production_pilot_service.V6_PAID_CONVERSION_SURFACES
    }
    states["refund"] = "support_ready"
    ready = production_pilot_service.paid_conversion_flow_completion(states)
    assert ready["completionState"] == "ready"
    assert ready["revenueImpactAuditable"] is True
    assert all(row["providerPayloadStored"] is False for row in ready["surfaces"])


def test_v62_usage_ledger_quota_reliability_covers_actions_and_reconciliation():
    default_reliability = production_pilot_service.usage_ledger_quota_reliability_completion()
    assert default_reliability["reliabilityState"] == "blocked"
    assert "quota_display" in default_reliability["blockers"]

    states = {
        surface: "covered"
        for surface in production_pilot_service.V6_USAGE_QUOTA_SURFACES
    }
    ready = production_pilot_service.usage_ledger_quota_reliability_completion(states)
    assert ready["reliabilityState"] == "ready"
    assert {"missing", "duplicate", "stale", "manual_adjusted"}.issubset(
        ready["reconciliationCovers"]
    )
    assert all(row["parentAdminExplanation"] for row in ready["surfaces"])


def test_v62_verification_recovery_completion_keeps_secrets_out_of_evidence():
    default_completion = (
        production_pilot_service.verification_lifecycle_account_recovery_completion()
    )
    assert default_completion["completionState"] == "blocked"
    assert "email_verification" in default_completion["blockers"]

    states = {
        surface: "tested"
        for surface in production_pilot_service.V6_VERIFICATION_RECOVERY_SURFACES
    }
    ready = production_pilot_service.verification_lifecycle_account_recovery_completion(states)
    assert ready["completionState"] == "ready"
    assert ready["blockers"] == []
    assert all(row["privateMaterialExposed"] is False for row in ready["surfaces"])
    assert all(row["auditable"] for row in ready["surfaces"])


def test_v62_billing_support_lifecycle_messages_require_support_capacity():
    default_completion = production_pilot_service.billing_support_lifecycle_messaging_completion()
    assert default_completion["completionState"] == "blocked"
    assert "support_capacity" in default_completion["blockers"]

    states = {
        surface: "ready"
        for surface in production_pilot_service.V6_BILLING_LIFECYCLE_SURFACES
    }
    states["win_back"] = "not_approved"
    states["failed_payment"] = "disabled_for_pilot"
    ready = production_pilot_service.billing_support_lifecycle_messaging_completion(
        states,
        support_capacity_ready=True,
    )
    assert ready["completionState"] == "ready"
    assert ready["supportCapacityReady"] is True
    assert ready["blockers"] == []


def test_v62_revenue_reliability_gate_allows_v63_after_account_risks_close():
    default_gate = production_pilot_service.v6_2_revenue_reliability_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["v6_3Allowed"] is False
    assert any(blocker.startswith("paid:") for blocker in default_gate["blockers"])

    ready = production_pilot_service.v6_2_revenue_reliability_gate(
        paid_conversion={"blockers": []},
        usage_quota={"blockers": []},
        verification={"blockers": []},
        billing_lifecycle={"blockers": []},
    )
    assert ready["decision"] == "controlled_growth"
    assert ready["v6_3Allowed"] is True
    assert ready["learningRisksSeparated"] is True


def test_v63_learning_outcome_review_separates_learning_from_account_risks():
    default_review = production_pilot_service.learning_outcome_evidence_review()
    assert default_review["reviewState"] == "blocked"
    assert "completion" in default_review["blockers"]

    states = {
        signal: "reviewed"
        for signal in production_pilot_service.V6_LEARNING_EVIDENCE_SIGNALS
    }
    ready = production_pilot_service.learning_outcome_evidence_review(states)
    assert ready["reviewState"] == "ready"
    assert ready["accountPaymentNotificationOnboardingSeparated"] is True
    assert ready["rawPrivateLearningArtifactsIncluded"] is False
    assert all(row["supportSafe"] for row in ready["signals"])


def test_v63_curriculum_quality_fixes_require_authorized_workflow():
    default_fixes = production_pilot_service.curriculum_exercise_explanation_quality_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "authorized_content_workflow" in default_fixes["blockers"]

    states = {
        surface: "improved"
        for surface in production_pilot_service.V6_CURRICULUM_QUALITY_SURFACES
    }
    ready = production_pilot_service.curriculum_exercise_explanation_quality_fixes(
        states,
        authorized_content_workflow=True,
    )
    assert ready["fixState"] == "ready"
    assert ready["curriculumEditPermissionsBroadened"] is False
    assert all(row["specialOperatorOnly"] for row in ready["surfaces"])


def test_v63_ai_teacher_quality_fixes_require_evals_and_review():
    default_quality = production_pilot_service.ai_teacher_summary_practice_quality_fixes()
    assert default_quality["qualityState"] == "blocked"
    assert "evaluation_fixtures" in default_quality["blockers"]
    assert "teacher_review" in default_quality["blockers"]

    states = {
        surface: "covered"
        for surface in production_pilot_service.V6_AI_TEACHER_QUALITY_SURFACES
    }
    ready = production_pilot_service.ai_teacher_summary_practice_quality_fixes(
        states,
        evaluation_fixtures_updated=True,
        teacher_review_ready=True,
    )
    assert ready["qualityState"] == "ready"
    assert {"accept", "edit", "reject", "explain", "follow_up"}.issubset(
        ready["teacherReviewModes"]
    )
    assert ready["unreviewedAutonomyExpanded"] is False


def test_v63_adaptive_recommendation_parent_progress_clarity_is_explainable():
    default_clarity = production_pilot_service.adaptive_recommendation_parent_progress_clarity()
    assert default_clarity["clarityState"] == "blocked"
    assert "duplicate_suppression" in default_clarity["blockers"]

    states = {
        surface: "improved"
        for surface in production_pilot_service.V6_ADAPTIVE_PROGRESS_SURFACES
    }
    ready = production_pilot_service.adaptive_recommendation_parent_progress_clarity(states)
    assert ready["clarityState"] == "ready"
    assert {"activity", "outcome", "next_step", "support_recommendation"}.issubset(
        ready["parentProgressConnects"]
    )
    assert all(row["internalScoringExposed"] is False for row in ready["surfaces"])


def test_v63_learning_quality_gate_allows_v64_after_learning_risks_close():
    default_gate = production_pilot_service.v6_3_learning_quality_gate()
    assert default_gate["decision"] == "continue_learning_quality_remediation"
    assert default_gate["v6_4Allowed"] is False
    assert any(blocker.startswith("outcome:") for blocker in default_gate["blockers"])

    hold = production_pilot_service.v6_3_learning_quality_gate(
        outcome_review={"blockers": []},
        curriculum_fixes={"blockers": []},
        ai_quality={"blockers": []},
        adaptive_progress={"blockers": []},
        automation_hold=True,
    )
    assert hold["decision"] == "hold_automation"
    assert hold["v6_4Allowed"] is False

    ready = production_pilot_service.v6_3_learning_quality_gate(
        outcome_review={"blockers": []},
        curriculum_fixes={"blockers": []},
        ai_quality={"blockers": []},
        adaptive_progress={"blockers": []},
    )
    assert ready["decision"] == "prepare_larger_cohort"
    assert ready["v6_4Allowed"] is True
    assert ready["largerCohortApproved"] is False


def test_v64_operations_risk_review_requires_selection_and_ownership():
    default_review = production_pilot_service.operations_risk_incident_review()
    assert default_review["reviewState"] == "blocked"
    assert "highest_risk_selection" in default_review["blockers"]

    states = {
        area: "reviewed"
        for area in production_pilot_service.V6_OPERATIONS_RISK_AREAS
    }
    states["manual_toil"] = "selected_for_fix"
    ready = production_pilot_service.operations_risk_incident_review(states)
    assert ready["reviewState"] == "ready"
    assert ready["selectedFindings"] == ["manual_toil"]
    assert {"product", "reliability", "support", "process"}.issubset(ready["gapTypes"])


def test_v64_admin_support_teacher_workflow_fixes_protect_sensitive_operations():
    default_fixes = production_pilot_service.admin_support_teacher_workflow_scale_fixes()
    assert default_fixes["workflowState"] == "blocked"
    assert "billing_support" in default_fixes["blockers"]

    states = {
        surface: "improved"
        for surface in production_pilot_service.V6_OPERATOR_WORKFLOW_SURFACES
    }
    ready = production_pilot_service.admin_support_teacher_workflow_scale_fixes(states)
    assert ready["workflowState"] == "ready"
    assert ready["privateContentLeakage"] is False
    assert ready["permissionBroadening"] is False
    assert all(row["sensitiveOperationProtected"] for row in ready["surfaces"])


def test_v64_observability_hardening_covers_alert_ownership_and_traffic_classes():
    default_observability = production_pilot_service.observability_alert_dashboard_hardening()
    assert default_observability["observabilityState"] == "blocked"
    assert "auth" in default_observability["blockers"]

    states = {
        surface: "hardened"
        for surface in production_pilot_service.V6_OBSERVABILITY_SURFACES
    }
    ready = production_pilot_service.observability_alert_dashboard_hardening(states)
    assert ready["observabilityState"] == "ready"
    assert {"test", "dry_run", "pilot", "real_customer"}.issubset(ready["trafficClasses"])
    assert ready["privateEvidenceExcluded"] is True
    assert all(row["runbookReady"] for row in ready["surfaces"])


def test_v64_release_migration_rollback_smoke_discipline_requires_hardening():
    default_release = production_pilot_service.release_migration_rollback_smoke_discipline()
    assert default_release["releaseState"] == "blocked"
    assert "migration" in default_release["blockers"]

    states = {
        surface: "hardened"
        for surface in production_pilot_service.V6_RELEASE_DISCIPLINE_SURFACES
    }
    ready = production_pilot_service.release_migration_rollback_smoke_discipline(states)
    assert ready["releaseState"] == "ready"
    assert {"code_sha", "deploy_build_id", "request_id", "timestamp", "owner"}.issubset(
        ready["evidenceLinks"]
    )
    assert all(row["rollbackExecutable"] for row in ready["surfaces"])


def test_v64_controlled_expansion_gate_holds_or_rolls_back_without_full_readiness():
    default_gate = production_pilot_service.v6_4_controlled_expansion_readiness_gate()
    assert default_gate["decision"] == "operations_hardening_cycle"
    assert default_gate["largerCohortAllowed"] is False

    hold = production_pilot_service.v6_4_controlled_expansion_readiness_gate(
        risk_review={"blockers": []},
        workflow_fixes={"blockers": []},
        observability={"blockers": []},
        release_discipline={"blockers": []},
        hold_requested=True,
    )
    assert hold["decision"] == "hold"
    assert hold["largerCohortAllowed"] is False

    rollback = production_pilot_service.v6_4_controlled_expansion_readiness_gate(
        risk_review={"blockers": []},
        workflow_fixes={"blockers": []},
        observability={"blockers": []},
        release_discipline={"blockers": []},
        rollback_required=True,
    )
    assert rollback["decision"] == "rollback"

    ready = production_pilot_service.v6_4_controlled_expansion_readiness_gate(
        risk_review={"blockers": []},
        workflow_fixes={"blockers": []},
        observability={"blockers": []},
        release_discipline={"blockers": []},
    )
    assert ready["decision"] == "larger_controlled_cohort"
    assert ready["largerCohortAllowed"] is True
    assert ready["publicLaunchApproved"] is False
    assert ready["paidMarketingApproved"] is False


def test_v65_production_access_refresh_requires_real_access_and_owner_signoff():
    default_refresh = production_pilot_service.production_evidence_access_approval_refresh()
    assert default_refresh["accessState"] == "blocked"
    assert "approved_credential_path" in default_refresh["blockers"]
    assert default_refresh["evidencePolicy"]["localContractsAreNotProof"] is True

    states = {
        path: "available"
        for path in production_pilot_service.V65_PRODUCTION_ACCESS_PATHS
    }
    signoffs = {
        path: "approved"
        for path in production_pilot_service.V65_PRODUCTION_ACCESS_PATHS
    }
    ready = production_pilot_service.production_evidence_access_approval_refresh(
        states,
        owner_signoffs=signoffs,
        approved_credential_path=True,
    )
    assert ready["accessState"] == "ready"
    assert ready["blockers"] == []
    assert all(row["redactedMetadataOnly"] for row in ready["accessPaths"])


def test_v65_production_account_payment_usage_smoke_builds_blocker_package():
    default_smoke = production_pilot_service.production_account_payment_usage_smoke()
    assert default_smoke["smokeState"] == "blocked"
    assert "usage_ledger" in default_smoke["blockers"]
    assert default_smoke["blockerPackage"]
    assert default_smoke["mutationPolicy"]["allowed"] is False

    states = {
        surface: "read_only_verified"
        for surface in production_pilot_service.V65_ACCOUNT_PAYMENT_USAGE_SURFACES
    }
    states["checkout_paywall"] = "disabled_for_pilot"
    ready = production_pilot_service.production_account_payment_usage_smoke(states)
    assert ready["smokeState"] == "ready"
    assert ready["blockers"] == []
    assert ready["mutationPolicy"]["scope"] == "read_only"


def test_v65_notification_support_mobile_learning_smoke_requires_production_modes():
    states = {
        surface: "passed"
        for surface in production_pilot_service.V65_NOTIFICATION_SUPPORT_MOBILE_LEARNING_SURFACES
    }
    missing_modes = production_pilot_service.production_notification_support_mobile_learning_smoke(
        states
    )
    assert missing_modes["smokeState"] == "blocked"
    assert any(blocker.startswith("evidence_mode:") for blocker in missing_modes["blockers"])

    modes = {
        surface: "production"
        for surface in production_pilot_service.V65_NOTIFICATION_SUPPORT_MOBILE_LEARNING_SURFACES
    }
    disabled = {"notification_delivery"}
    ready = production_pilot_service.production_notification_support_mobile_learning_smoke(
        states,
        disabled_surfaces=disabled,
        evidence_modes=modes,
    )
    assert ready["smokeState"] == "ready"
    assert set(ready["disabledSurfaces"]) == disabled
    assert ready["dryRunOrLocalFixtureIsNotProductionEvidence"] is True


def test_v65_first_cohort_launch_packet_requires_finalized_packet_and_dry_run():
    default_packet = production_pilot_service.first_cohort_launch_packet_execution()
    assert default_packet["packetState"] == "blocked"
    assert "dry_run" in default_packet["blockers"]

    states = {
        area: "finalized"
        for area in production_pilot_service.V65_COHORT_LAUNCH_PACKET_AREAS
    }
    ready = production_pilot_service.first_cohort_launch_packet_execution(
        states,
        dry_run_passed=True,
    )
    assert ready["packetState"] == "ready"
    assert "first_learning_action" in ready["dryRunCoverage"]
    assert ready["blockers"] == []


def test_v65_live_pilot_start_decision_handoff_blocks_v66_without_real_evidence():
    default_gate = production_pilot_service.live_pilot_start_decision_handoff()
    assert default_gate["decision"] == "hold"
    assert default_gate["v6_6Allowed"] is False
    assert default_gate["realUserOperationsAllowed"] is False

    ready = production_pilot_service.live_pilot_start_decision_handoff(
        access_refresh={"accessState": "ready", "blockers": []},
        account_smoke={"smokeState": "ready", "blockers": []},
        support_mobile_learning_smoke={"smokeState": "ready", "blockers": []},
        launch_packet={"packetState": "ready", "blockers": []},
    )
    assert ready["decision"] == "start_limited_pilot"
    assert ready["safeToStart"] is True
    assert ready["v6_6Allowed"] is True
    assert "dailyOperatingCadence" in ready["handoff"]

    harden = production_pilot_service.live_pilot_start_decision_handoff(
        access_refresh={"accessState": "blocked", "blockers": ["provider"]},
        account_smoke={"smokeState": "ready", "blockers": []},
        support_mobile_learning_smoke={"smokeState": "ready", "blockers": []},
        launch_packet={"packetState": "ready", "blockers": []},
        accepted_blockers=["access:provider"],
    )
    assert harden["decision"] == "harden_further"
    assert harden["v6_6Allowed"] is False


def test_v66_day_one_operations_converts_v65_hold_to_fix_board():
    default_start = production_pilot_service.cohort_day_one_operations_or_blocker_sprint_start()
    assert default_start["mode"] == "blocker_sprint"
    assert default_start["operationsState"] == "blocked"
    assert default_start["rows"]
    assert default_start["trafficClassesSeparated"] is True

    signals = {
        signal: "healthy"
        for signal in production_pilot_service.V66_COHORT_OPERATION_SIGNALS
    }
    ready = production_pilot_service.cohort_day_one_operations_or_blocker_sprint_start(
        v65_start_gate={"decision": "start_limited_pilot", "blockers": []},
        observed_signals=signals,
    )
    assert ready["mode"] == "cohort_operations"
    assert ready["operationsState"] == "ready"
    assert ready["blockers"] == []


def test_v66_activation_account_entitlement_fixes_require_fixed_or_deferred():
    default_fixes = production_pilot_service.activation_account_verification_entitlement_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "login" in default_fixes["blockers"]

    states = {
        surface: "fixed"
        for surface in production_pilot_service.V66_ACCOUNT_ENTITLEMENT_FIX_SURFACES
    }
    states["recovery"] = "explicitly_deferred"
    ready = production_pilot_service.activation_account_verification_entitlement_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["rolesCovered"] == ["parent", "student", "admin_support"]
    assert all(row["reversible"] for row in ready["surfaces"])


def test_v66_support_teacher_notification_mobile_fixes_allow_pilot_disablement():
    default_fixes = production_pilot_service.support_teacher_notification_mobile_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "support_queue" in default_fixes["blockers"]

    states = {
        surface: "fixed"
        for surface in production_pilot_service.V66_SUPPORT_TEACHER_MOBILE_FIX_SURFACES
    }
    states["notification_delivery"] = "disabled_for_pilot"
    ready = production_pilot_service.support_teacher_notification_mobile_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["escalationVisible"] is True
    assert any(row["fallbackCopyReady"] for row in ready["surfaces"])


def test_v66_learning_parent_clarity_fixes_preserve_boundaries_and_rank_gaps():
    default_fixes = production_pilot_service.first_learning_action_parent_clarity_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "onboarding" in default_fixes["blockers"]

    states = {
        surface: "fixed"
        for surface in production_pilot_service.V66_LEARNING_PARENT_FIX_SURFACES
    }
    states["recommendations"] = "accepted_gap"
    ready = production_pilot_service.first_learning_action_parent_clarity_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["curriculumAuthorizationPreserved"] is True
    assert ready["aiBoundariesPreserved"] is True
    assert ready["knownLearningGapsForV6_8"] == ["recommendations"]


def test_v66_live_cohort_outcome_gate_allows_v67_only_after_fixes_close():
    default_gate = production_pilot_service.v66_live_cohort_outcome_gate()
    assert default_gate["decision"] == "hold"
    assert default_gate["v6_7Allowed"] is False

    rollback = production_pilot_service.v66_live_cohort_outcome_gate(
        operations={"blockers": []},
        account_fixes={"blockers": []},
        support_fixes={"blockers": []},
        learning_fixes={"blockers": []},
        rollback_required=True,
    )
    assert rollback["decision"] == "rollback"

    ready = production_pilot_service.v66_live_cohort_outcome_gate(
        operations={"blockers": []},
        account_fixes={"blockers": []},
        support_fixes={"blockers": []},
        learning_fixes={"blockers": []},
    )
    assert ready["decision"] == "proceed_to_revenue_retention"
    assert ready["v6_7Allowed"] is True


def test_v67_paid_conversion_billing_review_requires_reconciliation_and_owner_approval():
    default_review = production_pilot_service.paid_conversion_billing_reality_review()
    assert default_review["reviewState"] == "blocked"
    assert "checkout" in default_review["blockers"]
    assert "owner_approved_corrections" in default_review["blockers"]

    states = {
        surface: "reviewed"
        for surface in production_pilot_service.V67_PAID_BILLING_REVIEW_SURFACES
    }
    states["entitlement_activation"] = "reconciled"
    states["manual_correction"] = "reconciled"
    ready = production_pilot_service.paid_conversion_billing_reality_review(
        states,
        owner_approved_corrections=True,
    )
    assert ready["reviewState"] == "ready"
    assert ready["blockers"] == []
    assert ready["parentCopyReady"] is True
    assert ready["revenueCorrectionsAuditable"] is True
    assert ready["reversible"] is True


def test_v67_usage_quota_account_reliability_excludes_private_learning_content():
    default_fixes = production_pilot_service.usage_quota_parent_account_reliability_fixes()
    assert default_fixes["fixState"] == "blocked"
    assert "usage_ledger" in default_fixes["blockers"]

    states = {
        surface: "reliable"
        for surface in production_pilot_service.V67_USAGE_ACCOUNT_RELIABILITY_SURFACES
    }
    states["reconciliation_reports"] = "fixed"
    ready = production_pilot_service.usage_quota_parent_account_reliability_fixes(states)
    assert ready["fixState"] == "ready"
    assert ready["supportCanExplainWithoutPrivateLearningContent"] is True
    assert all(row["supportSafe"] for row in ready["surfaces"])
    assert not any(row["privateLearningContentIncluded"] for row in ready["surfaces"])


def test_v67_lifecycle_retention_requires_support_capacity_measurement():
    default_execution = production_pilot_service.lifecycle_retention_support_capacity_execution()
    assert default_execution["executionState"] == "blocked"
    assert "support_capacity_measured" in default_execution["blockers"]

    states = {
        surface: "executed"
        for surface in production_pilot_service.V67_LIFECYCLE_RETENTION_SURFACES
    }
    states["win_back"] = "disabled_for_pilot"
    ready = production_pilot_service.lifecycle_retention_support_capacity_execution(
        states,
        support_capacity_measured=True,
    )
    assert ready["executionState"] == "ready"
    assert ready["supportCapacityMeasured"] is True
    assert ready["retentionSignalsDistinguishRealUsers"] is True
    assert ready["testTrafficExcludedFromRetention"] is True


def test_v67_controlled_intake_requires_capacity_and_support_gates():
    default_intake = production_pilot_service.referral_waitlist_controlled_intake_execution()
    assert default_intake["intakeState"] == "blocked"
    assert "capacity_gate" in default_intake["blockers"]
    assert "support_gate" in default_intake["blockers"]

    states = {
        surface: "ready"
        for surface in production_pilot_service.V67_CONTROLLED_INTAKE_SURFACES
    }
    states["referral"] = "disabled_for_pilot"
    ready = production_pilot_service.referral_waitlist_controlled_intake_execution(
        states,
        capacity_gate_ready=True,
        support_gate_ready=True,
    )
    assert ready["intakeState"] == "ready"
    assert ready["publicLaunchApproved"] is False
    assert ready["paidMarketingApproved"] is False
    assert ready["feedsCohortPlanning"] is True


def test_v67_revenue_growth_gate_controls_v68_access_and_public_launch_scope():
    default_gate = production_pilot_service.v67_revenue_growth_decision_gate()
    assert default_gate["decision"] == "revenue_remediation"
    assert default_gate["v6_8Allowed"] is False

    rollback = production_pilot_service.v67_revenue_growth_decision_gate(
        revenue_review={"blockers": []},
        usage_account={"blockers": []},
        lifecycle={"blockers": []},
        intake={"blockers": []},
        rollback_required=True,
    )
    assert rollback["decision"] == "rollback"

    ready = production_pilot_service.v67_revenue_growth_decision_gate(
        revenue_review={"blockers": []},
        usage_account={"blockers": []},
        lifecycle={"blockers": []},
        intake={"blockers": []},
    )
    assert ready["decision"] == "controlled_growth"
    assert ready["v6_8Allowed"] is True
    assert ready["paidMarketingApproved"] is False
    assert ready["publicLaunchApproved"] is False
    assert ready["learningRisksSeparated"] is True


def test_v68_learning_outcome_analysis_requires_ranked_real_learning_signals():
    default_analysis = production_pilot_service.real_learning_outcome_weak_topic_analysis()
    assert default_analysis["analysisState"] == "blocked"
    assert "completion" in default_analysis["blockers"]
    assert "top_issues_ranked" in default_analysis["blockers"]

    states = {
        signal: "analyzed"
        for signal in production_pilot_service.V68_REAL_LEARNING_OUTCOME_SIGNALS
    }
    ready = production_pilot_service.real_learning_outcome_weak_topic_analysis(
        states,
        top_issues_ranked=True,
    )
    assert ready["analysisState"] == "ready"
    assert ready["accountBillingNotificationSupportOnboardingSeparated"] is True
    assert all(row["supportSafe"] for row in ready["signals"])
    assert not any(row["rawPrivateStudentContentIncluded"] for row in ready["signals"])


def test_v68_curriculum_quality_release_preserves_authorized_workflow():
    default_release = production_pilot_service.curriculum_exercise_explanation_quality_release()
    assert default_release["releaseState"] == "blocked"
    assert "authorized_content_workflow" in default_release["blockers"]

    states = {
        surface: "released"
        for surface in production_pilot_service.V68_CURRICULUM_RELEASE_SURFACES
    }
    states["preview"] = "validated"
    ready = production_pilot_service.curriculum_exercise_explanation_quality_release(
        states,
        authorized_content_workflow=True,
    )
    assert ready["releaseState"] == "ready"
    assert ready["curriculumEditPermissionsBroadened"] is False
    assert ready["progressIntegrityPreserved"] is True
    assert ready["recommendationIntegrityPreserved"] is True


def test_v68_ai_teacher_quality_release_requires_fixtures_and_teacher_review():
    default_quality = production_pilot_service.ai_teacher_summary_practice_quality_release()
    assert default_quality["qualityState"] == "blocked"
    assert "evaluation_fixtures" in default_quality["blockers"]
    assert "teacher_review" in default_quality["blockers"]

    states = {
        surface: "released"
        for surface in production_pilot_service.V68_AI_TEACHER_RELEASE_SURFACES
    }
    states["refusal_fallback"] = "fallback_ready"
    ready = production_pilot_service.ai_teacher_summary_practice_quality_release(
        states,
        evaluation_fixtures_updated=True,
        teacher_review_ready=True,
    )
    assert ready["qualityState"] == "ready"
    assert "follow_up" in ready["teacherReviewModes"]
    assert ready["unsafeOffTopicOverconfidentCaught"] is True


def test_v68_adaptive_parent_progress_release_keeps_scores_and_prompts_private():
    default_release = production_pilot_service.adaptive_recommendation_parent_progress_release()
    assert default_release["releaseState"] == "blocked"
    assert "recent_learning" in default_release["blockers"]

    states = {
        surface: "released"
        for surface in production_pilot_service.V68_ADAPTIVE_PROGRESS_RELEASE_SURFACES
    }
    states["freshness"] = "improved"
    ready = production_pilot_service.adaptive_recommendation_parent_progress_release(states)
    assert ready["releaseState"] == "ready"
    assert all(not row["internalScoringExposed"] for row in ready["surfaces"])
    assert all(not row["promptExposed"] for row in ready["surfaces"])
    assert "support_recommendation" in ready["parentProgressConnects"]


def test_v68_learning_expansion_gate_controls_market_readiness_access():
    default_gate = production_pilot_service.v68_learning_expansion_decision_gate()
    assert default_gate["decision"] == "learning_remediation"
    assert default_gate["v6_9Allowed"] is False

    freeze = production_pilot_service.v68_learning_expansion_decision_gate(
        outcome_analysis={"blockers": []},
        curriculum_release={"blockers": []},
        ai_quality={"blockers": []},
        adaptive_progress={"blockers": []},
        content_ai_freeze=True,
    )
    assert freeze["decision"] == "content_ai_freeze"

    ready = production_pilot_service.v68_learning_expansion_decision_gate(
        outcome_analysis={"blockers": []},
        curriculum_release={"blockers": []},
        ai_quality={"blockers": []},
        adaptive_progress={"blockers": []},
    )
    assert ready["decision"] == "learning_scale"
    assert ready["v6_9Allowed"] is True
    assert ready["publicLaunchApproved"] is False
    assert ready["paidMarketingApproved"] is False
    assert ready["marketReadinessRisksSeparated"] is True
