"""Privacy-safe usage ledger and quota reconciliation services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from stoa.config import Settings
from stoa.db.repositories import usage_ledger_repo, user_repo
from stoa.services import entitlement_service


QUESTION_SUBMISSION_ACTION = "question_submission"
QUESTION_COUNTER_USAGE_TYPE = "daily_question_submission"
LEDGER_SCHEMA_VERSION = "usage-ledger.v1"


def today_period() -> str:
    """Return the UTC quota period used by the existing daily question counter."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def counter_ttl() -> int:
    """Return the existing two-day TTL horizon for daily question counter rows."""
    return int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())


def build_question_idempotency_key(question_id: str, request_key: str | None = None) -> str:
    """Resolve a stable idempotency key for a question submission."""
    key = str(request_key or "").strip()
    if key:
        return key
    return f"question:{question_id}"


def get_question_usage_event(
    *,
    student_id: str,
    quota_period: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Read an existing question usage ledger event for retry handling."""
    return usage_ledger_repo.get_usage_event(
        student_id=student_id,
        action=QUESTION_SUBMISSION_ACTION,
        quota_period=quota_period,
        idempotency_key=idempotency_key,
    )


def record_question_usage_event(
    *,
    student_id: str,
    question_id: str,
    quota_period: str,
    idempotency_key: str,
    counter_key: str,
    counter_value: int,
    quantity: int,
    entitlement: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Persist one consumed question usage event.

    The atomic counter remains the enforcement primitive. The ledger write happens
    after the counter increment and stores the entitlement snapshot used for that
    quota decision, without raw question content or provider billing payloads.
    """
    effective_plan = str(entitlement.get("effectivePlan") or "free")
    parent_id = entitlement.get("parentId")
    event = {
        "PK": f"USAGE_LEDGER#{student_id}",
        "SK": f"EVENT#{QUESTION_SUBMISSION_ACTION}#{quota_period}#{idempotency_key}",
        "entity_type": "usage_ledger_event",
        "schema_version": LEDGER_SCHEMA_VERSION,
        "event_id": f"{student_id}:{QUESTION_SUBMISSION_ACTION}:{quota_period}:{idempotency_key}",
        "actor_id": student_id,
        "actor_role": "student",
        "student_id": student_id,
        "parent_id": parent_id,
        "action": QUESTION_SUBMISSION_ACTION,
        "quantity": quantity,
        "quota_period": quota_period,
        "counter_key": counter_key,
        "counter_value_after": counter_value,
        "idempotency_key": idempotency_key,
        "request_correlation_id": question_id,
        "question_id": question_id,
        "effective_plan": effective_plan,
        "entitlement_source": entitlement.get("source"),
        "entitlement_snapshot": _entitlement_snapshot(entitlement),
        "privacy": {
            "raw_content_stored": False,
            "private_artifact_keys_stored": False,
            "provider_payloads_stored": False,
        },
        "metadata": {
            "usage_type": QUESTION_COUNTER_USAGE_TYPE,
            "write_order": "counter_then_ledger",
        },
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": counter_ttl(),
    }
    created = usage_ledger_repo.put_usage_event(event)
    return {**event, "idempotency_status": "created" if created else "duplicate"}


def reconcile_question_usage(
    *,
    student_id: str,
    day: str,
    repair: bool = False,
) -> dict[str, Any]:
    """Compare one daily question counter row with ledger event totals."""
    counter = usage_ledger_repo.get_daily_question_counter(student_id, day) or {}
    events = usage_ledger_repo.list_usage_events(
        student_id=student_id,
        action=QUESTION_SUBMISSION_ACTION,
        quota_period=day,
    )
    counter_count = int(counter.get("count") or 0)
    ledger_count = sum(int(event.get("quantity") or 0) for event in events)
    status = _reconciliation_status(counter_count, ledger_count)
    repaired = False
    if repair and status in {"counter-missing", "count-mismatch"}:
        usage_ledger_repo.set_daily_question_counter(
            student_id=student_id,
            day=day,
            count=ledger_count,
            expires_at=int(counter.get("expires_at") or counter_ttl()),
        )
        counter_count = ledger_count
        status = _reconciliation_status(counter_count, ledger_count)
        repaired = True
    return {
        "studentId": student_id,
        "action": QUESTION_SUBMISSION_ACTION,
        "quotaPeriod": day,
        "counterKey": f"USAGE#{student_id}/QUESTION#{day}",
        "counterCount": counter_count,
        "ledgerCount": ledger_count,
        "eventCount": len(events),
        "status": status,
        "repairMode": "applied" if repaired else ("preview" if not repair else "noop"),
        "repaired": repaired,
        "partial": status != "matched",
    }


def build_student_usage_summary(
    *,
    student_id: str,
    settings: Settings,
    day: str | None = None,
    entitlement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded support-grade usage summary for one student."""
    day = day or today_period()
    profile = user_repo.get_user(student_id) or {}
    entitlement = entitlement or entitlement_service.resolve_student_entitlement(
        student_id,
        settings=settings,
        student_profile=profile,
    )
    reconciliation = reconcile_question_usage(student_id=student_id, day=day)
    limit = int((entitlement.get("limits") or {}).get("dailyAiQuestionLimit") or 0)
    consumed = reconciliation["counterCount"]
    remaining = max(limit - consumed, 0)
    return {
        "studentId": student_id,
        "parentId": entitlement.get("parentId"),
        "quotaPeriod": day,
        "action": QUESTION_SUBMISSION_ACTION,
        "consumed": consumed,
        "limit": limit,
        "remaining": remaining,
        "effectivePlan": entitlement.get("effectivePlan"),
        "entitlementSource": entitlement.get("source"),
        "billingState": entitlement.get("billingState"),
        "reconciliation": reconciliation,
        "partial": reconciliation["status"] != "matched",
        "stale": False,
        "unreconciled": reconciliation["status"] != "matched",
    }


def list_parent_usage_summaries(
    *,
    parent_id: str,
    settings: Settings,
    day: str | None = None,
) -> list[dict[str, Any]]:
    """Return usage summaries for every active child binding."""
    summaries: list[dict[str, Any]] = []
    for binding in user_repo.list_parent_student_bindings(parent_id):
        if str(binding.get("status") or "active") != "active":
            continue
        student_id = str(binding.get("student_id") or "")
        if not student_id:
            continue
        summaries.append(build_student_usage_summary(student_id=student_id, settings=settings, day=day))
    return summaries


def list_question_usage_events(
    *,
    student_id: str,
    day: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return redacted usage ledger events for support/admin inspection."""
    events = usage_ledger_repo.list_usage_events(
        student_id=student_id,
        action=QUESTION_SUBMISSION_ACTION,
        quota_period=day,
        limit=limit,
    )
    return [_event_response(event) for event in events]


def _entitlement_snapshot(entitlement: dict[str, Any]) -> dict[str, Any]:
    return {
        "effectivePlan": entitlement.get("effectivePlan"),
        "source": entitlement.get("source"),
        "limits": entitlement.get("limits") or {},
        "billingState": entitlement.get("billingState"),
        "period": entitlement.get("period") or {},
        "blockingReason": entitlement.get("blockingReason"),
        "bindingStatus": entitlement.get("bindingStatus"),
        "studentTier": entitlement.get("studentTier"),
        "parentTier": entitlement.get("parentTier"),
    }


def _reconciliation_status(counter_count: int, ledger_count: int) -> str:
    if counter_count == ledger_count:
        return "matched"
    if counter_count > 0 and ledger_count == 0:
        return "ledger-missing"
    if counter_count == 0 and ledger_count > 0:
        return "counter-missing"
    return "count-mismatch"


def _event_response(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": event.get("event_id"),
        "studentId": event.get("student_id"),
        "parentId": event.get("parent_id"),
        "action": event.get("action"),
        "quantity": event.get("quantity"),
        "quotaPeriod": event.get("quota_period"),
        "counterKey": event.get("counter_key"),
        "counterValueAfter": event.get("counter_value_after"),
        "idempotencyKey": event.get("idempotency_key"),
        "questionId": event.get("question_id"),
        "effectivePlan": event.get("effective_plan"),
        "entitlementSource": event.get("entitlement_source"),
        "entitlementSnapshot": event.get("entitlement_snapshot") or {},
        "privacy": event.get("privacy") or {},
        "createdAt": event.get("created_at"),
    }
