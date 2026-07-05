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
