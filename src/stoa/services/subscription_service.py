"""Subscription operations for manual and provider-managed billing workflows."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib.util import find_spec
from typing import Any, Protocol, overload, runtime_checkable
from uuid import uuid4

from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from stoa.config import Settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, checkout_command_repo, user_repo
from stoa.models.billing import (
    CheckoutCommandState,
    CheckoutIntent,
    PurchasablePlanId,
)
from stoa.models.user import SubscriptionTier
from stoa.services import entitlement_service, notification_service
from stoa.services.billing_callback_service import build_checkout_return_urls


type SubscriptionItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _HighLevelTransactionTable(Protocol):
    def transact_write_items(self, **kwargs: object) -> object: ...


class _DynamoClient(Protocol):
    def transact_write_items(self, **kwargs: object) -> object: ...


class _DynamoMeta(Protocol):
    client: _DynamoClient


@runtime_checkable
class _DynamoTable(Protocol):
    meta: _DynamoMeta


def _subscription_mapping(value: object) -> SubscriptionItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("subscription data dependency unavailable")
    result: SubscriptionItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("subscription data dependency unavailable")
        result[key] = member
    return result


def _subscription_optional_item(value: object) -> SubscriptionItem | None:
    return None if value is None else _subscription_mapping(value)


def _subscription_get(table: object, **kwargs: object) -> SubscriptionItem:
    if not isinstance(table, _GetTable):
        raise RuntimeError("subscription data dependency unavailable")
    return _subscription_mapping(table.get_item(**kwargs))


def _subscription_put(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise RuntimeError("subscription data dependency unavailable")
    return table.put_item(**kwargs)


def _subscription_query(table: object, **kwargs: object) -> SubscriptionItem:
    if not isinstance(table, _QueryTable):
        raise RuntimeError("subscription data dependency unavailable")
    return _subscription_mapping(table.query(**kwargs))


def _subscription_scan(table: object, **kwargs: object) -> SubscriptionItem:
    if not isinstance(table, _ScanTable):
        raise RuntimeError("subscription data dependency unavailable")
    return _subscription_mapping(table.scan(**kwargs))


def _subscription_items(response: Mapping[str, object]) -> list[SubscriptionItem]:
    items = response.get("Items", [])
    if not isinstance(items, list):
        raise RuntimeError("subscription data dependency unavailable")
    return [_subscription_mapping(item) for item in items]


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


REQUEST_ENTITY = "subscription_request"
OPEN_GUARD_ENTITY = "subscription_request_open_guard"
BILLING_ENTITY = "subscription_billing"
BILLING_EVENT_ENTITY = "subscription_billing_event"
BILLING_EVENT_DEDUPE_ENTITY = "subscription_billing_event_dedupe"
BILLING_PROVIDER_LOOKUP_ENTITY = "subscription_billing_provider_lookup"
BILLING_REFUND_IDEMPOTENCY_ENTITY = "subscription_billing_refund_idempotency"
PAYMENT_ROLLOUT_ENTITY = "subscription_payment_rollout"
PAYMENT_ROLLOUT_STATES = {"disabled", "canary", "enabled", "rolled_back"}
READINESS_STATES = {
    "test",
    "not_configured",
    "live_ready_but_blocked",
    "live_enabled",
    "provider_api_failed",
}
REQUEST_STATUSES = {"requested", "in_review", "approved", "applied", "rejected", "cancelled"}
OPEN_STATUSES = {"requested", "in_review", "approved"}
TERMINAL_STATUSES = {"applied", "rejected", "cancelled"}
REQUEST_TYPES = {"upgrade", "downgrade", "cancel"}
BILLING_STATUSES = {
    "none",
    "checkout_pending",
    "active",
    "past_due",
    "canceled",
    "payment_failed",
    "manual_override",
    "provider_unknown",
}
PROVIDER_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.expired",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "charge.refunded",
    "refund.created",
    "refund.updated",
    "refund.failed",
    "customer.updated",
}

ALLOWED_TRANSITIONS = {
    "requested": {"in_review", "approved", "rejected", "cancelled"},
    "in_review": {"approved", "rejected", "cancelled"},
    "approved": {"applied", "rejected", "cancelled"},
    "applied": set(),
    "rejected": set(),
    "cancelled": set(),
}

PLAN_BENEFITS: dict[str, dict[str, Any]] = {
    "free_trial": {
        "label": "Free Trial",
        "dailyAiQuestionLimit": 5,
        "dailyChatMessageLimit": 8,
        "dailyHintLimit": 2,
        "teacherSupport": "none",
        "weeklyReport": "none",
    },
    "student": {
        "label": "Student",
        "dailyAiQuestionLimit": 30,
        "dailyChatMessageLimit": 80,
        "dailyHintLimit": 30,
        "teacherSupport": "text_support",
        "weeklyReport": "enabled",
    },
    "teacher_supported": {
        "label": "Teacher-supported",
        "dailyAiQuestionLimit": 100,
        "dailyChatMessageLimit": 200,
        "dailyHintLimit": 80,
        "teacherSupport": "priority_support",
        "weeklyReport": "enhanced",
    },
    "family": {
        "label": "Family",
        "dailyAiQuestionLimit": 100,
        "dailyChatMessageLimit": 200,
        "dailyHintLimit": 80,
        "teacherSupport": "priority_support",
        "weeklyReport": "enhanced",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_parent_subscription(parent_id: str, settings: Settings | None = None) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    current_tier = _normalize_tier(profile.get("subscription_tier"))
    billing = _billing_response(_get_billing_item(parent_id), parent_id=parent_id, settings=settings)
    if billing["status"] == "none":
        billing["subscriptionTier"] = current_tier
    effective_entitlements = (
        entitlement_service.list_parent_child_entitlements(parent_id, settings=settings)
        if settings
        else []
    )
    return {
        "parentId": parent_id,
        "currentTier": current_tier,
        "plans": PLAN_BENEFITS,
        "pendingRequest": _request_response(_latest_open_request(parent_id)),
        "billing": billing,
        "effectiveEntitlements": effective_entitlements,
    }


CHECKOUT_PRICE_CATALOG_VERSION = 1
CHECKOUT_PLAN_VERSION = 1
CHECKOUT_PROVIDER_LEASE_SECONDS = 30
CHECKOUT_REPLAY_POLL_ATTEMPTS = 50
CHECKOUT_REPLAY_POLL_SECONDS = 0.005


def _checkout_http_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _require_checkout_beneficiaries(
    *,
    parent_id: str,
    parent: Mapping[str, object],
    plan: PurchasablePlanId,
    beneficiary_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if (
        len(set(beneficiary_ids)) != len(beneficiary_ids)
        or not beneficiary_ids
        or (plan is PurchasablePlanId.FAMILY and len(beneficiary_ids) > 3)
        or (
            plan in {
                PurchasablePlanId.STUDENT,
                PurchasablePlanId.TEACHER_SUPPORTED,
            }
            and len(beneficiary_ids) != 1
        )
    ):
        raise _checkout_http_error(
            status_code=400,
            code="checkout_beneficiary_cardinality",
            message="The selected plan requires a different beneficiary count.",
        )
    if (
        parent.get("user_id") != parent_id
        or parent.get("role") != "parent"
        or parent.get("account_status") != "active"
    ):
        raise _checkout_http_error(
            status_code=409,
            code="checkout_parent_inactive",
            message="Checkout is not available for this account.",
        )
    for student_id in beneficiary_ids:
        student = user_repo.get_user(student_id)
        forward = user_repo.get_parent_student_binding(parent_id, student_id)
        reverse = user_repo.get_student_parent_binding(student_id, parent_id)
        expected = {
            "parent_id": parent_id,
            "student_id": student_id,
            "relationship": "child",
            "status": "active",
        }
        if (
            student is None
            or student.get("user_id") != student_id
            or student.get("role") != "student"
            or student.get("account_status") != "active"
            or forward is None
            or reverse is None
            or any(forward.get(field) != value for field, value in expected.items())
            or any(reverse.get(field) != value for field, value in expected.items())
        ):
            raise _checkout_http_error(
                status_code=409,
                code="checkout_beneficiary_invalid",
                message="One or more selected beneficiaries are unavailable.",
            )
    return tuple(sorted(beneficiary_ids))


def _require_sandbox_checkout_configuration(
    *,
    plan: PurchasablePlanId,
    settings: Settings,
) -> str:
    api_key = settings.stripe_api_key.strip()
    price_id = _price_id_for_tier(plan.value, settings).strip()
    if (
        not api_key.startswith("sk_test_")
        or not price_id.startswith("price_")
        or price_id.startswith("price_live_")
        or "_live" in price_id.lower()
    ):
        raise _checkout_http_error(
            status_code=503,
            code="checkout_sandbox_required",
            message="Sandbox checkout is not configured.",
        )
    return price_id


def _attached_checkout_response(
    command: Mapping[str, object] | None,
) -> dict[str, Any] | None:
    if (
        command is None
        or command.get("provider_effect_status") != "session_attached"
        or not isinstance(command.get("checkout_ref"), str)
        or not isinstance(command.get("provider_session_id"), str)
        or not isinstance(command.get("provider_session_url"), str)
        or not isinstance(command.get("plan_id"), str)
        or not isinstance(command.get("beneficiary_ids"), list)
    ):
        return None
    try:
        state = CheckoutCommandState(str(command.get("command_state") or ""))
    except ValueError:
        return None
    if state is not CheckoutCommandState.PROVIDER_SESSION_OPEN:
        return None
    return {
        "checkoutRef": command["checkout_ref"],
        "commandState": state.value,
        "checkoutSessionId": command["provider_session_id"],
        "checkoutUrl": command["provider_session_url"],
        "safeActions": ["recheck_payment", "contact_support"],
        "targetPlan": command["plan_id"],
        "beneficiaries": list(command["beneficiary_ids"]),
    }


def _poll_attached_checkout(
    *,
    checkout_ref: str,
    parent_id: str,
) -> dict[str, Any] | None:
    for _ in range(CHECKOUT_REPLAY_POLL_ATTEMPTS):
        result = checkout_command_repo.get_checkout_command_by_public_ref(
            checkout_ref,
            parent_id=parent_id,
        )
        response = _attached_checkout_response(result.command)
        if response is not None:
            return response
        if result.disposition not in {
            checkout_command_repo.CheckoutCommandDisposition.REPLAYED,
            checkout_command_repo.CheckoutCommandDisposition.RETRYABLE,
        }:
            return None
        time.sleep(CHECKOUT_REPLAY_POLL_SECONDS)
    return None


def create_or_resume_checkout_command(
    *,
    parent_id: str,
    idempotency_key: str,
    plan: str,
    beneficiary_ids: tuple[str, ...],
    settings: Settings,
) -> dict[str, Any]:
    parent = _require_parent(parent_id)
    try:
        target_plan = PurchasablePlanId(plan)
        command_id = checkout_command_repo.checkout_command_id(
            parent_id, idempotency_key
        )
    except ValueError as exc:
        raise _checkout_http_error(
            status_code=400,
            code="checkout_request_invalid",
            message="Checkout request is invalid.",
        ) from exc
    beneficiaries = _require_checkout_beneficiaries(
        parent_id=parent_id,
        parent=parent,
        plan=target_plan,
        beneficiary_ids=beneficiary_ids,
    )
    price_id = _require_sandbox_checkout_configuration(
        plan=target_plan,
        settings=settings,
    )
    created_at = datetime.now(timezone.utc)
    intent = CheckoutIntent(
        commandId=command_id,
        parentId=parent_id,
        idempotencyKey=idempotency_key,
        planId=target_plan,
        beneficiaryIds=beneficiaries,
        priceCatalogVersion=CHECKOUT_PRICE_CATALOG_VERSION,
        planVersion=CHECKOUT_PLAN_VERSION,
        createdAt=created_at,
    )
    registration = checkout_command_repo.register_checkout_command(
        intent,
        price_id=price_id,
        environment=settings.environment,
        now_iso=created_at.isoformat(),
    )
    if (
        registration.disposition
        is checkout_command_repo.CheckoutCommandDisposition.IDENTITY_MISMATCH
    ):
        raise _checkout_http_error(
            status_code=409,
            code="checkout_idempotency_mismatch",
            message="This checkout key is already bound to another selection.",
        )
    if (
        registration.disposition
        is checkout_command_repo.CheckoutCommandDisposition.OPEN_COMMAND_EXISTS
    ):
        raise _checkout_http_error(
            status_code=409,
            code="checkout_already_in_progress",
            message="Another checkout is already in progress.",
        )
    if registration.disposition not in {
        checkout_command_repo.CheckoutCommandDisposition.CREATED,
        checkout_command_repo.CheckoutCommandDisposition.REPLAYED,
    }:
        raise _checkout_http_error(
            status_code=503,
            code="checkout_temporarily_unavailable",
            message="Checkout is temporarily unavailable.",
        )
    replay = _attached_checkout_response(registration.command)
    if replay is not None:
        return replay
    command = registration.command
    if command is None or not isinstance(command.get("checkout_ref"), str):
        raise _checkout_http_error(
            status_code=503,
            code="checkout_temporarily_unavailable",
            message="Checkout is temporarily unavailable.",
        )
    checkout_ref = str(command["checkout_ref"])
    now_epoch = int(time.time())
    claim = checkout_command_repo.claim_provider_create(
        command,
        lease_owner=f"checkout-worker-{uuid4().hex}",
        now_epoch=now_epoch,
        lease_expires_at=now_epoch + CHECKOUT_PROVIDER_LEASE_SECONDS,
        now_iso=now_iso(),
    )
    if claim.disposition is checkout_command_repo.CheckoutCommandDisposition.LEASE_BUSY:
        concurrent = _poll_attached_checkout(
            checkout_ref=checkout_ref,
            parent_id=parent_id,
        )
        if concurrent is not None:
            return concurrent
        raise _checkout_http_error(
            status_code=503,
            code="checkout_confirmation_pending",
            message="Checkout creation is still being confirmed.",
        )
    replay = _attached_checkout_response(claim.command)
    if replay is not None:
        return replay
    if (
        claim.disposition
        is not checkout_command_repo.CheckoutCommandDisposition.CLAIMED
        or claim.provider_claim is None
    ):
        raise _checkout_http_error(
            status_code=503,
            code="checkout_temporarily_unavailable",
            message="Checkout is temporarily unavailable.",
        )
    provider_claim = claim.provider_claim
    return_urls = build_checkout_return_urls(checkout_ref, settings)
    provider_kwargs = {
        "checkout_ref": checkout_ref,
        "provider_idempotency_key": provider_claim.provider_key_digest,
        "price_id": price_id,
        "success_url": return_urls.success_url,
        "cancel_url": return_urls.cancel_url,
        "settings": settings,
    }
    try:
        session = _create_provider_checkout_session(**provider_kwargs)
    except Exception:
        try:
            session = _create_provider_checkout_session(**provider_kwargs)
        except Exception as exc:
            checkout_command_repo.mark_provider_outcome_unknown(
                provider_claim,
                now_iso=now_iso(),
            )
            raise _checkout_http_error(
                status_code=503,
                code="checkout_provider_ambiguous",
                message="Checkout creation is being confirmed.",
            ) from exc
    if (
        session.get("livemode") is not False
        or not isinstance(session.get("id"), str)
        or not str(session["id"]).startswith("cs_test_")
        or not isinstance(session.get("url"), str)
        or not str(session["url"]).startswith("https://checkout.stripe.com/")
    ):
        checkout_command_repo.mark_provider_outcome_unknown(
            provider_claim,
            now_iso=now_iso(),
        )
        raise _checkout_http_error(
            status_code=503,
            code="checkout_provider_ambiguous",
            message="Checkout creation is being confirmed.",
        )
    attached = checkout_command_repo.attach_provider_session(
        provider_claim,
        provider_session_id=str(session["id"]),
        provider_session_url=str(session["url"]),
        now_iso=now_iso(),
    )
    response = _attached_checkout_response(attached.command)
    if response is not None and attached.disposition in {
        checkout_command_repo.CheckoutCommandDisposition.ATTACHED,
        checkout_command_repo.CheckoutCommandDisposition.ALREADY_ATTACHED,
    }:
        return response
    raise _checkout_http_error(
        status_code=503,
        code="checkout_confirmation_pending",
        message="Checkout creation is still being confirmed.",
    )


def get_parent_billing(parent_id: str, settings: Settings | None = None) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    item = _get_billing_item(parent_id)
    response = _billing_response(item, parent_id=parent_id, include_events=True, settings=settings)
    if response["status"] == "none":
        response["subscriptionTier"] = _normalize_tier(profile.get("subscription_tier"))
    if settings:
        response["effectiveEntitlements"] = entitlement_service.list_parent_child_entitlements(
            parent_id,
            settings=settings,
        )
    return response


def list_admin_billing(
    *,
    limit: int = 50,
    parent_id: str | None = None,
    billing_status: str | None = None,
    billing_provider: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    if billing_status is not None:
        _require_choice(billing_status, BILLING_STATUSES, "billing_status")
    scan_kwargs: dict[str, Any] = dict(
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": BILLING_ENTITY},
    )
    items: list[dict[str, Any]] = []
    while True:
        response = _subscription_scan(get_table(), **scan_kwargs)
        items.extend(
            item
            for item in _subscription_items(response)
            if item.get("SK") == "SUMMARY"
            and item.get("entity_type") == BILLING_ENTITY
            and _matches(item, "parent_id", parent_id)
            and _matches(item, "billing_status", billing_status)
            and _matches(item, "billing_provider", billing_provider)
        )
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return [
        _billing_response(
            item,
            parent_id=str(item.get("parent_id") or ""),
            include_events=True,
            settings=settings,
        )
        for item in sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]
    ]


def get_admin_billing(parent_id: str, settings: Settings | None = None) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    response = _billing_response(
        _get_billing_item(parent_id),
        parent_id=parent_id,
        include_events=True,
        settings=settings,
    )
    if response["status"] == "none":
        response["subscriptionTier"] = _normalize_tier(profile.get("subscription_tier"))
    if settings:
        response["effectiveEntitlements"] = entitlement_service.list_parent_child_entitlements(
            parent_id,
            settings=settings,
        )
    return response


def list_admin_accounting_handoff(
    *,
    limit: int = 100,
    parent_id: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    billing_rows = list_admin_billing(limit=limit, parent_id=parent_id, settings=settings)
    return [
        row["accountingHandoff"]
        for row in billing_rows
        if row.get("accountingHandoff", {}).get("providerInvoiceId")
        or row.get("accountingHandoff", {}).get("providerSubscriptionId")
    ]


def get_provider_readiness(settings: Settings) -> dict[str, Any]:
    """Return redacted, read-only provider activation readiness for admins."""
    local = get_billing_readiness(settings)
    api_key = settings.stripe_api_key.strip()
    provider_mode = _api_key_mode(api_key)
    blockers = list(local.get("blockers") or [])
    warnings = list(local.get("warnings") or [])
    provider_failure = False
    account_capability_status = "unknown"

    prices = {
        "student": _price_readiness(
            "student", settings.stripe_student_price_id, settings=settings
        ),
        "teacher_supported": _price_readiness(
            "teacher_supported",
            settings.stripe_teacher_supported_price_id,
            settings=settings,
        ),
        "family": _price_readiness(
            "family", settings.stripe_family_price_id, settings=settings
        ),
    }

    should_check_provider = (
        settings.is_production
        and provider_mode == "live"
        and bool(api_key)
        and _stripe_sdk_available()
    )
    if should_check_provider:
        try:
            account = _retrieve_stripe_account(settings)
            account_capability_status = _stripe_capability_status(account, "twint_payments")
        except Exception:
            provider_failure = True
            blockers.append("stripe_account_lookup_failed")

        for tier, price in prices.items():
            if not price["configured"]:
                continue
            try:
                provider_price = _retrieve_stripe_price(str(price["priceId"]), settings)
                prices[tier].update(_provider_price_readiness(provider_price))
            except Exception:
                provider_failure = True
                prices[tier]["providerLookup"] = "failed"
                prices[tier]["blockers"].append(f"{tier}_price_lookup_failed")
                blockers.append(f"{tier}_price_lookup_failed")
    elif settings.is_production and provider_mode == "live" and not _stripe_sdk_available():
        provider_failure = True

    for tier, price in prices.items():
        if price["configured"] and price.get("providerLookup") == "not_checked":
            if settings.is_production and provider_mode == "live":
                warnings.append(f"{tier}_price_provider_lookup_not_checked")
        blockers.extend(price["blockers"])

    webhook = _webhook_readiness(settings)
    blockers.extend(webhook["blockers"])
    warnings.extend(webhook["warnings"])

    twint = _provider_twint_readiness(
        local_twint=local.get("twint") or {},
        capability_status=account_capability_status,
        settings=settings,
        provider_checked=should_check_provider and not provider_failure,
    )
    blockers.extend(twint["blockers"])
    warnings.extend(twint["warnings"])

    finance = _finance_readiness()
    rollout = get_payment_rollout_controls(settings)
    refund = _provider_refund_capability_readiness(local=local, twint=twint, settings=settings)
    refunds_allowed = bool(_rollout_state_allows(rollout["refunds"]["state"]) and local.get("livemode") and not provider_failure)

    if provider_failure:
        state = "provider_api_failed"
    else:
        state = str(local["state"])
    checkout_allowed = bool(local["checkoutAllowed"] and not blockers and not provider_failure)
    if state == "live_ready_but_blocked":
        checkout_allowed = False
    if checkout_allowed:
        rollout["providerReadiness"] = "ready"
        rollout["activationState"] = "activated" if settings.stripe_live_charges_enabled else "approved_canary_only"
    elif state == "live_ready_but_blocked":
        rollout["providerReadiness"] = "ready"
        rollout["activationState"] = "deferred"

    return {
        "state": state,
        "checkoutAllowed": checkout_allowed,
        "refundsAllowed": refunds_allowed,
        "providerMode": provider_mode,
        "credentials": {
            "apiKeyMode": provider_mode,
            "apiKey": _redacted_presence(api_key),
            "webhookSecretConfigured": bool(settings.stripe_webhook_secret.strip()),
            "studentPriceConfigured": bool(settings.stripe_student_price_id.strip()),
            "teacherSupportedPriceConfigured": bool(
                settings.stripe_teacher_supported_price_id.strip()
            ),
            "familyPriceConfigured": bool(settings.stripe_family_price_id.strip()),
        },
        "prices": prices,
        "twint": twint,
        "webhook": webhook,
        "refund": refund,
        "finance": finance,
        "rollout": rollout,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }


def handle_stripe_webhook(
    *,
    payload: bytes,
    signature_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    event = _parse_provider_event(payload, signature_header, settings)
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Provider event id and type are required")
    if event_type not in PROVIDER_EVENT_TYPES:
        return {"received": True, "ignored": True, "eventId": event_id, "eventType": event_type}

    event_object = ((event.get("data") or {}).get("object") or {})
    if not isinstance(event_object, dict):
        raise HTTPException(status_code=400, detail="Provider event object is required")

    parent_id = _parent_id_from_provider_object(event_object)
    if not parent_id:
        parent_id = _find_parent_id_for_provider_object(event_object)
    if not parent_id:
        raise HTTPException(status_code=400, detail="Unable to resolve parent for provider event")
    _require_parent(parent_id)

    existing = _get_billing_item(parent_id) or {}
    if _provider_event_seen(event_id):
        _record_provider_processing_event(
            parent_id=parent_id,
            event_id=event_id,
            event_type=event_type,
            event_created=event.get("created"),
            event_object=event_object,
            existing=existing,
            processing_result="deduplicated",
            idempotency_status="replayed",
            now=now_iso(),
        )
        return {
            "received": True,
            "deduplicated": True,
            "eventId": event_id,
            "eventType": event_type,
            "parentId": parent_id,
            "billingStatus": existing.get("billing_status") or "none",
        }

    now = now_iso()
    transition = _billing_transition(event_type, event_object, existing)
    if _provider_event_is_stale(event.get("created"), existing):
        _record_stale_provider_event(
            parent_id=parent_id,
            event_id=event_id,
            event_type=event_type,
            event_created=event.get("created"),
            event_object=event_object,
            existing=existing,
            now=now,
        )
        return {
            "received": True,
            "deduplicated": False,
            "eventId": event_id,
            "eventType": event_type,
            "parentId": parent_id,
            "billingStatus": existing.get("billing_status") or "none",
            "processingResult": "stale_ignored",
        }
    updated = _apply_billing_transition(
        parent_id=parent_id,
        event_id=event_id,
        event_type=event_type,
        event_created=event.get("created"),
        event_object=event_object,
        transition=transition,
        existing=existing,
        now=now,
    )
    return {
        "received": True,
        "deduplicated": False,
        "eventId": event_id,
        "eventType": event_type,
        "parentId": parent_id,
        "billingStatus": updated.get("billing_status"),
    }


def execute_billing_refund(
    *,
    parent_id: str,
    amount: int,
    reason: str,
    idempotency_key: str,
    user: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    _require_parent(parent_id)
    amount = _require_refund_amount(amount)
    reason = _require_refund_reason(reason)
    idempotency_key = _require_idempotency_key(idempotency_key)

    existing_replay = _get_refund_idempotency(parent_id, idempotency_key)
    if existing_replay:
        return _refund_execution_response(
            parent_id=parent_id,
            idempotency_status="replayed",
            idempotency_record=existing_replay,
            settings=settings,
        )

    rollout = get_payment_rollout_controls(settings)
    if not _rollout_state_allows(rollout["refunds"]["state"]):
        raise HTTPException(status_code=409, detail="Direct refund execution is not enabled")
    if settings.is_production and not settings.stripe_api_key.strip().startswith("sk_live_"):
        raise HTTPException(status_code=503, detail="Live Stripe API key is required for direct refunds")

    existing = _get_billing_item(parent_id)
    readiness = _refund_readiness(existing)
    if not readiness["eligible"]:
        raise HTTPException(status_code=409, detail={"message": "Billing record is not refundable", "refund": readiness})
    if amount > int(readiness["eligibleAmount"] or 0):
        raise HTTPException(status_code=409, detail="Refund amount exceeds remaining refundable amount")
    if not _twint_refund_window_open(existing):
        raise HTTPException(status_code=409, detail="TWINT refund window has expired")

    now = now_iso()
    actor = _actor_id(user)
    _reserve_refund_idempotency(
        parent_id=parent_id,
        idempotency_key=idempotency_key,
        amount=amount,
        reason=reason,
        actor=actor,
        at=now,
    )
    try:
        provider_refund = _create_provider_refund(
            provider_charge_id=str(readiness.get("providerChargeId") or ""),
            provider_payment_intent_id=str(readiness.get("providerPaymentIntentId") or ""),
            amount=amount,
            reason=reason,
            idempotency_key=idempotency_key,
            settings=settings,
        )
    except Exception as exc:
        _record_refund_idempotency_failure(
            parent_id=parent_id,
            idempotency_key=idempotency_key,
            amount=amount,
            reason=reason,
            actor=actor,
            at=now_iso(),
        )
        raise HTTPException(status_code=502, detail="Stripe refund creation failed") from exc

    updated = _apply_direct_refund_result(
        parent_id=parent_id,
        existing=existing or {},
        provider_refund=provider_refund,
        amount=amount,
        reason=reason,
        idempotency_key=idempotency_key,
        actor=actor,
        requested_at=now,
    )
    _record_refund_idempotency_success(
        parent_id=parent_id,
        idempotency_key=idempotency_key,
        amount=amount,
        reason=reason,
        actor=actor,
        at=now,
        provider_refund_id=updated.get("refund_summary", {}).get("providerRefundId"),
    )
    return {
        "idempotencyStatus": "new",
        "refund": updated.get("refund_summary") or {},
        "billing": _billing_response(updated, parent_id=parent_id, include_events=True, settings=settings),
    }


def get_payment_rollout_controls(settings: Settings) -> dict[str, Any]:
    item = _get_payment_rollout_item()
    checkout_state = str(
        item.get("checkout_state")
        if item
        else ("enabled" if settings.stripe_live_charges_enabled else "disabled")
    )
    refunds_state = str(
        item.get("refunds_state")
        if item
        else ("enabled" if settings.stripe_refunds_enabled else "disabled")
    )
    if checkout_state not in PAYMENT_ROLLOUT_STATES:
        checkout_state = "disabled"
    if refunds_state not in PAYMENT_ROLLOUT_STATES:
        refunds_state = "disabled"
    updated_at = item.get("updated_at") if item else None
    updated_by = item.get("updated_by") if item else None
    reason = item.get("reason") if item else None
    controls = {
        "checkout": {
            "state": checkout_state,
            "allowed": _rollout_state_allows(checkout_state),
        },
        "refunds": {
            "state": refunds_state,
            "allowed": _rollout_state_allows(refunds_state),
        },
        "providerReadiness": "ready" if checkout_state == "enabled" else "blocked",
        "activationState": _activation_state_from_rollout(checkout_state, refunds_state),
        "rollbackAvailable": True,
        "updatedAt": updated_at,
        "updatedBy": updated_by,
        "reason": reason,
    }
    return controls


def update_payment_rollout_controls(
    *,
    checkout_state: str | None,
    refunds_state: str | None,
    reason: str,
    user: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    current = get_payment_rollout_controls(settings)
    checkout_state = checkout_state or current["checkout"]["state"]
    refunds_state = refunds_state or current["refunds"]["state"]
    if checkout_state not in PAYMENT_ROLLOUT_STATES:
        raise HTTPException(status_code=400, detail="Unsupported checkout rollout state")
    if refunds_state not in PAYMENT_ROLLOUT_STATES:
        raise HTTPException(status_code=400, detail="Unsupported refund rollout state")
    cleaned_reason = _require_refund_reason(reason)
    now = now_iso()
    item = {
        **_payment_rollout_key(),
        "entity_type": PAYMENT_ROLLOUT_ENTITY,
        "checkout_state": checkout_state,
        "refunds_state": refunds_state,
        "reason": cleaned_reason,
        "updated_by": _actor_id(user),
        "updated_at": now,
    }
    _subscription_put(get_table(), Item=item)
    return get_payment_rollout_controls(settings)


def create_parent_request(
    *,
    parent_id: str,
    request_type: str,
    requested_tier: str | None,
    parent_note: str | None,
    source: str = "parent_portal",
) -> dict[str, Any]:
    profile = _require_parent(parent_id)
    request_type = _require_choice(request_type, REQUEST_TYPES, "request_type")
    current_tier = _normalize_tier(profile.get("subscription_tier"))
    target_tier = _target_tier(request_type, requested_tier)

    if request_type == "upgrade" and _tier_rank(target_tier) <= _tier_rank(current_tier):
        raise HTTPException(status_code=400, detail="Upgrade request must target a higher tier")
    if request_type == "downgrade" and _tier_rank(target_tier) >= _tier_rank(current_tier):
        raise HTTPException(status_code=400, detail="Downgrade request must target a lower tier")
    if request_type == "cancel" and target_tier != SubscriptionTier.FREE_TRIAL.value:
        raise HTTPException(status_code=400, detail="Cancellation requests target the free tier")

    created_at = now_iso()
    request_id = f"subreq-{uuid4().hex}"
    item: dict[str, Any] = {
        "PK": _request_pk(request_id),
        "SK": "SUMMARY",
        "entity_type": REQUEST_ENTITY,
        "request_id": request_id,
        "parent_id": parent_id,
        "student_id": None,
        "current_tier": current_tier,
        "requested_tier": target_tier,
        "request_type": request_type,
        "status": "requested",
        "source": source,
        "parent_note": _clean_note(parent_note),
        "admin_note": None,
        "created_at": created_at,
        "updated_at": created_at,
        "effective_at": None,
        "applied_at": None,
        "applied_by": None,
    }
    event = _event(
        request_id,
        "requested",
        actor_id=parent_id,
        actor_role="parent",
        at=created_at,
        note=item["parent_note"],
        changes={"requested_tier": target_tier, "request_type": request_type},
    )
    item["history"] = [event]
    event_item = {**event, "PK": _request_pk(request_id), "SK": _event_sk(created_at, event["event_id"])}
    guard = {
        **_open_guard_key(parent_id),
        "entity_type": OPEN_GUARD_ENTITY,
        "parent_id": parent_id,
        "request_id": request_id,
        "status": "requested",
        "created_at": created_at,
        "updated_at": created_at,
    }
    try:
        _transact_write(
            [
                {"Put": {"Item": item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"Item": guard, "ConditionExpression": "attribute_not_exists(PK)"}},
            ]
        )
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Parent already has an open subscription request",
            ) from exc
        raise
    notification_service.emit_subscription_update(
        request_item=item,
        recipient_id=None,
        recipient_role="admin",
        actor_id=parent_id,
        actor_role="parent",
    )
    return _request_response(item)


def list_parent_requests(parent_id: str, limit: int = 25) -> list[dict[str, Any]]:
    _require_parent(parent_id)
    return [_request_response(item) for item in _list_requests(parent_id=parent_id, limit=limit)]


def list_admin_requests(
    *,
    limit: int = 50,
    status: str | None = None,
    requested_tier: str | None = None,
    parent_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None:
        _require_choice(status, REQUEST_STATUSES, "status")
    if requested_tier is not None:
        _normalize_tier(requested_tier)
    return [
        _request_response(item)
        for item in _list_requests(
            limit=limit,
            status=status,
            requested_tier=requested_tier,
            parent_id=parent_id,
            date_from=date_from,
            date_to=date_to,
        )
    ]


def get_request(request_id: str) -> dict[str, Any]:
    item = _get_request_item(request_id)
    item = dict(item)
    item["history"] = _list_events(request_id) or item.get("history") or []
    return _request_response(item)


def update_request_status(
    *,
    request_id: str,
    status: str,
    admin_note: str | None,
    effective_at: str | None,
    user: dict[str, Any],
) -> dict[str, Any]:
    status = _require_choice(status, REQUEST_STATUSES - {"applied"}, "status")
    item = _get_request_item(request_id)
    current = item.get("status", "requested")
    if status == current and not admin_note and not effective_at:
        return get_request(request_id)
    _require_transition(current, status)

    now = now_iso()
    updates: dict[str, Any] = {"status": status, "updated_at": now}
    if admin_note is not None:
        updates["admin_note"] = _clean_note(admin_note)
    if effective_at is not None:
        updates["effective_at"] = effective_at

    event = _event(
        request_id,
        status,
        actor_id=_actor_id(user),
        actor_role=str(user.get("role") or "admin"),
        at=now,
        note=updates.get("admin_note"),
        changes={key: value for key, value in updates.items() if key != "updated_at"},
    )
    updated = _update_request_item(
        item,
        updates,
        event,
        expected_status=current,
        clear_open_guard=status in TERMINAL_STATUSES,
    )
    notification_service.emit_subscription_update(
        request_item=updated,
        recipient_id=str(updated.get("parent_id") or ""),
        recipient_role="parent",
        actor_id=_actor_id(user),
        actor_role=str(user.get("role") or "admin"),
    )
    return _request_response(updated)


def apply_request(
    *,
    request_id: str,
    admin_note: str | None,
    effective_at: str | None,
    user: dict[str, Any],
) -> dict[str, Any]:
    item = _get_request_item(request_id)
    if item.get("status") != "approved":
        raise HTTPException(status_code=409, detail="Only approved subscription requests can be applied")

    parent_id = item.get("parent_id")
    if not parent_id:
        raise HTTPException(status_code=400, detail="Subscription request is missing parent_id")
    _require_parent(parent_id)

    requested_tier = _normalize_tier(item.get("requested_tier"))
    now = now_iso()
    actor = _actor_id(user)
    updates = {
        "status": "applied",
        "updated_at": now,
        "effective_at": effective_at or item.get("effective_at") or now,
        "applied_at": now,
        "applied_by": actor,
    }
    if admin_note is not None:
        updates["admin_note"] = _clean_note(admin_note)
    event = _event(
        request_id,
        "applied",
        actor_id=actor,
        actor_role=str(user.get("role") or "admin"),
        at=now,
        note=updates.get("admin_note"),
        changes={"subscription_tier": requested_tier, "effective_at": updates["effective_at"]},
    )
    updated = _apply_request_item(
        item,
        parent_id=parent_id,
        requested_tier=requested_tier,
        updates=updates,
        event=event,
    )
    _record_manual_override(
        parent_id=parent_id,
        requested_tier=requested_tier,
        actor_id=actor,
        source_request_id=request_id,
        at=now,
    )
    notification_service.emit_subscription_update(
        request_item=updated,
        recipient_id=str(updated.get("parent_id") or ""),
        recipient_role="parent",
        actor_id=actor,
        actor_role=str(user.get("role") or "admin"),
    )
    return _request_response(updated)


def _request_pk(request_id: str) -> str:
    return f"SUBSCRIPTION_REQUEST#{request_id}"


def _open_guard_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"SUBSCRIPTION_OPEN#{parent_id}", "SK": "GUARD"}


def _event_sk(at: str, event_id: str) -> str:
    return f"EVENT#{at}#{event_id}"


def _require_parent(parent_id: str) -> dict[str, Any]:
    profile = user_repo.get_user(parent_id)
    if not profile or profile.get("role") != "parent":
        raise HTTPException(status_code=404, detail="Parent profile not found")
    return profile


def _get_request_item(request_id: str) -> dict[str, Any]:
    response = _subscription_get(
        get_table(), Key={"PK": _request_pk(request_id), "SK": "SUMMARY"}
    )
    item = _subscription_optional_item(response.get("Item"))
    if not item:
        raise HTTPException(status_code=404, detail="Subscription request not found")
    return item


def _list_requests(
    *,
    limit: int,
    status: str | None = None,
    requested_tier: str | None = None,
    parent_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    scan_kwargs: dict[str, Any] = dict(
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": REQUEST_ENTITY},
    )
    items: list[dict[str, Any]] = []
    while True:
        response = _subscription_scan(get_table(), **scan_kwargs)
        items.extend(
            item
            for item in _subscription_items(response)
            if item.get("SK") == "SUMMARY"
            and _matches(item, "status", status)
            and _matches(item, "requested_tier", requested_tier)
            and _matches(item, "parent_id", parent_id)
            and _within_dates(_optional_text(item.get("created_at")), date_from, date_to)
        )
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(
        items,
        key=lambda item: _optional_text(item.get("created_at")) or "",
        reverse=True,
    )[:limit]


def _latest_open_request(parent_id: str) -> dict[str, Any] | None:
    response = _subscription_get(get_table(), Key=_open_guard_key(parent_id))
    guard = _subscription_optional_item(response.get("Item"))
    if not guard or not guard.get("request_id"):
        return None
    item = _get_request_item(str(guard["request_id"]))
    if item.get("status") in OPEN_STATUSES:
        return item
    return None


def _list_events(request_id: str) -> list[dict[str, Any]]:
    response = _subscription_query(
        get_table(),
        KeyConditionExpression=Key("PK").eq(_request_pk(request_id)) & Key("SK").begins_with("EVENT#"),
    )
    return sorted(
        _subscription_items(response),
        key=lambda item: _optional_text(item.get("event_at")) or "",
    )


def _update_request_item(
    item: dict[str, Any],
    updates: dict[str, Any],
    event: dict[str, Any],
    *,
    expected_status: str,
    clear_open_guard: bool,
) -> dict[str, Any]:
    expression_names = {f"#{key}": key for key in updates}
    expression_values = {f":{key}": value for key, value in updates.items()}
    update_expression = "SET " + ", ".join(
        f"#{key} = :{key}" for key in updates
    )
    expression_names["#current_status"] = "status"
    expression_values[":current_status"] = expected_status
    event_item = {**event, "PK": item["PK"], "SK": _event_sk(event["event_at"], event["event_id"])}
    transaction = [
        {
            "Update": {
                "Key": {"PK": item["PK"], "SK": "SUMMARY"},
                "UpdateExpression": update_expression,
                "ExpressionAttributeNames": expression_names,
                "ExpressionAttributeValues": expression_values,
                "ConditionExpression": "#current_status = :current_status",
            }
        },
        {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
    ]
    if clear_open_guard:
        transaction.append({"Delete": {"Key": _open_guard_key(str(item["parent_id"]))}})
    try:
        _transact_write(transaction)
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Subscription request changed before update could be applied",
            ) from exc
        raise
    updated = {**item, **updates}
    updated["history"] = _list_events(updated["request_id"]) or updated.get("history") or [event]
    return updated


def _apply_request_item(
    item: dict[str, Any],
    *,
    parent_id: str,
    requested_tier: str,
    updates: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    expression_names = {f"#{key}": key for key in updates}
    expression_names["#current_status"] = "status"
    expression_values = {f":{key}": value for key, value in updates.items()}
    expression_values[":current_status"] = "approved"
    expression_values[":tier"] = requested_tier
    update_expression = "SET " + ", ".join(f"#{key} = :{key}" for key in updates)
    event_item = {**event, "PK": item["PK"], "SK": _event_sk(event["event_at"], event["event_id"])}
    profile = _require_parent(parent_id)
    try:
        _transact_write(
            [
                *_versioned_profile_operations(
                    parent_id,
                    profile=profile,
                    update_expression="SET subscription_tier = :tier",
                    expression_attribute_values={":tier": requested_tier},
                ),
                {
                    "Update": {
                        "Key": {"PK": item["PK"], "SK": "SUMMARY"},
                        "UpdateExpression": update_expression,
                        "ExpressionAttributeNames": expression_names,
                        "ExpressionAttributeValues": expression_values,
                        "ConditionExpression": "#current_status = :current_status",
                    }
                },
                {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Delete": {"Key": _open_guard_key(parent_id)}},
            ]
        )
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(
                status_code=409,
                detail="Subscription request changed before apply could complete",
            ) from exc
        raise
    updated = {**item, **updates}
    updated["history"] = _list_events(updated["request_id"]) or updated.get("history") or [event]
    return updated


@overload
def _request_response(item: None) -> None: ...


@overload
def _request_response(item: dict[str, Any]) -> dict[str, Any]: ...


def _request_response(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    history = [
        {
            "eventId": event.get("event_id"),
            "eventAt": event.get("event_at"),
            "eventType": event.get("event_type"),
            "actorId": event.get("actor_id"),
            "actorRole": event.get("actor_role"),
            "note": event.get("note"),
            "changes": event.get("changes") or {},
        }
        for event in item.get("history") or []
    ]
    return {
        "requestId": item.get("request_id"),
        "parentId": item.get("parent_id"),
        "studentId": item.get("student_id"),
        "currentTier": item.get("current_tier"),
        "requestedTier": item.get("requested_tier"),
        "requestType": item.get("request_type"),
        "status": item.get("status"),
        "source": item.get("source"),
        "parentNote": item.get("parent_note"),
        "adminNote": item.get("admin_note"),
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "effectiveAt": item.get("effective_at"),
        "appliedAt": item.get("applied_at"),
        "appliedBy": item.get("applied_by"),
        "history": history,
    }


def _billing_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"SUBSCRIPTION_BILLING#{parent_id}", "SK": "SUMMARY"}


def _billing_event_sk(at: str, event_id: str) -> str:
    return f"EVENT#{at}#{event_id}"


def _provider_event_key(event_id: str) -> dict[str, str]:
    return {"PK": f"BILLING_PROVIDER_EVENT#stripe#{event_id}", "SK": "SUMMARY"}


def _provider_lookup_key(provider: str, object_type: str, object_id: str) -> dict[str, str]:
    return {
        "PK": f"BILLING_PROVIDER_LOOKUP#{provider}#{object_type}#{object_id}",
        "SK": "SUMMARY",
    }


def _payment_rollout_key() -> dict[str, str]:
    return {"PK": "SUBSCRIPTION_PAYMENT_ROLLOUT", "SK": "SUMMARY"}


def _refund_idempotency_key(parent_id: str, idempotency_key: str) -> dict[str, str]:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return {
        "PK": f"BILLING_REFUND_IDEMPOTENCY#{parent_id}#{digest}",
        "SK": "SUMMARY",
    }


def _get_billing_item(parent_id: str) -> dict[str, Any] | None:
    response = _subscription_get(get_table(), Key=_billing_key(parent_id))
    item = _subscription_optional_item(response.get("Item"))
    return dict(item) if item else None


def _list_billing_events(parent_id: str, limit: int = 25) -> list[dict[str, Any]]:
    response = _subscription_query(
        get_table(),
        KeyConditionExpression=Key("PK").eq(_billing_key(parent_id)["PK"]) & Key("SK").begins_with("EVENT#"),
    )
    events = sorted(
        _subscription_items(response),
        key=lambda item: _optional_text(item.get("event_at")) or "",
        reverse=True,
    )
    return events[:limit]


def _billing_response(
    item: dict[str, Any] | None,
    *,
    parent_id: str,
    include_events: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if item is None:
        readiness = get_billing_readiness(settings) if settings else None
        response = {
            "parentId": parent_id,
            "provider": None,
            "mode": "manual",
            "status": "none",
            "subscriptionTier": SubscriptionTier.FREE_TRIAL.value,
            "requestedTier": None,
            "providerCustomerId": None,
            "providerSubscriptionId": None,
            "providerPriceId": None,
            "checkoutSessionId": None,
            "checkoutUrl": None,
            "providerLivemode": None,
            "readiness": readiness or {},
            "twint": (readiness or {}).get("twint", {}),
            "paymentMethodType": None,
            "latestInvoice": {},
            "refund": _refund_readiness(None),
            "dunning": _dunning_projection(None),
            "accountingHandoff": _accounting_handoff(None, parent_id=parent_id),
            "currentPeriodStart": None,
            "currentPeriodEnd": None,
            "cancelAtPeriodEnd": False,
            "lastProviderEventId": None,
            "lastProviderEventType": None,
            "lastProviderEventAt": None,
            "manualOverrideAt": None,
            "manualOverrideBy": None,
            "manualOverrideSource": None,
            "updatedAt": None,
        }
    else:
        persisted_readiness = _stored_readiness(item)
        response = {
            "parentId": parent_id,
            "provider": item.get("billing_provider"),
            "mode": item.get("billing_mode") or "manual",
            "status": item.get("billing_status") or "none",
            "subscriptionTier": (
                item.get("subscription_tier") or SubscriptionTier.FREE_TRIAL.value
            ),
            "requestedTier": item.get("requested_tier"),
            "providerCustomerId": item.get("provider_customer_id"),
            "providerSubscriptionId": item.get("provider_subscription_id"),
            "providerPriceId": item.get("provider_price_id"),
            "checkoutSessionId": item.get("checkout_session_id"),
            "checkoutUrl": item.get("checkout_url"),
            "providerLivemode": item.get("provider_livemode"),
            "readiness": persisted_readiness,
            "environmentReadiness": get_billing_readiness(settings) if settings else {},
            "twint": _stored_twint(item),
            "paymentMethodType": item.get("payment_method_type"),
            "latestInvoice": item.get("latest_invoice") or {},
            "refund": item.get("refund_summary") or _refund_readiness(item),
            "dunning": item.get("dunning") or _dunning_projection(item),
            "accountingHandoff": item.get("accounting_handoff")
            or _accounting_handoff(item, parent_id=parent_id),
            "currentPeriodStart": item.get("current_period_start"),
            "currentPeriodEnd": item.get("current_period_end"),
            "cancelAtPeriodEnd": bool(item.get("cancel_at_period_end") or False),
            "lastProviderEventId": item.get("last_provider_event_id"),
            "lastProviderEventType": item.get("last_provider_event_type"),
            "lastProviderEventAt": item.get("last_provider_event_at"),
            "manualOverrideAt": item.get("manual_override_at"),
            "manualOverrideBy": item.get("manual_override_by"),
            "manualOverrideSource": item.get("manual_override_source"),
            "updatedAt": item.get("updated_at"),
        }
    if include_events:
        response["events"] = [
            {
                "eventId": event.get("event_id"),
                "eventAt": event.get("event_at"),
                "eventType": event.get("event_type"),
                "provider": event.get("provider"),
                "providerMode": event.get("provider_mode"),
                "providerLivemode": event.get("provider_livemode"),
                "billingStatus": event.get("billing_status"),
                "processingResult": event.get("processing_result"),
                "idempotencyStatus": event.get("idempotency_status"),
                "requestId": event.get("request_id"),
                "correlationId": event.get("correlation_id"),
                "requestedTier": event.get("requested_tier"),
                "providerEventId": event.get("provider_event_id"),
                "providerEventAt": event.get("provider_event_at"),
                "paymentMethodType": event.get("payment_method_type"),
                "twintStatus": event.get("twint_status"),
            }
            for event in _list_billing_events(parent_id)
        ]
    response["supportEvidence"] = _billing_support_evidence(response)
    return response


def _billing_support_evidence(response: dict[str, Any]) -> dict[str, Any]:
    events = response.get("events") or []
    duplicate_count = sum(1 for event in events if event.get("processingResult") == "deduplicated")
    stale_count = sum(1 for event in events if event.get("processingResult") == "stale_ignored")
    invoice = response.get("latestInvoice") or {}
    refund = response.get("refund") or {}
    dunning = response.get("dunning") or {}
    status = response.get("status") or "none"
    mode = response.get("mode") or "manual"
    source = "manual_override" if status == "manual_override" or mode == "manual" else "provider_billing"
    if status == "none":
        source = "none"
    return {
        "lifecycle": {
            "status": status,
            "mode": mode,
            "subscriptionTier": response.get("subscriptionTier"),
            "requestedTier": response.get("requestedTier"),
            "source": source,
            "cancelAtPeriodEnd": bool(response.get("cancelAtPeriodEnd") or False),
            "manualOverride": {
                "active": status == "manual_override",
                "source": response.get("manualOverrideSource"),
                "appliedBy": response.get("manualOverrideBy"),
                "appliedAt": response.get("manualOverrideAt"),
            },
        },
        "invoice": {
            "providerInvoiceId": invoice.get("providerInvoiceId"),
            "providerSubscriptionId": response.get("providerSubscriptionId") or invoice.get("providerSubscriptionId"),
            "providerChargeId": invoice.get("providerChargeId"),
            "providerPaymentIntentId": invoice.get("providerPaymentIntentId"),
            "currency": invoice.get("currency"),
            "amountPaid": invoice.get("amountPaid"),
            "amountRemaining": invoice.get("amountRemaining"),
            "amountRefunded": invoice.get("amountRefunded"),
            "periodStart": invoice.get("periodStart") or response.get("currentPeriodStart"),
            "periodEnd": invoice.get("periodEnd") or response.get("currentPeriodEnd"),
            "reconciliationId": invoice.get("reconciliationId") or invoice.get("providerInvoiceId"),
        },
        "refund": {
            "state": refund.get("state"),
            "providerRefundId": refund.get("providerRefundId"),
            "eligibleAmount": refund.get("eligibleAmount"),
            "refundedAmount": refund.get("refundedAmount"),
            "providerHandoffState": refund.get("providerHandoffState"),
            "requestedBy": refund.get("requestedBy"),
            "requestedAt": refund.get("requestedAt"),
        },
        "dunning": {
            "state": dunning.get("state"),
            "supportAction": dunning.get("supportAction"),
            "nextPaymentAttempt": dunning.get("nextPaymentAttempt"),
            "paymentMethodType": dunning.get("paymentMethodType") or response.get("paymentMethodType"),
        },
        "reconciliation": {
            "lastProviderEventId": response.get("lastProviderEventId"),
            "lastProviderEventType": response.get("lastProviderEventType"),
            "lastProviderEventAt": response.get("lastProviderEventAt"),
            "eventCount": len(events),
            "duplicateEvents": duplicate_count,
            "staleIgnoredEvents": stale_count,
            "latestProcessingResult": events[0].get("processingResult") if events else None,
        },
    }


def _stored_readiness(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": item.get("readiness_state"),
        "blockers": item.get("readiness_blockers") or [],
    }


def _stored_twint(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "inScope": bool(item.get("twint_in_scope")),
        "status": item.get("twint_status"),
    }


def get_billing_readiness(settings: Settings) -> dict[str, Any]:
    api_key = settings.stripe_api_key.strip()
    webhook_secret = settings.stripe_webhook_secret.strip()
    student_price = settings.stripe_student_price_id.strip()
    teacher_supported_price = settings.stripe_teacher_supported_price_id.strip()
    family_price = settings.stripe_family_price_id.strip()
    blockers: list[str] = []
    warnings: list[str] = []
    sdk_available = _stripe_sdk_available()
    rollout = get_payment_rollout_controls(settings)

    if settings.is_production:
        if not api_key:
            blockers.append("missing_stripe_api_key")
        elif not api_key.startswith("sk_live_"):
            blockers.append("stripe_api_key_not_live")
        if not webhook_secret:
            blockers.append("missing_stripe_webhook_secret")
        if not student_price:
            blockers.append("missing_student_price_id")
        if not teacher_supported_price:
            blockers.append("missing_teacher_supported_price_id")
        if not family_price:
            blockers.append("missing_family_price_id")
        if not sdk_available:
            blockers.append("stripe_sdk_missing")
        if blockers:
            state = "not_configured"
        elif not _rollout_state_allows(rollout["checkout"]["state"]):
            state = "live_ready_but_blocked"
        else:
            state = "live_enabled"
    else:
        state = "test"
        if api_key.startswith("sk_live_"):
            warnings.append("live_key_present_outside_production")

    twint_status = "disabled"
    if settings.stripe_twint_enabled:
        if not settings.stripe_twint_capability_confirmed:
            twint_status = "capability_unconfirmed"
        elif settings.is_production and state != "live_enabled":
            twint_status = "blocked_by_live_gate"
        else:
            twint_status = "eligible"

    return {
        "state": state,
        "mode": "live" if state in {"live_ready_but_blocked", "live_enabled"} else "test",
        "livemode": state in {"live_ready_but_blocked", "live_enabled"},
        "checkoutAllowed": not settings.is_production or state == "live_enabled",
        "liveChargesEnabled": _rollout_state_allows(rollout["checkout"]["state"]),
        "rollout": rollout,
        "blockers": blockers,
        "warnings": warnings,
        "configured": {
            "apiKey": _redacted_presence(api_key),
            "webhookSecret": _redacted_presence(webhook_secret),
            "studentPrice": _redacted_presence(student_price),
            "teacherSupportedPrice": _redacted_presence(teacher_supported_price),
            "familyPrice": _redacted_presence(family_price),
            "webOrigins": bool(settings.stripe_checkout_web_origins),
            "resultPath": bool(settings.stripe_checkout_result_path),
            "stripeSdk": sdk_available,
        },
        "twint": {
            "inScope": True,
            "enabled": bool(settings.stripe_twint_enabled),
            "capabilityConfirmed": bool(settings.stripe_twint_capability_confirmed),
            "status": twint_status,
        },
    }


def _provider_mode(settings: Settings, readiness: dict[str, Any] | None = None) -> str:
    readiness = readiness or get_billing_readiness(settings)
    if readiness["state"] in {"live_ready_but_blocked", "live_enabled"}:
        return "live"
    return "test"


def _require_checkout_allowed(readiness: dict[str, Any], settings: Settings) -> None:
    if readiness["checkoutAllowed"]:
        return
    detail = {
        "message": "Live checkout is not enabled",
        "readiness": readiness,
    }
    status_code = 503 if readiness["state"] == "not_configured" else 409
    raise HTTPException(status_code=status_code, detail=detail)


def _stripe_sdk_available() -> bool:
    return find_spec("stripe") is not None


def _load_stripe_sdk() -> Any:
    try:
        return importlib.import_module("stripe")
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Stripe SDK is not installed") from exc


def _redacted_presence(value: str) -> str:
    return "configured" if value else "missing"


def _api_key_mode(api_key: str) -> str:
    if not api_key:
        return "missing"
    if api_key.startswith("sk_live_"):
        return "live"
    if api_key.startswith("sk_test_"):
        return "test"
    return "unknown"


def _retrieve_stripe_account(settings: Settings) -> dict[str, Any]:
    stripe = _load_stripe_sdk()
    stripe.api_key = settings.stripe_api_key
    account = stripe.Account.retrieve()
    return _stripe_object_to_dict(account)


def _retrieve_stripe_price(price_id: str, settings: Settings) -> dict[str, Any]:
    stripe = _load_stripe_sdk()
    stripe.api_key = settings.stripe_api_key
    price = stripe.Price.retrieve(price_id)
    return _stripe_object_to_dict(price)


def _create_provider_refund(
    *,
    provider_charge_id: str,
    provider_payment_intent_id: str,
    amount: int,
    reason: str,
    idempotency_key: str,
    settings: Settings,
) -> dict[str, Any]:
    stripe = _load_stripe_sdk()
    stripe.api_key = settings.stripe_api_key
    create_kwargs: dict[str, Any] = {
        "amount": amount,
        "metadata": {
            "stoa_operator_reason": reason,
            "stoa_idempotency_key": idempotency_key,
        },
    }
    if provider_charge_id:
        create_kwargs["charge"] = provider_charge_id
    else:
        create_kwargs["payment_intent"] = provider_payment_intent_id
    refund = stripe.Refund.create(**create_kwargs, idempotency_key=idempotency_key)
    return _stripe_object_to_dict(refund)


def _stripe_capability_status(account: dict[str, Any], capability: str) -> str:
    capabilities = account.get("capabilities") or {}
    status = capabilities.get(capability)
    if status in {"active", "inactive", "pending"}:
        return str(status)
    return "unknown"


def _price_readiness(tier: str, price_id: str, *, settings: Settings) -> dict[str, Any]:
    configured = bool(price_id.strip())
    blockers: list[str] = []
    if settings.is_production and not configured:
        blockers.append(f"missing_{tier}_price_id")
    return {
        "tier": tier,
        "configured": configured,
        "priceId": _redacted_identifier(price_id),
        "providerLookup": "not_checked",
        "currency": None,
        "recurring": None,
        "livemode": None,
        "active": None,
        "blockers": blockers,
        "warnings": [],
    }


def _provider_price_readiness(price: dict[str, Any]) -> dict[str, Any]:
    currency = str(price.get("currency") or "").upper() or None
    recurring = bool(price.get("recurring"))
    livemode = bool(price.get("livemode"))
    active = bool(price.get("active", True))
    blockers: list[str] = []
    if currency != "CHF":
        blockers.append("price_currency_not_chf")
    if not recurring:
        blockers.append("price_not_recurring")
    if not livemode:
        blockers.append("price_not_live")
    if not active:
        blockers.append("price_not_active")
    return {
        "providerLookup": "verified",
        "currency": currency,
        "recurring": recurring,
        "livemode": livemode,
        "active": active,
        "blockers": blockers,
        "warnings": [],
    }


def _provider_twint_readiness(
    *,
    local_twint: dict[str, Any],
    capability_status: str,
    settings: Settings,
    provider_checked: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    enabled = bool(local_twint.get("enabled"))
    capability_confirmed = bool(local_twint.get("capabilityConfirmed"))
    status = "disabled"
    if enabled:
        if not capability_confirmed:
            status = "capability_unconfirmed"
            blockers.append("twint_capability_unconfirmed")
        elif provider_checked and capability_status in {"pending", "inactive"}:
            status = capability_status
            blockers.append(f"twint_capability_{capability_status}")
        elif provider_checked and capability_status == "active":
            status = "eligible" if settings.stripe_live_charges_enabled else "blocked_by_live_gate"
        elif settings.is_production:
            status = "unknown"
            blockers.append("twint_capability_unknown")
        else:
            status = str(local_twint.get("status") or "eligible")

    return {
        "inScope": True,
        "enabled": enabled,
        "capabilityConfirmed": capability_confirmed,
        "providerCapability": capability_status,
        "status": status,
        "constraints": {
            "customerLocation": "CH",
            "currency": "CHF",
            "maximumAmount": 500000,
            "maximumAmountCurrency": "CHF",
            "recurringSupported": True,
            "manualCaptureSupported": False,
            "refundsSupported": True,
            "partialRefundsSupported": True,
            "refundWindowDays": 180,
            "merchantOnboardingRequired": [
                "functional_public_website",
                "visible_legal_and_contact_information",
                "checkout_prices_in_chf",
            ],
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _webhook_readiness(settings: Settings) -> dict[str, Any]:
    endpoint = settings.stripe_webhook_endpoint_url.strip()
    endpoint_configured = bool(endpoint)
    endpoint_https = endpoint.startswith("https://")
    blockers: list[str] = []
    warnings: list[str] = []
    if settings.is_production and not endpoint_configured:
        blockers.append("missing_stripe_webhook_endpoint_url")
    elif endpoint_configured and not endpoint_https:
        blockers.append("stripe_webhook_endpoint_not_https")
    if settings.is_production and not settings.stripe_webhook_secret.strip():
        blockers.append("missing_stripe_webhook_secret")
    last_event = _last_observed_provider_event()
    return {
        "endpointConfigured": endpoint_configured,
        "endpointMode": "https" if endpoint_https else "missing" if not endpoint_configured else "non_https",
        "signingSecretConfigured": bool(settings.stripe_webhook_secret.strip()),
        "requiredEventTypes": sorted(PROVIDER_EVENT_TYPES),
        "quickAckExpected": True,
        "lastObservedProviderEventAt": last_event.get("eventAt"),
        "lastObservedEventType": last_event.get("eventType"),
        "blockers": blockers,
        "warnings": warnings,
    }


def _last_observed_provider_event() -> dict[str, Any]:
    response = _subscription_scan(
        get_table(),
        FilterExpression="entity_type = :entity",
        ExpressionAttributeValues={":entity": BILLING_EVENT_ENTITY},
    )
    events = [
        item
        for item in _subscription_items(response)
        if item.get("provider") == "stripe" and item.get("event_type") in PROVIDER_EVENT_TYPES
    ]
    if not events:
        return {"eventAt": None, "eventType": None}
    latest = sorted(
        events,
        key=lambda item: _optional_text(item.get("event_at")) or "",
        reverse=True,
    )[0]
    return {
        "eventAt": latest.get("event_at"),
        "eventType": latest.get("event_type"),
    }


def _provider_refund_capability_readiness(
    *,
    local: dict[str, Any],
    twint: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    mutation_configured = bool(settings.stripe_refunds_enabled)
    return {
        "provider": "stripe",
        "mutationConfigured": mutation_configured,
        "eligibleWhenBillingState": ["active", "past_due", "payment_failed"],
        "requiresProviderReference": True,
        "requiresOperatorReason": True,
        "requiresIdempotencyKey": True,
        "twintRefundWindowDays": twint["constraints"]["refundWindowDays"],
        "blockers": [] if mutation_configured else ["direct_refund_execution_not_enabled"],
        "warnings": [] if local.get("livemode") else ["refund_readiness_requires_live_provider_mode"],
    }


def _get_payment_rollout_item() -> dict[str, Any]:
    try:
        response = _subscription_get(get_table(), Key=_payment_rollout_key())
        item = _subscription_optional_item(response.get("Item"))
    except Exception:
        return {}
    return dict(item) if item else {}


def _rollout_state_allows(state: str) -> bool:
    return state == "enabled"


def _activation_state_from_rollout(checkout_state: str, refunds_state: str) -> str:
    states = {checkout_state, refunds_state}
    if "enabled" in states:
        return "activated"
    if "canary" in states:
        return "approved_canary_only"
    if "rolled_back" in states:
        return "blocked"
    return "deferred"


def _finance_readiness() -> dict[str, Any]:
    return {
        "accountingExportAvailable": True,
        "invoiceMetadataAvailable": True,
        "refundMetadataAvailable": True,
        "taxMetadataAvailable": True,
        "dunningMetadataAvailable": True,
        "reconciliationMetadataAvailable": True,
        "blockers": [],
        "warnings": [],
    }


def _redacted_identifier(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) <= 8:
        return "configured"
    return f"...{cleaned[-6:]}"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _create_provider_checkout_session(
    *,
    checkout_ref: str,
    provider_idempotency_key: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    settings: Settings,
) -> dict[str, Any]:
    stripe = _load_stripe_sdk()
    stripe.api_key = settings.stripe_api_key
    metadata = {"stoa_checkout_ref": checkout_ref}
    create_kwargs: dict[str, Any] = {
        "mode": "subscription",
        "client_reference_id": checkout_ref,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "idempotency_key": provider_idempotency_key,
    }
    session = stripe.checkout.Session.create(**create_kwargs)
    session_dict = _stripe_object_to_dict(session)
    session_id = str(session_dict.get("id") or "")
    checkout_url = str(session_dict.get("url") or "")
    return {
        "id": session_id,
        "url": checkout_url,
        "livemode": session_dict.get("livemode"),
    }


def _stripe_object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict_recursive", None)
    if callable(to_dict):
        converted = to_dict()
        return converted if isinstance(converted, dict) else {}
    return dict(value) if hasattr(value, "keys") else {}


def _checkout_payment_method_types(readiness: dict[str, Any]) -> list[str] | None:
    twint = readiness.get("twint") or {}
    if twint.get("enabled") and twint.get("capabilityConfirmed") and twint.get("status") == "eligible":
        return ["card", "twint"]
    return None


def _price_id_for_tier(tier: str, settings: Settings) -> str:
    configured = {
        SubscriptionTier.STUDENT.value: settings.stripe_student_price_id,
        SubscriptionTier.TEACHER_SUPPORTED.value: settings.stripe_teacher_supported_price_id,
        SubscriptionTier.FAMILY.value: settings.stripe_family_price_id,
    }[tier]
    return configured or f"price_test_stoa_{tier}_monthly"


def _checkout_url(session_id: str) -> str:
    return f"https://checkout.stripe.com/c/pay/{session_id}"


def _put_billing_event(parent_id: str, event: dict[str, Any]) -> None:
    item = {
        **event,
        "PK": _billing_key(parent_id)["PK"],
        "SK": _billing_event_sk(str(event["event_at"]), str(event["event_id"])),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
    }
    _subscription_put(get_table(), Item=item)


def _put_provider_lookup_rows(
    *,
    parent_id: str,
    provider_mode: str,
    livemode: bool,
    created_at: str,
    **provider_ids: Any,
) -> list[dict[str, Any]]:
    rows = []
    for object_type, object_id in provider_ids.items():
        normalized = _provider_id_value(object_id)
        if not normalized:
            continue
        rows.append(
            {
                **_provider_lookup_key("stripe", object_type, normalized),
                "entity_type": BILLING_PROVIDER_LOOKUP_ENTITY,
                "provider": "stripe",
                "object_type": object_type,
                "object_id": normalized,
                "parent_id": parent_id,
                "provider_mode": provider_mode,
                "provider_livemode": livemode,
                "created_at": created_at,
            }
        )
    for row in rows:
        _subscription_put(get_table(), Item=row)
    return rows


def _provider_lookup_rows_for_event(
    *,
    parent_id: str,
    provider_mode: str,
    livemode: bool,
    event_object: dict[str, Any],
    created_at: str,
) -> list[dict[str, Any]]:
    return [
        {
            **_provider_lookup_key("stripe", object_type, object_id),
            "entity_type": BILLING_PROVIDER_LOOKUP_ENTITY,
            "provider": "stripe",
            "object_type": object_type,
            "object_id": object_id,
            "parent_id": parent_id,
            "provider_mode": provider_mode,
            "provider_livemode": livemode,
            "created_at": created_at,
        }
        for object_type, object_id in _provider_object_ids(event_object).items()
    ]


def _provider_event_seen(event_id: str) -> bool:
    response = _subscription_get(get_table(), Key=_provider_event_key(event_id))
    return _subscription_optional_item(response.get("Item")) is not None


def _parse_provider_event(
    payload: bytes,
    signature_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    if settings.stripe_webhook_secret:
        if _stripe_sdk_available():
            stripe = _load_stripe_sdk()
            try:
                event = stripe.Webhook.construct_event(
                    payload,
                    signature_header,
                    settings.stripe_webhook_secret,
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Stripe signature verification failed") from exc
            return _stripe_object_to_dict(event)
        _verify_stripe_signature(payload, signature_header, settings.stripe_webhook_secret)
    elif settings.is_production or not settings.stripe_allow_unsigned_test_webhooks:
        raise HTTPException(status_code=400, detail="Stripe webhook signing secret is required")
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid provider event payload") from exc
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Provider event must be a JSON object")
    return event


def _verify_stripe_signature(payload: bytes, signature_header: str | None, secret: str) -> None:
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")
    parts: dict[str, list[str]] = {}
    for raw_part in signature_header.split(","):
        if "=" not in raw_part:
            continue
        key, value = raw_part.split("=", 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    timestamp_values = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamp_values or not signatures:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature header")
    try:
        timestamp = int(timestamp_values[0])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature timestamp") from exc
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(status_code=400, detail="Stripe signature timestamp is outside tolerance")
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise HTTPException(status_code=400, detail="Stripe signature verification failed")


def _parent_id_from_provider_object(event_object: dict[str, Any]) -> str | None:
    metadata = event_object.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return (
        metadata.get("stoa_parent_id")
        or metadata.get("parent_id")
        or event_object.get("client_reference_id")
    )


def _find_parent_id_for_provider_object(event_object: dict[str, Any]) -> str | None:
    ids = _provider_object_ids(event_object)
    for object_type, object_id in ids.items():
        response = _subscription_get(
            get_table(),
            Key=_provider_lookup_key("stripe", object_type, object_id),
        )
        lookup = _subscription_optional_item(response.get("Item"))
        if lookup and lookup.get("parent_id"):
            return str(lookup["parent_id"])
    customer_id = ids.get("customer")
    subscription_id = ids.get("subscription")
    session_id = ids.get("checkout_session")
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": "entity_type = :entity",
        "ExpressionAttributeValues": {":entity": BILLING_ENTITY},
    }
    while True:
        response = _subscription_scan(get_table(), **scan_kwargs)
        for item in _subscription_items(response):
            if item.get("SK") != "SUMMARY":
                continue
            if customer_id and item.get("provider_customer_id") == customer_id:
                return str(item.get("parent_id"))
            if subscription_id and item.get("provider_subscription_id") == subscription_id:
                return str(item.get("parent_id"))
            if session_id and item.get("checkout_session_id") == session_id:
                return str(item.get("parent_id"))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return None


def _provider_object_ids(event_object: dict[str, Any]) -> dict[str, str]:
    object_type = str(event_object.get("object") or "")
    ids: dict[str, str] = {
        "customer": _provider_id_value(event_object.get("customer")),
        "subscription": _provider_id_value(event_object.get("subscription")),
        "invoice": _provider_id_value(event_object.get("invoice")),
        "payment_intent": _provider_id_value(event_object.get("payment_intent")),
        "charge": _provider_id_value(event_object.get("charge") or event_object.get("latest_charge")),
        "refund": _provider_id_value(event_object.get("refund")),
    }
    if object_type == "checkout.session":
        ids["checkout_session"] = _provider_id_value(event_object.get("id"))
    if object_type == "subscription":
        ids["subscription"] = _provider_id_value(event_object.get("id"))
    if object_type == "invoice":
        ids["invoice"] = _provider_id_value(event_object.get("id"))
    if object_type == "payment_intent":
        ids["payment_intent"] = _provider_id_value(event_object.get("id"))
    if object_type == "charge":
        ids["charge"] = _provider_id_value(event_object.get("id"))
    if object_type == "refund":
        ids["refund"] = _provider_id_value(event_object.get("id"))
    return {key: value for key, value in ids.items() if value}


def _provider_id_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("id")
    cleaned = str(value or "").strip()
    return cleaned


def _billing_transition(
    event_type: str,
    event_object: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    metadata_value = event_object.get("metadata")
    metadata: Mapping[str, object] = (
        metadata_value if isinstance(metadata_value, Mapping) else {}
    )
    requested_tier = _normalize_tier(metadata.get("requested_tier") or existing.get("requested_tier"))
    status = existing.get("billing_status") or "none"
    subscription_tier = None
    if event_type == "checkout.session.completed":
        status = "checkout_pending"
    elif event_type == "checkout.session.expired":
        previous_status = existing.get("previous_billing_status")
        if previous_status and previous_status != "checkout_pending":
            status = previous_status
            subscription_tier = existing.get("previous_subscription_tier")
        elif existing.get("billing_status") == "checkout_pending":
            status = "canceled"
    elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        status = _status_from_provider_subscription(event_object.get("status"))
    elif event_type == "customer.subscription.deleted":
        status = "canceled"
    elif event_type == "invoice.paid":
        status = "active"
    elif event_type == "invoice.payment_failed":
        status = "payment_failed"
    elif event_type in {"charge.refunded", "refund.created", "refund.updated"}:
        status = existing.get("billing_status") or "provider_unknown"
    elif event_type == "refund.failed":
        status = existing.get("billing_status") or "provider_unknown"
    elif event_type == "customer.updated":
        status = existing.get("billing_status") or "provider_unknown"
    invoice = _invoice_from_provider_object(event_type, event_object, existing)
    refund = _refund_from_provider_object(event_type, event_object, existing)
    invoice_period = _invoice_period(event_object) if str(event_object.get("object") or "") == "invoice" else {}
    return {
        "billing_status": status,
        "subscription_tier": subscription_tier,
        "requested_tier": requested_tier,
        "provider_customer_id": event_object.get("customer") or existing.get("provider_customer_id"),
        "provider_subscription_id": event_object.get("subscription")
        or (event_object.get("id") if str(event_object.get("object") or "") == "subscription" else None)
        or existing.get("provider_subscription_id"),
        "provider_price_id": _price_from_provider_object(event_object) or existing.get("provider_price_id"),
        "checkout_session_id": event_object.get("id")
        if str(event_object.get("object") or "") == "checkout.session"
        else existing.get("checkout_session_id"),
        "current_period_start": _timestamp_to_iso(event_object.get("current_period_start"))
        or invoice_period.get("start")
        or existing.get("current_period_start"),
        "current_period_end": _timestamp_to_iso(event_object.get("current_period_end"))
        or invoice_period.get("end")
        or existing.get("current_period_end"),
        "cancel_at_period_end": bool(event_object.get("cancel_at_period_end") or False),
        "payment_method_type": _selected_payment_method_type_from_provider_object(event_object)
        or existing.get("payment_method_type"),
        "latest_invoice": invoice,
        "refund": refund,
        "next_payment_attempt": _timestamp_to_iso(event_object.get("next_payment_attempt")),
    }


def _selected_payment_method_type_from_provider_object(event_object: dict[str, Any]) -> str | None:
    payment_method = event_object.get("payment_method")
    if isinstance(payment_method, dict):
        payment_method_type = payment_method.get("type")
        return str(payment_method_type) if payment_method_type else None
    payment_method_details = event_object.get("payment_method_details")
    if isinstance(payment_method_details, dict):
        payment_method_type = payment_method_details.get("type")
        return str(payment_method_type) if payment_method_type else None
    return None


def _invoice_from_provider_object(
    event_type: str,
    event_object: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    current = dict(existing.get("latest_invoice") or {})
    object_type = str(event_object.get("object") or "")
    if object_type != "invoice" and not event_object.get("invoice"):
        return current
    invoice = event_object if object_type == "invoice" else {}
    provider_invoice_id = _provider_id_value(invoice.get("id") or event_object.get("invoice"))
    if not provider_invoice_id:
        return current
    period = _invoice_period(invoice)
    invoice_status = invoice.get("status")
    if event_type == "invoice.paid" and not invoice_status:
        invoice_status = "paid"
    elif event_type == "invoice.payment_failed" and not invoice_status:
        invoice_status = "payment_failed"
    payment_method_type = _selected_payment_method_type_from_provider_object(invoice)
    return {
        **current,
        "providerInvoiceId": provider_invoice_id,
        "providerSubscriptionId": _provider_id_value(invoice.get("subscription"))
        or current.get("providerSubscriptionId")
        or existing.get("provider_subscription_id"),
        "providerPaymentIntentId": _provider_id_value(invoice.get("payment_intent"))
        or current.get("providerPaymentIntentId"),
        "providerChargeId": _provider_id_value(invoice.get("charge") or invoice.get("latest_charge"))
        or current.get("providerChargeId"),
        "hostedInvoiceUrl": invoice.get("hosted_invoice_url") or current.get("hostedInvoiceUrl"),
        "receiptUrl": invoice.get("receipt_url") or current.get("receiptUrl"),
        "invoiceStatus": invoice_status or current.get("invoiceStatus"),
        "currency": str(invoice.get("currency") or current.get("currency") or "chf").upper(),
        "amountDue": _amount_value(invoice.get("amount_due"), current.get("amountDue")),
        "amountPaid": _amount_value(invoice.get("amount_paid"), current.get("amountPaid")),
        "amountRemaining": _amount_value(invoice.get("amount_remaining"), current.get("amountRemaining")),
        "amountRefunded": _amount_value(invoice.get("amount_refunded"), current.get("amountRefunded")),
        "taxAmount": _amount_value(invoice.get("tax"), current.get("taxAmount")),
        "taxStatus": "provider_managed" if "tax" in invoice or invoice.get("automatic_tax") else "provider_managed",
        "periodStart": period.get("start") or current.get("periodStart"),
        "periodEnd": period.get("end") or current.get("periodEnd"),
        "paymentMethodType": payment_method_type or current.get("paymentMethodType"),
        "reconciliationId": invoice.get("number") or provider_invoice_id,
    }


def _invoice_period(invoice: dict[str, Any]) -> dict[str, str | None]:
    lines = ((invoice.get("lines") or {}).get("data") or []) if isinstance(invoice.get("lines"), dict) else []
    line_period = lines[0].get("period") if lines and isinstance(lines[0], dict) else {}
    if not isinstance(line_period, dict):
        line_period = {}
    return {
        "start": _timestamp_to_iso(invoice.get("period_start") or line_period.get("start")),
        "end": _timestamp_to_iso(invoice.get("period_end") or line_period.get("end")),
    }


def _refund_from_provider_object(
    event_type: str,
    event_object: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any] | None:
    if event_type not in {"charge.refunded", "refund.created", "refund.updated", "refund.failed"}:
        return None
    current = dict(existing.get("refund_summary") or {})
    refund_id = _provider_id_value(event_object.get("refund") or event_object.get("id"))
    provider_charge_id = _provider_id_value(event_object.get("charge") or event_object.get("latest_charge"))
    amount = _amount_value(
        event_object.get("amount_refunded") or event_object.get("amount"),
        current.get("refundedAmount"),
    )
    status = str(event_object.get("status") or "").strip()
    if event_type == "charge.refunded":
        provider_state = "succeeded"
    elif event_type == "refund.failed":
        provider_state = "failed"
    elif status in {"succeeded", "failed", "canceled", "cancelled"}:
        provider_state = "cancelled" if status == "canceled" else status
    else:
        provider_state = "requested"
    return {
        **current,
        "state": provider_state,
        "providerHandoffState": provider_state,
        "refundedAmount": amount,
        "currency": str(event_object.get("currency") or current.get("currency") or "chf").upper(),
        "requiresReason": False,
        "providerRefundId": refund_id or current.get("providerRefundId"),
        "providerChargeId": provider_charge_id or current.get("providerChargeId"),
        "providerPaymentIntentId": _provider_id_value(event_object.get("payment_intent"))
        or current.get("providerPaymentIntentId"),
        "providerInvoiceId": _provider_id_value(event_object.get("invoice")) or current.get("providerInvoiceId"),
        "updatedAt": now_iso(),
    }


def _amount_value(value: Any, fallback: Any = None) -> int | None:
    if value in (None, ""):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _refund_readiness(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "eligible": False,
            "state": "not_eligible",
            "providerHandoffState": "not_eligible",
            "eligibleAmount": None,
            "currency": None,
            "requiresReason": True,
            "providerInvoiceId": None,
            "providerChargeId": None,
            "providerPaymentIntentId": None,
            "providerRefundId": None,
        }
    invoice = item.get("latest_invoice") or {}
    amount_paid = _amount_value(invoice.get("amountPaid"), 0) or 0
    amount_refunded = _amount_value(invoice.get("amountRefunded"), 0) or 0
    eligible_amount = max(amount_paid - amount_refunded, 0)
    has_provider_reference = bool(
        invoice.get("providerChargeId")
        or invoice.get("providerPaymentIntentId")
        or invoice.get("providerInvoiceId")
    )
    eligible = item.get("billing_status") in {"active", "past_due", "payment_failed"} and eligible_amount > 0
    state = "ready_for_provider" if eligible and has_provider_reference else "not_eligible"
    return {
        "eligible": state == "ready_for_provider",
        "state": state,
        "providerHandoffState": state,
        "eligibleAmount": eligible_amount if state == "ready_for_provider" else None,
        "currency": invoice.get("currency"),
        "requiresReason": True,
        "providerInvoiceId": invoice.get("providerInvoiceId"),
        "providerChargeId": invoice.get("providerChargeId"),
        "providerPaymentIntentId": invoice.get("providerPaymentIntentId"),
        "providerRefundId": None,
    }


def _require_refund_amount(amount: int) -> int:
    try:
        parsed = int(amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Refund amount must be an integer") from exc
    if parsed <= 0:
        raise HTTPException(status_code=422, detail="Refund amount must be positive")
    return parsed


def _require_refund_reason(reason: str) -> str:
    cleaned = str(reason or "").strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Refund reason is required")
    return cleaned[:500]


def _require_idempotency_key(idempotency_key: str) -> str:
    cleaned = str(idempotency_key or "").strip()
    if len(cleaned) < 8:
        raise HTTPException(status_code=422, detail="Refund idempotency key must be at least 8 characters")
    return cleaned[:200]


def _twint_refund_window_open(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    invoice = item.get("latest_invoice") or {}
    payment_method = str(
        item.get("payment_method_type") or invoice.get("paymentMethodType") or ""
    ).lower()
    if payment_method != "twint":
        return True
    paid_at = _parse_iso_datetime(
        invoice.get("paidAt")
        or item.get("last_provider_event_at")
        or item.get("updated_at")
    )
    if paid_at is None:
        return True
    return datetime.now(timezone.utc) <= paid_at + timedelta(days=180)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_refund_idempotency(parent_id: str, idempotency_key: str) -> dict[str, Any] | None:
    response = _subscription_get(
        get_table(), Key=_refund_idempotency_key(parent_id, idempotency_key)
    )
    item = _subscription_optional_item(response.get("Item"))
    return dict(item) if item else None


def _reserve_refund_idempotency(
    *,
    parent_id: str,
    idempotency_key: str,
    amount: int,
    reason: str,
    actor: str,
    at: str,
) -> None:
    item = _refund_idempotency_item(
        parent_id=parent_id,
        idempotency_key=idempotency_key,
        amount=amount,
        reason=reason,
        actor=actor,
        status="in_progress",
        at=at,
        provider_refund_id=None,
    )
    try:
        _transact_write([{"Put": {"Item": item, "ConditionExpression": "attribute_not_exists(PK)"}}])
    except ClientError as exc:
        if _is_conditional_failure(exc):
            raise HTTPException(status_code=409, detail="Refund idempotency key is already in use") from exc
        raise


def _record_refund_idempotency_failure(
    *,
    parent_id: str,
    idempotency_key: str,
    amount: int,
    reason: str,
    actor: str,
    at: str,
) -> None:
    _subscription_put(
        get_table(),
        Item=_refund_idempotency_item(
            parent_id=parent_id,
            idempotency_key=idempotency_key,
            amount=amount,
            reason=reason,
            actor=actor,
            status="failed",
            at=at,
            provider_refund_id=None,
        )
    )


def _record_refund_idempotency_success(
    *,
    parent_id: str,
    idempotency_key: str,
    amount: int,
    reason: str,
    actor: str,
    at: str,
    provider_refund_id: str | None,
) -> None:
    _subscription_put(
        get_table(),
        Item=_refund_idempotency_item(
            parent_id=parent_id,
            idempotency_key=idempotency_key,
            amount=amount,
            reason=reason,
            actor=actor,
            status="succeeded",
            at=at,
            provider_refund_id=provider_refund_id,
        )
    )


def _refund_idempotency_item(
    *,
    parent_id: str,
    idempotency_key: str,
    amount: int,
    reason: str,
    actor: str,
    status: str,
    at: str,
    provider_refund_id: str | None,
) -> dict[str, Any]:
    return {
        **_refund_idempotency_key(parent_id, idempotency_key),
        "entity_type": BILLING_REFUND_IDEMPOTENCY_ENTITY,
        "parent_id": parent_id,
        "idempotency_key_hash": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
        "status": status,
        "amount": amount,
        "reason": reason,
        "actor": actor,
        "provider_refund_id": provider_refund_id,
        "created_at": at,
        "updated_at": at,
    }


def _refund_execution_response(
    *,
    parent_id: str,
    idempotency_status: str,
    idempotency_record: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    billing = get_admin_billing(parent_id, settings=settings)
    return {
        "idempotencyStatus": idempotency_status,
        "refund": billing.get("refund") or {
            "state": idempotency_record.get("status"),
            "providerRefundId": idempotency_record.get("provider_refund_id"),
        },
        "billing": billing,
    }


def _apply_direct_refund_result(
    *,
    parent_id: str,
    existing: dict[str, Any],
    provider_refund: dict[str, Any],
    amount: int,
    reason: str,
    idempotency_key: str,
    actor: str,
    requested_at: str,
) -> dict[str, Any]:
    now = now_iso()
    invoice = dict(existing.get("latest_invoice") or {})
    previous_refunded = _amount_value(invoice.get("amountRefunded"), 0) or 0
    invoice["amountRefunded"] = previous_refunded + amount
    invoice["amountRemaining"] = max((_amount_value(invoice.get("amountPaid"), 0) or 0) - invoice["amountRefunded"], 0)
    provider_refund_id = _provider_id_value(provider_refund.get("id")) or f"refund_{uuid4().hex}"
    provider_state = str(provider_refund.get("status") or "requested")
    refund_summary = {
        **_refund_readiness({**existing, "latest_invoice": invoice}),
        "state": provider_state,
        "providerHandoffState": provider_state,
        "refundedAmount": amount,
        "currency": str(provider_refund.get("currency") or invoice.get("currency") or "CHF").upper(),
        "requiresReason": False,
        "providerRefundId": provider_refund_id,
        "providerChargeId": _provider_id_value(provider_refund.get("charge")) or invoice.get("providerChargeId"),
        "providerPaymentIntentId": _provider_id_value(provider_refund.get("payment_intent"))
        or invoice.get("providerPaymentIntentId"),
        "providerInvoiceId": _provider_id_value(provider_refund.get("invoice")) or invoice.get("providerInvoiceId"),
        "reason": reason,
        "idempotencyKey": idempotency_key,
        "requestedBy": actor,
        "requestedAt": requested_at,
        "updatedAt": now,
    }
    updated = {
        **existing,
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "latest_invoice": invoice,
        "refund_summary": refund_summary,
        "updated_at": now,
    }
    updated["accounting_handoff"] = _accounting_handoff(updated, parent_id=parent_id)
    event_id = f"direct_refund_{provider_refund_id}"
    event = {
        **_billing_key(parent_id),
        "SK": _billing_event_sk(now, event_id),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
        "event_id": event_id,
        "event_type": "direct_refund.created",
        "event_at": now,
        "provider": "stripe",
        "provider_mode": updated.get("billing_mode"),
        "provider_livemode": updated.get("provider_livemode"),
        "billing_status": updated.get("billing_status"),
        "processing_result": "processed",
        "idempotency_status": "new",
        "provider_refund_id": provider_refund_id,
        "request_id": idempotency_key,
        "requested_tier": updated.get("requested_tier"),
        "payment_method_type": updated.get("payment_method_type"),
        "twint_status": updated.get("twint_status"),
    }
    operations: list[dict[str, Any]] = [
        {"Put": {"Item": updated}},
        {"Put": {"Item": event, "ConditionExpression": "attribute_not_exists(PK)"}},
        {
            "Put": {
                "Item": {
                    **_provider_lookup_key("stripe", "refund", provider_refund_id),
                    "entity_type": BILLING_PROVIDER_LOOKUP_ENTITY,
                    "provider": "stripe",
                    "object_type": "refund",
                    "object_id": provider_refund_id,
                    "parent_id": parent_id,
                    "provider_mode": updated.get("billing_mode"),
                    "provider_livemode": updated.get("provider_livemode"),
                    "created_at": now,
                }
            }
        },
    ]
    _transact_write(operations)
    return updated


def _dunning_projection(
    item: dict[str, Any] | None,
    *,
    next_payment_attempt: str | None = None,
    previous_status: str | None = None,
) -> dict[str, Any]:
    status = (item or {}).get("billing_status") or "none"
    invoice = (item or {}).get("latest_invoice") or {}
    if status == "none":
        state = "none"
    elif status == "checkout_pending":
        state = "checkout_pending"
    elif status == "active" and previous_status in {"past_due", "payment_failed"}:
        state = "recovered"
    elif status == "active":
        state = "active"
    elif status == "past_due":
        state = "retrying" if next_payment_attempt else "past_due"
    elif status == "payment_failed":
        state = "retrying" if next_payment_attempt else "payment_failed"
    elif status == "canceled":
        state = "cancelled"
    elif status in {"provider_unknown", "manual_override"}:
        state = "manual_review"
    else:
        state = "manual_review"
    return {
        "state": state,
        "billingStatus": status,
        "providerInvoiceId": invoice.get("providerInvoiceId"),
        "invoiceStatus": invoice.get("invoiceStatus"),
        "nextPaymentAttempt": next_payment_attempt,
        "paymentMethodType": (item or {}).get("payment_method_type") or invoice.get("paymentMethodType"),
        "supportAction": _dunning_support_action(state),
    }


def _dunning_support_action(state: str) -> str:
    return {
        "none": "none",
        "active": "none",
        "checkout_pending": "wait_for_provider_confirmation",
        "past_due": "monitor_provider_retry",
        "payment_failed": "contact_parent_or_wait_for_provider_retry",
        "retrying": "monitor_provider_retry",
        "recovered": "none",
        "cancelled": "confirm_access_and_support_history",
        "manual_review": "review_provider_billing_record",
    }.get(state, "review_provider_billing_record")


def _accounting_handoff(item: dict[str, Any] | None, *, parent_id: str) -> dict[str, Any]:
    item = item or {}
    invoice = item.get("latest_invoice") or {}
    refund = item.get("refund_summary") or _refund_readiness(item)
    provider_invoice_id = invoice.get("providerInvoiceId")
    return {
        "parentId": parent_id,
        "billingAccountRef": item.get("provider_customer_id"),
        "tier": item.get("subscription_tier") or SubscriptionTier.FREE_TRIAL.value,
        "provider": item.get("billing_provider"),
        "providerMode": item.get("billing_mode"),
        "providerLivemode": item.get("provider_livemode"),
        "providerCustomerId": item.get("provider_customer_id"),
        "providerSubscriptionId": item.get("provider_subscription_id") or invoice.get("providerSubscriptionId"),
        "providerInvoiceId": provider_invoice_id,
        "providerChargeId": invoice.get("providerChargeId") or refund.get("providerChargeId"),
        "providerPaymentIntentId": invoice.get("providerPaymentIntentId") or refund.get("providerPaymentIntentId"),
        "currency": invoice.get("currency"),
        "amountDue": invoice.get("amountDue"),
        "amountPaid": invoice.get("amountPaid"),
        "amountRemaining": invoice.get("amountRemaining"),
        "taxAmount": invoice.get("taxAmount"),
        "taxStatus": invoice.get("taxStatus") or "provider_managed",
        "periodStart": invoice.get("periodStart") or item.get("current_period_start"),
        "periodEnd": invoice.get("periodEnd") or item.get("current_period_end"),
        "hostedInvoiceUrl": invoice.get("hostedInvoiceUrl"),
        "receiptUrl": invoice.get("receiptUrl"),
        "refund": {
            "state": refund.get("state"),
            "providerRefundId": refund.get("providerRefundId"),
            "eligibleAmount": refund.get("eligibleAmount"),
            "refundedAmount": refund.get("refundedAmount"),
            "currency": refund.get("currency"),
            "reason": refund.get("reason"),
            "idempotencyKey": refund.get("idempotencyKey"),
            "requestedBy": refund.get("requestedBy"),
            "requestedAt": refund.get("requestedAt"),
            "providerHandoffState": refund.get("providerHandoffState"),
        },
        "paymentMethodType": item.get("payment_method_type") or invoice.get("paymentMethodType"),
        "reconciliationId": invoice.get("reconciliationId") or provider_invoice_id,
    }


def _status_from_provider_subscription(status: Any) -> str:
    return {
        "trialing": "active",
        "active": "active",
        "past_due": "past_due",
        "unpaid": "payment_failed",
        "canceled": "canceled",
        "incomplete": "checkout_pending",
        "incomplete_expired": "canceled",
    }.get(str(status or ""), "provider_unknown")


def _price_from_provider_object(event_object: dict[str, Any]) -> str | None:
    price = event_object.get("price")
    if isinstance(price, dict):
        return price.get("id")
    items = ((event_object.get("items") or {}).get("data") or [])
    if items and isinstance(items[0], dict):
        nested_price = items[0].get("price")
        if isinstance(nested_price, dict):
            return nested_price.get("id")
    return None


def _timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _provider_event_is_stale(event_created: Any, existing: dict[str, Any]) -> bool:
    event_at = _parse_iso_datetime(_timestamp_to_iso(event_created))
    last_event_at = _parse_iso_datetime(existing.get("last_provider_event_at"))
    return bool(event_at and last_event_at and event_at < last_event_at)


def _record_stale_provider_event(
    *,
    parent_id: str,
    event_id: str,
    event_type: str,
    event_created: Any,
    event_object: dict[str, Any],
    existing: dict[str, Any],
    now: str,
) -> None:
    event = _provider_processing_event(
        parent_id=parent_id,
        event_id=event_id,
        event_type=event_type,
        event_created=event_created,
        event_object=event_object,
        existing=existing,
        processing_result="stale_ignored",
        idempotency_status="ignored",
        now=now,
    )
    event_item = {
        **event,
        "PK": _billing_key(parent_id)["PK"],
        "SK": _billing_event_sk(str(event["event_at"]), str(event["event_id"])),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
    }
    dedupe = {
        **_provider_event_key(event_id),
        "entity_type": BILLING_EVENT_DEDUPE_ENTITY,
        "provider": "stripe",
        "provider_event_id": event_id,
        "event_type": event_type,
        "parent_id": parent_id,
        "created_at": now,
        "processing_result": "stale_ignored",
    }
    try:
        _transact_write(
            [
                {"Put": {"Item": dedupe, "ConditionExpression": "attribute_not_exists(PK)"}},
                {"Put": {"Item": event_item, "ConditionExpression": "attribute_not_exists(PK)"}},
            ]
        )
    except ClientError as exc:
        if not _is_conditional_failure(exc):
            raise


def _apply_billing_transition(
    *,
    parent_id: str,
    event_id: str,
    event_type: str,
    event_created: Any,
    event_object: dict[str, Any],
    transition: dict[str, Any],
    existing: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    current_status = existing.get("billing_status")
    manual_override_active = current_status == "manual_override"
    status = current_status if manual_override_active else transition["billing_status"]
    tier = (
        transition.get("subscription_tier")
        or existing.get("subscription_tier")
        or SubscriptionTier.FREE_TRIAL.value
    )
    if not manual_override_active and status == "active":
        tier = transition.get("subscription_tier") or transition["requested_tier"]
    elif not manual_override_active and status == "canceled":
        tier = SubscriptionTier.FREE_TRIAL.value

    updated = {
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "subscription_tier": tier,
        "requested_tier": transition["requested_tier"],
        "billing_provider": "stripe",
        "billing_mode": existing.get("billing_mode") or "test",
        "billing_status": status,
        "provider_livemode": bool(existing.get("provider_livemode") or event_object.get("livemode") or False),
        "readiness_state": existing.get("readiness_state"),
        "readiness_blockers": existing.get("readiness_blockers") or [],
        "twint_in_scope": bool(existing.get("twint_in_scope") or True),
        "twint_status": existing.get("twint_status"),
        "payment_method_type": transition.get("payment_method_type"),
        "previous_billing_status": existing.get("previous_billing_status"),
        "previous_subscription_tier": existing.get("previous_subscription_tier"),
        "latest_invoice": transition.get("latest_invoice") or existing.get("latest_invoice") or {},
        "refund_summary": transition.get("refund") or existing.get("refund_summary") or {},
        "provider_customer_id": transition.get("provider_customer_id"),
        "provider_subscription_id": transition.get("provider_subscription_id"),
        "provider_price_id": transition.get("provider_price_id"),
        "checkout_session_id": transition.get("checkout_session_id"),
        "checkout_url": existing.get("checkout_url"),
        "success_url": existing.get("success_url"),
        "cancel_url": existing.get("cancel_url"),
        "current_period_start": transition.get("current_period_start"),
        "current_period_end": transition.get("current_period_end"),
        "cancel_at_period_end": transition.get("cancel_at_period_end"),
        "last_provider_event_id": event_id,
        "last_provider_event_type": event_type,
        "last_provider_event_at": _timestamp_to_iso(event_created) or now,
        "manual_override_at": existing.get("manual_override_at"),
        "manual_override_by": existing.get("manual_override_by"),
        "manual_override_source": existing.get("manual_override_source"),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    provider_refund = transition.get("refund")
    if provider_refund:
        invoice = dict(updated.get("latest_invoice") or {})
        refunded_amount = _amount_value(provider_refund.get("refundedAmount"), 0) or 0
        invoice["amountRefunded"] = (_amount_value(invoice.get("amountRefunded"), 0) or 0) + refunded_amount
        updated["latest_invoice"] = invoice
        readiness = _refund_readiness(updated)
        updated["refund_summary"] = {
            **readiness,
            "state": provider_refund.get("state") or readiness["state"],
            "providerHandoffState": provider_refund.get("providerHandoffState")
            or readiness["providerHandoffState"],
            "providerRefundId": provider_refund.get("providerRefundId"),
            "refundedAmount": refunded_amount,
            "updatedAt": provider_refund.get("updatedAt"),
        }
    else:
        existing_refund = existing.get("refund_summary") or {}
        updated["refund_summary"] = (
            existing_refund if existing_refund.get("providerRefundId") else _refund_readiness(updated)
        )
    next_payment_attempt = transition.get("next_payment_attempt") or (
        existing.get("dunning") or {}
    ).get("nextPaymentAttempt")
    updated["dunning"] = _dunning_projection(
        updated,
        next_payment_attempt=next_payment_attempt,
        previous_status=current_status,
    )
    updated["accounting_handoff"] = _accounting_handoff(updated, parent_id=parent_id)
    event = {
        "PK": updated["PK"],
        "SK": _billing_event_sk(now, event_id),
        "entity_type": BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
        "event_id": f"stripe_{event_id}",
        "provider_event_id": event_id,
        "event_type": event_type,
        "event_at": now,
        "provider": "stripe",
        "provider_mode": updated["billing_mode"],
        "provider_livemode": updated["provider_livemode"],
        "billing_status": status,
        "processing_result": "deduplicated" if event_id == existing.get("last_provider_event_id") else "processed",
        "idempotency_status": "new",
        "requested_tier": transition["requested_tier"],
        "payment_method_type": transition.get("payment_method_type"),
        "twint_status": updated.get("twint_status"),
    }
    dedupe = {
        **_provider_event_key(event_id),
        "entity_type": BILLING_EVENT_DEDUPE_ENTITY,
        "provider": "stripe",
        "provider_event_id": event_id,
        "event_type": event_type,
        "parent_id": parent_id,
        "created_at": now,
    }
    operations: list[dict[str, Any]] = [
        {"Put": {"Item": dedupe, "ConditionExpression": "attribute_not_exists(PK)"}},
        {"Put": {"Item": updated}},
        {"Put": {"Item": event, "ConditionExpression": "attribute_not_exists(PK)"}},
    ]
    for lookup in _provider_lookup_rows_for_event(
        parent_id=parent_id,
        provider_mode=updated["billing_mode"],
        livemode=updated["provider_livemode"],
        event_object=event_object,
        created_at=now,
    ):
        operations.append({"Put": {"Item": lookup}})
    if not manual_override_active and status in {"active", "canceled"}:
        operations.extend(
            _versioned_profile_operations(
                parent_id,
                profile=_require_parent(parent_id),
                update_expression="SET subscription_tier = :tier",
                expression_attribute_values={":tier": tier},
            )
        )
    try:
        _transact_write(operations)
    except ClientError as exc:
        if _is_conditional_failure(exc):
            return _get_billing_item(parent_id) or updated
        raise
    return updated


def _record_provider_processing_event(
    *,
    parent_id: str,
    event_id: str,
    event_type: str,
    event_created: Any,
    event_object: dict[str, Any],
    existing: dict[str, Any],
    processing_result: str,
    idempotency_status: str,
    now: str,
) -> None:
    _put_billing_event(
        parent_id,
        _provider_processing_event(
            parent_id=parent_id,
            event_id=event_id,
            event_type=event_type,
            event_created=event_created,
            event_object=event_object,
            existing=existing,
            processing_result=processing_result,
            idempotency_status=idempotency_status,
            now=now,
        ),
    )


def _provider_processing_event(
    *,
    parent_id: str,
    event_id: str,
    event_type: str,
    event_created: Any,
    event_object: dict[str, Any],
    existing: dict[str, Any],
    processing_result: str,
    idempotency_status: str,
    now: str,
) -> dict[str, Any]:
    return {
        "event_id": f"stripe_{processing_result}_{event_id}_{uuid4().hex}",
        "provider_event_id": event_id,
        "provider_event_at": _timestamp_to_iso(event_created),
        "event_type": event_type,
        "event_at": now,
        "provider": "stripe",
        "provider_mode": existing.get("billing_mode") or "test",
        "provider_livemode": bool(existing.get("provider_livemode") or event_object.get("livemode") or False),
        "billing_status": existing.get("billing_status") or "none",
        "processing_result": processing_result,
        "idempotency_status": idempotency_status,
        "requested_tier": existing.get("requested_tier"),
        "payment_method_type": existing.get("payment_method_type"),
        "twint_status": existing.get("twint_status"),
        "correlation_id": f"stripe:{event_id}",
        "parent_id": parent_id,
    }


def _record_manual_override(
    *,
    parent_id: str,
    requested_tier: str,
    actor_id: str,
    source_request_id: str,
    at: str,
) -> None:
    existing = _get_billing_item(parent_id) or {}
    item = {
        **_billing_key(parent_id),
        "entity_type": BILLING_ENTITY,
        "parent_id": parent_id,
        "subscription_tier": requested_tier,
        "requested_tier": requested_tier,
        "billing_provider": existing.get("billing_provider"),
        "billing_mode": "manual",
        "billing_status": "manual_override",
        "provider_customer_id": existing.get("provider_customer_id"),
        "provider_subscription_id": existing.get("provider_subscription_id"),
        "provider_price_id": existing.get("provider_price_id"),
        "checkout_session_id": existing.get("checkout_session_id"),
        "checkout_url": existing.get("checkout_url"),
        "success_url": existing.get("success_url"),
        "cancel_url": existing.get("cancel_url"),
        "current_period_start": existing.get("current_period_start"),
        "current_period_end": existing.get("current_period_end"),
        "cancel_at_period_end": bool(existing.get("cancel_at_period_end") or False),
        "last_provider_event_id": existing.get("last_provider_event_id"),
        "last_provider_event_type": existing.get("last_provider_event_type"),
        "last_provider_event_at": existing.get("last_provider_event_at"),
        "manual_override_at": at,
        "manual_override_by": actor_id,
        "manual_override_source": source_request_id,
        "created_at": existing.get("created_at") or at,
        "updated_at": at,
    }
    _subscription_put(get_table(), Item=item)
    _put_billing_event(
        parent_id,
        {
            "event_id": f"manual_override_{source_request_id}",
            "event_type": "manual_override",
            "event_at": at,
            "provider": item.get("billing_provider") or "manual",
            "provider_mode": "manual",
            "billing_status": "manual_override",
            "requested_tier": requested_tier,
            "provider_event_id": None,
        },
    )


def _event(
    request_id: str,
    event_type: str,
    *,
    actor_id: str,
    actor_role: str,
    at: str,
    note: str | None,
    changes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entity_type": "subscription_request_event",
        "event_id": f"subevt-{uuid4().hex}",
        "request_id": request_id,
        "event_type": event_type,
        "event_at": at,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "note": _clean_note(note),
        "changes": changes,
    }


def _actor_id(user: dict[str, Any]) -> str:
    return str(user.get("sub") or user.get("username") or "admin")


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _require_choice(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: {value}")
    return value


def _require_transition(current: str, target: str) -> None:
    if current in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Subscription request is already terminal")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=400, detail=f"Invalid transition from {current} to {target}")


def _normalize_tier(value: Any) -> str:
    raw = (
        value.value
        if isinstance(value, SubscriptionTier)
        else str(value or SubscriptionTier.FREE_TRIAL.value)
    )
    if raw not in {tier.value for tier in SubscriptionTier}:
        raise HTTPException(status_code=400, detail=f"Invalid subscription tier: {raw}")
    return raw


def _target_tier(request_type: str, requested_tier: str | None) -> str:
    if request_type == "cancel":
        return (
            SubscriptionTier.FREE_TRIAL.value
            if requested_tier is None
            else _normalize_tier(requested_tier)
        )
    if requested_tier is None:
        raise HTTPException(status_code=400, detail="requested_tier is required")
    return _normalize_tier(requested_tier)


def _tier_rank(value: str) -> int:
    return {
        SubscriptionTier.FREE_TRIAL.value: 0,
        SubscriptionTier.STUDENT.value: 1,
        SubscriptionTier.TEACHER_SUPPORTED.value: 2,
        SubscriptionTier.FAMILY.value: 3,
    }[value]


def _matches(item: dict[str, Any], field: str, expected: str | None) -> bool:
    return expected is None or item.get(field) == expected


def _within_dates(value: str | None, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return False
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


def _transact_write(operations: list[dict[str, Any]]) -> None:
    table = get_table()
    if isinstance(table, _HighLevelTransactionTable):
        table.transact_write_items(TransactItems=operations)
        return

    table_name = getattr(table, "name", None)
    if not table_name:
        table_name = getattr(table, "table_name", None)
    if not table_name:
        raise RuntimeError("DynamoDB table name is unavailable for transaction")

    serializer = TypeSerializer()
    client_ops: list[dict[str, Any]] = []
    for operation in operations:
        if "ConditionCheck" in operation:
            check = operation["ConditionCheck"]
            client_ops.append(
                {
                    "ConditionCheck": {
                        "TableName": table_name,
                        "Key": _serialize_map(check["Key"], serializer),
                        **_transaction_common(check, serializer),
                    }
                }
            )
        elif "Put" in operation:
            put = operation["Put"]
            client_ops.append(
                {
                    "Put": {
                        "TableName": table_name,
                        "Item": _serialize_map(put["Item"], serializer),
                        **_transaction_common(put, serializer),
                    }
                }
            )
        elif "Update" in operation:
            update = operation["Update"]
            client_ops.append(
                {
                    "Update": {
                        "TableName": table_name,
                        "Key": _serialize_map(update["Key"], serializer),
                        "UpdateExpression": update["UpdateExpression"],
                        **_transaction_common(update, serializer),
                    }
                }
            )
        elif "Delete" in operation:
            delete = operation["Delete"]
            client_ops.append(
                {
                    "Delete": {
                        "TableName": table_name,
                        "Key": _serialize_map(delete["Key"], serializer),
                        **_transaction_common(delete, serializer),
                    }
                }
            )
        else:
            raise ValueError(f"Unsupported transaction operation: {operation}")

    if not isinstance(table, _DynamoTable):
        raise RuntimeError("DynamoDB transaction client is unavailable")
    table.meta.client.transact_write_items(TransactItems=client_ops)


def _versioned_profile_operations(
    user_id: str,
    *,
    profile: dict[str, Any],
    update_expression: str,
    expression_attribute_values: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compose an ordinary profile CAS into a wider domain transaction."""
    table = get_table()
    fence = account_deletion_repo.require_active_account_fence(user_id, table=table)
    generation = fence.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed account fence generation"
        )
    version = profile.get("version")
    if isinstance(version, Decimal) and version == version.to_integral_value():
        version = int(version)
    if version is not None:
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed profile version"
            )
    return [
        account_deletion_repo.active_fence_condition(user_id, generation),
        user_repo.profile_update_operation(
            user_id,
            update_expression=update_expression,
            expression_attribute_values=expression_attribute_values,
            expected_version=version,
        ),
    ]


def _transaction_common(operation: dict[str, Any], serializer: TypeSerializer) -> dict[str, Any]:
    common: dict[str, Any] = {}
    if operation.get("ConditionExpression"):
        common["ConditionExpression"] = operation["ConditionExpression"]
    if operation.get("ExpressionAttributeNames"):
        common["ExpressionAttributeNames"] = operation["ExpressionAttributeNames"]
    if operation.get("ExpressionAttributeValues"):
        common["ExpressionAttributeValues"] = _serialize_map(
            operation["ExpressionAttributeValues"],
            serializer,
        )
    return common


def _serialize_map(values: dict[str, Any], serializer: TypeSerializer) -> dict[str, Any]:
    return {key: serializer.serialize(value) for key, value in values.items()}


def _is_conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }
