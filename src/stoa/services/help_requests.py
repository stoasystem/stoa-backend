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
- whether the student's usage period still lets them ask: `usage_period`;
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
from enum import StrEnum
from itertools import islice
from typing import Any, Literal, cast

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import owner_registry
from stoa.db import table as db_table
from stoa import config
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo, weekly_counter
from stoa.models.attachment import AttachmentSummary
from stoa.rule_violation import RuleContract, RuleViolation, register_codes
from stoa.security.authorization import AuthorizationAction
from stoa.security.private_telemetry import emit_private_event
from stoa.services import (
    attachment_service,
    learning_session,
    notification_service,
    teacher_dispatch_service,
    teacher_reply_service,
    teacher_support_allowance_service,
    usage_period,
)
from stoa.services.ask_question_errors import AskQuestionErrorCode

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

# How the student wants the teacher's help (#480): a written answer, or the
# virtual classroom. The student chooses when asking; nothing changes it after.
TEXT = "text"
CLASSROOM = "classroom"
HelpMode = Literal["text", "classroom"]
MODES: tuple[HelpMode, ...] = (TEXT, CLASSROOM)
#: What a request asked before #480, stored without a mode, counts as: every
#: request then was answered in writing, and a written answer is what every
#: plan with teacher support includes (#474).
LEGACY_MODE: HelpMode = TEXT

# Logged for each request nobody could be offered that has waited past the
# alert limit (#88). stoa-infra's metric filter matches this exact string.
TEACHER_HELP_WAITING_EVENT = teacher_dispatch_service.TEACHER_HELP_WAITING_EVENT

# What an offer writes, and what finding nobody writes. Each write that ends
# one of them removes exactly these. `dispatch_fallback` marks a standing offer:
# one made again to a teacher who let it lapse, because nobody else was free
# (#391).
_OFFER_FIELDS = ("dispatched_teacher_id", "dispatch_id", "dispatch_deadline_at", "dispatch_fallback")
_NO_CANDIDATE_FIELDS = ("dispatch_no_candidate_reason", "dispatch_no_candidate_since")
# Teachers who declined the request (#391), kept apart from the ones who let
# its offer lapse (`previous_dispatch_teacher_ids`): a lapse is offered again
# when nobody else is free, a refusal never. Nothing writes it yet - there is
# no way to decline - but the dispatch already honours it.
DECLINED_FIELD = "declined_dispatch_teacher_ids"
# A scan's ceiling on pages; the table is far from it.
_SCAN_PAGE_LIMIT = 1000
# A read on GSI-StudentId continues from the index's key as well as the table's.
_STUDENT_INDEX_KEY = ("PK", "SK", "student_id", "created_at")

# ── The indexes a request is found through (#608) ────────────────────────────
#
# `list_all` finds requests by scanning the whole table, so what it reads
# follows the size of the table, not how many requests there are. Two sparse
# indexes hold the requests the frequent readers - the sweep and a teacher's
# queue - want:
#
# - A request not yet ended (`pending`, `in_progress`) carries `sweep_bucket`
#   and `sweep_due_at`, the keys of GSI-SweepPending (#502), in a bucket of its
#   own and ordered by when it was asked. The write that ends it removes them.
# - A request a teacher holds carries `started_at` beside its `teacher_id`, the
#   keys of GSI-TeacherId, from the write that gives it to the teacher until
#   one takes the teacher off it. An ended request stays there: it is still
#   its teacher's to read.
#
# Every write of the record sets or removes them through `index_fields`, in the
# same write that changes the state they follow. Account deletion replaces the
# record with a tombstone that keeps none of them.
OPEN_INDEX = "GSI-SweepPending"
OPEN_BUCKET = "help_open"
OPEN_INDEX_FIELDS = ("sweep_bucket", "sweep_due_at")
HOLDER_INDEX = "GSI-TeacherId"
HOLDER_INDEX_FIELD = "started_at"
INDEX_FIELDS = (*OPEN_INDEX_FIELDS, HOLDER_INDEX_FIELD)
_OPEN_INDEX_KEY = ("PK", "SK", *OPEN_INDEX_FIELDS)
_HOLDER_INDEX_KEY = ("PK", "SK", "teacher_id", HOLDER_INDEX_FIELD)
# What a record whose own times cannot be read is filed under: first in the
# index, so it is read early rather than hidden, and the same on every write.
_INDEX_TIME_UNKNOWN = "1970-01-01T00:00:00Z"
# Every request, ended ones too, is also in GSI-Listing (card 133), for the
# admin statistics: `listing` names the list and `listed_at` is when it was
# asked. Set once by `ask`; no later write moves them, and a tombstone keeps neither.
LISTING_INDEX = "GSI-Listing"
LISTING_NAME = "help_request"
LISTING_INDEX_FIELDS = ("listing", "listed_at")
_LISTING_INDEX_KEY = ("PK", "SK", *LISTING_INDEX_FIELDS)

# The question words a request's state is told in. Their one reader is
# `sla_metrics`: the admin stats count requests beside the legacy question rows,
# in those rows' words.
_QUESTION_STATUS = {
    PENDING: "escalated",
    IN_PROGRESS: "teacher_active",
    RESOLVED: "resolved",
    WITHDRAWN: "withdrawn",
    EXPIRED: "expired",
}


# ── Errors ───────────────────────────────────────────────────────────────────


class HelpRequestErrorCode(StrEnum):
    """Why a help request refused a change; the strings are the client's (#211)."""

    # A teacher's write (`teachers.py`): the frontend's `CONFLICT_CODES`.
    HELP_REQUEST_NOT_HELD = "help_request_not_held"
    # Replying to a request only offered: the teacher accepts it first (#479).
    HELP_REQUEST_NOT_ACCEPTED = "help_request_not_accepted"
    HELP_REQUEST_CHANGED = "help_request_changed"
    HELP_REQUEST_UNAVAILABLE = "help_request_unavailable"
    # The student asking (`conversations.py`). An ended usage period is refused
    # with the question's own `usage_period_ended` (`ask`), not a code of ours.
    TEACHER_SUPPORT_ADMISSION_RECOVERABLE = "teacher_support_admission_recoverable"
    TEACHER_SUPPORT_NOT_INCLUDED = "teacher_support_not_included"
    TEACHER_SUPPORT_ALLOWANCE_EXHAUSTED = "teacher_support_allowance_exhausted"
    TEACHER_SUPPORT_CASE_CONFLICT = "teacher_support_case_conflict"
    TEACHER_HELP_NOT_REQUESTED = "teacher_help_not_requested"
    # Ending one nobody took (withdrawal, expiry).
    TEACHER_HELP_REQUEST_NOT_FOUND = "teacher_help_request_not_found"
    TEACHER_HELP_ALREADY_ACCEPTED = "teacher_help_already_accepted"
    TEACHER_HELP_REQUEST_CLOSED = "teacher_help_request_closed"
    TEACHER_HELP_REQUEST_NOT_DUE = "teacher_help_request_not_due"
    TEACHER_HELP_REQUEST_NOT_WITHDRAWABLE = "teacher_help_request_not_withdrawable"
    TEACHER_HELP_WITHDRAWAL_UNAVAILABLE = "teacher_help_withdrawal_unavailable"
    # Entering the classroom (#481). A request asked as a written answer has
    # no classroom, for the student or the teacher; a classroom request opens
    # to the student once its teacher has accepted it.
    HELP_REQUEST_NOT_CLASSROOM = "help_request_not_classroom"
    TEACHER_HELP_NOT_YET_ACCEPTED = "teacher_help_not_yet_accepted"

    @property
    def contract(self) -> RuleContract:
        return HELP_REQUEST_ERROR_REGISTRY[self]


class HelpRequestClientAction(StrEnum):
    REFRESH_HELP_REQUEST = "refresh_help_request"
    ACCEPT_HELP_REQUEST = "accept_help_request"
    RETRY_SAME_CASE = "retry_same_case"
    RETRY_LATER = "retry_later"
    CONTACT_ADMINISTRATOR = "contact_administrator"
    WAIT_FOR_NEXT_WEEK = "wait_for_next_week"


def _sent_with_action(action: HelpRequestClientAction, status: int, **retry: Any) -> RuleContract:
    """A code whose body names what to do next, as these bodies always have."""
    return RuleContract(status, action, public_fields=frozenset({"action"}), **retry)


_Code = HelpRequestErrorCode
_Action = HelpRequestClientAction

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.help_request`).
HELP_REQUEST_ERROR_REGISTRY: dict[HelpRequestErrorCode, RuleContract] = {
    _Code.HELP_REQUEST_NOT_HELD: _sent_with_action(_Action.REFRESH_HELP_REQUEST, 409),
    _Code.HELP_REQUEST_NOT_ACCEPTED: _sent_with_action(_Action.ACCEPT_HELP_REQUEST, 409),
    _Code.HELP_REQUEST_CHANGED: _sent_with_action(_Action.REFRESH_HELP_REQUEST, 409),
    _Code.HELP_REQUEST_UNAVAILABLE: RuleContract(
        503, _Action.RETRY_LATER, retryable=True, max_attempts=1
    ),
    _Code.TEACHER_SUPPORT_ADMISSION_RECOVERABLE: _sent_with_action(
        _Action.RETRY_SAME_CASE, 503, retryable=True, idempotent_only=True, max_attempts=1
    ),
    # Nobody can buy their way past this while the paid surface is frozen, and
    # on an assigned account there was never anything to buy.
    _Code.TEACHER_SUPPORT_NOT_INCLUDED: _sent_with_action(_Action.CONTACT_ADMINISTRATOR, 403),
    _Code.TEACHER_SUPPORT_ALLOWANCE_EXHAUSTED: _sent_with_action(_Action.WAIT_FOR_NEXT_WEEK, 429),
    _Code.TEACHER_SUPPORT_CASE_CONFLICT: RuleContract(409),
    _Code.TEACHER_HELP_NOT_REQUESTED: RuleContract(404),
    _Code.TEACHER_HELP_REQUEST_NOT_FOUND: RuleContract(404),
    _Code.TEACHER_HELP_ALREADY_ACCEPTED: RuleContract(409),
    _Code.TEACHER_HELP_REQUEST_CLOSED: RuleContract(409),
    _Code.TEACHER_HELP_REQUEST_NOT_DUE: RuleContract(409),
    _Code.TEACHER_HELP_REQUEST_NOT_WITHDRAWABLE: RuleContract(409),
    _Code.TEACHER_HELP_WITHDRAWAL_UNAVAILABLE: _sent_with_action(
        _Action.RETRY_SAME_CASE, 503, retryable=True, idempotent_only=True, max_attempts=1
    ),
    _Code.HELP_REQUEST_NOT_CLASSROOM: RuleContract(409),
    _Code.TEACHER_HELP_NOT_YET_ACCEPTED: RuleContract(409),
}

register_codes("help_request", HelpRequestErrorCode, HELP_REQUEST_ERROR_REGISTRY)


class HelpRequestViolation(RuleViolation):
    """A help request refused a change; a body that names an action carries it."""

    def __init__(
        self,
        code: HelpRequestErrorCode | str,
        *,
        internal_detail: str | None = None,
    ) -> None:
        resolved = HelpRequestErrorCode(code)
        super().__init__(resolved, internal_detail=internal_detail)
        if "action" in resolved.contract.public_fields:
            self.with_public(action=str(resolved.contract.action))


class HelpRequestConflict(HelpRequestViolation):
    """The request is not in the state the change was decided on."""

    def __init__(
        self,
        detail: str = "",
        *,
        code: HelpRequestErrorCode = HelpRequestErrorCode.HELP_REQUEST_CHANGED,
    ) -> None:
        super().__init__(code, internal_detail=detail or None)


class HelpRequestEndingRefused(HelpRequestViolation):
    """The request cannot be ended this way; ``code`` says why, for the response."""

    def __init__(self, code: HelpRequestErrorCode | str) -> None:
        super().__init__(code)


class HelpRequestEndingUnavailable(HelpRequestViolation):
    """Ending the request could not be completed now; trying again is safe."""

    def __init__(self, conversation_id: str = "") -> None:
        super().__init__(
            HelpRequestErrorCode.TEACHER_HELP_WITHDRAWAL_UNAVAILABLE,
            internal_detail=conversation_id or None,
        )


class HelpRequestUnavailable(HelpRequestViolation):
    """The request could not be read or written now; trying again is safe."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            HelpRequestErrorCode.HELP_REQUEST_UNAVAILABLE, internal_detail=detail or None
        )


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
    store: Any = table or db_table.table()
    try:
        response = store.get_item(Key=key(conversation_id), ConsistentRead=True)
    except Exception as exc:  # noqa: BLE001 - unknown is not absent
        raise HelpRequestUnavailable(conversation_id) from exc
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(cast(Mapping[str, Any], item)) if _is_record(item) else None


def list_all(*, table: Any | None = None) -> list[dict[str, Any]]:
    """Every request on the table, ended ones included, from every page.

    A filtered scan stops at a page of the table, not at the matches (#95), so
    every page is read: the whole table, whatever its size. For the admin
    statistics and the index backfill only; the sweep and a teacher's queue
    read `list_open` and `list_for_teacher` (#608).
    """
    store: Any = table or db_table.table()
    items: list[dict[str, Any]] = []
    started_at: dict[str, Any] | None = None
    try:
        for page in islice(
            db_table.pages(
                "scan", table=store, FilterExpression=Attr("entity_type").eq(ENTITY_TYPE)
            ),
            _SCAN_PAGE_LIMIT,
        ):
            items.extend(dict(item) for item in page.items if _is_record(item))
            if page.last_key is None:
                return items
            if page.last_key == started_at:
                raise HelpRequestUnavailable("scan did not advance")
            started_at = page.last_key
    except db_table.TableUnavailable as exc:
        if exc.code.startswith("malformed"):
            raise HelpRequestUnavailable("scan did not advance") from exc
        raise
    raise HelpRequestUnavailable("scan page limit reached")


def list_listed(*, table: Any | None = None) -> list[dict[str, Any]]:
    """Every request, ended ones included: one query of GSI-Listing (card 133).

    What it reads follows how many requests there are, not the size of the
    table. Eventually consistent. For the admin statistics; the backfills read
    `list_all`, which also finds a request written before it had the keys.
    """
    return _indexed_records(
        table,
        key=_LISTING_INDEX_KEY,
        IndexName=LISTING_INDEX,
        KeyConditionExpression=Key("listing").eq(LISTING_NAME),
    )


def listing_fields(record: Mapping[str, Any]) -> dict[str, str]:
    """The GSI-Listing keys of a request: filed under when it was asked."""
    return {
        "listing": LISTING_NAME,
        "listed_at": _index_time(record.get("created_at"), record.get("escalated_at")),
    }


def list_open(*, table: Any | None = None) -> list[dict[str, Any]]:
    """The requests a student is still waiting on: pending ones, the longest asked first.

    Read from the index of requests not yet ended (#608), not by a scan.
    """
    return [record for record in list_unended(table=table) if stored_status(record) == PENDING]


def list_for_teacher(teacher_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    """Every request a teacher could be shown, each once (#608).

    The ones not yet ended - an offer to this teacher is among them - and the
    ones this teacher holds, ended or not. Which of them this teacher may
    read is the policy's to decide (`teacher_may`); every request it admits
    is in one of the two. Two index queries, eventually consistent.
    """
    found: dict[str, dict[str, Any]] = {}
    for record in (*list_unended(table=table), *list_held_by(teacher_id, table=table)):
        found.setdefault(str(record["conversation_id"]), record)
    return list(found.values())


def index_fields(record: Mapping[str, Any]) -> dict[str, str]:
    """The index keys a record in this state carries (#608).

    The ones of `INDEX_FIELDS` not returned are the ones it must not carry.
    Derived from the record alone, so the same state always gives the same
    keys: a request not yet ended is filed under when it was asked, one a
    teacher holds under when that teacher took it.
    """
    fields: dict[str, str] = {}
    if stored_status(record) in OPEN:
        fields["sweep_bucket"] = OPEN_BUCKET
        fields["sweep_due_at"] = _index_time(
            record.get("escalated_at"), record.get("created_at")
        )
    if record.get("teacher_id"):
        fields[HOLDER_INDEX_FIELD] = _index_time(
            record.get("accepted_at"), record.get("escalated_at"), record.get("created_at")
        )
    return fields


def _index_time(*candidates: Any) -> str:
    """The first of `candidates` that reads as a time, UTC to the second, so it sorts as text."""
    for candidate in candidates:
        moment = _parse(candidate)
        if moment is not None:
            return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _INDEX_TIME_UNKNOWN


def list_unended(*, table: Any | None = None) -> list[dict[str, Any]]:
    """Every request not yet ended, the longest asked first: one query of its index (#608).

    What it reads follows how many requests are waiting or in progress, not
    the size of the table. Eventually consistent: a request written in the
    last moment may be missing, and one just ended may still be there, so a
    reader that acts on a record does so on a condition, as every write here does.
    """
    return _indexed_records(
        table,
        key=_OPEN_INDEX_KEY,
        IndexName=OPEN_INDEX,
        KeyConditionExpression=Key("sweep_bucket").eq(OPEN_BUCKET),
    )


def list_held_by(teacher_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    """The requests this teacher holds, the ended ones too: one query of its index (#608).

    Eventually consistent, as `list_unended` is.
    """
    if not teacher_id:
        return []
    return [
        record
        for record in _indexed_records(
            table,
            key=_HOLDER_INDEX_KEY,
            IndexName=HOLDER_INDEX,
            KeyConditionExpression=Key("teacher_id").eq(teacher_id),
            FilterExpression=Attr("entity_type").eq(ENTITY_TYPE),
        )
        if record.get("teacher_id") == teacher_id
    ]


def _indexed_records(table: Any | None, *, key: Sequence[str], **request: Any) -> list[dict[str, Any]]:
    """Every record an index query admits, from every page of it."""
    store: Any = table or db_table.table()
    found: list[dict[str, Any]] = []
    try:
        for page in islice(
            db_table.pages("query", table=store, key=key, **request), _SCAN_PAGE_LIMIT
        ):
            found.extend(dict(item) for item in page.items if _is_record(item))
            if page.last_key is None:
                return found
    except db_table.TableUnavailable as exc:
        if exc.code.startswith("malformed"):
            raise HelpRequestUnavailable("index read did not advance") from exc
        raise
    raise HelpRequestUnavailable("index page limit reached")


def reindex(record: Mapping[str, Any], *, table: Any | None = None) -> bool:
    """Give a record written before #608 the index keys its state calls for.

    For the one-off backfill (`scripts/backfill_help_request_index.py`). True
    when this call wrote them, False when the record already carried exactly
    them. Written on the version the record was read at, without moving it:
    a write that landed in between set the keys itself, and this one is
    refused with `HelpRequestConflict`.
    """
    fields = index_fields(record)
    if fields == {name: record[name] for name in INDEX_FIELDS if name in record}:
        return False
    absent = [name for name in INDEX_FIELDS if name not in fields]
    expression = ""
    if fields:
        expression = "SET " + ", ".join(f"#{name} = :{name}" for name in fields)
    if absent:
        expression += " REMOVE " + ", ".join(f"#{name}" for name in absent)
    try:
        db_table.update(
            table=table or db_table.table(),
            Key=key(str(record.get("conversation_id") or "")),
            UpdateExpression=expression.strip(),
            ConditionExpression=(
                "attribute_exists(PK) AND #entity = :entity AND #version = :version"
            ),
            ExpressionAttributeNames={
                **{f"#{name}": name for name in INDEX_FIELDS},
                "#entity": "entity_type",
                "#version": "version",
            },
            ExpressionAttributeValues={
                **{f":{name}": value for name, value in fields.items()},
                ":entity": ENTITY_TYPE,
                ":version": stored_int(record.get("version")) or 0,
            },
        )
    except db_table.WriteRefused as exc:
        raise HelpRequestConflict("help request changed before it was indexed") from exc
    return True


def for_student(student_id: str, *, table: Any | None = None) -> dict[str, dict[str, Any]]:
    """A student's requests, keyed by conversation id.

    The record carries `student_id` and `created_at`, so it is in
    GSI-StudentId beside the student's conversations; the readers that list a
    student's conversations read their requests from the same index.
    """
    if not student_id:
        return {}
    store: Any = table or db_table.table()
    found: dict[str, dict[str, Any]] = {}
    for page in islice(
        db_table.pages(
            "query",
            table=store,
            key=_STUDENT_INDEX_KEY,
            IndexName="GSI-StudentId",
            KeyConditionExpression=Key("student_id").eq(student_id),
            FilterExpression=Attr("entity_type").eq(ENTITY_TYPE),
        ),
        _SCAN_PAGE_LIMIT,
    ):
        for item in page.items:
            if _is_record(item) and item.get("student_id") == student_id:
                found[str(item["conversation_id"])] = dict(item)
        if page.last_key is None:
            return found
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


def mode(record: Mapping[str, Any]) -> HelpMode:
    """How the student asked to be helped; a request stored without one is `text` (#480)."""
    stored = record.get("mode")
    return cast(HelpMode, stored) if stored in MODES else LEGACY_MODE


def stored_status(record: Mapping[str, Any]) -> str:
    """The request's own state word, as stored: `pending` until a teacher takes it."""
    return str(record.get("escalation_status") or PENDING)


def student_view(record: Mapping[str, Any], *, now: str | None = None) -> tuple[str, str]:
    """What the waiting student is told, and which teacher (if any) to name (#86).

    Returns ``(status, teacher_id)``. A teacher is named only while it holds
    the request: it took it, or its offer has not lapsed.
    """
    timestamp = now or _now()
    stored = stored_status(record)
    holder = str(record.get("teacher_id") or "")
    if stored != PENDING:
        return stored, holder
    if holder:
        return "assigned", holder
    if _live_offer(record, timestamp) and not record.get("dispatch_fallback"):
        return "assigned", str(record.get("dispatched_teacher_id") or "")
    # A standing offer waits on a teacher who let it lapse once (#391): nobody
    # is expected to answer within minutes, and the student is told so.
    if record.get("dispatch_status") == "no_candidate" or record.get("dispatch_fallback"):
        return "waiting_no_teacher", ""
    return PENDING, ""


@dataclass(frozen=True)
class TeacherView:
    """What a teacher is shown of a request: the list, the detail and the stats.

    ``status`` is the stored one (#215 decision 3): a teacher never sees the
    student's `assigned` or `waiting_no_teacher`.
    """

    request_id: str
    conversation_id: str
    student_id: str
    subject: str
    grade: str
    status: str
    mode: HelpMode
    request_message: str | None
    created_at: str
    first_teacher_action_at: str | None
    resolved_at: str | None
    sla: dict[str, Any]


def teacher_view(record: Mapping[str, Any], *, now: str | None = None) -> TeacherView:
    """The request as a teacher reads it (#215 decision 2).

    A request is dated when it was asked, else when it last changed,
    else ``now``.
    """
    conversation_id = _text(record.get("conversation_id"))
    return TeacherView(
        request_id=_text(record.get("escalation_request_id"), default=conversation_id),
        conversation_id=conversation_id,
        student_id=_text(record.get("student_id")),
        subject=_text(record.get("subject"), default="General"),
        grade=_text(record.get("grade")),
        status=stored_status(record),
        mode=mode(record),
        request_message=_optional_text(record.get("escalation_message")),
        created_at=_text(
            record.get("escalated_at"),
            default=_text(record.get("updated_at"), default=now or _now()),
        ),
        first_teacher_action_at=_optional_text(record.get("first_teacher_action_at")),
        resolved_at=_optional_text(record.get("escalation_resolved_at")),
        sla=sla(record),
    )


def holder_or_offered(record: Mapping[str, Any], teacher_id: str) -> bool:
    """Whether this teacher may write the request at all.

    Only the teacher holding it, or the one it is offered to. A teacher the
    policy admits through an assignment may read it but not write it (#73).
    """
    holder = str(record.get("teacher_id") or "")
    if holder:
        return holder == teacher_id
    return str(record.get("dispatched_teacher_id") or "") == teacher_id


# A teacher's writes on a request; reading it, and making a summary, a draft or
# a report from it (CREATE), are its reads.
_TEACHER_WRITES = frozenset(
    {AuthorizationAction.RESPOND, AuthorizationAction.RESOLVE, AuthorizationAction.UPDATE}
)
_TEACHER_READS = frozenset({AuthorizationAction.READ, AuthorizationAction.CREATE})
# Closed to every teacher: ended without one (`_end` writes the outcome here),
# or closed to the teacher whose account was scrubbed from it (`scrub_teacher`).
_CLOSED_DISPATCH = frozenset({"revoked", WITHDRAWN, EXPIRED})


def teacher_may(
    record: Mapping[str, Any], teacher_id: str, action: AuthorizationAction, *, now: datetime
) -> bool:
    """Whether the request lets this teacher do this to it (#215 decision 6).

    The policy asks this once it has matched the resource to the request; the
    accounts, a standing assignment, and which resources an offered teacher
    may write through are the policy's to judge.

    - A request that ended without a teacher, or was closed to its teacher,
      lets nobody do anything.
    - RESPOND / RESOLVE / UPDATE: the teacher holding it, while in progress or
      resolved; or, while it is pending and nobody holds it, the teacher a live
      offer names, unless that teacher let it lapse before.
    - READ / CREATE: the teacher holding it, else the one it was offered to,
      while pending, in progress or resolved, unless the offer has lapsed.
    - Anything else, a claim among them: no.

    A deadline that cannot be read counts as passed (`_deadline_passed`).
    """
    status = stored_status(record)
    dispatch_status = str(record.get("dispatch_status") or "")
    if status in {WITHDRAWN, EXPIRED} or dispatch_status in _CLOSED_DISPATCH:
        return False
    holder = str(record.get("teacher_id") or "")
    offered = str(record.get("dispatched_teacher_id") or "")
    lapsed = dispatch_status == "dispatched" and _deadline_passed(
        record.get("dispatch_deadline_at"), now
    )
    if action in _TEACHER_WRITES:
        previous = record.get("previous_dispatch_teacher_ids")
        let_lapse = isinstance(previous, (list, tuple, set, frozenset)) and teacher_id in {
            str(item) for item in previous
        }
        live_offer = (
            not holder
            and status == PENDING
            and dispatch_status == "dispatched"
            and offered == teacher_id
            and not let_lapse
            and not lapsed
        )
        return live_offer or (holder == teacher_id and status in {IN_PROGRESS, RESOLVED})
    if action in _TEACHER_READS:
        return (
            (holder or offered) == teacher_id
            and status in {PENDING, IN_PROGRESS, RESOLVED}
            and not lapsed
        )
    return False


#: How long after resolving a student's request its teacher may still assign
#: them practice (#495).
HELPED_STUDENT_DAYS = 14


def teacher_helped_student(
    records: Sequence[Mapping[str, Any]], teacher_id: str, student_id: str, *, now: datetime
) -> bool:
    """Whether this teacher took one of this student's requests (布置练习的权限, #495).

    The teacher holds one of them in progress, or resolved it no more than
    `HELPED_STUDENT_DAYS` ago. An offer never taken, a request reassigned to
    another teacher, one withdrawn or expired, and one closed to the teacher
    whose account was scrubbed do not count. A resolution time that cannot be
    read counts as long past. The accounts are the policy's to judge.
    """
    if not teacher_id or not student_id:
        return False
    for record in records:
        if record.get("student_id") != student_id or record.get("teacher_id") != teacher_id:
            continue
        if str(record.get("dispatch_status") or "") in _CLOSED_DISPATCH:
            continue
        status = stored_status(record)
        if status == IN_PROGRESS:
            return True
        if status == RESOLVED:
            resolved_at = _parse(record.get("escalation_resolved_at"))
            if resolved_at is not None and now - resolved_at <= timedelta(
                days=HELPED_STUDENT_DAYS
            ):
                return True
    return False


def admit_student_to_classroom(record: Mapping[str, Any] | None) -> None:
    """Refuse the student entry unless a teacher has accepted their classroom request (#481).

    The classroom opens to the student only for a request asked in the
    `classroom` mode, and only once a teacher holds it in progress: they are
    told by the acceptance notification, not left waiting in an empty room.
    In order: a conversation that never asked is `teacher_help_not_requested`;
    one that ended, however it ended, `teacher_help_request_closed`; a
    request for a written answer (a stored one without a mode among them),
    `help_request_not_classroom`; one no teacher has accepted yet,
    `teacher_help_not_yet_accepted`.
    """
    if record is None:
        raise HelpRequestViolation(HelpRequestErrorCode.TEACHER_HELP_NOT_REQUESTED)
    status = stored_status(record)
    if status not in OPEN:
        raise HelpRequestViolation(HelpRequestErrorCode.TEACHER_HELP_REQUEST_CLOSED)
    _refuse_classroom_unless_asked(record)
    if status != IN_PROGRESS or not str(record.get("teacher_id") or ""):
        raise HelpRequestViolation(HelpRequestErrorCode.TEACHER_HELP_NOT_YET_ACCEPTED)


def admit_teacher_to_classroom(record: Mapping[str, Any], teacher_id: str) -> None:
    """Refuse the teacher entry unless they hold a classroom request in progress (#467, #481).

    Being offered the request is not enough: the teacher takes it first. A
    request this teacher does not hold is `help_request_not_held`; one they
    held that has ended is `teacher_help_request_closed`; one asked for a
    written answer is `help_request_not_classroom`.
    """
    if str(record.get("teacher_id") or "") != teacher_id:
        raise HelpRequestConflict(
            "teacher does not hold the request", code=HelpRequestErrorCode.HELP_REQUEST_NOT_HELD
        )
    if stored_status(record) != IN_PROGRESS:
        raise HelpRequestViolation(HelpRequestErrorCode.TEACHER_HELP_REQUEST_CLOSED)
    _refuse_classroom_unless_asked(record)


def _refuse_classroom_unless_asked(record: Mapping[str, Any]) -> None:
    """Only a request asked in the `classroom` mode has a classroom (#481)."""
    if mode(record) != CLASSROOM:
        raise HelpRequestViolation(HelpRequestErrorCode.HELP_REQUEST_NOT_CLASSROOM)


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
        "status": _QUESTION_STATUS.get(stored_status(record), stored_status(record)),
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
    mode: HelpMode = TEXT,
    now: str | None = None,
    table: Any | None = None,
) -> AskOutcome:
    """Open the conversation's request, spending a case of the week, and offer it.

    ``mode`` is how the student wants the help, stored on the request and
    never changed after (#480). A conversation that already has a request
    answers with it, whatever its state and mode: one conversation asks a
    teacher once (#189 decision 3). A new
    request is refused `usage_period_ended` while the student's usage period is
    not active (#344), judged from one read before the allowance is asked, so no
    case of the week is spent. The case is
    admitted by the allowance, and the record, the system message that opens
    the request in the conversation and the case are written in one
    transaction behind the student's account fence. The first offer is made
    right after; it is best effort, and the sweep makes it if this one fails.
    """
    if mode not in MODES:
        raise ValueError(f"unsupported help request mode: {mode}")
    store: Any = table or db_table.table()
    timestamp = now or _now()
    conversation_id = str(conversation.get("conversation_id") or "")
    if not conversation_id or conversation.get("student_id") != student_id:
        raise HelpRequestConflict("conversation is not this student's")
    existing = get(conversation_id, table=store)
    if existing is not None:
        return AskOutcome(None, existing)
    # One read, no condition in the transaction: an administrator changing the
    # period at the same moment is decided by what this read found (#239 shape 5).
    if not usage_period.student_may_ask(student_id, table=store):
        raise RuleViolation(AskQuestionErrorCode.USAGE_PERIOD_ENDED)

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
        "mode": mode,
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
    record.update(index_fields(record))
    record.update(listing_fields(record))
    # The system message that opens the request in the conversation; its id
    # is the conversation's, so a conversation has one.
    system_message_put = learning_session.append(
        conversation_id,
        role="system",
        message_id=conversation_id,
        student_id=student_id,
        generation=generation,
        content=system_message,
        created_at=timestamp,
        system_event="teacher_help_requested",
        escalation_message=message,
    )
    record_operations = learning_session.build_conversation_write_transaction(
        item=record, owner_id=student_id, generation=generation
    )
    rows: list[dict[str, Any]] = [
        *cast(list[dict[str, Any]], record_operations),
        cast(dict[str, Any], system_message_put),
        {
            "ConditionCheck": {
                "Key": {"PK": f"CONV#{conversation_id}", "SK": "CONV"},
                "ConditionExpression": "attribute_exists(PK) AND student_id = :student",
                "ExpressionAttributeValues": {":student": student_id},
            }
        },
    ]

    def persist_case(
        allowance_operations: tuple[dict[str, Any], ...], fences: Mapping[str, int]
    ) -> bool:
        try:
            db_table.fenced(
                student_id,
                [*rows, *allowance_operations],
                generation=generation,
                also=fences,
                table=store,
            )
        except Exception:  # noqa: BLE001 - every refusal means something moved
            return False
        return True

    Disposition = teacher_support_allowance_service.TeacherSupportAdmissionDisposition
    admission = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=conversation_id,
        case_kind="conversation",
        beneficiary_id=student_id,
        # Counted against the weekly figure of the way the student chose (#482).
        mode=mode,
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
    """Teachers who let the request's offer lapse, in the order they did.

    The ones recorded, and the teacher of an offer that lapsed unanswered:
    recording the lapse in the same write as the next offer is what keeps the
    two from disagreeing. They are offered it again only when nobody else can
    be (#391). Every name a record stored before #391 is a lapse: no code ever
    wrote a refusal there.
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


def _declined(record: Mapping[str, Any]) -> list[str]:
    """Teachers who declined the request: it is never offered to them again (#391)."""
    return [str(item) for item in record.get(DECLINED_FIELD) or [] if item]


def dispatch(record: Mapping[str, Any], *, now: str | None = None, table: Any | None = None) -> dict[str, Any]:
    """Offer a pending request to the best available teacher, or say nobody is free.

    Returns the record as written. A request already taken, ended, or holding
    a live offer is returned as it is. The offer binds the chosen teacher's
    active account and profile version, and the record's version.

    A teacher who has not had the request comes first. With none free, it is
    offered again to a free teacher who let it lapse - never to one who
    declined it - as a standing offer, open until the request expires (#391).
    A standing offer still gives way to a teacher who becomes free.
    """
    timestamp = now or _now()
    store: Any = table or db_table.table()
    if stored_status(record) != PENDING or record.get("teacher_id"):
        return dict(record)
    standing = _live_offer(record, timestamp)
    if standing and not record.get("dispatch_fallback"):
        return dict(record)
    previous = _previous(record, timestamp)
    declined = _declined(record)
    # Before the plan reads the teachers, so it reads this one paused (#472).
    _pause_lapsed_teacher(record, timestamp)
    profiles = teacher_dispatch_service.list_teacher_profiles()

    def plan(excluded: list[str]) -> dict[str, Any]:
        return teacher_dispatch_service.plan_dispatch(
            {**record, "previous_dispatch_teacher_ids": excluded}, profiles, now=timestamp
        )

    if standing:
        holder = str(record.get("dispatched_teacher_id") or "")
        fresh = plan([*previous, holder, *declined])
        if not fresh["selected"]:
            return dict(record)
        return _offer(
            record, fresh["selected"][0], previous=[*previous, holder], standing=False, now=timestamp, table=store
        )
    first = plan([*previous, *declined])
    if first["selected"]:
        return _offer(record, first["selected"][0], previous=previous, standing=False, now=timestamp, table=store)
    again = [candidate for candidate in plan(declined)["selected"] if str(candidate["teacherId"]) in previous]
    if again:
        teacher_id = str(again[0]["teacherId"])
        return _offer(
            record,
            again[0],
            previous=[value for value in previous if value != teacher_id],
            standing=True,
            now=timestamp,
            table=store,
        )
    reason = str(first["summary"]["noCandidateReason"] or "no_eligible_teacher")
    return _record_no_candidate(record, reason=reason, previous=previous, now=timestamp, table=store)


def _pause_lapsed_teacher(record: Mapping[str, Any], now: str) -> None:
    """Pause the teacher an ordinary offer lapsed on, and tell them (#472).

    A standing offer is not one: it stays open until the request expires.
    Best effort: the request goes on to the next teacher whatever happens here.
    """
    teacher_id = str(record.get("dispatched_teacher_id") or "")
    dispatch_id = str(record.get("dispatch_id") or "")
    if (
        not teacher_id
        or not dispatch_id
        or record.get("dispatch_status") != "dispatched"
        or record.get("dispatch_fallback")
        or not _expired(record.get("dispatch_deadline_at"), now)
    ):
        return
    try:
        if not teacher_dispatch_service.pause_after_lapse(teacher_id, dispatch_id=dispatch_id, now=now):
            return
        notification_service.emit_teacher_dispatch_paused(
            teacher_id=teacher_id,
            dispatch_id=dispatch_id,
            accept_minutes=teacher_dispatch_service.DISPATCH_ACCEPT_TIMEOUT_SECONDS // 60,
        )
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("dispatch_lapse_pause_failed error=%s", type(exc).__name__)


def _offer(
    record: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    previous: list[str],
    standing: bool,
    now: str,
    table: Any,
) -> dict[str, Any]:
    """Write one offer to ``candidate`` and tell them, closing the offer it replaces."""
    teacher_id = str(candidate["teacherId"])
    dispatch_id = str(uuid.uuid4())
    deadline = _standing_deadline(record, now) if standing else _deadline(now)
    changes: dict[str, Any] = {
        "dispatched_teacher_id": teacher_id,
        "dispatch_status": "dispatched",
        "dispatch_id": dispatch_id,
        "dispatch_deadline_at": deadline,
        "dispatch_attempt_count": _int(record.get("dispatch_attempt_count"), 0) + 1,
        "dispatch_updated_at": now,
        "previous_dispatch_teacher_ids": previous,
    }
    remove: tuple[str, ...] = _NO_CANDIDATE_FIELDS
    if standing:
        changes["dispatch_fallback"] = True
    else:
        remove = (*_NO_CANDIDATE_FIELDS, "dispatch_fallback")
    try:
        written = _write(
            record,
            changes,
            remove=remove,
            condition="escalation_status = :pending AND attribute_not_exists(teacher_id)",
            values={":pending": PENDING},
            teacher=candidate,
            table=table,
        )
    except HelpRequestConflict:
        return dict(record)
    replaced = str(record.get("dispatched_teacher_id") or "")
    _close_offer(record, "expired" if replaced == teacher_id else "reassigned", now=now)
    # Only after the offer is written, so a refused offer tells nobody (#141).
    try:
        notification_service.emit_teacher_help_dispatched(
            conversation=written,
            teacher_id=teacher_id,
            dispatch_id=dispatch_id,
            deadline_at=deadline,
            accept_minutes=teacher_dispatch_service.DISPATCH_ACCEPT_TIMEOUT_SECONDS // 60,
            standing=standing,
        )
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("dispatch_teacher_alert_failed error=%s", type(exc).__name__)
    return written


def _close_offer(record: Mapping[str, Any], state: str, *, now: str) -> None:
    """Mark the notification of the offer ``record`` held as no longer open (#391)."""
    dispatch_id = str(record.get("dispatch_id") or "")
    if not dispatch_id or record.get("dispatch_status") != "dispatched":
        return
    try:
        notification_service.close_teacher_help_offer(dispatch_id=dispatch_id, state=state, now=now)
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("dispatch_offer_close_failed error=%s", type(exc).__name__)


def _standing_deadline(record: Mapping[str, Any], now: str) -> str:
    """When a standing offer lapses: when the request expires, never sooner than an ordinary offer."""
    ordinary = _deadline(now)
    asked = _parse(record.get("escalated_at"))
    if asked is None:
        return ordinary
    expires = asked + timedelta(seconds=config.settings().teacher_help_expiry_seconds)
    if expires <= (_parse(ordinary) or expires):
        return ordinary
    return expires.isoformat()


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
        written = _write(
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
    _close_offer(record, "expired", now=now)
    return written


# ── Ending a request nobody took ─────────────────────────────────────────────


@dataclass(frozen=True)
class _Ending:
    record: dict[str, Any]
    changed: bool
    refund: Any = None
    refund_week: str | None = None
    #: The record as this ending read it, before its write.
    before: Mapping[str, Any] | None = None


def withdraw(
    conversation_id: str, *, student_id: str, now: str | None = None, table: Any | None = None
) -> dict[str, Any]:
    """The student takes back a request no teacher has taken (#86).

    The request ends `withdrawn` and the week's case goes back, in one write
    that a teacher taking it at the same moment refuses. Withdrawing twice
    returns the withdrawn request and writes nothing.
    """
    timestamp = now or _now()
    ending = _end(conversation_id, outcome=WITHDRAWN, student_id=student_id, now=timestamp, table=table)
    if ending.changed and ending.before is not None:
        _close_offer(ending.before, WITHDRAWN, now=timestamp)
    return ending.record


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
    if ending.before is not None:
        _close_offer(ending.before, EXPIRED, now=timestamp)
    observed =_parse(timestamp) or datetime.now(timezone.utc)
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
    sweep passes none. Each attempt reads afresh and the refund makes one
    write; a refused write is followed by a new read, never by the same write
    again (`weekly_counter.retry`, the one place the attempts are counted).
    """
    allowance = teacher_support_allowance_service
    store: Any = table or db_table.table()
    timestamp = now or _now()
    observed = _parse(timestamp) or datetime.now(timezone.utc)

    def attempt() -> _Ending:
        try:
            record = get(conversation_id, table=store)
        except HelpRequestUnavailable as exc:
            raise HelpRequestEndingUnavailable(conversation_id) from exc
        if record is None:
            raise HelpRequestEndingRefused("teacher_help_request_not_found")
        owner = str(record.get("student_id") or "")
        if not owner or (student_id is not None and owner != student_id):
            raise HelpRequestEndingRefused("teacher_help_request_not_found")
        current = stored_status(record)
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
        generation = _int(record.get("account_fence_generation"), 1)

        def persist(refund_operations: tuple[dict[str, Any], ...]) -> bool:
            try:
                db_table.fenced(
                    owner, [update, *refund_operations], generation=generation, table=store
                )
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
                before=record,
            )
        if result.disposition is Disposition.IDEMPOTENCY_CONFLICT:
            raise HelpRequestEndingRefused("teacher_help_request_not_withdrawable")
        # Retryable: something moved (a teacher, the counter). Read again.
        raise weekly_counter.CounterConflict()

    ending = weekly_counter.retry(attempt, exhausted=None)
    if ending is None:
        raise HelpRequestEndingUnavailable(conversation_id)
    return ending


# ── The teacher's moves ──────────────────────────────────────────────────────


def take_or_finish(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    target: str,
    now: str | None = None,
    resolution_note: str | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """Take a request (`in_progress`), finish it (`resolved`), or both at once.

    The teacher it is offered to takes it here, and only here: a reply does
    not take a request (#479). The holder moves it on. Returns the record as written. When this write took the
    request, the student is told a teacher has it, once the write has landed
    (#215 decision 4); telling is best effort. Raises `HelpRequestConflict`
    when anything the move was decided on has moved.
    """
    timestamp = now or _now()
    written = _advance(
        record,
        teacher_id=teacher_id,
        target=target,
        now=timestamp,
        resolution_note=resolution_note,
        table=table,
    )
    if not record.get("teacher_id"):
        try:
            notification_service.emit_teacher_help_takeover(
                conversation=written, teacher_id=teacher_id, mode=mode(written)
            )
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            logger.warning("teacher_help_takeover_alert_failed error=%s", type(exc).__name__)
    return written


def _advance(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    target: str,
    now: str | None = None,
    resolution_note: str | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """Move a request to `target` for `teacher_id`, telling nobody.

    This is the only way a teacher takes a request (#479); a reply never does.
    Every condition the decision rested on is in the write: the exact live
    offer, that this teacher has not let it lapse before, the teacher's active
    account and profile, the student's fence and the record's version. If any
    moved, nothing is written and `HelpRequestConflict` is raised.
    """
    if target not in TEACHER_TARGETS:
        raise ValueError(f"unsupported help request status: {target}")
    timestamp = now or _now()
    store: Any = table or db_table.table()
    current = stored_status(record)
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
    return _write(
        record,
        changes,
        condition=condition,
        values=values,
        fence=True,
        teacher=_teacher_standing(teacher_id, store),
        table=store,
    )


@dataclass(frozen=True)
class Reply:
    """A teacher's reply in a request (#215 decision 5): its `NOTE#` row, read back.

    ``attachments`` is filled when the reply was just written; a reply read
    back carries only ``attachment_ids``, which the reader resolves.
    """

    id: str
    content: str
    created_at: str
    teacher_id: str
    teacher_name: str
    rich: dict[str, Any] | None
    format: str | None
    attachment_ids: list[str]
    attachments: list[AttachmentSummary]


def reply(
    record: Mapping[str, Any],
    *,
    teacher_id: str,
    author_name: str | None,
    content: str,
    rich: dict[str, Any] | None,
    format: str | None,
    images: Sequence[dict[str, Any]] = (),
    now: str | None = None,
    table: Any | None = None,
) -> Reply:
    """The holder's reply, and its images, written only while the request is theirs.

    The reply is a `NOTE#` row and a teacher message in the student's
    conversation, written in one transaction with the record. Only the
    teacher holding the request replies: the teacher it is only offered to is
    refused `help_request_not_accepted` and takes it first with
    `take_or_finish` (#479); anyone else is refused `help_request_not_held`.
    A refused reply writes nothing. A resolved request still takes its
    holder's replies (#189 decision 2); the first reply is the request's
    first response. The rows are the student's: stamped with the student as
    owner and written behind their account fence, so the student's deletion
    removes them and a late reply cannot bring them back (#74). The teacher's
    identity stays on them when the teacher is deleted (user decision,
    2026-09-28). Once written the student is told of the reply, best effort.
    """
    timestamp = now or _now()
    store: Any = table or db_table.table()
    _refuse_reply_unless_held(record, teacher_id)
    conversation_id = _text(record.get("conversation_id"))
    student_id = _text(record.get("student_id"))
    try:
        # The generation stamped on the rows is the one the fence check holds
        # them to, read from the fence itself, not a copy on the record.
        generation = int(
            account_deletion_repo.require_active_account_fence(student_id, table=store)["generation"]
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise HelpRequestConflict("student account is not writable") from exc
    note_id = str(uuid.uuid4())
    # The reply is also a message in the conversation, appended by the
    # learning session, so it follows the message contract the student's
    # history reader enforces on every row (#66, 2026-09-28).
    message_id = str(uuid.uuid4())
    image_operations: list[dict[str, Any]] = []
    attachments: list[AttachmentSummary] = []
    attachment_ids: list[str] | None = None
    if images:
        image_operations, attachments = attachment_service.reply_image_operations(
            images,
            teacher_id=teacher_id,
            student_id=student_id,
            account_fence_generation=generation,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        attachment_ids = [summary.attachment_id for summary in attachments]
    teacher_name = _text(author_name, default="Teacher")
    note_row = _reply_row(
        conversation_id=conversation_id,
        note_id=note_id,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        content=content,
        rich=rich,
        format=format,
        created_at=timestamp,
        attachment_ids=attachment_ids,
    )
    # The student sees who wrote each reply, as named when it was written
    # (#65): the profile's name only, never the email.
    message_put = learning_session.append(
        conversation_id,
        role="teacher",
        message_id=message_id,
        student_id=student_id,
        generation=generation,
        content=content,
        created_at=timestamp,
        teacher_response_rich=rich,
        teacher_response_format=format,
        author_name=author_name,
        attachment_ids=attachment_ids,
    )
    reply_operations = (
        learning_session.build_conversation_write_transaction(
            item=note_row, owner_id=student_id, generation=generation
        )[0],
        message_put,
        *image_operations,
    )
    # Each upload changes hands to the student as it is spent: the registry
    # needs it as it will stand (#589).
    image_rows = [
        row for upload in images for row in owner_registry.rows_after(upload, image_operations)
    ]
    changes: dict[str, Any] = {"updated_at": timestamp}
    if not record.get("first_teacher_action_at"):
        changes["first_teacher_action_at"] = timestamp
    # The condition holds the reply to the teacher holding it at write time:
    # a request taken by nobody, or by someone else since the read, is refused.
    written = _write(
        record,
        changes,
        condition="teacher_id = :teacher",
        values={":teacher": teacher_id},
        extra=reply_operations,
        extra_rows=image_rows,
        fence=True,
        table=store,
    )
    try:
        notification_service.emit_teacher_help_reply(
            conversation=written, teacher_id=teacher_id, reply_id=note_id
        )
    except Exception as exc:  # noqa: BLE001 - best effort by contract
        logger.warning("teacher_help_reply_alert_failed error=%s", type(exc).__name__)
    return Reply(
        id=note_id,
        content=content,
        created_at=timestamp,
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        rich=rich,
        format=format,
        attachment_ids=list(attachment_ids or []),
        attachments=attachments,
    )


def _refuse_reply_unless_held(record: Mapping[str, Any], teacher_id: str) -> None:
    """Refuse a reply from anyone but the teacher holding the request (#479).

    The teacher it is offered to is told to accept it first; anyone else that
    it is not theirs.
    """
    holder = str(record.get("teacher_id") or "")
    if holder == teacher_id:
        return
    if not holder and holder_or_offered(record, teacher_id):
        raise HelpRequestConflict(
            "teacher replied to a request offered, not accepted",
            code=HelpRequestErrorCode.HELP_REQUEST_NOT_ACCEPTED,
        )
    raise HelpRequestConflict(
        "help request is not this teacher's", code=HelpRequestErrorCode.HELP_REQUEST_NOT_HELD
    )


def _reply_row(
    *,
    conversation_id: str,
    note_id: str,
    teacher_id: str,
    teacher_name: str,
    content: str,
    rich: dict[str, Any] | None,
    format: str | None,
    created_at: str,
    attachment_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A reply's `NOTE#` row, before the owner and fence stamps of its write."""
    row: dict[str, Any] = {
        "PK": learning_session.conv_pk(conversation_id),
        "SK": f"NOTE#{note_id}",
        "entity_type": "conversation_teacher_note",
        "note_id": note_id,
        "conversation_id": conversation_id,
        "teacher_id": teacher_id,
        "teacher_name": teacher_name,
        "content": content,
        "teacher_response_rich": rich,
        "teacher_response_format": format,
        "created_at": created_at,
    }
    if attachment_ids:
        row["attachment_ids"] = list(attachment_ids)
    return row


def replies(conversation_id: str, *, table: Any | None = None) -> list[Reply]:
    """The teachers' replies in a request, oldest first: one page of its `NOTE#` rows."""
    store: Any = table or db_table.table()
    response = store.query(
        KeyConditionExpression=(
            Key("PK").eq(learning_session.conv_pk(conversation_id)) & Key("SK").begins_with("NOTE#")
        ),
        ScanIndexForward=True,
    )
    items = response.get("Items", []) if isinstance(response, Mapping) else None
    if not isinstance(items, list):
        raise HelpRequestUnavailable(conversation_id)
    return [_reply_from_row(item, conversation_id) for item in items]


def _reply_from_row(row: object, conversation_id: str) -> Reply:
    if not isinstance(row, Mapping):
        raise HelpRequestUnavailable(conversation_id)
    required = [row.get(field) for field in ("note_id", "content", "created_at")]
    if not all(isinstance(value, str) and value for value in required):
        raise HelpRequestUnavailable(conversation_id)
    rich = row.get("teacher_response_rich")
    return Reply(
        id=str(required[0]),
        content=str(required[1]),
        created_at=str(required[2]),
        teacher_id=_text(row.get("teacher_id")),
        teacher_name=_text(row.get("teacher_name"), default="Teacher"),
        rich=dict(rich) if isinstance(rich, Mapping) else None,
        format=_optional_text(row.get("teacher_response_format")),
        attachment_ids=[str(value) for value in _id_list(row.get("attachment_ids"))],
        attachments=[],
    )


def _id_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _teacher_standing(teacher_id: str, table: Any) -> dict[str, Any]:
    """The acting teacher's active fence and exact current profile, as a dispatch candidate."""
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
    return {
        "teacherId": teacher_id,
        "role": str(profile.get("role")),
        "accountFenceGeneration": int(fence["generation"]),
        "profileVersion": _int(profile.get("version"), 0),
    }


# ── The sweep ────────────────────────────────────────────────────────────────


def sweep(*, now: str | None = None, table: Any | None = None) -> dict[str, Any]:
    """Keep every waiting student attached to a teacher who is expected to answer.

    For each pending request: one asked more than 24 hours ago that nobody
    took ends `expired` (#87); one whose offer lapsed, or that was never
    offered, is offered again - to a teacher who let it lapse only when nobody
    else is free (#391) - and one nobody but such a teacher can be offered is
    reported once it has waited past the alert limit (#88). Safe to run
    repeatedly: a live offer is left alone, a standing one unless a teacher who
    has not had the request is free.
    """
    timestamp = now or _now()
    store: Any = table or db_table.table()
    cutoff = (
        (_parse(timestamp) or datetime.now(timezone.utc))
        - timedelta(seconds=config.settings().teacher_help_expiry_seconds)
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
            live = _live_offer(record, timestamp)
            if record.get("teacher_id") or (live and not record.get("dispatch_fallback")):
                continue
            waiting += 1
            if record.get("dispatch_status") == "dispatched" and not live:
                lapsed += 1
            written = dispatch(record, now=timestamp, table=store)
            outcome = str(written.get("dispatch_status") or "")
            if outcome in {"dispatched", "no_candidate"} and written.get("version") != record.get("version"):
                offered.append({"conversationId": conversation_id, "status": outcome})
            if outcome == "no_candidate" or written.get("dispatch_fallback"):
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
    if waited < config.settings().teacher_help_alert_after_seconds:
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
    if DECLINED_FIELD in record:
        changes[DECLINED_FIELD] = [value for value in _declined(record) if value != teacher_id]
    remove: tuple[str, ...] = ()
    if holds:
        remove = ("teacher_id", "accepted_at", *_OFFER_FIELDS)
        if stored_status(record) in OPEN:
            changes.update({"escalation_status": PENDING, "dispatch_status": "unassigned"})
        else:
            changes["dispatch_status"] = "revoked"
    try:
        _write(
            record,
            changes,
            remove=remove,
            extra=(account_deletion_repo.deletion_fence_condition(teacher_id, generation),),
            table=table or db_table.table(),
        )
    except HelpRequestConflict as exc:
        raise account_deletion_repo.AccountDeletionRowConflict("help request changed during cleanup") from exc


def references_teacher(record: Mapping[str, Any], teacher_id: str) -> bool:
    return (
        teacher_id in {record.get("teacher_id"), record.get("dispatched_teacher_id")}
        or teacher_id in (record.get("previous_dispatch_teacher_ids") or [])
        or teacher_id in _declined(record)
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
    """One update of the record, bound to the version it was read at.

    It also leaves the record with the index keys its new state calls for (#608).
    """
    changes, remove = _with_index_fields(record, changes, remove)
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


def _with_index_fields(
    record: Mapping[str, Any], changes: Mapping[str, Any], remove: Sequence[str]
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """`changes` and `remove`, with the index keys of the record they leave (#608).

    The keys are derived from the record as the write leaves it, so applying
    this to its own result changes nothing.
    """
    left = {name: value for name, value in record.items() if name not in remove}
    left.update(changes)
    fields = index_fields(left)
    return (
        {**{name: value for name, value in changes.items() if name not in INDEX_FIELDS}, **fields},
        tuple(
            dict.fromkeys(
                (
                    *(name for name in remove if name not in fields),
                    *(name for name in INDEX_FIELDS if name not in fields),
                )
            )
        ),
    )


def _write(
    record: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    remove: Sequence[str] = (),
    condition: str | None = None,
    values: Mapping[str, Any] | None = None,
    extra: Sequence[dict[str, Any]] = (),
    extra_rows: Sequence[Mapping[str, Any]] = (),
    fence: bool = False,
    teacher: Mapping[str, Any] | None = None,
    table: Any,
) -> dict[str, Any]:
    """Write one change to the record (and ``extra``) in one transaction.

    ``extra_rows`` are rows as an Update in ``extra`` leaves them, where it
    changes whom they name (`db_table.fenced`'s ``rows``, #589).

    ``fence`` holds it behind the student's active account fence, for writes
    that put rows in the student's conversation. ``teacher``, a `plan_dispatch`
    candidate, binds the teacher's profile and holds it behind the teacher's
    fence too. Returns the record as written.
    """
    # Here as well as in `_update_operation`, so the record returned carries them.
    changes, remove = _with_index_fields(record, changes, remove)
    fences: dict[str, int] = {}
    if fence:
        fences[str(record.get("student_id") or "")] = _int(record.get("account_fence_generation"), 1)
    operations = [
        _update_operation(record, changes, remove=remove, condition=condition, values=values)
    ]
    if teacher is not None:
        fences[str(teacher["teacherId"])] = int(teacher["accountFenceGeneration"])
        operations.extend(teacher_dispatch_service.teacher_assignment_conditions(dict(teacher)))
    operations.extend(extra)
    # The request names its teachers (`teacher_id`, `dispatched_teacher_id`,
    # `previous_dispatch_teacher_ids`) in an Update, and `_record_no_candidate`
    # writes without any fence: the write registers every account the request
    # names from the request as it will stand, without making its fence a
    # condition of the write (#397, #589).
    merged = {**record, **changes}
    merged.setdefault("entity_type", ENTITY_TYPE)
    merged.update(operations[0]["Update"]["Key"])
    try:
        if fences:
            owner, *others = fences
            db_table.fenced(
                owner,
                operations,
                generation=fences[owner],
                also={account: fences[account] for account in others},
                rows=[merged, *extra_rows],
                table=table,
            )
        else:
            db_table.registered(operations, rows=[merged, *extra_rows], table=table)
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


def _deadline_passed(value: Any, now: datetime) -> bool:
    """Whether an offer's deadline has passed, as authorization reads one.

    No deadline has not passed; one that cannot be read has, so doubt refuses
    the teacher. Offering and the sweep read deadlines with `_expired`, where
    doubt keeps the offer.
    """
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= now
    except (TypeError, ValueError):
        return True


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


def _text(value: Any, *, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
