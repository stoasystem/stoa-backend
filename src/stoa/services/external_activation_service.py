"""Release-operation smoke readiness for external provider activation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stoa.config import Settings
from stoa.services import (
    account_verification_service,
    notification_service,
    subscription_service,
    support_destination_service,
    support_sla_service,
)


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


def build_notification_support_smoke_report(settings: Settings) -> dict[str, Any]:
    """Build a redacted notification/support activation report for release operators."""
    notification = _notification_smoke(settings)
    support = _support_smoke(settings)
    blockers = _unique([*notification["blockers"], *support["blockers"]])
    warnings = _unique([*notification["warnings"], *support["warnings"]])
    live_ready = (
        notification["classification"] == "live_ready"
        and support["classification"] == "live_ready"
        and not blockers
    )
    overall = "live_ready" if live_ready else "blocked"
    if not live_ready and (
        notification["classification"] != "blocked"
        or support["classification"] != "blocked"
    ):
        overall = "read_only_verifiable"

    return {
        "generatedAt": _now_iso(),
        "taxonomy": list(TAXONOMY),
        "overallState": overall,
        "safeToMutate": bool(notification["safeToMutate"] and support["safeToMutate"] and not blockers),
        "notification": notification,
        "support": support,
        "blockers": blockers,
        "warnings": warnings,
        "privacy": {
            "secretsRedacted": True,
            "rawProviderPayloadsIncluded": False,
            "customerMessagesIncluded": False,
            "providerTicketPayloadsIncluded": False,
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


def _notification_smoke(settings: Settings) -> dict[str, Any]:
    websocket = _websocket_smoke(settings)
    email = _notification_email_smoke(settings)
    push = _notification_push_smoke(settings)
    blockers = _unique([*websocket["blockers"], *email["blockers"], *push["blockers"]])
    warnings = _unique([*websocket["warnings"], *email["warnings"], *push["warnings"]])
    live_ready = (
        websocket["classification"] == "live_ready"
        and email["classification"] == "live_ready"
        and push["classification"] == "live_ready"
    )
    if live_ready:
        classification = "live_ready"
    elif any(section["classification"] == "read_only_verifiable" for section in (websocket, email, push)):
        classification = "read_only_verifiable"
    else:
        classification = "blocked"
    return {
        "classification": classification,
        "safeToMutate": bool(live_ready and not blockers),
        "websocket": websocket,
        "emailDigest": email,
        "push": push,
        "preferences": {
            "categories": sorted(notification_service.PREFERENCE_CATEGORIES),
            "channels": sorted(notification_service.PREFERENCE_CHANNELS),
            "gatingEnforced": True,
        },
        "tokenRegistration": {
            "supported": True,
            "platforms": sorted(notification_service.PUSH_TOKEN_PLATFORMS),
            "rawTokensStored": False,
            "providerReferenceSupported": True,
        },
        "deliveryStatusEvidence": {
            "adminRoute": "GET /admin/notifications/delivery-status",
            "recentAttemptsBounded": True,
            "rawProviderPayloadsIncluded": False,
        },
        "smoke": {
            "mode": "live_send" if live_ready else "read_only",
            "customerMutationAllowed": bool(live_ready and not blockers),
            "safeFixtureRequired": True,
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _websocket_smoke(settings: Settings) -> dict[str, Any]:
    endpoint = (settings.websocket_api_endpoint or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not endpoint:
        blockers.append("missing_websocket_api_endpoint")
    if not settings.websocket_live_routes_configured:
        blockers.append("websocket_live_routes_not_configured")
    if not settings.websocket_live_deployed:
        blockers.append("websocket_live_not_deployed")
    if not settings.websocket_live_smoke_passed:
        blockers.append("websocket_live_smoke_not_passed")
    if not settings.websocket_stale_cleanup_enabled:
        blockers.append("websocket_stale_cleanup_disabled")
    classification = "live_ready" if not blockers else ("blocked" if not endpoint else "read_only_verifiable")
    if endpoint and blockers:
        warnings.append("websocket_requires_live_smoke_evidence")
    return {
        "classification": classification,
        "endpointConfigured": bool(endpoint),
        "routesConfigured": bool(settings.websocket_live_routes_configured),
        "deployed": bool(settings.websocket_live_deployed),
        "liveSmokePassed": bool(settings.websocket_live_smoke_passed),
        "staleCleanupEnabled": bool(settings.websocket_stale_cleanup_enabled),
        "connectionTtlSeconds": max(int(settings.websocket_connection_ttl_seconds), 1),
        "blockers": blockers,
        "warnings": warnings,
    }


def _notification_email_smoke(settings: Settings) -> dict[str, Any]:
    provider = (settings.notification_email_provider or "").strip()
    sender = (settings.notification_email_sender or "").strip()
    template = (settings.notification_email_digest_template or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not provider:
        blockers.append("missing_notification_email_provider")
    if provider and not settings.notification_email_provider_approved:
        blockers.append("notification_email_provider_not_approved")
    if provider and not sender:
        blockers.append("missing_notification_email_sender")
    if provider and not template:
        blockers.append("missing_notification_email_digest_template")
    if provider and not settings.notification_email_send_enabled:
        warnings.append("notification_email_send_disabled")
    classification = _provider_classification(
        configured=bool(provider),
        approved=bool(settings.notification_email_provider_approved),
        send_enabled=bool(settings.notification_email_send_enabled),
        blockers=blockers,
    )
    return {
        "classification": classification,
        "provider": provider or "disabled",
        "configured": bool(provider and not blockers),
        "approved": bool(settings.notification_email_provider_approved),
        "sendEnabled": bool(settings.notification_email_send_enabled),
        "senderConfigured": bool(sender),
        "template": template,
        "blockers": blockers,
        "warnings": warnings,
    }


def _notification_push_smoke(settings: Settings) -> dict[str, Any]:
    provider = (settings.notification_push_provider or "").strip()
    template = (settings.notification_push_template or "").strip()
    api_key = (settings.notification_push_provider_api_key or "").strip()
    endpoint = (settings.notification_push_provider_endpoint_url or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not provider:
        blockers.append("missing_notification_push_provider")
    if provider and not settings.notification_push_provider_approved:
        blockers.append("notification_push_provider_not_approved")
    if provider and not template:
        blockers.append("missing_notification_push_template")
    if provider and not api_key:
        blockers.append("missing_notification_push_provider_api_key")
    if provider and not endpoint:
        blockers.append("missing_notification_push_provider_endpoint_url")
    if provider and not settings.notification_push_send_enabled:
        warnings.append("notification_push_send_disabled")
    classification = _provider_classification(
        configured=bool(provider),
        approved=bool(settings.notification_push_provider_approved),
        send_enabled=bool(settings.notification_push_send_enabled),
        blockers=blockers,
    )
    return {
        "classification": classification,
        "provider": provider or "disabled",
        "configured": bool(provider and not blockers),
        "approved": bool(settings.notification_push_provider_approved),
        "sendEnabled": bool(settings.notification_push_send_enabled),
        "credentials": "configured" if api_key else "missing",
        "endpointConfigured": bool(endpoint),
        "template": template,
        "blockers": blockers,
        "warnings": warnings,
    }


def _support_smoke(settings: Settings) -> dict[str, Any]:
    internal_queue = _support_internal_queue_smoke(settings)
    third_party = _support_third_party_smoke(settings)
    crm = _support_crm_smoke(settings)
    blockers = _unique([*internal_queue["blockers"], *third_party["blockers"], *crm["blockers"]])
    warnings = _unique([*internal_queue["warnings"], *third_party["warnings"], *crm["warnings"]])
    live_ready = (
        internal_queue["classification"] == "live_ready"
        and third_party["classification"] == "live_ready"
        and crm["classification"] == "live_ready"
    )
    if live_ready:
        classification = "live_ready"
    elif any(section["classification"] == "read_only_verifiable" for section in (internal_queue, third_party, crm)):
        classification = "read_only_verifiable"
    else:
        classification = "blocked"
    return {
        "classification": classification,
        "safeToMutate": bool(live_ready and not blockers),
        "internalQueue": internal_queue,
        "thirdPartyProvider": third_party,
        "crmMessaging": crm,
        "deliveryLifecycle": {
            "adminRoutes": [
                "GET /admin/reports/support-handoff-deliveries",
                "GET /admin/reports/support-handoff-sla",
                "POST /admin/reports/support-handoff-deliveries/{delivery_id}/retry",
                "POST /admin/reports/support-handoff-deliveries/{delivery_id}/provider-sync",
            ],
            "retrySupported": True,
            "providerSyncSupported": True,
            "rawProviderPayloadsIncluded": False,
        },
        "smoke": {
            "mode": "live_provider_write" if live_ready else "read_only",
            "customerMutationAllowed": bool(live_ready and not blockers),
            "safeFixtureRequired": True,
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _support_internal_queue_smoke(settings: Settings) -> dict[str, Any]:
    blockers = [] if settings.support_internal_queue_approved else ["support_internal_queue_not_approved"]
    return {
        "classification": "live_ready" if not blockers else "blocked",
        "destination": support_destination_service.INTERNAL_QUEUE_DESTINATION,
        "approved": bool(settings.support_internal_queue_approved),
        "blockers": blockers,
        "warnings": [],
    }


def _support_third_party_smoke(settings: Settings) -> dict[str, Any]:
    api_key = (settings.support_third_party_provider_api_key or "").strip()
    endpoint = (settings.support_third_party_provider_endpoint_url or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    if not settings.support_third_party_provider_approved:
        blockers.append("support_third_party_provider_not_approved")
    if not api_key:
        blockers.append("missing_support_third_party_provider_api_key")
    if not endpoint:
        blockers.append("missing_support_third_party_provider_endpoint_url")
    if settings.support_third_party_provider_fail_delivery:
        blockers.append("support_third_party_provider_delivery_failing")
    classification = "live_ready" if not blockers else ("read_only_verifiable" if settings.support_third_party_provider_approved else "blocked")
    return {
        "classification": classification,
        "destination": support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION,
        "approved": bool(settings.support_third_party_provider_approved),
        "credentials": "configured" if api_key else "missing",
        "endpointConfigured": bool(endpoint),
        "retryMaxAttempts": support_destination_service.MAX_PROVIDER_RETRY_ATTEMPTS,
        "blockers": blockers,
        "warnings": warnings,
    }


def _support_crm_smoke(settings: Settings) -> dict[str, Any]:
    approved_templates = sorted(set(settings.support_crm_approved_templates or []))
    supported_templates = sorted(support_sla_service.MESSAGE_TEMPLATES)
    blockers: list[str] = []
    warnings: list[str] = []
    if not settings.support_crm_messaging_approved:
        blockers.append("support_crm_messaging_not_approved")
    if not settings.support_crm_destination_approved:
        blockers.append("support_crm_destination_not_approved")
    if not approved_templates:
        blockers.append("missing_support_crm_approved_templates")
    if settings.support_crm_fail_delivery:
        blockers.append("support_crm_provider_delivery_failing")
    unknown_templates = [template for template in approved_templates if template not in support_sla_service.MESSAGE_TEMPLATES]
    if unknown_templates:
        warnings.append("support_crm_has_unknown_approved_templates")
    classification = "live_ready" if not blockers else ("read_only_verifiable" if approved_templates else "blocked")
    return {
        "classification": classification,
        "messagingApproved": bool(settings.support_crm_messaging_approved),
        "destinationApproved": bool(settings.support_crm_destination_approved),
        "supportedTemplates": supported_templates,
        "approvedTemplates": approved_templates,
        "destinations": sorted(support_sla_service.MESSAGE_DESTINATIONS),
        "blockers": blockers,
        "warnings": warnings,
    }


def _provider_classification(
    *,
    configured: bool,
    approved: bool,
    send_enabled: bool,
    blockers: list[str],
) -> str:
    if blockers:
        return "blocked" if not configured or not approved else "read_only_verifiable"
    if send_enabled:
        return "live_ready"
    return "read_only_verifiable"


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
