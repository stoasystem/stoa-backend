"""Effective entitlement resolution for paid student access."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stoa.config import FREE_STORAGE_BYTES, PAID_STORAGE_BYTES, Settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.models.user import SubscriptionTier
from stoa.services import paid_entitlement_service


ACTIVE_BILLING_STATUSES = {"active", "manual_override"}
BLOCKED_BILLING_STATUSES = {"checkout_pending", "payment_failed", "past_due", "canceled"}
PLAN_RANK = {
    SubscriptionTier.FREE_TRIAL.value: 0,
    SubscriptionTier.STUDENT.value: 1,
    SubscriptionTier.TEACHER_SUPPORTED.value: 2,
    SubscriptionTier.FAMILY.value: 3,
}


def resolve_student_entitlement(
    student_id: str,
    *,
    settings: Settings,
    student_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the plan that should govern a student's product access."""
    student_profile = student_profile if student_profile is not None else user_repo.get_user(student_id)
    student_profile = student_profile or {}
    student_tier = _normalize_tier(student_profile.get("subscription_tier"))
    parent_id = _linked_parent_id(student_profile)
    binding = _active_parent_binding(parent_id, student_id) if parent_id else None
    parent_profile = user_repo.get_user(parent_id) if parent_id else None
    billing = _get_billing_item(parent_id) if parent_id else None
    rollout = _get_payment_rollout_item() if parent_id else None
    paid_grant = (
        paid_entitlement_service.get_active_beneficiary_grant(
            parent_id,
            student_id,
            table=get_table(),
        )
        if parent_id and binding
        else None
    )

    decision = _billing_decision(
        billing=billing,
        parent_profile=parent_profile,
        student_tier=student_tier,
        has_active_binding=bool(binding),
        paid_grant=paid_grant,
    )
    effective_plan = _normalize_tier(decision["effective_plan"])
    question_limit = _daily_question_limit(effective_plan, settings)
    chat_limit = _daily_chat_message_limit(effective_plan, settings)
    hint_limit = _daily_hint_limit(effective_plan, settings)
    period = {
        "start": (billing or {}).get("current_period_start"),
        "end": (billing or {}).get("current_period_end"),
        "cancelAtPeriodEnd": bool((billing or {}).get("cancel_at_period_end") or False),
    }

    return {
        "studentId": student_id,
        "parentId": parent_id or None,
        "effectivePlan": effective_plan,
        "source": decision["source"],
        "limits": {
            "dailyAiQuestionLimit": question_limit,
            "dailyChatMessageLimit": chat_limit,
            "dailyHintLimit": hint_limit,
            "attachmentStorageBytes": attachment_storage_limit(effective_plan, settings),
        },
        "billingState": decision["billing_state"],
        "period": period,
        "blockingReason": decision["blocking_reason"],
        "supportExplanation": decision["support_explanation"],
        "bindingStatus": str((binding or {}).get("status") or "missing"),
        "studentTier": student_tier,
        "parentTier": _normalize_tier((parent_profile or {}).get("subscription_tier")),
        "rollout": _rollout_summary(rollout),
    }


def list_parent_child_entitlements(parent_id: str, *, settings: Settings) -> list[dict[str, Any]]:
    """Return effective entitlement summaries for every active child binding."""
    items = []
    for binding in user_repo.list_parent_student_bindings(parent_id):
        if str(binding.get("status") or "active") != "active":
            continue
        student_id = str(binding.get("student_id") or "")
        if not student_id:
            continue
        items.append(resolve_student_entitlement(student_id, settings=settings))
    return items


def _billing_decision(
    *,
    billing: dict[str, Any] | None,
    parent_profile: dict[str, Any] | None,
    student_tier: str,
    has_active_binding: bool,
    paid_grant: dict[str, object] | None,
) -> dict[str, str | None]:
    billing_status = str((billing or {}).get("billing_status") or "none")
    parent_tier = _normalize_tier((parent_profile or {}).get("subscription_tier"))
    billing_tier = _normalize_tier((billing or {}).get("subscription_tier") or parent_tier)

    if not has_active_binding:
        return _decision(
            effective_plan=student_tier,
            source="student_profile" if _is_paid(student_tier) else "free_tier",
            billing_state=billing_status,
            blocking_reason="missing_parent_binding",
            support_explanation="No active parent binding was found; student-local entitlement applies.",
        )

    if paid_grant is not None:
        return _decision(
            effective_plan=_normalize_tier(paid_grant.get("plan_id")),
            source="paid_beneficiary_grant",
            billing_state=billing_status,
            blocking_reason=None,
            support_explanation="An explicit active beneficiary grant determines paid access.",
        )

    if billing_status == "manual_override":
        return _decision(
            effective_plan=billing_tier,
            source="manual_override",
            billing_state=billing_status,
            blocking_reason=None,
            support_explanation="Manual admin override currently determines this student's paid access.",
        )

    if billing_status == "active":
        return _decision(
            effective_plan=student_tier,
            source="student_profile" if _is_paid(student_tier) else "free_tier",
            billing_state=billing_status,
            blocking_reason="missing_beneficiary_grant",
            support_explanation="Parent billing is active, but this student has no active beneficiary grant.",
        )

    if billing_status in {"checkout_pending"}:
        return _decision(
            effective_plan=(
                student_tier
                if _is_paid(student_tier)
                else SubscriptionTier.FREE_TRIAL.value
            ),
            source="student_profile" if _is_paid(student_tier) else "free_tier",
            billing_state=billing_status,
            blocking_reason="checkout_pending",
            support_explanation="Checkout is pending; paid parent access is not active yet.",
        )

    if billing_status in {"payment_failed", "past_due"}:
        return _decision(
            effective_plan=(
                student_tier
                if _is_paid(student_tier)
                else SubscriptionTier.FREE_TRIAL.value
            ),
            source="student_profile" if _is_paid(student_tier) else "free_tier",
            billing_state=billing_status,
            blocking_reason="payment_issue",
            support_explanation="Parent billing needs attention before paid access can apply.",
        )

    if billing_status == "canceled":
        return _decision(
            effective_plan=(
                student_tier
                if _is_paid(student_tier)
                else SubscriptionTier.FREE_TRIAL.value
            ),
            source="student_profile" if _is_paid(student_tier) else "free_tier",
            billing_state=billing_status,
            blocking_reason="billing_inactive",
            support_explanation="Parent billing is canceled or expired; paid parent access is inactive.",
        )

    return _decision(
        effective_plan=student_tier,
        source="student_profile" if _is_paid(student_tier) else "free_tier",
        billing_state=billing_status,
        blocking_reason=None,
        support_explanation="Free tier applies because no paid parent billing or override is active.",
    )


