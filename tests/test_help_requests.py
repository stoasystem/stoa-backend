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
    table.seed(
        {
            "PK": f"CONV#{CONV}",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": CONV,
            "student_id": STUDENT,
            "owner_id": STUDENT,
            "account_fence_generation": 1,
            "subject": "mathematics",
            "grade": "6",
            "created_at": at(-30),
        },
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
    for name in ("emit_teacher_help_dispatched", "emit_teacher_help_expired"):
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

    taken = help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(4), table=world.table)
    assert taken["teacher_id"] == TEACHER
    # Taking it is not a response (#189 Q4).
    assert "first_teacher_action_at" not in world.record

    replied = help_requests.reply(
        world.record, teacher_id=TEACHER, reply_operations=(), now=at(7), table=world.table
    )
    assert replied["first_teacher_action_at"] == at(7)
    assert help_requests.sla(world.record)["requestToFirstActionMinutes"] == 7

    help_requests.reply(world.record, teacher_id=TEACHER, reply_operations=(), now=at(9), table=world.table)
    assert world.record["first_teacher_action_at"] == at(7)


def test_replying_to_an_offer_takes_it_in_the_same_write(world) -> None:
    world.ask()
    message = {"Put": {"Item": {"PK": f"CONV#{CONV}", "SK": "MSG#reply", "role": "teacher"}}}

    help_requests.reply(world.record, teacher_id=TEACHER, reply_operations=(message,), now=at(3), table=world.table)

    record = world.record
    assert record["teacher_id"] == TEACHER
    assert record["escalation_status"] == "in_progress"
    assert record["first_teacher_action_at"] == at(3)
    assert (f"CONV#{CONV}", "MSG#reply") in world.table.rows


def test_a_teacher_without_the_offer_cannot_take_it(world) -> None:
    world.ask()

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(world.record, teacher_id=OTHER, target="in_progress", now=at(2), table=world.table)
    assert "teacher_id" not in world.record


def test_a_lapsed_offer_cannot_be_taken(world) -> None:
    world.ask()

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(11), table=world.table)


def test_a_write_on_a_stale_read_is_refused(world) -> None:
    world.ask()
    stale = world.record
    help_requests.advance(stale, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(stale, teacher_id=TEACHER, target="resolved", now=at(3), table=world.table)


def test_resolving_ends_it_and_the_holder_can_still_reply(world) -> None:
    world.ask()
    help_requests.advance(world.record, teacher_id=TEACHER, target="resolved", now=at(5), table=world.table, resolution_note="done")

    record = world.record
    assert record["escalation_status"] == "resolved"
    assert record["escalation_resolved_at"] == at(5)
    help_requests.reply(record, teacher_id=TEACHER, reply_operations=(), now=at(6), table=world.table)
    assert world.record["escalation_status"] == "resolved"
    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(7), table=world.table)


# ── the student ──────────────────────────────────────────────────────────────


def test_a_taken_request_cannot_be_withdrawn(world) -> None:
    world.ask()
    help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)

    with pytest.raises(help_requests.HelpRequestEndingRefused) as refused:
        help_requests.withdraw(CONV, student_id=STUDENT, now=at(3), table=world.table)
    assert refused.value.code == "teacher_help_already_accepted"


def test_withdrawing_takes_the_offer_off(world) -> None:
    world.ask()

    withdrawn = help_requests.withdraw(CONV, student_id=STUDENT, now=at(2), table=world.table)

    assert withdrawn["escalation_status"] == "withdrawn"
    assert "dispatched_teacher_id" not in world.record
    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(withdrawn, teacher_id=TEACHER, target="in_progress", now=at(3), table=world.table)


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


# ── readers keyed by a question id ───────────────────────────────────────────


def test_the_request_reads_as_a_question_where_one_is_expected(world) -> None:
    world.ask()

    view = help_requests.question_view_for(CONV, table=world.table)

    assert view is not None
    assert view["question_id"] == CONV
    assert view["status"] == "escalated"
    assert view["source"] == "conversation_escalation"
    assert view["content"] == "Step 2?"
    assert view["student_id"] == STUDENT


# ── account deletion ─────────────────────────────────────────────────────────


def test_deleting_the_holder_returns_an_open_request_to_waiting(world) -> None:
    world.ask()
    help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    help_requests.scrub_teacher(world.record, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)

    record = world.record
    assert record["escalation_status"] == "pending"
    assert record["dispatch_status"] == "unassigned"
    assert "teacher_id" not in record
    assert help_requests.references_teacher(record, TEACHER) is False


def test_deleting_a_teacher_keeps_a_resolved_request_resolved(world) -> None:
    world.ask()
    help_requests.advance(world.record, teacher_id=TEACHER, target="resolved", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    help_requests.scrub_teacher(world.record, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)

    assert world.record["escalation_status"] == "resolved"
    assert "teacher_id" not in world.record


def test_a_scrub_on_a_stale_read_is_retried_not_applied(world) -> None:
    world.ask()
    stale = world.record
    help_requests.advance(stale, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    world.table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")].update(status="deletion_pending", generation=2)

    with pytest.raises(account_deletion_repo.AccountDeletionRowConflict):
        help_requests.scrub_teacher(stale, teacher_id=TEACHER, generation=2, now=at(3), table=world.table)


def test_a_teacher_who_let_it_lapse_cannot_take_it_even_holding_an_offer(world) -> None:
    """Belt and braces: a re-offer never goes back to them, but the write refuses it too."""
    world.ask()
    world.table.rows[(f"CONV#{CONV}", "HELP")]["previous_dispatch_teacher_ids"] = [TEACHER]

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.advance(world.record, teacher_id=TEACHER, target="in_progress", now=at(2), table=world.table)
    assert "teacher_id" not in world.record
