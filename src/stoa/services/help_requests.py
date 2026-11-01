"""真人求助: a student's request for a human teacher, kept and moved in one place (#189).

One conversation has at most one help request, so the request's id is the
conversation's and its record sits in the conversation's partition:
`PK=CONV#{conversation_id}`, `SK=HELP`. Before #189 a request was two rows -
fields on the conversation and a queue row in the question table - written
together in six places, with an ordering between them that lived only in the
reconciler. Now there is this record and this module, and nothing else
writes it.

The record keeps the field names the conversation used (`escalation_status`,
`dispatch_*`, `teacher_id`, ...), so what reads a request - notifications, the
teacher's and the student's responses, account deletion - reads the same
words. Every write is conditional on the record's `version`, so a write made
on a stale read is refused rather than applied.

What lives elsewhere, and is called from here:
- which teacher to offer a request to: `teacher_dispatch_service.plan_dispatch`;
- the weekly case allowance: `teacher_support_allowance_service`;
- telling people: `notification_service`.

The lifecycle (`escalation_status`): `pending` until a teacher takes it, then
`in_progress`, then `resolved`; a request nobody took ends `withdrawn` (the
student) or `expired` (24 hours, the sweep). While pending it is offered to one
teacher at a time for 10 minutes; a teacher who let an offer lapse is not
offered it again.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from boto3.dynamodb.conditions import Attr, Key

from stoa.config import settings
from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.security.private_telemetry import emit_private_event
from stoa.services import (
    notification_service,
    teacher_dispatch_service,
    teacher_reply_service,
    teacher_support_allowance_service,
)

logger = logging.getLogger(__name__)

ENTITY_TYPE = "help_request"
SCHEMA_VERSION = "help-request.v1"
SORT_KEY = "HELP"

PENDING = "pending"
IN_PROGRESS = "in_progress"
RESOLVED = "resolved"
WITHDRAWN = "withdrawn"
EXPIRED = "expired"
OPEN = frozenset({PENDING, IN_PROGRESS})
#: What a teacher moves a request to.
TEACHER_TARGETS = (IN_PROGRESS, RESOLVED)

# Logged for each request nobody could be offered that has waited past the
# alert limit (#88). stoa-infra's metric filter matches this exact string.
TEACHER_HELP_WAITING_EVENT = teacher_dispatch_service.TEACHER_HELP_WAITING_EVENT

# What an offer writes, and what finding nobody writes. Each write that ends
# one of them removes exactly these.
_OFFER_FIELDS = ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at")
_NO_CANDIDATE_FIELDS = ("dispatch_no_candidate_reason", "dispatch_no_candidate_since")
# A scan's ceiling on pages; the table is far from it.
_SCAN_PAGE_LIMIT = 1000

# The question words a request's state is told in, for the readers that take
# a request where they take a question: authorization and the routes keyed by
# a question id (the assistance summary, AI drafts, reports).
_QUESTION_STATUS = {
    PENDING: "escalated",
    IN_PROGRESS: "teacher_active",
    RESOLVED: "resolved",
    WITHDRAWN: "withdrawn",
    EXPIRED: "expired",
}


# ── Errors ───────────────────────────────────────────────────────────────────


class HelpRequestConflict(Exception):
    """The request is not in the state the change was decided on."""


class HelpRequestEndingRefused(Exception):
    """The request cannot be ended this way; ``code`` says why, for the response."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HelpRequestEndingUnavailable(Exception):
    """Ending the request could not be completed now; trying again is safe."""


class HelpRequestUnavailable(Exception):
    """The request could not be read or written now; trying again is safe."""


# ── Reading ──────────────────────────────────────────────────────────────────


def key(conversation_id: str) -> dict[str, str]:
    return {"PK": f"CONV#{conversation_id}", "SK": SORT_KEY}


def _is_record(item: object) -> bool:
    return (
        isinstance(item, Mapping)
        and item.get("entity_type") == ENTITY_TYPE
        and not account_deletion_repo.is_deletion_tombstone(item)
        and bool(item.get("conversation_id"))
    )


def get(conversation_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    """The request of one conversation, read strongly; None when it never asked.

    A failed read is raised as `HelpRequestUnavailable`, never answered as
    absent: "never asked" is a decision callers act on.
    """
    if not conversation_id:
        return None
    store: Any = table or get_table()
    try:
        response = store.get_item(Key=key(conversation_id), ConsistentRead=True)
    except Exception as exc:  # noqa: BLE001 - unknown is not absent
        raise HelpRequestUnavailable(conversation_id) from exc
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(cast(Mapping[str, Any], item)) if _is_record(item) else None


def list_all(*, table: Any | None = None) -> list[dict[str, Any]]:
    """Every request on the table, ended ones included, from every page.

    A filtered scan stops at a page of the table, not at the matches (#95), so
    every page is read. There is no index by state; requests are few.
    """
    store: Any = table or get_table()
    request: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq(ENTITY_TYPE)}
    items: list[dict[str, Any]] = []
    for _page in range(_SCAN_PAGE_LIMIT):
        response = store.scan(**request)
        items.extend(dict(item) for item in response.get("Items", []) if _is_record(item))
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return items
        if not isinstance(cursor, Mapping) or cursor == request.get("ExclusiveStartKey"):
            raise HelpRequestUnavailable("scan did not advance")
        request["ExclusiveStartKey"] = dict(cursor)
    raise HelpRequestUnavailable("scan page limit reached")