def _decision(
    *,
    effective_plan: str,
    source: str,
    billing_state: str,
    blocking_reason: str | None,
    support_explanation: str,
) -> dict[str, str | None]:
    return {
        "effective_plan": effective_plan,
        "source": source,
        "billing_state": billing_state,
        "blocking_reason": blocking_reason,
        "support_explanation": support_explanation,
    }


def _linked_parent_id(student_profile: dict[str, Any]) -> str | None:
    parent_id = str(student_profile.get("parent_id") or "").strip()
    if parent_id and str(student_profile.get("parent_binding_status") or "active") == "active":
        return parent_id
    return None


def _active_parent_binding(parent_id: str | None, student_id: str) -> dict[str, Any] | None:
    if not parent_id:
        return None
    binding = user_repo.get_parent_student_binding(parent_id, student_id)
    if binding and str(binding.get("status") or "active") == "active":
        return binding
    return None


def _get_billing_item(parent_id: str | None) -> dict[str, Any] | None:
    if not parent_id:
        return None
    response = get_table().get_item(
        Key={"PK": f"SUBSCRIPTION_BILLING#{parent_id}", "SK": "SUMMARY"}
    )
    item = response.get("Item")
    return dict(item) if item else None


def _get_payment_rollout_item() -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": "SUBSCRIPTION_PAYMENT_ROLLOUT", "SK": "SUMMARY"})
    item = response.get("Item")
    return dict(item) if item else None


def _rollout_summary(item: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "checkoutState": (item or {}).get("checkout_state") or "config_default",
        "refundsState": (item or {}).get("refunds_state") or "config_default",
        "updatedAt": (item or {}).get("updated_at"),
    }


def _daily_question_limit(plan: str, settings: Settings) -> int:
    return {
        SubscriptionTier.FREE_TRIAL.value: settings.free_tier_daily_question_limit,
        SubscriptionTier.STUDENT.value: settings.standard_tier_daily_question_limit,
        SubscriptionTier.TEACHER_SUPPORTED.value: settings.premium_tier_daily_question_limit,
        SubscriptionTier.FAMILY.value: settings.premium_tier_daily_question_limit,
    }.get(plan, settings.free_tier_daily_question_limit)


def _daily_chat_message_limit(plan: str, settings: Settings) -> int:
    return {
        SubscriptionTier.FREE_TRIAL.value: settings.free_tier_daily_chat_message_limit,
        SubscriptionTier.STUDENT.value: settings.standard_tier_daily_chat_message_limit,
        SubscriptionTier.TEACHER_SUPPORTED.value: settings.premium_tier_daily_chat_message_limit,
        SubscriptionTier.FAMILY.value: settings.premium_tier_daily_chat_message_limit,
    }.get(plan, settings.free_tier_daily_chat_message_limit)


def _daily_hint_limit(plan: str, settings: Settings) -> int:
    return {
        SubscriptionTier.FREE_TRIAL.value: settings.free_tier_daily_hint_limit,
        SubscriptionTier.STUDENT.value: settings.standard_tier_daily_hint_limit,
        SubscriptionTier.TEACHER_SUPPORTED.value: settings.premium_tier_daily_hint_limit,
        SubscriptionTier.FAMILY.value: settings.premium_tier_daily_hint_limit,
    }.get(plan, settings.free_tier_daily_hint_limit)


def attachment_storage_limit(plan: str, settings: Settings) -> int:
    """Return the authoritative attachment-storage allowance for an effective plan."""
    normalized = _normalize_tier(plan)
    if normalized == SubscriptionTier.FREE_TRIAL.value:
        return settings.free_attachment_storage_bytes or FREE_STORAGE_BYTES
    return settings.paid_attachment_storage_bytes or PAID_STORAGE_BYTES


def _normalize_tier(value: Any) -> str:
    tier = str(value or SubscriptionTier.FREE_TRIAL.value)
    return tier if tier in PLAN_RANK else SubscriptionTier.FREE_TRIAL.value


def _is_paid(tier: str) -> bool:
    return PLAN_RANK.get(tier, 0) > 0


def period_is_current(period_end: str | None) -> bool:
    """Return whether an ISO timestamp is still in the future."""
    if not period_end:
        return False
    try:
        parsed = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed > datetime.now(timezone.utc)
