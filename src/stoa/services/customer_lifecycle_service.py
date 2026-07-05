"""Customer lifecycle messaging contracts and release evidence helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from stoa.services import release_evidence_service


RELEASE_STATE = "customer-lifecycle-ready-local-contracts"
FORBIDDEN_EVIDENCE_FIELDS = {
    "answer",
    "answers",
    "authorization",
    "cookie",
    "id_token",
    "object_key",
    "password",
    "prompt",
    "provider_payload",
    "raw_learning_content",
    "refresh_token",
    "s3_key",
    "secret",
    "student_work",
    "token",
}
APPROVED_PROVIDER_STATES = {"approved_fixture", "read_only_verified", "live_ready"}
SUPPORT_SAFE_PAYLOAD_FIELDS = {
    "account_status",
    "billing_status",
    "child_count",
    "entitlement_status",
    "event",
    "message_state",
    "next_action",
    "provider_state",
    "quota_state",
    "recipient_role",
    "support_case_state",
    "template_id",
    "verification_state",
}


@dataclass(frozen=True)
class LifecycleMessageDefinition:
    event: str
    audience: str
    template_id: str
    channel: str
    preference_category: str
    provider_dependency: str
    trigger_state: str
    next_action: str

    def taxonomy_row(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "audience": self.audience,
            "templateId": self.template_id,
            "channel": self.channel,
            "preferenceGate": self.preference_category,
            "providerDependency": self.provider_dependency,
            "triggerState": self.trigger_state,
            "idempotencyKey": f"lifecycle:{self.event}:{{recipient_id}}:{{state_version}}",
            "supportSafePayloadFields": sorted(SUPPORT_SAFE_PAYLOAD_FIELDS),
            "excludedFields": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        }


MESSAGE_CATALOG: dict[str, LifecycleMessageDefinition] = {
    "onboarding_welcome": LifecycleMessageDefinition(
        event="onboarding_welcome",
        audience="parent",
        template_id="lifecycle_parent_welcome_v1",
        channel="email",
        preference_category="account",
        provider_dependency="transactional_email",
        trigger_state="parent_registered",
        next_action="complete child setup and first practice session",
    ),
    "email_verification_reminder": LifecycleMessageDefinition(
        event="email_verification_reminder",
        audience="parent",
        template_id="lifecycle_email_verification_v1",
        channel="email",
        preference_category="account",
        provider_dependency="transactional_email",
        trigger_state="email_unverified",
        next_action="verify email before sign-in",
    ),
    "payment_failed": LifecycleMessageDefinition(
        event="payment_failed",
        audience="parent",
        template_id="lifecycle_payment_failed_v1",
        channel="email",
        preference_category="billing",
        provider_dependency="billing_provider",
        trigger_state="payment_failed",
        next_action="update payment method",
    ),
    "payment_recovered": LifecycleMessageDefinition(
        event="payment_recovered",
        audience="parent",
        template_id="lifecycle_payment_recovered_v1",
        channel="email",
        preference_category="billing",
        provider_dependency="billing_provider",
        trigger_state="payment_recovered",
        next_action="resume learning plan",
    ),
    "quota_warning": LifecycleMessageDefinition(
        event="quota_warning",
        audience="parent",
        template_id="lifecycle_quota_warning_v1",
        channel="email",
        preference_category="usage",
        provider_dependency="usage_ledger",
        trigger_state="quota_near_limit",
        next_action="review usage or upgrade",
    ),
    "subscription_state": LifecycleMessageDefinition(
        event="subscription_state",
        audience="parent",
        template_id="lifecycle_subscription_state_v1",
        channel="email",
        preference_category="billing",
        provider_dependency="billing_provider",
        trigger_state="subscription_changed",
        next_action="review subscription status",
    ),
    "support_incident_update": LifecycleMessageDefinition(
        event="support_incident_update",
        audience="parent",
        template_id="lifecycle_support_incident_v1",
        channel="email",
        preference_category="support",
        provider_dependency="support_crm",
        trigger_state="support_case_updated",
        next_action="review support update",
    ),
    "learning_progress_nudge": LifecycleMessageDefinition(
        event="learning_progress_nudge",
        audience="parent",
        template_id="lifecycle_progress_nudge_v1",
        channel="email",
        preference_category="learning_updates",
        provider_dependency="weekly_progress",
        trigger_state="progress_available",
        next_action="review weekly progress",
    ),
    "re_engagement": LifecycleMessageDefinition(
        event="re_engagement",
        audience="parent",
        template_id="lifecycle_re_engagement_v1",
        channel="email",
        preference_category="learning_updates",
        provider_dependency="engagement_state",
        trigger_state="inactive_parent",
        next_action="restart practice",
    ),
}


def message_taxonomy(*, provider_state: str = "blocked") -> dict[str, Any]:
    return {
        "schemaVersion": "v1",
        "providerState": provider_state,
        "events": [definition.taxonomy_row() for definition in MESSAGE_CATALOG.values()],
        "privacy": _privacy_contract(),
        "externalWritePolicy": {
            "requiresProviderApproval": True,
            "requiresTemplateApproval": True,
            "requiresDestinationApproval": True,
            "defaultMode": "dry_run",
        },
    }


def plan_lifecycle_message(
    *,
    event: str,
    account: dict[str, Any],
    preferences: dict[str, bool] | None = None,
    provider_state: str = "blocked",
    template_approved: bool = True,
    destination_approved: bool = True,
    dry_run: bool = True,
    request_id: str | None = None,
) -> dict[str, Any]:
    definition = _definition(event)
    recipient_id = _safe_text(account.get("recipient_id") or account.get("parent_id") or account.get("user_id"))
    role = _safe_text(account.get("recipient_role") or account.get("role") or definition.audience)
    state_version = _safe_text(account.get("state_version") or account.get("updated_at") or "current")
    support_payload = _support_safe_payload(definition, account, provider_state=provider_state)
    refusal_reasons = _delivery_refusals(
        definition=definition,
        role=role,
        preferences=preferences or {},
        provider_state=provider_state,
        template_approved=template_approved,
        destination_approved=destination_approved,
        account=account,
        payload=support_payload,
    )
    state = "refused" if refusal_reasons else ("preview" if dry_run else "ready_to_send")
    return {
        "event": definition.event,
        "state": state,
        "recipientRole": role,
        "templateId": definition.template_id,
        "channel": definition.channel,
        "preferenceCategory": definition.preference_category,
        "providerState": provider_state,
        "idempotencyKey": _idempotency_key(definition.event, recipient_id, state_version),
        "requestId": request_id,
        "dryRun": dry_run,
        "retry": retry_policy(attempt_count=int(account.get("attempt_count") or 0), state=state),
        "refusalReasons": refusal_reasons,
        "supportSafePayload": support_payload,
    }


def plan_lifecycle_journey(
    *,
    account: dict[str, Any],
    preferences: dict[str, bool] | None = None,
    provider_state: str = "blocked",
    approved_events: set[str] | None = None,
) -> list[dict[str, Any]]:
    approved_events = approved_events or set(MESSAGE_CATALOG)
    return [
        plan_lifecycle_message(
            event=event,
            account=account,
            preferences=preferences,
            provider_state=provider_state,
            template_approved=event in approved_events,
            destination_approved=True,
            dry_run=True,
        )
        for event in MESSAGE_CATALOG
    ]


def parent_message_history(messages: list[dict[str, Any]], *, parent_id: str) -> dict[str, Any]:
    visible = []
    for message in messages:
        payload = dict(message.get("supportSafePayload") or {})
        if _safe_text(payload.get("parent_id")) and _safe_text(payload.get("parent_id")) != parent_id:
            continue
        visible.append(
            {
                "event": message.get("event"),
                "state": message.get("state"),
                "templateId": message.get("templateId"),
                "channel": message.get("channel"),
                "nextAction": payload.get("next_action"),
                "messageState": payload.get("message_state"),
            }
        )
    return {"parentId": parent_id, "messages": visible, "privacy": _privacy_contract()}


def admin_message_history(messages: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for message in messages:
        rows.append(
            {
                "event": message.get("event"),
                "state": message.get("state"),
                "templateId": message.get("templateId"),
                "channel": message.get("channel"),
                "recipientRole": message.get("recipientRole"),
                "providerState": message.get("providerState"),
                "retry": message.get("retry"),
                "refusalReasons": message.get("refusalReasons") or [],
                "requestId": message.get("requestId"),
            }
        )
    return {"messages": rows, "operatorActions": ["preview", "retry_allowed_message"], "privacy": _privacy_contract()}


def provider_activation_smoke(
    *,
    provider_approved: bool,
    credential_configured: bool,
    template_approved: bool,
    destination_approved: bool,
    opt_out: bool = False,
    provider_failure: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    refusal_reasons: list[str] = []
    if not provider_approved:
        refusal_reasons.append("missing_provider_approval")
    if not credential_configured:
        refusal_reasons.append("missing_provider_credential")
    if not template_approved:
        refusal_reasons.append("missing_template_approval")
    if not destination_approved:
        refusal_reasons.append("unapproved_destination")
    if opt_out:
        refusal_reasons.append("recipient_opted_out")
    if provider_failure:
        refusal_reasons.append("provider_failure")
    state = "read_only_verified" if not refusal_reasons else "blocked"
    return {
        "requestId": request_id,
        "state": state,
        "refusalReasons": refusal_reasons,
        "idempotencyKey": _idempotency_key("provider_activation_smoke", request_id or "fixture", state),
        "evidence": {
            "metadataOnly": True,
            "rawProviderPayloadIncluded": False,
            "requestId": request_id,
        },
    }


def release_gate_evidence() -> dict[str, Any]:
    fixture_account = {
        "parent_id": "parent-fixture",
        "recipient_id": "parent-fixture",
        "role": "parent",
        "state_version": "fixture-v1",
        "account_status": "active",
        "verification_state": "verified",
        "billing_status": "active",
        "quota_state": "available",
        "support_case_state": "none",
        "child_count": 1,
    }
    journey = plan_lifecycle_journey(
        account=fixture_account,
        preferences={"account": True, "billing": True, "usage": True, "support": True, "learning_updates": True},
        provider_state="approved_fixture",
    )
    provider_blocked = provider_activation_smoke(
        provider_approved=False,
        credential_configured=False,
        template_approved=True,
        destination_approved=True,
        request_id="lifecycle-smoke-fixture",
    )
    evidence = {
        "releaseState": RELEASE_STATE,
        "journeyEvents": [message["event"] for message in journey],
        "journeyStates": {message["event"]: message["state"] for message in journey},
        "templateInventoryCount": len(MESSAGE_CATALOG),
        "providerBlockedState": provider_blocked,
        "disableControls": ["provider_state_blocked", "template_approval_required", "destination_approval_required"],
        "privacy": _privacy_contract(),
    }
    assert_support_safe(evidence)
    return evidence


def assert_support_safe(payload: dict[str, Any]) -> None:
    _assert_no_forbidden_keys(payload)
    hits = release_evidence_service.private_marker_hits(payload)
    if hits:
        raise ValueError(f"customer lifecycle evidence contains private markers: {hits}")


def retry_policy(*, attempt_count: int, state: str) -> dict[str, Any]:
    retryable = state in {"ready_to_send", "preview"} and attempt_count < 3
    return {
        "retryable": retryable,
        "attemptCount": attempt_count,
        "nextBackoffSeconds": 0 if not retryable else min(3600, 60 * (2 ** max(attempt_count, 0))),
        "duplicateSuppression": True,
    }


def _definition(event: str) -> LifecycleMessageDefinition:
    if event not in MESSAGE_CATALOG:
        raise ValueError(f"unsupported_lifecycle_event:{event}")
    return MESSAGE_CATALOG[event]


def _delivery_refusals(
    *,
    definition: LifecycleMessageDefinition,
    role: str,
    preferences: dict[str, bool],
    provider_state: str,
    template_approved: bool,
    destination_approved: bool,
    account: dict[str, Any],
    payload: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if role != definition.audience:
        reasons.append("recipient_role_not_allowed")
    if preferences.get("global_opt_out") or preferences.get(definition.preference_category) is False:
        reasons.append("recipient_opted_out")
    if bool(account.get("quiet_hours_active")):
        reasons.append("quiet_hours_active")
    if provider_state not in APPROVED_PROVIDER_STATES:
        reasons.append("provider_not_approved")
    if not template_approved:
        reasons.append("template_not_approved")
    if not destination_approved:
        reasons.append("destination_not_approved")
    if _safe_text(account.get("current_state")) and _safe_text(account.get("current_state")) != definition.trigger_state:
        reasons.append("stale_or_mismatched_state")
    try:
        assert_support_safe(payload)
    except ValueError:
        reasons.append("privacy_denylist_failed")
    return reasons


def _support_safe_payload(
    definition: LifecycleMessageDefinition,
    account: dict[str, Any],
    *,
    provider_state: str,
) -> dict[str, Any]:
    payload = {
        "event": definition.event,
        "parent_id": _safe_text(account.get("parent_id")),
        "recipient_role": _safe_text(account.get("recipient_role") or account.get("role") or definition.audience),
        "template_id": definition.template_id,
        "provider_state": provider_state,
        "message_state": definition.trigger_state,
        "next_action": definition.next_action,
        "account_status": _safe_text(account.get("account_status") or "unknown"),
        "verification_state": _safe_text(account.get("verification_state") or "unknown"),
        "billing_status": _safe_text(account.get("billing_status") or "unknown"),
        "quota_state": _safe_text(account.get("quota_state") or "unknown"),
        "support_case_state": _safe_text(account.get("support_case_state") or "none"),
        "entitlement_status": _safe_text(account.get("entitlement_status") or "unknown"),
        "child_count": int(account.get("child_count") or 0),
    }
    return payload


def _idempotency_key(event: str, recipient_id: str, state_version: str) -> str:
    material = f"{event}|{recipient_id}|{state_version}".encode("utf-8")
    return f"lifecycle-{hashlib.sha256(material).hexdigest()[:24]}"


def _privacy_contract() -> dict[str, Any]:
    return {
        "metadataOnly": True,
        "excludedFields": sorted(FORBIDDEN_EVIDENCE_FIELDS),
        "supportSafePayloadFields": sorted(SUPPORT_SAFE_PAYLOAD_FIELDS),
    }


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_EVIDENCE_FIELDS:
                raise ValueError(f"forbidden customer lifecycle evidence field: {key}")
            _assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(child)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()