def list_open(*, table: Any | None = None) -> list[dict[str, Any]]:
    """The requests a student is still waiting on: pending ones."""
    return [record for record in list_all(table=table) if _status(record) == PENDING]


def for_student(student_id: str, *, table: Any | None = None) -> dict[str, dict[str, Any]]:
    """A student's requests, keyed by conversation id.

    The record carries `student_id` and `created_at`, so it is in
    GSI-StudentId beside the student's conversations; the readers that list a
    student's conversations read their requests from the same index.
    """
    if not student_id:
        return {}
    store: Any = table or get_table()
    request: dict[str, Any] = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": Key("student_id").eq(student_id),
        "FilterExpression": Attr("entity_type").eq(ENTITY_TYPE),
    }
    found: dict[str, dict[str, Any]] = {}
    for _page in range(_SCAN_PAGE_LIMIT):
        response = store.query(**request)
        for item in response.get("Items", []):
            if _is_record(item) and item.get("student_id") == student_id:
                found[str(item["conversation_id"])] = dict(item)
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return found
        request["ExclusiveStartKey"] = cursor
    raise HelpRequestUnavailable("student index page limit reached")


def with_requests(
    conversations: Sequence[Mapping[str, Any]], student_id: str, *, table: Any | None = None
) -> list[dict[str, Any]]:
    """The student's conversations, each with its request's fields laid over it.

    For the readers that ask of a conversation whether a teacher was asked
    (`escalated`, `escalated_at`, `escalation_status`, `escalation_message`):
    the request is no longer on the conversation row. A read that fails gives
    the conversations as they are - these readers summarise, they decide nothing.
    """
    try:
        requests = for_student(student_id, table=table)
    except Exception:  # noqa: BLE001 - a summary without the requests, not none
        logger.warning("help_requests_unavailable_for_summary", exc_info=True)
        requests = {}
    merged: list[dict[str, Any]] = []
    for row in conversations:
        request = (
            requests.get(str(row.get("conversation_id") or ""))
            if row.get("entity_type") == "conversation"
            else None
        )
        merged.append({**row, **_overlay(request)} if request else dict(row))
    return merged


def _overlay(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "escalated": True,
        "escalated_at": record.get("escalated_at"),
        "escalation_status": record.get("escalation_status"),
        "escalation_message": record.get("escalation_message"),
        "escalation_request_id": record.get("escalation_request_id"),
    }


def _status(record: Mapping[str, Any]) -> str:
    return str(record.get("escalation_status") or PENDING)


def student_view(record: Mapping[str, Any], *, now: str | None = None) -> tuple[str, str]:
    """What the waiting student is told, and which teacher (if any) to name (#86).

    Returns ``(status, teacher_id)``. A teacher is named only while it holds
    the request: it took it, or its offer has not lapsed.
    """
    timestamp = now or _now()
    stored = _status(record)
    holder = str(record.get("teacher_id") or "")
    if stored != PENDING:
        return stored, holder
    if holder:
        return "assigned", holder
    if _live_offer(record, timestamp):
        return "assigned", str(record.get("dispatched_teacher_id") or "")
    if record.get("dispatch_status") == "no_candidate":
        return "waiting_no_teacher", ""
    return PENDING, ""


def question_view(record: Mapping[str, Any]) -> dict[str, Any]:
    """The request told as a question, for the readers keyed by a question id.

    Authorization judges a teacher's task on a question's fields; the
    assistance summary, AI drafts and reports take a question. The request id
    is the question id they are given.
    """
    view = dict(record)
    view.update(
        {
            "question_id": str(record.get("escalation_request_id") or record.get("conversation_id")),
            "entity_type": "question",
            "source": "conversation_escalation",
            "status": _QUESTION_STATUS.get(_status(record), _status(record)),
            "content": str(record.get("escalation_message") or ""),
            "teacher_requested_at": record.get("escalated_at"),
            "dispatch_status": str(
                record.get("dispatch_status") or ("accepted" if record.get("teacher_id") else "unassigned")
            ),
        }
    )
    return view


