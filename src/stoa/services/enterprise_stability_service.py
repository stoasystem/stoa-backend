"""Enterprise stability, disaster recovery, and compliance evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stoa.services import release_evidence_service


RELEASE_STATE = "enterprise-hardening-ready-local-contracts"
FORBIDDEN_EVIDENCE_FIELDS = {
    "answer",
    "authorization",
    "cookie",
    "credential",
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
SERVICE_NAMES = {
    "api_lambda",
    "dynamodb",
    "s3",
    "cognito",
    "ses",
    "bedrock",
    "notification_provider",
    "support_provider",
    "bi_apm",
    "frontend",
    "mobile",
    "queues",
    "schedules",
}
INCIDENT_DOMAINS = {
    "auth",
    "billing_payment",
    "usage_quota",
    "curriculum",
    "ai_provider",
    "notification",
    "support_crm",
    "mobile",
    "report_operations",
    "production_deploy_failure",
}


@dataclass(frozen=True)
class ServiceRisk:
    service: str
    owner: str
    failure_mode: str
    recovery_action: str
    slo_target: str
    evidence_source: str
    blocker: str
    risk_category: str

    def row(self) -> dict[str, str]:
        return {
            "service": self.service,
            "owner": self.owner,
            "failureMode": self.failure_mode,
            "recoveryAction": self.recovery_action,
            "sloTarget": self.slo_target,
            "evidenceSource": self.evidence_source,
            "blocker": self.blocker,
            "riskCategory": self.risk_category,
        }


SERVICE_RISK_REGISTER = [
    ServiceRisk("api_lambda", "backend", "5xx or timeout spike", "rollback Lambda/CDK deploy", "99.5% monthly availability", "api logs and release evidence", "live dashboard activation", "product_regression"),
    ServiceRisk("dynamodb", "backend", "table read/write or PITR issue", "restore/export/readback drill", "zero acknowledged data loss for core account tables", "backup drill evidence", "live PITR verification", "data_loss"),
    ServiceRisk("s3", "backend", "artifact metadata or object access failure", "readback metadata and disable private artifact exposure", "99.5% artifact metadata availability", "report artifact evidence", "live bucket policy audit", "privacy"),
    ServiceRisk("cognito", "backend", "auth or verification outage", "switch to incident runbook and defer sign-in changes", "99.5% auth availability", "auth smoke evidence", "live Cognito smoke", "provider_blocker"),
    ServiceRisk("ses", "backend", "email send failure", "disable sends and surface verification resend blocker", "95% transactional email acceptance", "provider smoke evidence", "SES production readiness", "provider_blocker"),
    ServiceRisk("bedrock", "backend", "AI provider refusal/latency/failure", "fallback to teacher review and disable autonomy", "p95 under 15s for approved AI surfaces", "AI operations evidence", "live provider telemetry", "provider_blocker"),
    ServiceRisk("notification_provider", "backend", "push/realtime/email delivery failure", "defer channel and keep in-app record", "95% delivery attempt visibility", "notification delivery status", "push provider activation", "provider_blocker"),
    ServiceRisk("support_provider", "operations", "CRM write/sync failure", "keep internal queue and provider blocked state", "100% support-safe blocker visibility", "support CRM smoke", "provider credentials/templates", "provider_blocker"),
    ServiceRisk("bi_apm", "operations", "dashboard stale or unavailable", "fall back to local release evidence", "dashboard freshness under 24h", "BI/APM readiness evidence", "warehouse/APM activation", "release_process"),
    ServiceRisk("frontend", "frontend", "production UI regression", "rollback static deployment and freeze release", "99.5% app shell availability", "frontend e2e/build evidence", "production CDN smoke", "product_regression"),
    ServiceRisk("mobile", "mobile", "native app crash/regression", "halt rollout and use previous build channel", "crash-free sessions above 98%", "mobile QA evidence", "store/TestFlight activation", "product_regression"),
    ServiceRisk("queues", "backend", "job backlog or poison message", "pause producer and replay safe jobs", "no critical job stale over 30m", "job evidence", "live queue alarms", "release_process"),
    ServiceRisk("schedules", "backend", "scheduled reports/jobs fail", "manual replay safe fixture and freeze schedule", "critical schedule completion within 24h", "schedule evidence", "live schedule alarms", "release_process"),
]


def ops_risk_register() -> dict[str, Any]:
    rows = [risk.row() for risk in SERVICE_RISK_REGISTER]
    result = {
        "services": rows,
        "serviceCount": len(rows),
        "riskCounts": _count_by(rows, "riskCategory"),
        "highestRiskRoutes": {
            "backupRestore": ["dynamodb", "s3"],
            "incidentRollback": ["api_lambda", "frontend", "mobile", "queues", "schedules"],
            "accessRotation": ["cognito", "ses", "bedrock", "support_provider", "bi_apm"],
        },
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(result)
    return result


def backup_restore_drills() -> dict[str, Any]:
    drills = [
        {
            "drillId": "core-account-readback-fixture",
            "scope": "DynamoDB core account/product data",
            "procedure": "export safe fixture, read back metadata, compare counts/checksums",
            "state": "local_ready",
            "mutation": "none",
            "cleanupRequired": False,
        },
        {
            "drillId": "report-artifact-metadata-readback",
            "scope": "S3/report evidence object metadata",
            "procedure": "read metadata-only artifact index and validate privacy gates",
            "state": "local_ready",
            "mutation": "none",
            "cleanupRequired": False,
        },
        {
            "drillId": "config-release-state-readback",
            "scope": "release/config evidence",
            "procedure": "read release-state snapshot and verify rollback marker",
            "state": "local_ready",
            "mutation": "none",
            "cleanupRequired": False,
        },
    ]
    result = {
        "drills": drills,
        "dataLifecycle": {
            "retention": ["account metadata retained while account active", "audit evidence retained metadata-only"],
            "deletionRequests": "route through account operations and immutable audit exception review",
            "legalHold": "suspend deletion for scoped metadata evidence only",
            "customerExport": "metadata/report summaries only unless separately approved",
        },
        "productionMutationAllowed": False,
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(result)
    return result


def incident_runbooks() -> dict[str, Any]:
    runbooks = [
        {
            "domain": domain,
            "owner": _domain_owner(domain),
            "firstAction": _first_action(domain),
            "rollbackControl": _rollback_control(domain),
            "evidence": "request_id, timestamp, owner, release_state, support-safe outcome",
        }
        for domain in sorted(INCIDENT_DOMAINS)
    ]
    result = {
        "runbooks": runbooks,
        "rollbackFreezeControls": rollback_freeze_controls(),
        "tabletopDrill": {
            "drillId": "enterprise-hardening-tabletop-fixture",
            "state": "local_ready",
            "owner": "operations",
            "outcome": "runbook paths classified without production mutation",
        },
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(result)
    return result


def slo_dashboard_summary(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    events = events or []
    allowed_dimensions = {"availability", "error_rate", "latency", "provider_blocker", "stale_data", "release_state"}
    counts: dict[str, int] = {}
    for event in events:
        dimension = str(event.get("dimension") or "unknown")
        if dimension not in allowed_dimensions:
            dimension = "unknown"
        counts[dimension] = counts.get(dimension, 0) + 1
    result = {
        "dimensions": sorted(allowed_dimensions),
        "eventCounts": counts,
        "targets": {
            "availability": "99.5% draft",
            "error_rate": "<1% critical API errors",
            "latency": "p95 API under 2s and AI under 15s",
            "provider_blocker": "100% visible blocker state",
            "stale_data": "critical data under 24h stale",
            "release_state": "every deploy has rollback marker",
        },
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(result)
    return result


def rollback_freeze_controls() -> dict[str, Any]:
    return {
        "backendLambda": "rollback previous Lambda/CDK deployment",
        "cdk": "freeze deploy and restore last known stack output",
        "frontend": "rollback static deployment artifact",
        "mobile": "halt phased rollout or keep previous internal build",
        "providerFlags": "disable provider writes and surface blocked state",
        "scheduledJobs": "pause schedule and replay approved safe jobs",
    }


def access_rotation_evidence(*, dry_run: bool = True) -> dict[str, Any]:
    inventory = [
        {"surface": "admin_access", "owner": "operations", "rotationExpectation": "quarterly review"},
        {"surface": "cognito_groups", "owner": "backend", "rotationExpectation": "review on role change"},
        {"surface": "aws_profiles", "owner": "operations", "rotationExpectation": "least privilege and MFA review"},
        {"surface": "provider_credentials", "owner": "operations", "rotationExpectation": "provider-specific rotation"},
        {"surface": "ci_deploy_credentials", "owner": "engineering", "rotationExpectation": "on staff/provider change"},
        {"surface": "break_glass_access", "owner": "operations", "rotationExpectation": "sealed emergency review"},
    ]
    result = {
        "inventory": inventory,
        "dryRun": dry_run,
        "rotationEvidence": {
            "surface": "provider_credentials",
            "state": "dry_run_recorded" if dry_run else "requires_approved_live_rotation",
            "metadataOnly": True,
        },
        "auditRetention": "metadata-only audit events retained with immutable evidence pointers",
        "legalHold": "hold scoped metadata evidence without exposing private content",
        "privacyRedaction": "denylist excludes secrets, tokens, raw provider payloads, private keys, prompts, and student work",
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(result)
    return result


def release_gate_evidence() -> dict[str, Any]:
    evidence = {
        "releaseState": RELEASE_STATE,
        "opsAudit": ops_risk_register(),
        "restoreDrills": backup_restore_drills(),
        "incidentSloRollback": {
            "incidentDomainCount": len(incident_runbooks()["runbooks"]),
            "sloDimensions": slo_dashboard_summary()["dimensions"],
            "rollbackControls": rollback_freeze_controls(),
        },
        "accessCompliance": access_rotation_evidence(dry_run=True),
        "blockers": [
            "live PITR/restore smoke requires approved AWS production fixture",
            "live provider credential rotation requires operations approval",
            "warehouse/APM/live alert activation remains provider-gated",
        ],
        "v5_24Recommendation": "proceed to limited production pilot readiness, not broad public launch",
        "privacy": _metadata_privacy_contract(),
    }
    assert_metadata_safe(evidence)
    return evidence


def assert_metadata_safe(payload: dict[str, Any]) -> None:
    _assert_no_forbidden_keys(payload)
    hits = release_evidence_service.private_marker_hits(payload)
    if hits:
        raise ValueError(f"enterprise hardening evidence contains private markers: {hits}")


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _metadata_privacy_contract() -> dict[str, Any]:
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
                raise ValueError(f"forbidden enterprise evidence field: {key}")
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(child)


def _domain_owner(domain: str) -> str:
    if domain in {"auth", "billing_payment", "usage_quota", "curriculum", "ai_provider", "report_operations"}:
        return "backend"
    if domain in {"notification", "support_crm"}:
        return "operations"
    if domain == "mobile":
        return "mobile"
    return "engineering"


def _first_action(domain: str) -> str:
    actions = {
        "auth": "confirm Cognito status and freeze auth config changes",
        "billing_payment": "disable payment mutation and surface billing blocker",
        "usage_quota": "switch to ledger reconciliation mode",
        "curriculum": "freeze content rollout and use last approved version",
        "ai_provider": "disable autonomy and route to teacher review",
        "notification": "disable external channel and keep in-app records",
        "support_crm": "use internal support queue and block CRM writes",
        "mobile": "halt rollout and keep previous build channel",
        "report_operations": "pause report generation and verify metadata-only artifacts",
        "production_deploy_failure": "freeze deploy and rollback last known release",
    }
    return actions[domain]


def _rollback_control(domain: str) -> str:
    if domain == "mobile":
        return "mobile"
    if domain in {"notification", "support_crm", "ai_provider", "billing_payment"}:
        return "providerFlags"
    if domain == "production_deploy_failure":
        return "backendLambda"
    if domain == "report_operations":
        return "scheduledJobs"
    return "cdk"
