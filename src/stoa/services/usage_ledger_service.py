"""Privacy-safe usage ledger and quota reconciliation services."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from stoa.config import Settings
from stoa.db.repositories import usage_ledger_repo, user_repo
from stoa.services import entitlement_service


QUESTION_SUBMISSION_ACTION = "question_submission"
QUESTION_COUNTER_USAGE_TYPE = "daily_question_submission"
LEDGER_SCHEMA_VERSION = "usage-ledger.v1"
CHAT_MESSAGE_ACTION = "chat_message"
HINT_REQUEST_ACTION = "hint_request"
QUESTION_TEACHER_HELP_ACTION = "question_teacher_help_request"
CONVERSATION_TEACHER_HELP_ACTION = "conversation_teacher_help_request"
PRACTICE_TEACHER_HELP_ACTION = "practice_teacher_help_request"
PRACTICE_ANSWER_ACTION = "practice_answer"
PRACTICE_LESSON_COMPLETION_ACTION = "practice_lesson_completion"
ASSIGNMENT_STARTED_ACTION = "assignment_started"
ASSIGNMENT_COMPLETED_ACTION = "assignment_completed"
ASSIGNMENT_SKIPPED_ACTION = "assignment_skipped"
ASSIGNMENT_ARCHIVED_ACTION = "assignment_archived"
REVIEWED_ASSIGNMENT_GENERATION_ACTION = "reviewed_assignment_generation"

_FORBIDDEN_METADATA_KEYS = {
    "answer",
    "assistant_message",
    "auth_token",
    "content",
    "correct_answer",
    "generated_artifact",
    "generated_content",
    "hint",
    "image_s3_key",
    "message",
    "private_artifact_key",
    "private_artifact_keys",
    "prompt",
    "provider_payload",
    "raw_content",
    "student_answer",
    "teacher_message",
    "teacher_response",
    "token",
    "verification_code",
}
_ALLOWED_METADATA_KEYS = {
    "action_family",
    "assignment_id",
    "attempt_result",
    "batch_id",
    "candidate_id",
    "challenge_id",
    "conversation_id",
    "counter_key",
    "counter_value_after",
    "delivery_state",
    "exercise_id",
    "grade_level",
    "lesson_id",
    "policy_id",
    "question_id",
    "request_id",
    "resource_id",
    "source",
    "source_type",
    "source_type",
    "status",
    "subject",
    "summary_group",
    "topic_id",
    "unit_id",
    "quota_enforced",
    "support_visible",
    "usage_type",
    "write_order",
}


@dataclass(frozen=True)
class UsageActionDefinition:
    """Governed usage ledger action contract.

    The taxonomy is intentionally small and explicit. It tells route-level
    instrumentation which actions may write ledger rows, how they should be
    summarized, and whether an existing quota counter participates.
    """

    action: str
    usage_type: str
    summary_group: str
    description: str
    quota_enforced: bool
    support_visible: bool
    counter_prefix: str | None = None
    entitlement_limit_key: str | None = None
    default_quantity: int = 1
    idempotency_strategy: str = "resource_id"
    success_condition: str = "successful_route_completion"
    excluded_when: tuple[str, ...] = ()


USAGE_ACTION_DEFINITIONS: dict[str, UsageActionDefinition] = {
    QUESTION_SUBMISSION_ACTION: UsageActionDefinition(
        action=QUESTION_SUBMISSION_ACTION,
        usage_type=QUESTION_COUNTER_USAGE_TYPE,
        summary_group="questions",
        description="Successful quota-governed student question submission.",
        quota_enforced=True,
        support_visible=True,
        counter_prefix="QUESTION",
        entitlement_limit_key="dailyAiQuestionLimit",
        idempotency_strategy="request_key_or_question_id",
        success_condition="daily_question_counter_incremented",
        excluded_when=("counter_rejected", "duplicate_retry_returned_existing_question"),
    ),
    CHAT_MESSAGE_ACTION: UsageActionDefinition(
        action=CHAT_MESSAGE_ACTION,
        usage_type="daily_chat_message",
        summary_group="chat",
        description="Successful student chat message that triggers an assistant response.",
        quota_enforced=True,
        support_visible=True,
        counter_prefix="CHAT",
        entitlement_limit_key="dailyChatMessageLimit",
        success_condition="chat_counter_incremented_and_messages_persisted",
        excluded_when=("conversation_not_found", "counter_rejected", "read_only_history"),
    ),
    HINT_REQUEST_ACTION: UsageActionDefinition(
        action=HINT_REQUEST_ACTION,
        usage_type="daily_hint_request",
        summary_group="hints",
        description="Successful student hint request for a practice challenge.",
        quota_enforced=True,
        support_visible=True,
        counter_prefix="HINT",
        entitlement_limit_key="dailyHintLimit",
        success_condition="hint_counter_incremented_and_hint_returned",
        excluded_when=("challenge_not_found", "counter_rejected", "passive_hint_render"),
    ),
    QUESTION_TEACHER_HELP_ACTION: UsageActionDefinition(
        action=QUESTION_TEACHER_HELP_ACTION,
        usage_type="support_question_teacher_help_request",
        summary_group="teacher_help",
        description="Successful student escalation of a question to human help.",
        quota_enforced=False,
        support_visible=True,
        success_condition="question_marked_escalated",
        excluded_when=("question_not_found", "not_owner", "already_teacher_active"),
    ),
    CONVERSATION_TEACHER_HELP_ACTION: UsageActionDefinition(
        action=CONVERSATION_TEACHER_HELP_ACTION,
        usage_type="support_conversation_teacher_help_request",
        summary_group="teacher_help",
        description="Successful student escalation of a conversation to human help.",
        quota_enforced=False,
        support_visible=True,
        success_condition="conversation_marked_escalated",
        excluded_when=("conversation_not_found", "not_owner"),
    ),
    PRACTICE_TEACHER_HELP_ACTION: UsageActionDefinition(
        action=PRACTICE_TEACHER_HELP_ACTION,
        usage_type="support_practice_teacher_help_request",
        summary_group="teacher_help",
        description="Successful student escalation of a practice challenge to human help.",
        quota_enforced=False,
        support_visible=True,
        success_condition="practice_teacher_help_request_accepted",
        excluded_when=("challenge_not_found", "not_owner"),
    ),
    PRACTICE_ANSWER_ACTION: UsageActionDefinition(
        action=PRACTICE_ANSWER_ACTION,
        usage_type="support_practice_answer",
        summary_group="practice",
        description="Submitted answer for a practice challenge.",
        quota_enforced=False,
        support_visible=True,
        success_condition="practice_attempt_recorded",
        excluded_when=("challenge_not_found", "passive_exercise_read"),
    ),
    PRACTICE_LESSON_COMPLETION_ACTION: UsageActionDefinition(
        action=PRACTICE_LESSON_COMPLETION_ACTION,
        usage_type="support_practice_lesson_completion",
        summary_group="practice",
        description="Student marks a practice lesson complete.",
        quota_enforced=False,
        support_visible=True,
        success_condition="lesson_completion_recorded",
        excluded_when=("lesson_not_found", "catalog_read"),
    ),
    ASSIGNMENT_STARTED_ACTION: UsageActionDefinition(
        action=ASSIGNMENT_STARTED_ACTION,
        usage_type="support_assignment_started",
        summary_group="assignments",
        description="Student starts a reviewed assignment.",
        quota_enforced=False,
        support_visible=True,
        success_condition="assignment_transitioned_to_started",
        excluded_when=("assignment_not_found", "unauthorized", "duplicate_transition"),
    ),
    ASSIGNMENT_COMPLETED_ACTION: UsageActionDefinition(
        action=ASSIGNMENT_COMPLETED_ACTION,
        usage_type="support_assignment_completed",
        summary_group="assignments",
        description="Student completes a reviewed assignment.",
        quota_enforced=False,
        support_visible=True,
        success_condition="assignment_transitioned_to_completed",
        excluded_when=("assignment_not_found", "unauthorized", "duplicate_transition"),
    ),
    ASSIGNMENT_SKIPPED_ACTION: UsageActionDefinition(
        action=ASSIGNMENT_SKIPPED_ACTION,
        usage_type="support_assignment_skipped",
        summary_group="assignments",
        description="Student skips a reviewed assignment.",
        quota_enforced=False,
        support_visible=True,
        success_condition="assignment_transitioned_to_skipped",
        excluded_when=("assignment_not_found", "unauthorized", "duplicate_transition"),
    ),
    ASSIGNMENT_ARCHIVED_ACTION: UsageActionDefinition(
        action=ASSIGNMENT_ARCHIVED_ACTION,
        usage_type="support_assignment_archived",
        summary_group="assignments",
        description="Tutor or admin archives a reviewed assignment.",
        quota_enforced=False,
        support_visible=True,
        success_condition="assignment_transitioned_to_archived",
        excluded_when=("assignment_not_found", "unauthorized", "duplicate_transition"),
    ),
    REVIEWED_ASSIGNMENT_GENERATION_ACTION: UsageActionDefinition(
        action=REVIEWED_ASSIGNMENT_GENERATION_ACTION,
        usage_type="support_reviewed_assignment_generation",
        summary_group="generation",
        description="Reviewed assignment or exercise generation accepted into a governed workflow.",
        quota_enforced=False,
        support_visible=True,
        success_condition="reviewed_generation_persisted",
        excluded_when=("preview_only", "draft_only", "provider_failure", "unreviewed_generation"),
    ),
}


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


def list_usage_action_definitions() -> list[dict[str, Any]]:
    """Return the governed usage actions as API/documentation-safe dictionaries."""
    return [asdict(definition) for definition in USAGE_ACTION_DEFINITIONS.values()]


def get_usage_action_definition(action: str) -> UsageActionDefinition:
    """Return a governed action definition or raise for unsupported actions."""
    try:
        return USAGE_ACTION_DEFINITIONS[action]
    except KeyError as exc:
        raise ValueError(f"Unsupported usage ledger action: {action}") from exc


def build_usage_idempotency_key(
    *,
    action: str,
    resource_id: str,
    request_key: str | None = None,
    qualifier: str | None = None,
) -> str:
    """Build a deterministic idempotency key for governed non-question actions."""
    get_usage_action_definition(action)
    key = str(request_key or "").strip()
    if key:
        return key
    resource = str(resource_id or "").strip()
    if not resource:
        raise ValueError("resource_id is required for usage idempotency")
    suffix = f":{qualifier.strip()}" if qualifier and qualifier.strip() else ""
    return f"{action}:{resource}{suffix}"


def safe_usage_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Filter usage metadata down to bounded support-safe fields."""
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = str(key)
        if normalized_key in _FORBIDDEN_METADATA_KEYS or normalized_key not in _ALLOWED_METADATA_KEYS:
            continue
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[normalized_key] = value
        elif isinstance(value, list):
            safe[normalized_key] = [item for item in value if isinstance(item, (str, int, float, bool))]
    return safe


def usage_privacy_flags() -> dict[str, bool]:
    """Return the privacy flags required on every usage ledger event."""
    return {
        "raw_content_stored": False,
        "raw_learning_content_stored": False,
        "private_artifact_keys_stored": False,
        "provider_payloads_stored": False,
        "auth_tokens_stored": False,
        "verification_codes_stored": False,
    }


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
            **usage_privacy_flags(),
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


def record_usage_event(
    *,
    student_id: str,
    action: str,
    quota_period: str,
    idempotency_key: str,
    quantity: int | None = None,
    created_at: str,
    entitlement: dict[str, Any] | None = None,
    parent_id: str | None = None,
    actor_role: str = "student",
    counter_key: str | None = None,
    counter_value: int | None = None,
    request_correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one governed non-question usage event.

    This helper is for v5.11 action coverage beyond question submissions. It is
    intentionally content-safe and taxonomy-gated. Question submissions keep the
    existing specialized helper because their counter remains the enforcement
    source and response compatibility matters.
    """
    definition = get_usage_action_definition(action)
    effective_entitlement = entitlement or {}
    event_parent_id = parent_id if parent_id is not None else effective_entitlement.get("parentId")
    event = {
        "PK": f"USAGE_LEDGER#{student_id}",
        "SK": f"EVENT#{action}#{quota_period}#{idempotency_key}",
        "entity_type": "usage_ledger_event",
        "schema_version": LEDGER_SCHEMA_VERSION,
        "event_id": f"{student_id}:{action}:{quota_period}:{idempotency_key}",
        "actor_id": student_id,
        "actor_role": actor_role,
        "student_id": student_id,
        "parent_id": event_parent_id,
        "action": action,
        "quantity": int(quantity if quantity is not None else definition.default_quantity),
        "quota_period": quota_period,
        "counter_key": counter_key,
        "counter_value_after": counter_value,
        "idempotency_key": idempotency_key,
        "request_correlation_id": request_correlation_id,
        "effective_plan": effective_entitlement.get("effectivePlan"),
        "entitlement_source": effective_entitlement.get("source"),
        "entitlement_snapshot": _entitlement_snapshot(effective_entitlement) if effective_entitlement else {},
        "privacy": {
            **usage_privacy_flags(),
        },
        "metadata": {
            "usage_type": definition.usage_type,
            "summary_group": definition.summary_group,
            "quota_enforced": definition.quota_enforced,
            "support_visible": definition.support_visible,
            **safe_usage_metadata(metadata),
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
    limit: int | None = None,
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
    stale = _counter_is_stale(counter)
    status = _reconciliation_status(counter_count, ledger_count, limit=limit, stale=stale)
    repaired = False
    if repair and status in {"counter-missing", "count-mismatch"}:
        usage_ledger_repo.set_daily_question_counter(
            student_id=student_id,
            day=day,
            count=ledger_count,
            expires_at=int(counter.get("expires_at") or counter_ttl()),
        )
        counter_count = ledger_count
        stale = False
        status = _reconciliation_status(counter_count, ledger_count, limit=limit)
        repaired = True
    support = _reconciliation_support_state(
        status=status,
        counter_count=counter_count,
        ledger_count=ledger_count,
        limit=limit,
        stale=stale,
    )
    return {
        "studentId": student_id,
        "action": QUESTION_SUBMISSION_ACTION,
        "quotaPeriod": day,
        "counterKey": f"USAGE#{student_id}/QUESTION#{day}",
        "counterCount": counter_count,
        "ledgerCount": ledger_count,
        "eventCount": len(events),
        "status": status,
        "drift": counter_count - ledger_count,
        "stale": stale,
        "supportAction": support["supportAction"],
        "explanation": support["explanation"],
        "repairMode": "applied" if repaired else ("preview" if not repair else "noop"),
        "repaired": repaired,
        "partial": not _reconciliation_is_ok(status),
    }


def reconcile_usage_action(
    *,
    student_id: str,
    day: str,
    action: str,
    repair: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Reconcile one governed action for support summaries."""
    if action == QUESTION_SUBMISSION_ACTION:
        return reconcile_question_usage(student_id=student_id, day=day, repair=repair, limit=limit)
    definition = get_usage_action_definition(action)
    events = usage_ledger_repo.list_usage_events(
        student_id=student_id,
        action=action,
        quota_period=day,
    )
    ledger_count = sum(int(event.get("quantity") or 0) for event in events)
    counter_count = 0
    counter_key = None
    status = "ledger-only"
    stale = False
    if definition.counter_prefix:
        counter = usage_ledger_repo.get_daily_usage_counter(
            student_id=student_id,
            counter_prefix=definition.counter_prefix,
            day=day,
        ) or {}
        counter_count = int(counter.get("count") or 0)
        counter_key = f"USAGE#{student_id}/{definition.counter_prefix}#{day}"
        stale = _counter_is_stale(counter)
        status = _reconciliation_status(counter_count, ledger_count, limit=limit, stale=stale)
    support = _reconciliation_support_state(
        status=status,
        counter_count=counter_count,
        ledger_count=ledger_count,
        limit=limit,
        stale=stale,
    )
    return {
        "studentId": student_id,
        "action": action,
        "quotaPeriod": day,
        "counterKey": counter_key,
        "counterCount": counter_count,
        "ledgerCount": ledger_count,
        "eventCount": len(events),
        "status": status,
        "drift": counter_count - ledger_count,
        "stale": stale,
        "supportAction": support["supportAction"],
        "explanation": support["explanation"],
        "repairMode": "preview" if not repair else "unsupported",
        "repaired": False,
        "partial": not _reconciliation_is_ok(status),
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
    limit = int((entitlement.get("limits") or {}).get("dailyAiQuestionLimit") or 0)
    reconciliation = reconcile_question_usage(student_id=student_id, day=day, limit=limit)
    consumed = reconciliation["counterCount"]
    remaining = max(limit - consumed, 0)
    action_summaries = _build_action_summaries(
        student_id=student_id,
        day=day,
        entitlement=entitlement,
        question_reconciliation=reconciliation,
    )
    groups = _usage_groups(action_summaries)
    unreconciled = any(not _reconciliation_is_ok(item["reconciliation"]["status"]) for item in action_summaries)
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
        "supportAction": reconciliation["supportAction"],
        "explanation": reconciliation["explanation"],
        "actions": action_summaries,
        "groups": groups,
        "totals": {
            "consumed": sum(int(item.get("consumed") or 0) for item in action_summaries),
            "quotaEnforcedConsumed": sum(
                int(item.get("consumed") or 0) for item in action_summaries if item.get("quotaEnforced")
            ),
            "supportVisibleConsumed": sum(
                int(item.get("consumed") or 0) for item in action_summaries if item.get("supportVisible")
            ),
            "actionCount": len(action_summaries),
            "unreconciledActionCount": sum(
                1 for item in action_summaries if not _reconciliation_is_ok(item["reconciliation"]["status"])
            ),
        },
        "partial": unreconciled,
        "stale": any(bool(item["reconciliation"].get("stale")) for item in action_summaries),
        "unreconciled": unreconciled,
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


def list_usage_events(
    *,
    student_id: str,
    day: str,
    action: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return redacted usage ledger events for support/admin inspection."""
    actions = [action] if action else list(USAGE_ACTION_DEFINITIONS)
    events: list[dict[str, Any]] = []
    per_action_limit = max(limit, 1)
    for action_name in actions:
        get_usage_action_definition(action_name)
        events.extend(
            usage_ledger_repo.list_usage_events(
                student_id=student_id,
                action=action_name,
                quota_period=day,
                limit=per_action_limit,
            )
        )
    events = sorted(events, key=lambda event: str(event.get("created_at") or ""), reverse=True)[:limit]
    return [_event_response(event) for event in events]


def list_question_usage_events(
    *,
    student_id: str,
    day: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return redacted question usage ledger events for legacy callers."""
    return list_usage_events(
        student_id=student_id,
        day=day,
        action=QUESTION_SUBMISSION_ACTION,
        limit=limit,
    )


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


def _reconciliation_status(
    counter_count: int,
    ledger_count: int,
    *,
    limit: int | None = None,
    stale: bool = False,
) -> str:
    if counter_count == 0 and ledger_count == 0:
        return "no-usage"
    if limit is not None and limit >= 0 and counter_count > limit:
        return "over-limit"
    if stale and counter_count > 0:
        return "stale"
    if counter_count == ledger_count:
        return "matched"
    if counter_count > 0 and ledger_count == 0:
        return "ledger-missing"
    if counter_count == 0 and ledger_count > 0:
        return "counter-missing"
    return "count-mismatch"


def _counter_is_stale(counter: dict[str, Any]) -> bool:
    expires_at = counter.get("expires_at")
    if expires_at is None:
        return False
    try:
        return int(expires_at) < int(datetime.now(timezone.utc).timestamp())
    except (TypeError, ValueError):
        return False


def _reconciliation_is_ok(status: str) -> bool:
    return status in {"matched", "ledger-only", "no-usage"}


def _reconciliation_support_state(
    *,
    status: str,
    counter_count: int,
    ledger_count: int,
    limit: int | None,
    stale: bool,
) -> dict[str, str]:
    limit_text = "unknown" if limit is None else str(limit)
    if status == "matched":
        return {
            "supportAction": "none",
            "explanation": "Counter and usage ledger match for this quota period.",
        }
    if status == "no-usage":
        return {
            "supportAction": "none",
            "explanation": "No usage was recorded for this action and quota period.",
        }
    if status == "ledger-only":
        return {
            "supportAction": "review_if_disputed",
            "explanation": "This support-visible action is tracked only in the ledger and has no quota counter.",
        }
    if status == "over-limit":
        return {
            "supportAction": "review_counter_and_entitlement",
            "explanation": (
                f"Counter value {counter_count} is above the entitlement limit {limit_text}; "
                "review quota enforcement and recent retries before changing access."
            ),
        }
    if status == "stale" or stale:
        return {
            "supportAction": "review_stale_counter",
            "explanation": "The counter row appears stale for this quota period; verify TTL behavior before using it for support decisions.",
        }
    if status == "ledger-missing":
        return {
            "supportAction": "review_counter_without_ledger",
            "explanation": f"Counter shows {counter_count} consumed but no matching ledger events were found.",
        }
    if status == "counter-missing":
        return {
            "supportAction": "review_ledger_without_counter",
            "explanation": f"Ledger shows {ledger_count} consumed but no matching counter row was found.",
        }
    return {
        "supportAction": "review_count_mismatch",
        "explanation": f"Counter value {counter_count} and ledger total {ledger_count} do not match.",
    }


def _build_action_summaries(
    *,
    student_id: str,
    day: str,
    entitlement: dict[str, Any],
    question_reconciliation: dict[str, Any],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for definition in USAGE_ACTION_DEFINITIONS.values():
        limit = _action_limit(definition, entitlement)
        reconciliation = (
            question_reconciliation
            if definition.action == QUESTION_SUBMISSION_ACTION
            else reconcile_usage_action(student_id=student_id, day=day, action=definition.action, limit=limit)
        )
        consumed = (
            int(reconciliation.get("counterCount") or 0)
            if definition.quota_enforced and reconciliation.get("counterKey")
            else int(reconciliation.get("ledgerCount") or 0)
        )
        summaries.append(
            {
                "action": definition.action,
                "usageType": definition.usage_type,
                "summaryGroup": definition.summary_group,
                "quotaEnforced": definition.quota_enforced,
                "supportVisible": definition.support_visible,
                "consumed": consumed,
                "limit": limit,
                "remaining": max(limit - consumed, 0) if limit is not None else None,
                "reconciliation": reconciliation,
                "supportAction": reconciliation["supportAction"],
                "explanation": reconciliation["explanation"],
                "partial": not _reconciliation_is_ok(reconciliation["status"]),
                "unreconciled": not _reconciliation_is_ok(reconciliation["status"]),
            }
        )
    return summaries


def _action_limit(definition: UsageActionDefinition, entitlement: dict[str, Any]) -> int | None:
    if not definition.quota_enforced:
        return None
    if definition.entitlement_limit_key:
        value = (entitlement.get("limits") or {}).get(definition.entitlement_limit_key)
        if value is not None:
            return int(value)
    return None


def _usage_groups(action_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in action_summaries:
        group = str(item.get("summaryGroup") or "other")
        current = grouped.setdefault(
            group,
            {
                "group": group,
                "consumed": 0,
                "quotaEnforcedConsumed": 0,
                "supportVisibleConsumed": 0,
                "actions": [],
                "unreconciled": False,
                "partial": False,
            },
        )
        consumed = int(item.get("consumed") or 0)
        current["consumed"] += consumed
        if item.get("quotaEnforced"):
            current["quotaEnforcedConsumed"] += consumed
        if item.get("supportVisible"):
            current["supportVisibleConsumed"] += consumed
        current["actions"].append(item["action"])
        current["unreconciled"] = bool(current["unreconciled"] or item.get("unreconciled"))
        current["partial"] = bool(current["partial"] or item.get("partial"))
    return [grouped[key] for key in sorted(grouped)]


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
        "metadata": safe_usage_metadata(event.get("metadata") or {}),
        "createdAt": event.get("created_at"),
    }