def question_view_for(request_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    """`question_view` of the request with this id, or None when there is none."""
    record = get(request_id, table=table)
    return question_view(record) if record else None


def holder_or_offered(record: Mapping[str, Any], teacher_id: str) -> bool:
    """Whether this teacher may write the request at all.

    Only the teacher holding it, or the one it is offered to. A teacher the
    policy admits through an assignment may read it but not write it (#73).
    """
    holder = str(record.get("teacher_id") or "")
    if holder:
        return holder == teacher_id
    return str(record.get("dispatched_teacher_id") or "") == teacher_id


def sla(record: Mapping[str, Any]) -> dict[str, Any]:
    """How long the student waited for a first reply (#189 Q4: the first reply).

    Opening the request no longer counts; only a teacher's reply does.
    """
    seconds = _seconds_between(record.get("escalated_at"), record.get("first_teacher_action_at"))
    return {
        "status": teacher_reply_service.sla_bucket(seconds),
        "requestToFirstActionMinutes": round(seconds / 60) if seconds is not None else None,
        "targetMinutes": teacher_reply_service.FIRST_REPLY_TARGET_SECONDS // 60,
    }


def sla_metrics(record: Mapping[str, Any]) -> dict[str, Any]:
    """One request in the words `teacher_reply_service.aggregate_teacher_sla` counts."""
    first_reply = _seconds_between(record.get("escalated_at"), record.get("first_teacher_action_at"))
    return {
        "status": _QUESTION_STATUS.get(_status(record), _status(record)),
        "teacher_requested_at": record.get("escalated_at"),
        "sla_request_to_first_reply_seconds": first_reply,
        "sla_request_to_takeover_seconds": _seconds_between(
            record.get("escalated_at"), record.get("accepted_at")
        ),
        "sla_request_to_resolved_seconds": _seconds_between(
            record.get("escalated_at"), record.get("escalation_resolved_at")
        ),
        "teacher_first_reply_sla_bucket": (
            teacher_reply_service.sla_bucket(first_reply) if first_reply is not None else None
        ),
    }


# ── Asking ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AskOutcome:
    """What asking came to. ``record`` is set unless the admission refused."""

    disposition: teacher_support_allowance_service.TeacherSupportAdmissionDisposition | None
    record: dict[str, Any] | None
    #: True when this call wrote the request; False for one asked before.
    created: bool = False


def ask(
    *,
    conversation: Mapping[str, Any],
    student_id: str,
    message: str | None,
    system_message: str,
    now: str | None = None,
    table: Any | None = None,
) -> AskOutcome:
    """Open the conversation's request, spending a case of the week, and offer it.

    A conversation that already has a request answers with it, whatever its
    state: one conversation asks a teacher once (#189 decision 3). The case is
    admitted by the allowance, and the record, the system message that opens
    the request in the conversation and the case are written in one
    transaction behind the student's account fence. The first offer is made
    right after; it is best effort, and the sweep makes it if this one fails.
    """
    store: Any = table or get_table()
    timestamp = now or _now()
    conversation_id = str(conversation.get("conversation_id") or "")
    if not conversation_id or conversation.get("student_id") != student_id:
        raise HelpRequestConflict("conversation is not this student's")
    existing = get(conversation_id, table=store)
    if existing is not None:
        return AskOutcome(None, existing)

    generation = int(
        account_deletion_repo.require_active_account_fence(student_id, table=store)["generation"]
    )
    record = {
        **key(conversation_id),
        "entity_type": ENTITY_TYPE,
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": student_id,
        "owner_id": student_id,
        "account_fence_generation": generation,
        "version": 1,
        "escalated": True,
        "escalation_status": PENDING,
        "escalated_at": timestamp,
        # With `student_id`, this puts the record in GSI-StudentId (`for_student`).
        "created_at": timestamp,
        "updated_at": timestamp,
        "subject": str(conversation.get("subject") or ""),
        "grade": str(conversation.get("grade") or ""),
    }
    note = str(message or "").strip()
    if note:
        record["escalation_message"] = note
    system_row = {
        "PK": f"CONV#{conversation_id}",
        "SK": f"MSG#{conversation_id}",
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": conversation_id,
        "conversation_id": conversation_id,
        "student_id": student_id,
        "owner_id": student_id,
        "account_fence_generation": generation,
        "role": "system",
        "content": system_message,
        "system_event": "teacher_help_requested",
        "escalation_message": message,
        "created_at": timestamp,
    }
    record_operations = attachment_repo.build_conversation_write_transaction(
        item=record, owner_id=student_id, generation=generation
    )
    rows: list[dict[str, Any]] = [
        *cast(list[dict[str, Any]], record_operations),
        cast(
            dict[str, Any],
            attachment_repo.build_conversation_write_transaction(
                item=system_row, owner_id=student_id, generation=generation
            )[1],
        ),
        {
            "ConditionCheck": {
                "Key": {"PK": f"CONV#{conversation_id}", "SK": "CONV"},
                "ConditionExpression": "attribute_exists(PK) AND student_id = :student",
                "ExpressionAttributeValues": {":student": student_id},
            }
        },
    ]

    def persist_case(allowance_operations: tuple[dict[str, Any], ...]) -> bool:
        try:
            account_deletion_repo.transact([*rows, *allowance_operations], table=store)
        except Exception:  # noqa: BLE001 - every refusal means something moved
            return False
        return True

    Disposition = teacher_support_allowance_service.TeacherSupportAdmissionDisposition
    admission = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=conversation_id,
        case_kind="conversation",
        beneficiary_id=student_id,
        observed_at=_parse(timestamp) or datetime.now(timezone.utc),
        persist_case=persist_case,
        table=store,
    )
    if admission.disposition is Disposition.REPLAYED:
        # The first attempt's write is there; answer with what it wrote.
        written = get(conversation_id, table=store)
        if written is None:
            raise HelpRequestUnavailable(conversation_id)
        return AskOutcome(admission.disposition, written)
    if admission.disposition is not Disposition.ADMITTED:
        return AskOutcome(admission.disposition, None)

    try:
        offered = dispatch(record, now=timestamp, table=store)
    except Exception:  # noqa: BLE001 - the case is admitted; the sweep offers it
        logger.exception("help request first offer failed")
        offered = record
    return AskOutcome(admission.disposition, offered, created=True)


# ── Offering ─────────────────────────────────────────────────────────────────


def _live_offer(record: Mapping[str, Any], now: str) -> bool:
    return (
        record.get("dispatch_status") == "dispatched"
        and bool(record.get("dispatched_teacher_id"))
        and not _expired(record.get("dispatch_deadline_at"), now)
    )


def _previous(record: Mapping[str, Any], now: str) -> list[str]:
    """Teachers this request must not be offered to again.

    The ones recorded, and the teacher of an offer that lapsed unanswered:
    recording the lapse in the same write as the next offer is what keeps the
    two from disagreeing.
    """
    previous = list(
        dict.fromkeys(str(item) for item in record.get("previous_dispatch_teacher_ids") or [] if item)
    )
    lapsed = str(record.get("dispatched_teacher_id") or "")
    if (
        lapsed
        and record.get("dispatch_status") == "dispatched"
        and _expired(record.get("dispatch_deadline_at"), now)
        and lapsed not in previous
    ):
        previous.append(lapsed)
    return previous


def dispatch(record: Mapping[str, Any], *, now: str | None = None, table: Any | None = None) -> dict[str, Any]:
    """Offer a pending request to the best available teacher, or say nobody is free.

    Returns the record as written. A request already taken, ended, or holding
    a live offer is returned as it is. The offer binds the chosen teacher's
    active account and profile version, and the record's version.
    """
    timestamp = now or _now()
    store: Any = table or get_table()
    if _status(record) != PENDING or record.get("teacher_id") or _live_offer(record, timestamp):
        return dict(record)
    previous = _previous(record, timestamp)
    plan = teacher_dispatch_service.plan_dispatch(
        {**record, "previous_dispatch_teacher_ids": previous}, now=timestamp
    )
    if not plan["selected"]:
        reason = str(plan["summary"]["noCandidateReason"] or "no_eligible_teacher")
        return _record_no_candidate(record, reason=reason, previous=previous, now=timestamp, table=store)

    candidate = plan["selected"][0]
    teacher_id = str(candidate["teacherId"])
    dispatch_id = str(uuid.uuid4())
    deadline = _deadline(timestamp)
    changes: dict[str, Any] = {
        "dispatched_teacher_id": teacher_id,
        "dispatch_status": "dispatched",
        "dispatch_id": dispatch_id,
        "dispatch_deadline_at": deadline,
        "dispatch_attempt_count": _int(record.get("dispatch_attempt_count"), 0) + 1,
        "dispatch_updated_at": timestamp,
        "previous_dispatch_teacher_ids": previous,
    }
    try:
        written = _write(
            record,
            changes,
            remove=_NO_CANDIDATE_FIELDS,
            condition="escalation_status = :pending AND attribute_not_exists(teacher_id)",
            values={":pending": PENDING},
            extra=teacher_dispatch_service.teacher_assignment_conditions(candidate),
            table=store,
        )
    except HelpRequestConflict:
        return dict(record)
    # Only after the offer is written, so a refused offer tells nobody (#141).
    try:
        notification_service.emit_teacher_help_dispatched(
            conversation=written,
            teacher_id=teacher_id,
            dispatch_id=dispatch_id,
            deadline_at=deadline,
            accept_minutes=teacher_dispatch_service.DISPATCH_ACCEPT_TIMEOUT_SECONDS // 60,
        )
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("dispatch_teacher_alert_failed error=%s", type(exc).__name__)
    return written


def _record_no_candidate(
    record: Mapping[str, Any], *, reason: str, previous: list[str], now: str, table: Any
) -> dict[str, Any]:
    """Say that nobody could be offered the request, and since when (#86).

    Written only when something changes, not on every sweep; `since` keeps the
    first time, which the long-wait alert measures from when the request has
    no stamp of its own. A lapsed offer is taken off in the same write and its
    teacher recorded among those already tried.
    """
    unchanged = (
        record.get("dispatch_status") == "no_candidate"
        and record.get("dispatch_no_candidate_reason") == reason
        and not record.get("dispatch_id")
        and previous == list(record.get("previous_dispatch_teacher_ids") or [])
    )
    if unchanged:
        return dict(record)
    changes: dict[str, Any] = {
        "dispatch_status": "no_candidate",
        "dispatch_no_candidate_reason": reason,
        "dispatch_no_candidate_since": record.get("dispatch_no_candidate_since") or now,
        "dispatch_updated_at": now,
        "previous_dispatch_teacher_ids": previous,
    }
    try:
        return _write(
            record,
            changes,
            remove=_OFFER_FIELDS,
            condition="escalation_status = :pending AND attribute_not_exists(teacher_id)",
            values={":pending": PENDING},
            table=table,
        )
    except HelpRequestConflict:
        # The request moved on (an offer, a teacher, a withdrawal); the next
        # sweep looks again.
        logger.info("No-candidate record skipped for %s", record.get("conversation_id"))
        return dict(record)


# ── Ending a request nobody took ─────────────────────────────────────────────


@dataclass(frozen=True)
class _Ending:
    record: dict[str, Any]
    changed: bool
    refund: Any = None
    refund_week: str | None = None


def withdraw(
    conversation_id: str, *, student_id: str, now: str | None = None, table: Any | None = None
) -> dict[str, Any]:
    """The student takes back a request no teacher has taken (#86).

    The request ends `withdrawn` and the week's case goes back, in one write
    that a teacher taking it at the same moment refuses. Withdrawing twice
    returns the withdrawn request and writes nothing.
    """
    return _end(conversation_id, outcome=WITHDRAWN, student_id=student_id, now=now, table=table).record


def expire(
    conversation_id: str,
    *,
    asked_before: str,
    now: str | None = None,
    table: Any | None = None,
) -> dict[str, Any] | None:
    """End a request no teacher took within the waiting limit (#87).

    The same ending as a withdrawal, to `expired`, for a request asked before
    ``asked_before``. The student is told once, by the call that ended it.
    Returns the expired request, or None when this call ended nothing.
    """
    timestamp = now or _now()
    try:
        ending = _end(
            conversation_id, outcome=EXPIRED, asked_before=asked_before, now=timestamp, table=table
        )
    except HelpRequestEndingRefused as refused:
        if refused.code not in _ORDINARY_EXPIRY_REFUSALS:
            logger.warning("Expiry of %s refused: %s", conversation_id, refused.code)
        return None
    if not ending.changed:
        return None
    observed = _parse(timestamp) or datetime.now(timezone.utc)
    notification_service.emit_teacher_help_expired(
        conversation=ending.record,
        case_returned=(
            ending.refund is teacher_support_allowance_service.TeacherSupportRefundDisposition.REFUNDED
            and ending.refund_week == teacher_support_allowance_service.current_week_identity(observed)
        ),
    )
    return ending.record


_ORDINARY_EXPIRY_REFUSALS = frozenset(
    {"teacher_help_already_accepted", "teacher_help_request_closed", "teacher_help_request_not_due"}
)


def _end(
    conversation_id: str,
    *,
    outcome: str,
    student_id: str | None = None,
    asked_before: str | None = None,
    now: str | None = None,
    table: Any | None = None,
) -> _Ending:
    """End a request nobody took, and give its case back.

    ``student_id`` is the withdrawing student, checked against the record; the
    sweep passes none. Each pass reads afresh and makes one attempt; a refused
    write is followed by a new read, never by the same write again.
    """
    allowance = teacher_support_allowance_service
    store: Any = table or get_table()
    timestamp = now or _now()
    observed = _parse(timestamp) or datetime.now(timezone.utc)
    for _ in range(4):
        try:
            record = get(conversation_id, table=store)
        except HelpRequestUnavailable as exc:
            raise HelpRequestEndingUnavailable(conversation_id) from exc
        if record is None:
            raise HelpRequestEndingRefused("teacher_help_request_not_found")
        owner = str(record.get("student_id") or "")
        if not owner or (student_id is not None and owner != student_id):
            raise HelpRequestEndingRefused("teacher_help_request_not_found")
        current = _status(record)
        if current == outcome:
            return _Ending(record, changed=False)
        if record.get("teacher_id") or current in {IN_PROGRESS, RESOLVED}:
            raise HelpRequestEndingRefused("teacher_help_already_accepted")
        if current != PENDING:
            raise HelpRequestEndingRefused("teacher_help_request_closed")
        if asked_before is not None:
            asked = _parse(record.get("escalated_at"))
            cutoff = _parse(asked_before)
            if asked is None:
                logger.warning("Cannot tell when %s was asked for; not expiring it", conversation_id)
                raise HelpRequestEndingRefused("teacher_help_request_not_due")
            if cutoff is None or asked > cutoff:
                raise HelpRequestEndingRefused("teacher_help_request_not_due")
        update = _update_operation(
            record,
            {
                "escalation_status": outcome,
                "dispatch_status": outcome,
                f"escalation_{outcome}_at": timestamp,
                "updated_at": timestamp,
            },
            remove=(*_OFFER_FIELDS, *_NO_CANDIDATE_FIELDS),
            condition="escalation_status = :pending AND attribute_not_exists(teacher_id)",
            values={":pending": PENDING},
        )
        rows = [
            account_deletion_repo.active_fence_condition(
                owner, _int(record.get("account_fence_generation"), 1)
            ),
            update,
        ]

        def persist(refund_operations: tuple[dict[str, Any], ...]) -> bool:
            try:
                account_deletion_repo.transact([*rows, *refund_operations], table=store)
            except Exception:  # noqa: BLE001 - every refusal means something moved
                return False
            return True

        result = allowance.refund_teacher_support_case(
            support_case_id=conversation_id,
            case_kind="conversation",
            beneficiary_id=owner,
            reason=outcome,
            persist_refund=persist,
            observed_at=observed,
            table=store,
            attempts=1,
        )
        Disposition = allowance.TeacherSupportRefundDisposition
        if result.disposition in {
            Disposition.REFUNDED,
            Disposition.ALREADY_REFUNDED,
            Disposition.NOT_ADMITTED,
        }:
            try:
                written = get(conversation_id, table=store)
            except HelpRequestUnavailable:
                written = None
            return _Ending(
                written or {**record, "escalation_status": outcome},
                changed=True,
                refund=result.disposition,
                refund_week=result.week_identity,
            )
        if result.disposition is Disposition.IDEMPOTENCY_CONFLICT:
            raise HelpRequestEndingRefused("teacher_help_request_not_withdrawable")
        # Retryable: something moved (a teacher, the counter). Read again.
    raise HelpRequestEndingUnavailable(conversation_id)


