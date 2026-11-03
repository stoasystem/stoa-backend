"""真人求助 through its own interface: one record, one module (#189).

The planner, the teacher's account conditions, the record's version and the
table are real; the weekly allowance and the notifications are stood in for,
since each has its own tests.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest
from fakes.dynamodb import FakeTable
from fakes.help_requests import seed_reply
from fakes.learning_session import seed_conversation

from stoa.db.repositories import account_deletion_repo
from stoa.services import help_requests, teacher_support_allowance_service

STUDENT = "student-189"
TEACHER = "teacher-189"
OTHER = "teacher-189-other"
CONV = "conv-189"
ASKED = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
Admission = teacher_support_allowance_service.TeacherSupportAdmissionDisposition
Refund = teacher_support_allowance_service.TeacherSupportRefundDisposition


def at(minutes: float = 0) -> str:
    return (ASKED + timedelta(minutes=minutes)).isoformat()


def _reply(record: dict, *, now: str, table: FakeTable, teacher_id: str = TEACHER, **fields) -> help_requests.Reply:
    return help_requests.reply(
        record,
        teacher_id=teacher_id,
        author_name=fields.pop("author_name", "Frau Muster"),
        content=fields.pop("content", "Subtract 5 from both sides."),
        rich={"version": 1, "blocks": []},
        format="stoa_teacher_reply_v1",
        images=(),
        now=now,
        table=table,
        **fields,
    )


def _teacher(teacher_id: str, availability: str = "available") -> list[dict]:
    return [
        {
            "PK": f"USER#{teacher_id}",
            "SK": "PROFILE",
            "user_id": teacher_id,
            "role": "teacher",
            "account_status": "active",
            "version": 1,
            "dispatch_subjects": ["math"],
            "dispatch_availability": availability,
        },
        {"PK": f"USER#{teacher_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    ]


class World:
    def __init__(self, table: FakeTable) -> None:
        self.table = table
        self.events: list[tuple[str, dict]] = []
        self.admission = Admission.ADMITTED
        self.refunds: list[str] = []

    def available(self, *teachers: str) -> None:
        for teacher in (TEACHER, OTHER):
            self.table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = (
                "available" if teacher in teachers else "paused"
            )

    @property
    def record(self) -> dict:
        return dict(self.table.rows[(f"CONV#{CONV}", "HELP")])

    def ask(self, *, now: str = at(), message: str | None = "Step 2?") -> help_requests.AskOutcome:
        return help_requests.ask(
            conversation=dict(self.table.rows[(f"CONV#{CONV}", "CONV")]),
            student_id=STUDENT,
            message=message,
            system_message="Teacher help requested.",
            now=now,
            table=self.table,
        )


@pytest.fixture
def world(monkeypatch) -> World:
    table = FakeTable()
    seed_conversation(
        table,
        conversation_id=CONV,
        student_id=STUDENT,
        subject="mathematics",
        grade="6",
        now=at(-30),
    )
    table.seed(
        {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
        *_teacher(TEACHER),
        *_teacher(OTHER, "paused"),
    )
    for name, module in list(sys.modules.items()):
        if name.startswith("stoa.") and hasattr(module, "get_table"):
            monkeypatch.setattr(module, "get_table", lambda table=table: table)
    built = World(table)

    def admit(*, persist_case, **_kwargs):
        if built.admission is not Admission.ADMITTED:
            return teacher_support_allowance_service.TeacherSupportAdmissionResult(built.admission)
        assert persist_case(())
        return teacher_support_allowance_service.TeacherSupportAdmissionResult(Admission.ADMITTED)

    def refund(*, persist_refund, reason, **_kwargs):
        assert persist_refund(())
        built.refunds.append(reason)
        return teacher_support_allowance_service.TeacherSupportRefundResult(
            Refund.REFUNDED, week_identity="2026-W44"
        )

    monkeypatch.setattr(teacher_support_allowance_service, "admit_teacher_support_case", admit)
    monkeypatch.setattr(teacher_support_allowance_service, "refund_teacher_support_case", refund)
    for name in (
        "emit_teacher_help_dispatched",
        "emit_teacher_help_expired",
        "emit_teacher_help_takeover",
        "emit_teacher_help_reply",
    ):
        monkeypatch.setattr(
            help_requests.notification_service,
            name,
            lambda name=name, **kwargs: built.events.append((name, kwargs)),
        )
    return built


# ── asking ───────────────────────────────────────────────────────────────────


def test_asking_writes_one_record_and_offers_it_to_a_free_teacher(world) -> None:
    outcome = world.ask()

    assert outcome.created
    record = world.record
    assert record["escalation_request_id"] == CONV
    assert record["escalation_status"] == "pending"
    assert record["escalation_message"] == "Step 2?"
    assert record["dispatched_teacher_id"] == TEACHER
    assert record["dispatch_status"] == "dispatched"
    assert record["dispatch_deadline_at"] == at(10)
    # The conversation row is not written, and there is no queue row.
    assert "escalated" not in world.table.rows[(f"CONV#{CONV}", "CONV")]
    assert not [row for row in world.table.rows if row[0].startswith("QUESTION#")]
    # The system message that opens the request is in the conversation.
    assert world.table.rows[(f"CONV#{CONV}", f"MSG#{CONV}")]["role"] == "system"
    assert [name for name, _ in world.events] == ["emit_teacher_help_dispatched"]
    assert help_requests.student_view(record, now=at(1)) == ("assigned", TEACHER)


def test_asking_again_answers_with_the_request_whatever_its_state(world) -> None:
    world.ask()
    help_requests.withdraw(CONV, student_id=STUDENT, now=at(2), table=world.table)

    again = world.ask(now=at(3))

    assert not again.created
    assert again.record is not None and again.record["escalation_status"] == "withdrawn"
    assert world.refunds == ["withdrawn"]


def test_a_refused_admission_writes_nothing(world) -> None:
    world.admission = Admission.LIMIT_EXCEEDED

    outcome = world.ask()

    assert outcome.disposition is Admission.LIMIT_EXCEEDED
    assert outcome.record is None
    assert (f"CONV#{CONV}", "HELP") not in world.table.rows


def test_nobody_free_is_said_and_the_student_told_so(world) -> None:
    world.available()

    world.ask()

    record = world.record
    assert record["dispatch_status"] == "no_candidate"
    assert record["dispatch_no_candidate_since"] == at()
    assert help_requests.student_view(record, now=at(1)) == ("waiting_no_teacher", "")


# ── the sweep ────────────────────────────────────────────────────────────────


def test_a_lapsed_offer_goes_to_someone_else_never_back(world) -> None:
    world.ask()
    world.available(TEACHER, OTHER)

    report = help_requests.sweep(now=at(11), table=world.table)

    record = world.record
    assert record["dispatched_teacher_id"] == OTHER
    assert record["previous_dispatch_teacher_ids"] == [TEACHER]
    assert report["reassigned"] == 1
    assert report["conversationsDispatched"] == [{"conversationId": CONV, "status": "dispatched"}]


def test_a_lapsed_offer_with_nobody_else_is_taken_off_and_remembered(world) -> None:
    world.ask()

    help_requests.sweep(now=at(11), table=world.table)

    record = world.record
    assert record["dispatch_status"] == "no_candidate"
    assert "dispatched_teacher_id" not in record
    assert record["previous_dispatch_teacher_ids"] == [TEACHER]
    assert help_requests.student_view(record, now=at(12)) == ("waiting_no_teacher", "")


def test_a_live_offer_is_left_alone(world) -> None:
    world.ask()
    before = world.record

    report = help_requests.sweep(now=at(5), table=world.table)

    assert world.record == before
    assert report["conversationsWaiting"] == 0


def test_a_request_nobody_took_in_24_hours_expires_and_its_case_goes_back(world, monkeypatch) -> None:
    world.available()
    world.ask()

    report = help_requests.sweep(now=at(24 * 60 + 1), table=world.table)

    assert report["conversationsExpired"] == [CONV]
    assert world.record["escalation_status"] == "expired"
    assert world.refunds == ["expired"]
    assert [name for name, _ in world.events] == ["emit_teacher_help_expired"]


def test_a_long_wait_with_nobody_free_is_reported(world, monkeypatch) -> None:
    reported: list[dict] = []
    monkeypatch.setattr(
        help_requests, "emit_private_event", lambda event, **kwargs: reported.append({"event": event, **kwargs})
    )
    world.available()
    world.ask()

    help_requests.sweep(now=at(29), table=world.table)
    assert reported == []
    # The no-candidate record is unchanged, so only the alert remains to say it.
    world.table.rows[(f"CONV#{CONV}", "HELP")]["dispatch_no_candidate_reason"] = "other"
    help_requests.sweep(now=at(31), table=world.table)

    assert [item["event"] for item in reported] == ["teacher_help_waiting_no_candidate"]
    assert reported[0]["wait_minutes"] == 31


# ── the teacher ──────────────────────────────────────────────────────────────


def test_the_offered_teacher_takes_it_and_its_first_reply_is_the_first_response(world) -> None:
    world.ask()

    taken = help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(4), table=world.table)
    assert taken["teacher_id"] == TEACHER
    # Taking it is not a response (#189 Q4).
    assert "first_teacher_action_at" not in world.record

    _reply(world.record, now=at(7), table=world.table)
    assert world.record["first_teacher_action_at"] == at(7)
    assert help_requests.sla(world.record)["requestToFirstActionMinutes"] == 7

    _reply(world.record, now=at(9), table=world.table)
    assert world.record["first_teacher_action_at"] == at(7)


def test_replying_to_an_offer_takes_it_in_the_same_write(world) -> None:
    world.ask()
    world.events.clear()

    written = _reply(world.record, now=at(3), table=world.table)

    record = world.record
    assert record["teacher_id"] == TEACHER
    assert record["escalation_status"] == "in_progress"
    assert record["first_teacher_action_at"] == at(3)
    assert (f"CONV#{CONV}", f"NOTE#{written.id}") in world.table.rows
    assert [row for key, row in world.table.rows.items() if key[1].startswith("MSG#") and row["role"] == "teacher"]
    # The student hears of the reply, not separately of the take-over.
    assert [name for name, _ in world.events] == ["emit_teacher_help_reply"]


def test_a_teacher_without_the_offer_cannot_take_it(world) -> None:
    world.ask()

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(world.record, teacher_id=OTHER, target="in_progress", now=at(2), table=world.table)
    assert "teacher_id" not in world.record


def test_a_lapsed_offer_cannot_be_taken(world) -> None:
    world.ask()

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(11), table=world.table)


def test_a_write_on_a_stale_read_is_refused(world) -> None:
    world.ask()
    stale = world.record
    help_requests.take_or_finish(stale, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(stale, teacher_id=TEACHER, target="resolved", now=at(3), table=world.table)


def test_resolving_ends_it_and_the_holder_can_still_reply(world) -> None:
    world.ask()
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="resolved", now=at(5), table=world.table, resolution_note="done")

    record = world.record
    assert record["escalation_status"] == "resolved"
    assert record["escalation_resolved_at"] == at(5)
    _reply(record, now=at(6), table=world.table)
    assert world.record["escalation_status"] == "resolved"
    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(7), table=world.table)


# ── the student ──────────────────────────────────────────────────────────────


def test_a_taken_request_cannot_be_withdrawn(world) -> None:
    world.ask()
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)

    with pytest.raises(help_requests.HelpRequestEndingRefused) as refused:
        help_requests.withdraw(CONV, student_id=STUDENT, now=at(3), table=world.table)
    assert refused.value.code == "teacher_help_already_accepted"


def test_withdrawing_takes_the_offer_off(world) -> None:
    world.ask()

    withdrawn = help_requests.withdraw(CONV, student_id=STUDENT, now=at(2), table=world.table)

    assert withdrawn["escalation_status"] == "withdrawn"
    assert "dispatched_teacher_id" not in world.record
    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(withdrawn, teacher_id=TEACHER, target="in_progress", now=at(3), table=world.table)


def test_another_student_cannot_withdraw_it(world) -> None:
    world.ask()

    with pytest.raises(help_requests.HelpRequestEndingRefused) as refused:
        help_requests.withdraw(CONV, student_id="someone-else", now=at(2), table=world.table)
    assert refused.value.code == "teacher_help_request_not_found"


def test_a_students_requests_are_found_by_the_student(world) -> None:
    world.ask()

    assert list(help_requests.for_student(STUDENT, table=world.table)) == [CONV]
    merged = help_requests.with_requests(
        [{"entity_type": "conversation", "conversation_id": CONV}, {"entity_type": "conversation", "conversation_id": "other"}],
        STUDENT,
        table=world.table,
    )
    assert merged[0]["escalated"] is True and merged[0]["escalated_at"] == at()
    assert "escalated" not in merged[1]


# ── what a teacher may do (#234) ─────────────────────────────────────────────
#
# The expectations are the rules, written out: a request that ended without a
# teacher, or was closed to its teacher ("revoked"), lets nobody do anything;
# writes (RESPOND / RESOLVE / UPDATE) go to the holder of an in-progress or
# resolved request, or to the teacher a live offer on a pending, unheld request
# names who has not let it lapse before; reads (READ / CREATE) go to the holder,
# else the offered teacher, while pending, in progress or resolved, unless the
# offer has lapsed; nothing else (CLAIM) is allowed. No deadline is a live one;
# one that cannot be read has passed.

ME = TEACHER
MAY_NOW = ASKED + timedelta(minutes=5)
LIVE = (ASKED + timedelta(minutes=10)).isoformat()
PAST = (ASKED + timedelta(minutes=1)).isoformat()
Action = help_requests.AuthorizationAction
WRITES = (Action.UPDATE, Action.RESPOND, Action.RESOLVE)
READS = (Action.READ, Action.CREATE)
ALL_ACTIONS = (*READS, *WRITES, Action.CLAIM)


def _request(status: str, **fields) -> dict:
    return {
        "conversation_id": CONV,
        "escalation_request_id": CONV,
        "student_id": STUDENT,
        "escalation_status": status,
        **fields,
    }


def _offered(**fields) -> dict:
    return _request(
        "pending", dispatch_status="dispatched", dispatched_teacher_id=ME, **fields
    )


NOTHING: frozenset = frozenset()
EVERYTHING_BUT_CLAIM = frozenset((*READS, *WRITES))
TEACHER_MAY_CASES = {
    "pending unassigned": (_request("pending", dispatch_status="unassigned"), NOTHING),
    "pending offered live": (_offered(dispatch_deadline_at=LIVE), EVERYTHING_BUT_CLAIM),
    "pending offered, no deadline": (_offered(), EVERYTHING_BUT_CLAIM),
    "pending offered expired": (_offered(dispatch_deadline_at=PAST), NOTHING),
    "pending offered, deadline unreadable": (
        _offered(dispatch_deadline_at="not-a-time"),
        NOTHING,
    ),
    "pending offered to a teacher who let it lapse before": (
        _offered(dispatch_deadline_at=LIVE, previous_dispatch_teacher_ids=[ME]),
        frozenset(READS),
    ),
    "pending offered to another": (
        _request(
            "pending",
            dispatch_status="dispatched",
            dispatched_teacher_id=OTHER,
            dispatch_deadline_at=LIVE,
        ),
        NOTHING,
    ),
    "pending no_candidate": (
        _request("pending", dispatch_status="no_candidate"),
        NOTHING,
    ),
    "in_progress held by me": (
        _request("in_progress", teacher_id=ME, dispatch_status="accepted"),
        EVERYTHING_BUT_CLAIM,
    ),
    "in_progress held by me, a lapsed offer still on it": (
        _request(
            "in_progress",
            teacher_id=ME,
            dispatch_status="dispatched",
            dispatched_teacher_id=ME,
            dispatch_deadline_at=PAST,
        ),
        frozenset(WRITES),
    ),
    "in_progress held by another": (
        _request("in_progress", teacher_id=OTHER, dispatch_status="accepted"),
        NOTHING,
    ),
    "in_progress held by another, offered to me before": (
        _request(
            "in_progress", teacher_id=OTHER, dispatched_teacher_id=ME, dispatch_status="accepted"
        ),
        NOTHING,
    ),
    "resolved held by me": (
        _request("resolved", teacher_id=ME, dispatch_status="accepted"),
        EVERYTHING_BUT_CLAIM,
    ),
    "resolved held by another": (
        _request("resolved", teacher_id=OTHER, dispatch_status="accepted"),
        NOTHING,
    ),
    "withdrawn": (
        _request("withdrawn", dispatch_status="withdrawn", dispatched_teacher_id=ME),
        NOTHING,
    ),
    "expired": (
        _request("expired", dispatch_status="expired", dispatched_teacher_id=ME),
        NOTHING,
    ),
    "revoked": (
        _request("resolved", teacher_id=ME, dispatch_status="revoked"),
        NOTHING,
    ),
}


@pytest.mark.parametrize("case", list(TEACHER_MAY_CASES))
@pytest.mark.parametrize("action", ALL_ACTIONS, ids=lambda action: action.value)
def test_what_a_teacher_may_do_to_a_request(case: str, action) -> None:
    record, allowed = TEACHER_MAY_CASES[case]

    assert help_requests.teacher_may(record, ME, action, now=MAY_NOW) is (action in allowed)


def test_a_request_without_a_status_is_pending() -> None:
    record = _offered(dispatch_deadline_at=LIVE)
    del record["escalation_status"]

    assert all(help_requests.teacher_may(record, ME, action, now=MAY_NOW) for action in WRITES)


def test_an_offer_is_written_through_the_request_only() -> None:
    """A live offer lets its teacher write the request itself, nothing else.

    `teacher_may` answers for the request; which resource an offered teacher
    writes through is the policy's to say. Writes through a question, a
    conversation or a draft keyed by the request take holding it; reads do not.
    """
    from stoa.security.authorization import (
        AuthorizationPurpose,
        ResourceRef,
        ResourceType,
        TeacherAuthorizationFacts,
    )

    def facts(record: dict) -> TeacherAuthorizationFacts:
        return TeacherAuthorizationFacts(
            request=record,
            teacher_account={"user_id": ME, "role": "teacher", "account_status": "active"},
            student_account={"user_id": STUDENT, "role": "student", "account_status": "active"},
        )

    def permits(record: dict, resource_type, action) -> bool:
        question_id = CONV if resource_type is ResourceType.AI_TEACHER_DRAFT else None
        resource_id = "draft-1" if question_id else CONV
        return facts(record).permits(
            ME,
            ResourceRef(resource_type, resource_id, STUDENT, question_id=question_id),
            action,
            AuthorizationPurpose.TEACHER_HELP,
            MAY_NOW,
        )

    offered = _offered(dispatch_deadline_at=LIVE)
    held = _request("in_progress", teacher_id=ME, dispatch_status="accepted")
    for action in WRITES:
        assert permits(offered, ResourceType.TEACHER_HELP_REQUEST, action)
        for resource_type in (
            ResourceType.QUESTION,
            ResourceType.CONVERSATION,
            ResourceType.AI_TEACHER_DRAFT,
        ):
            assert not permits(offered, resource_type, action)
            assert permits(held, resource_type, action)
    for action in READS:
        for resource_type in (
            ResourceType.TEACHER_HELP_REQUEST,
            ResourceType.QUESTION,
            ResourceType.CONVERSATION,
            ResourceType.AI_TEACHER_DRAFT,
        ):
            assert permits(offered, resource_type, action)


# ── the admin dashboard's reading of a request (#235 retires it) ─────────────


def test_the_request_reads_as_a_question_where_one_is_expected(world) -> None:
    world.ask()

    record = help_requests.get(CONV, table=world.table)
    assert record is not None
    view = help_requests.question_view(record)

    assert view["question_id"] == CONV
    assert view["status"] == "escalated"
    assert view["source"] == "conversation_escalation"
    assert view["content"] == "Step 2?"
    assert view["student_id"] == STUDENT


# ── account deletion ─────────────────────────────────────────────────────────


def test_deleting_the_holder_returns_an_open_request_to_waiting(world) -> None:
    world.ask()
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    help_requests.scrub_teacher(world.record, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)

    record = world.record
    assert record["escalation_status"] == "pending"
    assert record["dispatch_status"] == "unassigned"
    assert "teacher_id" not in record
    assert help_requests.references_teacher(record, TEACHER) is False


def test_deleting_a_teacher_keeps_a_resolved_request_resolved(world) -> None:
    world.ask()
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="resolved", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    help_requests.scrub_teacher(world.record, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)

    assert world.record["escalation_status"] == "resolved"
    assert "teacher_id" not in world.record


def test_a_scrub_on_a_stale_read_is_retried_not_applied(world) -> None:
    world.ask()
    stale = world.record
    help_requests.take_or_finish(stale, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    with pytest.raises(account_deletion_repo.AccountDeletionRowConflict):
        help_requests.scrub_teacher(stale, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)


def test_a_teacher_who_let_it_lapse_cannot_take_it_even_holding_an_offer(world) -> None:
    """Belt and braces: a re-offer never goes back to them, but the write refuses it too."""
    world.ask()
    world.table.rows[(f"CONV#{CONV}", "HELP")]["previous_dispatch_teacher_ids"] = [TEACHER]

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    assert "teacher_id" not in world.record


# ── the teacher's view (#233) ────────────────────────────────────────────────


@pytest.mark.parametrize("stored", ["pending", "in_progress", "resolved", "withdrawn", "expired"])
def test_a_teacher_reads_the_stored_status_never_the_students(stored) -> None:
    record = {
        "conversation_id": CONV,
        "escalation_request_id": CONV,
        "student_id": STUDENT,
        "escalation_status": stored,
        "escalated_at": at(),
        "subject": "mathematics",
        "grade": "6",
        "escalation_message": "Step 2?",
        "dispatch_status": "no_candidate",
    }

    view = help_requests.teacher_view(record, now=at(5))

    assert view.status == stored
    assert (view.request_id, view.conversation_id, view.student_id) == (CONV, CONV, STUDENT)
    assert (view.subject, view.grade, view.request_message) == ("mathematics", "6", "Step 2?")
    assert view.sla == help_requests.sla(record)


def test_a_request_is_dated_when_asked_else_when_changed_else_now() -> None:
    base = {"conversation_id": CONV}

    assert help_requests.teacher_view({**base, "escalated_at": at(1), "updated_at": at(2)}, now=at(3)).created_at == at(1)
    assert help_requests.teacher_view({**base, "updated_at": at(2)}, now=at(3)).created_at == at(2)
    view = help_requests.teacher_view(base, now=at(3))
    assert view.created_at == at(3)
    assert (view.request_id, view.subject, view.status, view.request_message) == (CONV, "General", "pending", None)


# ── the teacher's moves tell the student (#233) ──────────────────────────────


def test_taking_tells_the_student_once_and_finishing_tells_nobody(world) -> None:
    world.ask()
    world.events.clear()

    taken = help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="resolved", now=at(3), table=world.table)

    assert [name for name, _ in world.events] == ["emit_teacher_help_takeover"]
    assert world.events[0][1] == {"conversation": taken, "teacher_id": TEACHER}


def test_a_refused_take_tells_nobody(world) -> None:
    world.ask()
    world.events.clear()

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.take_or_finish(world.record, teacher_id=OTHER, target="in_progress", now=at(2), table=world.table)
    assert world.events == []


def test_a_failed_notice_does_not_undo_the_take(world, monkeypatch) -> None:
    world.ask()

    def fail(**_kwargs):
        raise RuntimeError("notifications down")

    monkeypatch.setattr(help_requests.notification_service, "emit_teacher_help_takeover", fail)

    taken = help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)

    assert taken["teacher_id"] == TEACHER == world.record["teacher_id"]


def test_a_reply_is_one_transaction_and_one_notice(world, monkeypatch) -> None:
    world.ask()
    help_requests.take_or_finish(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    world.events.clear()
    transactions: list[list[dict]] = []
    real_transact = account_deletion_repo.transact

    def capture(operations, *, table=None):
        transactions.append(list(operations))
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", capture)

    written = _reply(world.record, now=at(4), table=world.table, author_name="  Frau Muster ")

    [operations] = transactions
    fence, update, note_put, message_put = operations
    assert fence["ConditionCheck"]["Key"] == {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE"}
    assert update["Update"]["Key"] == {"PK": f"CONV#{CONV}", "SK": "HELP"}
    note = note_put["Put"]["Item"]
    message = message_put["Put"]["Item"]
    assert note["SK"] == f"NOTE#{written.id}"
    assert note["owner_id"] == STUDENT and note["teacher_name"] == "  Frau Muster "
    assert message["role"] == "teacher" and message["author_name"] == "Frau Muster"
    assert note["created_at"] == message["created_at"] == world.record["updated_at"] == at(4)
    assert "attachment_ids" not in note
    assert (written.teacher_name, written.content, written.attachment_ids) == (
        "  Frau Muster ",
        "Subtract 5 from both sides.",
        [],
    )
    assert [name for name, _ in world.events] == ["emit_teacher_help_reply"]
    assert world.events[0][1]["reply_id"] == written.id


def test_a_reply_without_a_name_is_signed_teacher(world) -> None:
    world.ask()

    written = _reply(world.record, now=at(3), table=world.table, author_name=None)

    assert written.teacher_name == "Teacher"
    assert world.table.rows[(f"CONV#{CONV}", f"NOTE#{written.id}")]["teacher_name"] == "Teacher"


def test_a_teacher_neither_holding_nor_offered_cannot_reply(world) -> None:
    world.ask()
    world.events.clear()

    with pytest.raises(help_requests.HelpRequestConflict):
        _reply(world.record, now=at(3), table=world.table, teacher_id=OTHER)
    assert not [key for key in world.table.rows if key[1].startswith("NOTE#")]
    assert world.events == []


def test_replies_are_read_back_oldest_first(world) -> None:
    world.ask()
    for note_id, minutes in (("b", 6), ("a", 4)):
        seed_reply(
            world.table,
            conversation_id=CONV,
            note_id=f"{minutes:02d}-{note_id}",
            teacher_id=TEACHER,
            teacher_name="Frau Muster",
            content=f"reply {note_id}",
            created_at=at(minutes),
            student_id=STUDENT,
            attachment_ids=["att-1"] if note_id == "b" else None,
        )

    replies = help_requests.replies(CONV, table=world.table)

    assert [reply.content for reply in replies] == ["reply a", "reply b"]
    assert replies[1].attachment_ids == ["att-1"] and replies[0].attachment_ids == []
    assert replies[0].rich == {"version": 1, "blocks": []}
    assert replies[0].format == "stoa_teacher_reply_v1"
    assert replies[0].attachments == []
