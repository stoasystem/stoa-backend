"""Deterministic product smoke readiness matrix.

The checks here are local release-gate contracts, not live provider probes.
They classify critical routes and expected blockers without calling Cognito,
AI providers, payment providers, or external notification services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CoreSmokeCheck:
    check_id: str
    flow: str
    category: str
    method: str
    route: str
    status: str
    readiness: str
    expected_status_codes: tuple[int, ...]
    expected_blocker: str | None
    regression: bool
    support_note: str
    request_metadata: dict[str, Any]


CORE_SMOKE_CHECKS: tuple[CoreSmokeCheck, ...] = (
    CoreSmokeCheck(
        check_id="service-health",
        flow="service availability",
        category="service",
        method="GET",
        route="/health",
        status="passed",
        readiness="service_available",
        expected_status_codes=(200,),
        expected_blocker=None,
        regression=False,
        support_note="Health route is local and does not require auth or external providers.",
        request_metadata={"requestId": "smoke:service-health"},
    ),
    CoreSmokeCheck(
        check_id="auth-login",
        flow="login",
        category="product_flow",
        method="POST",
        route="/auth/login",
        status="expected_blocked",
        readiness="route_available_external_provider_required",
        expected_status_codes=(200, 401, 403, 500),
        expected_blocker="cognito_or_verified_email_required",
        regression=False,
        support_note="Local gate should distinguish invalid credentials or provider setup from route regression.",
        request_metadata={"requestId": "smoke:auth-login", "bodyShape": ["email", "password"]},
    ),
    CoreSmokeCheck(
        check_id="parent-entitlement",
        flow="entitlement resolution",
        category="product_flow",
        method="GET",
        route="/parents/me/subscription",
        status="expected_blocked",
        readiness="requires_authenticated_parent",
        expected_status_codes=(200, 401, 403),
        expected_blocker="parent_auth_required",
        regression=False,
        support_note="Entitlement route is the canonical paid-state read path and should not use demo fallback for access decisions.",
        request_metadata={"requestId": "smoke:parent-entitlement"},
    ),
    CoreSmokeCheck(
        check_id="curriculum-read",
        flow="curriculum read",
        category="product_flow",
        method="GET",
        route="/practice/curriculum/catalog",
        status="expected_blocked",
        readiness="requires_authenticated_user_or_preview_policy",
        expected_status_codes=(200, 401, 403),
        expected_blocker="auth_or_preview_policy_required",
        regression=False,
        support_note="Curriculum read smoke is read-only and must not mutate practice progress or usage.",
        request_metadata={"requestId": "smoke:curriculum-read", "queryShape": ["subjectId", "gradeLevel"]},
    ),
    CoreSmokeCheck(
        check_id="question-submit",
        flow="question submit",
        category="product_flow",
        method="POST",
        route="/questions",
        status="expected_blocked",
        readiness="requires_student_auth_quota_and_ai_provider",
        expected_status_codes=(201, 401, 403, 429, 500),
        expected_blocker="student_auth_quota_or_ai_provider_required",
        regression=False,
        support_note="Question smoke must classify quota/provider blocks separately from route or ledger regressions.",
        request_metadata={"requestId": "smoke:question-submit", "bodyShape": ["subject", "idempotencyKey"]},
    ),
    CoreSmokeCheck(
        check_id="teacher-help",
        flow="teacher help",
        category="product_flow",
        method="POST",
        route="/teacher-help/request",
        status="expected_blocked",
        readiness="requires_student_auth_and_existing_conversation",
        expected_status_codes=(200, 401, 403, 404),
        expected_blocker="student_auth_or_existing_conversation_required",
        regression=False,
        support_note="Teacher-help smoke should confirm request routing without storing raw help messages.",
        request_metadata={"requestId": "smoke:teacher-help", "bodyShape": ["conversationId"]},
    ),
    CoreSmokeCheck(
        check_id="admin-account-operations",
        flow="admin account support",
        category="product_flow",
        method="GET",
        route="/admin/account-operations/parents/{parent_id}",
        status="expected_blocked",
        readiness="requires_admin_auth_and_parent_id",
        expected_status_codes=(200, 401, 403, 404),
        expected_blocker="admin_auth_or_parent_record_required",
        regression=False,
        support_note="Account operations smoke should expose verification, billing, child binding, entitlement, and usage support state.",
        request_metadata={"requestId": "smoke:admin-account-operations", "pathShape": ["parent_id"]},
    ),
)


def build_core_smoke_report() -> dict[str, Any]:
    """Return a support-safe local smoke readiness report."""
    checks = [asdict(check) for check in CORE_SMOKE_CHECKS]
    passed = sum(1 for check in checks if check["status"] == "passed")
    expected_blocked = sum(1 for check in checks if check["status"] == "expected_blocked")
    regressions = sum(1 for check in checks if check["regression"])
    return {
        "status": "failed" if regressions else "ready_with_expected_blocks",
        "summary": {
            "checkCount": len(checks),
            "passed": passed,
            "expectedBlocked": expected_blocked,
            "regressions": regressions,
        },
        "checks": checks,
        "privacy": {
            "rawContentStored": False,
            "providerPayloadsStored": False,
            "authTokensStored": False,
            "privateArtifactKeysStored": False,
        },
    }