# ── The teacher's moves ──────────────────────────────────────────────────────


def advance(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    target: str,
    now: str | None = None,
    resolution_note: str | None = None,
    reply_operations: Sequence[dict[str, Any]] = (),
    table: Any | None = None,
) -> dict[str, Any]:
    """Move a request to `target` for `teacher_id`: take it, finish it, or both.

    The teacher it is offered to takes it with their first write; the holder
    moves it on. ``reply_operations`` is a reply written in the same
    transaction - replying to an offer takes it - and a reply is what stamps
    the first response (#189 Q4). Every condition the decision rested on is in
    the write: the exact live offer, that this teacher has not let it lapse
    before, the teacher's active account and profile, the student's fence and
    the record's version. If any moved, nothing is written and
    `HelpRequestConflict` is raised.
    """
    if target not in TEACHER_TARGETS:
        raise ValueError(f"unsupported help request status: {target}")
    timestamp = now or _now()
    store: Any = table or get_table()
    current = _status(record)
    holder = str(record.get("teacher_id") or "")
    if current not in OPEN or (holder and holder != teacher_id):
        raise HelpRequestConflict("help request is not open to this teacher")
    accepting = not holder
    changes: dict[str, Any] = {"escalation_status": target, "updated_at": timestamp}
    values: dict[str, Any] = {":teacher": teacher_id}
    if accepting:
        offer = str(record.get("dispatch_id") or "")
        if (
            not offer
            or current != PENDING
            or record.get("dispatch_status") != "dispatched"
            or str(record.get("dispatched_teacher_id") or "") != teacher_id
        ):
            raise HelpRequestConflict("help request holds no offer for this teacher")
        if teacher_id in (record.get("previous_dispatch_teacher_ids") or []):
            raise HelpRequestConflict("teacher already let this request lapse")
        changes.update({"teacher_id": teacher_id, "dispatch_status": "accepted", "accepted_at": timestamp})
        condition = (
            "attribute_not_exists(teacher_id) AND escalation_status = :pending "
            "AND dispatch_status = :dispatched AND dispatched_teacher_id = :teacher "
            "AND dispatch_id = :offer AND dispatch_deadline_at > :now"
        )
        values.update({":pending": PENDING, ":dispatched": "dispatched", ":offer": offer, ":now": timestamp})
    else:
        condition = "teacher_id = :teacher AND escalation_status IN (:pending, :in_progress)"
        values.update({":pending": PENDING, ":in_progress": IN_PROGRESS})
    if target == RESOLVED:
        changes["escalation_resolved_at"] = timestamp
        if resolution_note:
            changes["resolution_note"] = resolution_note
    if reply_operations and not record.get("first_teacher_action_at"):
        changes["first_teacher_action_at"] = timestamp
    return _write(
        record,
        changes,
        condition=condition,
        values=values,
        extra=(*_teacher_standing_conditions(teacher_id, store), *reply_operations),
        fence=True,
        table=store,
    )


def reply(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    reply_operations: Sequence[dict[str, Any]],
    now: str | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """The holder's reply, written only while the request is still theirs.

    A request the teacher has not taken yet is taken by the reply (`advance`).
    A resolved request still takes its holder's replies (#189 decision 2). The
    first reply is the request's first response.
    """
    timestamp = now or _now()
    store: Any = table or get_table()
    if str(record.get("teacher_id") or "") != teacher_id:
        if holder_or_offered(record, teacher_id):
            return advance(
                record,
                teacher_id=teacher_id,
                target=IN_PROGRESS,
                now=timestamp,
                reply_operations=reply_operations,
                table=store,
            )
        raise HelpRequestConflict("help request is not this teacher's")
    changes: dict[str, Any] = {"updated_at": timestamp}
    if not record.get("first_teacher_action_at"):
        changes["first_teacher_action_at"] = timestamp
    return _write(
        record,
        changes,
        condition="teacher_id = :teacher",
        values={":teacher": teacher_id},
        extra=tuple(reply_operations),
        fence=True,
        table=store,
    )


def _teacher_standing_conditions(teacher_id: str, table: Any) -> tuple[dict[str, Any], ...]:
    """Bind the acting teacher's active fence and exact current profile."""
    try:
        response = table.get_item(Key={"PK": f"USER#{teacher_id}", "SK": "PROFILE"}, ConsistentRead=True)
        profile = response.get("Item") if isinstance(response, Mapping) else None
        fence = account_deletion_repo.require_active_account_fence(teacher_id, table=table)
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HelpRequestConflict("teacher account is not active") from exc
    if not isinstance(profile, Mapping) or profile.get("account_status") != "active":
        raise HelpRequestConflict("teacher account is not active")
    role = str(profile.get("role") or "").lower()
    if role not in teacher_dispatch_service.ELIGIBLE_ROLES:
        raise HelpRequestConflict("profile cannot take teacher help requests")
    return teacher_dispatch_service.teacher_assignment_conditions(
        {
            "teacherId": teacher_id,
            "role": str(profile.get("role")),
            "accountFenceGeneration": int(fence["generation"]),
            "profileVersion": _int(profile.get("version"), 0),
        }
    )


# ── The sweep ────────────────────────────────────────────────────────────────


def sweep(*, now: str | None = None, table: Any | None = None) -> dict[str, Any]:
    """Keep every waiting student attached to a teacher who is expected to answer.

    For each pending request: one asked more than 24 hours ago that nobody
    took ends `expired` (#87); one whose offer lapsed, or that was never
    offered, is offered again - never to a teacher who let it lapse - and one
    nobody can be offered is reported once it has waited past the alert limit
    (#88). Safe to run repeatedly: a live offer is left alone.
    """
    timestamp = now or _now()
    store: Any = table or get_table()
    cutoff = (
        (_parse(timestamp) or datetime.now(timezone.utc))
        - timedelta(seconds=settings.teacher_help_expiry_seconds)
    ).isoformat()
    waiting = 0
    lapsed = 0
    offered: list[dict[str, Any]] = []
    expired: list[str] = []
    status = "completed"
    try:
        for record in list_open(table=store):
            conversation_id = str(record.get("conversation_id") or "")
            if _due_to_expire(record, cutoff):
                try:
                    ended = expire(conversation_id, asked_before=cutoff, now=timestamp, table=store)
                except Exception:  # noqa: BLE001 - one request must not stop the sweep
                    logger.warning("Expiry of %s deferred", conversation_id, exc_info=True)
                    ended = None
                if ended is not None:
                    expired.append(conversation_id)
                    continue
            if record.get("teacher_id") or _live_offer(record, timestamp):
                continue
            waiting += 1
            if record.get("dispatch_status") == "dispatched":
                lapsed += 1
            written = dispatch(record, now=timestamp, table=store)
            outcome = str(written.get("dispatch_status") or "")
            if outcome in {"dispatched", "no_candidate"} and written.get("version") != record.get("version"):
                offered.append({"conversationId": conversation_id, "status": outcome})
            if outcome == "no_candidate":
                _report_long_wait(written, now=timestamp)
    except Exception:  # noqa: BLE001
        logger.warning("Help request sweep failed", exc_info=True)
        status = "failed"
    return {
        "reassigned": lapsed,
        "conversationSweep": status,
        "conversationsWaiting": waiting,
        "conversationsDispatched": offered,
        "conversationsExpired": expired,
        "generatedAt": timestamp,
    }


def _due_to_expire(record: Mapping[str, Any], cutoff: str) -> bool:
    if record.get("teacher_id"):
        return False
    asked = _parse(record.get("escalated_at"))
    limit = _parse(cutoff)
    return asked is None or (limit is not None and asked <= limit)


def _report_long_wait(record: Mapping[str, Any], *, now: str) -> None:
    """Tell operations a student has waited past the limit with nobody to ask (#88).

    One closed telemetry line per sweep: the request id and the minutes
    waited, nothing about the student.
    """
    asked = _parse(record.get("escalated_at")) or _parse(record.get("dispatch_no_candidate_since"))
    moment = _parse(now)
    if asked is None or moment is None:
        logger.warning("Cannot tell how long %s has waited; not reported", record.get("conversation_id"))
        return
    waited = (moment - asked).total_seconds()
    if waited < settings.teacher_help_alert_after_seconds:
        return
    emit_private_event(
        TEACHER_HELP_WAITING_EVENT,
        correlation_id=str(record.get("escalation_request_id") or ""),
        wait_minutes=int(waited // 60),
        level=logging.WARNING,
    )


# ── Account deletion ─────────────────────────────────────────────────────────


def scrub_teacher(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    generation: int,
    now: str | None = None,
    table: Any | None = None,
) -> None:
    """Take a deleting teacher off a request (#72).

    An open request goes back to waiting - its holder and offer removed - so
    the sweep offers it to someone else; a student's request is not closed
    unanswered because a teacher account went away. A closed request keeps its
    outcome and loses only the teacher references. Written under the
    teacher's deletion fence and the record's version; if either moved, the
    deletion pass is retried.
    """
    timestamp = now or _now()
    previous = [value for value in record.get("previous_dispatch_teacher_ids") or [] if value != teacher_id]
    holds = teacher_id in {record.get("teacher_id"), record.get("dispatched_teacher_id")}
    changes: dict[str, Any] = {"previous_dispatch_teacher_ids": previous, "updated_at": timestamp}
    remove: tuple[str, ...] = ()
    if holds:
        remove = ("teacher_id", "accepted_at", *_OFFER_FIELDS)
        if _status(record) in OPEN:
            changes.update({"escalation_status": PENDING, "dispatch_status": "unassigned"})
        else:
            changes["dispatch_status"] = "revoked"
    try:
        _write(
            record,
            changes,
            remove=remove,
            extra=(account_deletion_repo.deletion_fence_condition(teacher_id, generation),),
            table=table or get_table(),
        )
    except HelpRequestConflict as exc:
        raise account_deletion_repo.AccountDeletionRowConflict("help request changed during cleanup") from exc


def references_teacher(record: Mapping[str, Any], teacher_id: str) -> bool:
    return teacher_id in {record.get("teacher_id"), record.get("dispatched_teacher_id")} or teacher_id in (
        record.get("previous_dispatch_teacher_ids") or []
    )


# ── Writing ──────────────────────────────────────────────────────────────────


def _update_operation(
    record: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    remove: Sequence[str] = (),
    condition: str | None = None,
    values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One update of the record, bound to the version it was read at."""
    version = stored_int(record.get("version")) or 0
    names = {f"#{field}": field for field in (*changes, *remove, "version")}
    expression = "SET " + ", ".join(
        [f"#{field} = :set_{field}" for field in changes] + ["#version = :next_version"]
    )
    removed = [f"#{field}" for field in dict.fromkeys(remove) if field not in changes]
    if removed:
        expression += " REMOVE " + ", ".join(removed)
    expression_values: dict[str, Any] = {f":set_{field}": value for field, value in changes.items()}
    expression_values.update({":version": version, ":next_version": version + 1})
    expression_values.update(values or {})
    full_condition = "attribute_exists(PK) AND #version = :version"
    if condition:
        full_condition += f" AND {condition}"
    return {
        "Update": {
            "Key": key(str(record.get("conversation_id") or "")),
            "UpdateExpression": expression,
            "ConditionExpression": full_condition,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": expression_values,
        }
    }


def _write(
    record: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    remove: Sequence[str] = (),
    condition: str | None = None,
    values: Mapping[str, Any] | None = None,
    extra: Sequence[dict[str, Any]] = (),
    fence: bool = False,
    table: Any,
) -> dict[str, Any]:
    """Write one change to the record (and ``extra``) in one transaction.

    ``fence`` adds the student's active account fence, for writes that put
    rows in the student's conversation. Returns the record as written.
    """
    operations: list[dict[str, Any]] = []
    if fence:
        operations.append(
            account_deletion_repo.active_fence_condition(
                str(record.get("student_id") or ""), _int(record.get("account_fence_generation"), 1)
            )
        )
    operations.append(
        _update_operation(record, changes, remove=remove, condition=condition, values=values)
    )
    operations.extend(extra)
    try:
        account_deletion_repo.transact(operations, table=table)
    except Exception as exc:  # noqa: BLE001 - every refusal means the request moved on
        raise HelpRequestConflict("help request changed before the write") from exc
    written = {key_: value for key_, value in record.items() if key_ not in remove or key_ in changes}
    written.update(changes)
    written["version"] = (stored_int(record.get("version")) or 0) + 1
    return written


# ── Time ─────────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(value: Any) -> datetime | None:
    return cast(datetime | None, teacher_dispatch_service.parse_timestamp(value))


def _expired(deadline: Any, now: str) -> bool:
    parsed_deadline, parsed_now = _parse(deadline), _parse(now)
    return bool(parsed_deadline and parsed_now and parsed_deadline <= parsed_now)


def _deadline(now: str) -> str:
    moment = _parse(now) or datetime.now(timezone.utc)
    return (moment + timedelta(seconds=teacher_dispatch_service.DISPATCH_ACCEPT_TIMEOUT_SECONDS)).isoformat()


def _seconds_between(start: Any, end: Any) -> int | None:
    started, ended = _parse(start), _parse(end)
    if not started or not ended:
        return None
    return max(0, int((ended - started).total_seconds()))


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
