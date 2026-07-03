"""Parent/admin account operations visibility aggregation."""
from __future__ import annotations

from typing import Any

from stoa.config import Settings
from stoa.db.repositories import user_repo
from stoa.services import (
    account_verification_service,
    entitlement_service,
    subscription_service,
    usage_ledger_service,
)


def build_parent_operations_summary(
    parent_id: str,
    *,
    settings: Settings,
    day: str | None = None,
) -> dict[str, Any]:
    """Build the parent-visible account operations summary."""
    parent = _require_parent(parent_id)
    children = _child_operation_rows(parent_id, settings=settings, day=day)
    billing = subscription_service.get_parent_billing(parent_id, settings=settings)
    usage = [child["usage"] for child in children if child.get("usage")]
    return {
        "parentId": parent_id,
        "parent": _profile_summary(parent),
        "billing": _billing_summary(billing),
        "children": children,
        "usage": usage,
        "supportState": _support_state(parent, billing, children, usage),
    }


def build_admin_parent_operations_detail(
    parent_id: str,
    *,
    settings: Settings,
    day: str | None = None,
) -> dict[str, Any]:
    """Build the admin support-grade operations detail for one parent account."""
    parent = _require_parent(parent_id)
    children = _child_operation_rows(parent_id, settings=settings, day=day)
    billing = subscription_service.get_admin_billing(parent_id, settings=settings)
    usage = [child["usage"] for child in children if child.get("usage")]
    return {
        "parentId": parent_id,
        "parent": _profile_summary(parent),
        "billing": _billing_summary(billing, include_events=True),
        "children": children,
        "usage": usage,
        "supportState": _support_state(parent, billing, children, usage),
    }


def _require_parent(parent_id: str) -> dict[str, Any]:
    parent = user_repo.get_user(parent_id)
    if not parent or parent.get("role") != "parent":
        raise ValueError("parent_not_found")
    return parent


def _child_operation_rows(
    parent_id: str,
    *,
    settings: Settings,
    day: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in user_repo.list_parent_student_bindings(parent_id):
        student_id = str(binding.get("student_id") or "")
        if not student_id or student_id in seen:
            continue
        seen.add(student_id)
        rows.append(_child_operation_row(parent_id, student_id, binding, settings=settings, day=day))
    for child in user_repo.list_children_by_parent_scan(parent_id):
        student_id = str(child.get("user_id") or child.get("id") or "")
        if not student_id or student_id in seen:
            continue
        seen.add(student_id)
        rows.append(
            _child_operation_row(
                parent_id,
                student_id,
                {
                    "parent_id": parent_id,
                    "student_id": student_id,
                    "status": child.get("parent_binding_status") or "profile_parent_link",
                    "relationship": child.get("relationship") or "child",
                    "source": "student_profile_parent_id",
                },
                settings=settings,
                day=day,
                child_profile=child,
            )
        )
    return rows


def _child_operation_row(
    parent_id: str,
    student_id: str,
    binding: dict[str, Any],
    *,
    settings: Settings,
    day: str | None,
    child_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    child_profile = child_profile if child_profile is not None else user_repo.get_user(student_id)
    child_profile = child_profile or {
        "user_id": student_id,
        "role": "student",
        "email": "",
    }
    entitlement = entitlement_service.resolve_student_entitlement(
        student_id,
        settings=settings,
        student_profile=child_profile,
    )
    usage = usage_ledger_service.build_student_usage_summary(
        student_id=student_id,
        settings=settings,
        day=day,
        entitlement=entitlement,
    )
    return {
        "studentId": student_id,
        "profile": _profile_summary(child_profile),
        "binding": {
            "parentId": parent_id,
            "studentId": student_id,
            "status": binding.get("status") or "missing",
            "relationship": binding.get("relationship") or "child",
            "source": binding.get("source"),
            "updatedAt": binding.get("updated_at") or binding.get("created_at"),
        },
        "entitlement": entitlement,
        "usage": usage,
        "verification": account_verification_service.public_state(child_profile),
    }


def _profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    email = str(profile.get("email") or "")
    return {
        "userId": profile.get("user_id") or profile.get("id") or "",
        "email": email,
        "name": profile.get("name") or (email.split("@")[0] if email else ""),
        "role": profile.get("role") or "",
        "verification": account_verification_service.public_state(profile),
    }


def _billing_summary(billing: dict[str, Any], *, include_events: bool = False) -> dict[str, Any]:
    summary = {
        "status": billing.get("status"),
        "mode": billing.get("mode"),
        "provider": billing.get("provider"),
        "subscriptionTier": billing.get("subscriptionTier"),
        "requestedTier": billing.get("requestedTier"),
        "paymentMethodType": billing.get("paymentMethodType"),
        "currentPeriodStart": billing.get("currentPeriodStart"),
        "currentPeriodEnd": billing.get("currentPeriodEnd"),
        "cancelAtPeriodEnd": billing.get("cancelAtPeriodEnd"),
        "lastProviderEventType": billing.get("lastProviderEventType"),
        "lastProviderEventAt": billing.get("lastProviderEventAt"),
        "manualOverrideAt": billing.get("manualOverrideAt"),
        "manualOverrideSource": billing.get("manualOverrideSource"),
        "readiness": billing.get("readiness") or {},
        "twint": billing.get("twint") or {},
        "dunning": billing.get("dunning") or {},
        "refund": billing.get("refund") or {},
        "accountingHandoff": billing.get("accountingHandoff") or {},
    }
    if include_events:
        summary["events"] = billing.get("events") or []
    return summary


def _support_state(
    parent: dict[str, Any],
    billing: dict[str, Any],
    children: list[dict[str, Any]],
    usage: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if account_verification_service.email_verification_required(parent):
        blockers.append("parent_email_unverified")
    if billing.get("status") in {"payment_failed", "past_due", "canceled"}:
        blockers.append("billing_inactive")
    if not children:
        warnings.append("no_linked_children")
    for child in children:
        binding_status = str((child.get("binding") or {}).get("status") or "")
        if binding_status not in {"active", "profile_parent_link"}:
            warnings.append(f"child_binding_{binding_status}")
        child_verification = (child.get("profile") or {}).get("verification") or {}
        if child_verification.get("emailVerificationRequired"):
            warnings.append("child_email_unverified")
    if any(item.get("unreconciled") for item in usage):
        warnings.append("usage_unreconciled")
    return {
        "state": "blocked" if blockers else ("attention" if warnings else "ready"),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }
