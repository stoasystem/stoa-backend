"""Release-operation smoke readiness for external provider activation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stoa.config import Settings
from stoa.services import account_verification_service, subscription_service


TAXONOMY = [
    "live_ready",
    "read_only_verifiable",
    "safe_fixture_verifiable",
    "locally_ready",
    "blocked",
]


def build_payment_auth_smoke_report(settings: Settings) -> dict[str, Any]:
    """Build a redacted payment/auth activation report for release operators."""
    payment_readiness = subscription_service.get_provider_readiness(settings)
    payment = _payment_smoke(payment_readiness, settings)
    cognito_email = _cognito_email_smoke(settings)
    blockers = _unique(
        [
            *payment["blockers"],
            *cognito_email["configuration"]["blockers"],
            *cognito_email["liveDelivery"]["blockers"],
        ]
    )
    overall = "blocked" if blockers else "live_ready"
    if not blockers and (
        payment["classification"] != "live_ready"
        or cognito_email["classification"] != "live_ready"
    ):
        overall = "read_only_verifiable"
    if blockers and payment["classification"] != "blocked":
        overall = "read_only_verifiable"

    return {
        "generatedAt": _now_iso(),
        "taxonomy": list(TAXONOMY),
        "overallState": overall,
        "safeToMutate": bool(payment["safeToMutate"] and not blockers),
        "payment": payment,
        "cognitoEmail": cognito_email,
        "blockers": blockers,
        "warnings": _unique([*payment["warnings"], *cognito_email["warnings"]]),
        "privacy": {
            "secretsRedacted": True,
            "rawProviderPayloadsIncluded": False,
            "loginCodesIncluded": False,
            "customerMutationDefault": "disabled",
        },
    }


def _payment_smoke(readiness: dict[str, Any], settings: Settings) -> dict[str, Any]:
    blockers = list(readiness.get("blockers") or [])
    warnings = list(readiness.get("warnings") or [])
    checkout_allowed = bool(readiness.get("checkoutAllowed"))
    refunds_allowed = bool(readiness.get("refundsAllowed"))
    rollout = readiness.get("rollout") or {}
    checkout_state = ((rollout.get("checkout") or {}).get("state") or "disabled")
    refund_state = ((rollout.get("refunds") or {}).get("state") or "disabled")

    if blockers or readiness.get("state") in {"not_configured", "provider_api_failed"}:
        classification = "blocked"
    elif checkout_allowed:
        classification = "live_ready"
    else:
        classification = "read_only_verifiable"

    safe_to_mutate = bool(
        checkout_allowed
        and readiness.get("providerMode") == "live"
        and settings.stripe_live_charges_enabled
        and checkout_state in {"canary", "enabled"}
        and not blockers
    )

    smoke_blockers = []
    if not safe_to_mutate:
        smoke_blockers.append("live_payment_mutation_not_approved")
    if blockers:
        smoke_blockers.append("payment_provider_readiness_blocked")

    return {
        "provider": "stripe",
        "paymentMethods": ["card", "twint"],
        "classification": classification,
        "safeToMutate": safe_to_mutate,
        "readinessState": readiness.get("state"),
        "providerMode": readiness.get("providerMode"),
        "checkoutAllowed": checkout_allowed,
        "refundsAllowed": refunds_allowed,
        "credentials": readiness.get("credentials") or {},
        "webhook": readiness.get("webhook") or {},
        "twint": readiness.get("twint") or {},
        "finance": readiness.get("finance") or {},
        "refund": readiness.get("refund") or {},
        "rollout": rollout,
        "smoke": {
            "mode": "live_mutation" if safe_to_mutate else "read_only",
            "safeFixtureRequired": True,
            "customerMutationAllowed": safe_to_mutate,
            "checkoutRolloutState": checkout_state,
            "refundRolloutState": refund_state,
            "blockedBy": _unique(smoke_blockers),
        },
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }


def _cognito_email_smoke(settings: Settings) -> dict[str, Any]:
    configured_clients = {
        "student": _configured(settings.cognito_student_client_id),
        "parent": _configured(settings.cognito_parent_client_id),
        "teacher": _configured(settings.cognito_teacher_client_id),
        "admin": _configured(settings.cognito_admin_client_id),
    }
    missing_config = []
    if not _configured(settings.cognito_user_pool_id):
        missing_config.append("missing_cognito_user_pool_id")
    missing_config.extend(
        f"missing_cognito_{role}_client_id"
        for role, configured in configured_clients.items()
        if not configured
    )

    delivery_blockers = [
        "approved_email_delivery_test_inbox_required",
        "production_cognito_email_delivery_smoke_not_recorded",
    ]
    classification = "blocked" if missing_config else "locally_ready"
    warnings = []
    if not missing_config:
        warnings.append("live_email_delivery_requires_operator_smoke_evidence")

    return {
        "provider": "aws_cognito",
        "classification": classification,
        "policy": {
            "emailVerification": account_verification_service.EMAIL_VERIFICATION_POLICY,
            "loginCode": account_verification_service.LOGIN_CODE_POLICY,
            "resendCooldownSeconds": account_verification_service.RESEND_COOLDOWN_SECONDS,
        },
        "configuration": {
            "userPoolConfigured": _configured(settings.cognito_user_pool_id),
            "clientIdsConfigured": configured_clients,
            "region": settings.aws_region,
            "blockers": missing_config,
        },
        "localAuthBehavior": {
            "classification": "blocked" if missing_config else "locally_ready",
            "registrationCreatesPendingVerification": True,
            "tokensBlockedUntilVerified": True,
            "resendCooldownEnforced": True,
            "supportRecoveryVisible": True,
        },
        "liveDelivery": {
            "classification": "blocked",
            "safeToMutate": False,
            "safeFixtureRequired": True,
            "customerMutationAllowed": False,
            "blockedBy": delivery_blockers,
            "blockers": delivery_blockers,
        },
        "blockers": missing_config,
        "warnings": warnings,
    }


def _configured(value: str | None) -> bool:
    return bool((value or "").strip())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
