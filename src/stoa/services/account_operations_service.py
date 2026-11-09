"""Parent/admin account operations visibility aggregation."""
from __future__ import annotations

from typing import Any

from stoa import config
from stoa.config import Settings
from stoa.db.repositories import user_repo
from stoa.services import (
    account_verification_service,
    current_relationship,
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
    children = _current_child_operation_rows(parent_id, settings=settings, day=day)
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


def _current_child_operation_rows(
    parent_id: str,
    *,
    settings: Settings,
    day: str | None,
) -> list[dict[str, Any]]:
    """The parent-visible set: only relationships that are current right now.

    The admin detail below shows every relationship the parent's side stores,
    current or not, on purpose - support has to see a relationship that is no
    longer current to close it - and that route is authorized as an
    administrator, not as a party to the relationship.

    A child shared with another parent is shown through the entitlement's
    viewer projection, so this parent is not told who the other parent is -
    whether through the billing fields or through who pays the usage period.
    """
    rows = [
        _child_operation_row(
            parent_id,
            verdict.student_id,
            _relationship_row(verdict),
            settings=settings,
            day=day,
        )
        for verdict in current_relationship.children_of(parent_id)
    ]
    return [
        {**row, "entitlement": entitlement_service.for_parent_viewer(row["entitlement"], parent_id)}
        for row in rows
    ]


def _child_operation_rows(
    parent_id: str,
    *,
    settings: Settings,
    day: str | None,
) -> list[dict[str, Any]]:
    return [
        _child_operation_row(
            parent_id,
            verdict.student_id,
            _relationship_row(verdict),
            settings=settings,
            day=day,
        )
        for verdict in current_relationship.known_children_of(parent_id)
    ]


def _relationship_row(verdict: current_relationship.Verdict) -> dict[str, Any]:
    return {
        "parent_id": verdict.parent_id,
        "student_id": verdict.student_id,
        # What the rows store. A pair whose rows say active but whose account is
        # not usable shows as active here; the account's own state says why.
        "status": "active" if verdict.is_current else verdict.status or "missing",
        "relationship": verdict.relationship or "child",
        "source": verdict.source,
        "updated_at": verdict.version,
    }


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
    """Project the billing facts these two screens are allowed to show.

    While the paid surface is frozen there is nothing here anyone may act on, so
    the projection collapses to the freeze itself rather than the tier, the
    provider, the period or the override that opened it. The routes that reach
    this are about child access and usage; freezing them whole would take those
    away too, so the refusal belongs to the section, not the page.

    This is also why the freeze cannot be judged by what a route is called.
    Neither of the two that land here says anything about money in its path or
    its handler name, and both were handing out the same facts the frozen routes
    refuse -- one of them the very same function's answer.
    """
    if not config.BILLING_AND_SUBSCRIPTION_ENABLED:
        return {"status": "billing_frozen", "mode": None, "provider": None}
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
        if binding_status != "active":
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
