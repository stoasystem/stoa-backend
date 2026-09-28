"""A chat help request, from the offer to the end: stoasystem/stoa-backend#66.

A chat escalation is two rows: the conversation the student reads and the queue
question row the reconciler and dashboards read. Nothing used to let the teacher
it was dispatched to take it: the conversation never got a `teacher_id`, so the
teacher could read the request and nothing else, and each resolve route moved
only one of the two rows.

Rows here are shaped like production's (the attribute names were read from
`stoa-main` for #51). Dispatch is the real `dispatch_conversation`; routes,
repositories and the teacher policy are real, over the shared table double.
"""

from __future__ import annotations

import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable
import pytest

from actor_helpers import install_actor_overrides
from stoa.db.repositories import account_deletion_repo
from stoa.routers import teachers
from stoa.services import teacher_dispatch_service

TEACHER = "teacher-66"
OTHER_TEACHER = "teacher-66-other"
STUDENT = "student-66"
CONV = "conv-66"
REQUEST = "req-66"
CREATED = "2026-09-28T12:00:00+00:00"
CONV_KEY = (f"CONV#{CONV}", "CONV")
QUESTION_KEY = (f"QUESTION#{REQUEST}", "META")


def _teacher_rows(teacher_id: str) -> list[dict]:
    return [
        {
            "PK": f"USER#{teacher_id}",
            "SK": "PROFILE",
            "user_id": teacher_id,
            "role": "teacher",
            "account_status": "active",
            "version": 1,
            "dispatch_subjects": ["math"],
            "dispatch_availability": "available",
        },
        {"PK": f"USER#{teacher_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    ]


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    table = FakeTable()
    table.seed(
        {
            "PK": f"CONV#{CONV}",
            "SK": "CONV",
            "account_fence_generation": 1,
            "conversation_id": CONV,
            "created_at": CREATED,
            "entity_type": "conversation",
            "escalated": True,
            "escalated_at": CREATED,
            "escalation_message": "Step 2 makes no sense to me.",
            "escalation_request_id": REQUEST,
            "escalation_status": "pending",
            "grade": "6",
            "owner_id": STUDENT,
            "student_id": STUDENT,
            "subject": "mathematics",
            "title": "Fractions",
            "updated_at": CREATED,
        },
        {
            "PK": f"QUESTION#{REQUEST}",
            "SK": "META",
            "question_id": REQUEST,
            "entity_type": "question",
            "conversation_id": CONV,
            "source": "conversation_escalation",
            "student_id": STUDENT,
            "owner_id": STUDENT,
            "account_fence_generation": 1,
            "version": 1265,
            "status": "escalated",
            "subject": "mathematics",
            "grade": "6",
            "content": "Step 2 makes no sense to me.",
            "teacher_help_requested": True,
            "teacher_requested_at": CREATED,
            "queue_visible_at": CREATED,
            "dispatch_status": "unassigned",
            "dispatch_no_candidate_reason": "not_available",
            "dispatch_updated_at": CREATED,
            "created_at": CREATED,
            "updated_at": CREATED,
        },
        *_teacher_rows(TEACHER),
        *_teacher_rows(OTHER_TEACHER),
        {
            "PK": f"USER#{STUDENT}",
            "SK": "PROFILE",
            "user_id": STUDENT,
            "role": "student",
            "account_status": "active",
            "version": 1,
        },
        {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    )
    for name, module in list(sys.modules.items()):
        if name.startswith("stoa.") and hasattr(module, "get_table"):
            monkeypatch.setattr(module, "get_table", lambda table=table: table)
    return table


def _dispatch_to(table: FakeTable, teacher_id: str) -> None:
    # Only the named teacher is on dispatch when the offer is made.
    for other in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{other}", "PROFILE")]["dispatch_availability"] = (
            "available" if other == teacher_id else "paused"
        )
    result = teacher_dispatch_service.dispatch_conversation(
        CONV, conversation=dict(table.rows[CONV_KEY]), table=table
    )
    assert result["status"] == "dispatched"
    assert result["teacherId"] == teacher_id


def _client(teacher_id: str = TEACHER) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": teacher_id, "role": "teacher"})
    return TestClient(app)


def _conv(table: FakeTable) -> dict:
    return table.rows[CONV_KEY]


def _question(table: FakeTable) -> dict:
    return table.rows[QUESTION_KEY]


def _nothing_waits() -> None:
    outcome = teacher_dispatch_service.reconcile_dispatches()
    assert outcome["waiting"] == 0
    assert outcome["conversationsWaiting"] == 0


def _set_status(client: TestClient, status: str, **extra):
    return client.patch(f"/teachers/me/help-requests/{REQUEST}", json={"status": status, **extra})


def _reply(client: TestClient, content: str = "Look at the denominators first."):
    return client.post(f"/teachers/me/help-requests/{REQUEST}/notes", json={"content": content})


def test_the_dispatched_teacher_accepts_by_marking_it_in_progress(table):
    _dispatch_to(table, TEACHER)

    response = _set_status(_client(), "in_progress")

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    conv, question = _conv(table), _question(table)
    assert conv["teacher_id"] == TEACHER
    assert conv["escalation_status"] == "in_progress"
    assert conv["dispatch_status"] == "accepted"
    assert conv["first_teacher_action_at"]
    assert question["status"] == "teacher_active"
    assert question["teacher_id"] == TEACHER
    assert question["dispatch_status"] == "accepted"
    assert question["version"] == 1267  # dispatch + accept, each through the CAS
    _nothing_waits()


def test_an_accepted_request_takes_replies_and_resolving_closes_both_rows(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200

    assert _reply(client).status_code in {200, 201}
    resolved = _set_status(client, "resolved", resolutionNote="Worked through it together.")

    assert resolved.status_code == 200
    conv, question = _conv(table), _question(table)
    assert conv["escalation_status"] == "resolved"
    assert conv["escalation_resolved_at"]
    assert conv["resolution_note"] == "Worked through it together."
    assert question["status"] == "resolved"
    assert question["resolved_at"]
    _nothing_waits()
    stats = client.get("/teachers/me/stats").json()
    assert stats["pendingRequests"] == 0
    assert stats["resolvedToday"] == 1


def test_resolving_straight_from_the_offer_accepts_and_resolves_in_one_write(table):
    _dispatch_to(table, TEACHER)
    before = int(_question(table)["version"])

    response = _set_status(_client(), "resolved", resolutionNote="Answered in one go.")

    assert response.status_code == 200
    conv, question = _conv(table), _question(table)
    assert conv["teacher_id"] == TEACHER
    assert conv["escalation_status"] == "resolved"
    assert question["status"] == "resolved"
    assert question["teacher_id"] == TEACHER
    assert int(question["version"]) == before + 1
    _nothing_waits()


def test_replying_to_an_offer_accepts_it_with_the_reply(table):
    _dispatch_to(table, TEACHER)

    response = _reply(_client())

    assert response.status_code in {200, 201}
    conv = _conv(table)
    assert conv["teacher_id"] == TEACHER
    assert conv["escalation_status"] == "in_progress"
    assert _question(table)["status"] == "teacher_active"
    notes = [row for key, row in table.rows.items() if key[0] == f"CONV#{CONV}" and key[1].startswith("NOTE#")]
    assert len(notes) == 1
    assert notes[0]["teacher_id"] == TEACHER


def test_another_teacher_cannot_take_an_offer_made_to_someone_else(table):
    _dispatch_to(table, TEACHER)
    before = (dict(_conv(table)), dict(_question(table)))

    for attempt in (
        _set_status(_client(OTHER_TEACHER), "in_progress"),
        _set_status(_client(OTHER_TEACHER), "resolved"),
        _reply(_client(OTHER_TEACHER)),
    ):
        assert attempt.status_code == 404

    assert (_conv(table), _question(table)) == before


def test_an_expired_offer_cannot_be_accepted(table):
    _dispatch_to(table, TEACHER)
    for row in (_conv(table), _question(table)):
        row["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    before = (dict(_conv(table)), dict(_question(table)))

    response = _set_status(_client(), "in_progress")

    assert response.status_code in {403, 404}
    assert (_conv(table), _question(table)) == before


def test_an_offer_moved_on_between_the_check_and_the_write_is_refused(table, monkeypatch):
    # Authorization saw a live offer; by the time the write lands the reconciler
    # has re-offered the case. The write must be bound to the offer it checked.
    _dispatch_to(table, TEACHER)
    real_transact = account_deletion_repo.transact
    moved = []

    def transact_after_a_redispatch(operations, *, table=None):
        if not moved:
            moved.append(True)
            table.rows[CONV_KEY]["dispatch_id"] = "a-newer-offer"
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_a_redispatch)

    response = _set_status(_client(), "in_progress")

    assert moved
    assert response.status_code == 409
    assert "teacher_id" not in _conv(table)
    assert _conv(table)["escalation_status"] == "pending"
    assert _question(table)["status"] == "escalated"


def test_a_resolved_request_is_not_reopened(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "resolved").status_code == 200

    assert _set_status(client, "in_progress").status_code == 409
    assert _set_status(client, "resolved").status_code == 409
    assert _conv(table)["escalation_status"] == "resolved"


def test_only_in_progress_and_resolved_are_accepted(table):
    _dispatch_to(table, TEACHER)
    before = dict(_conv(table))

    response = _set_status(_client(), "done")

    assert response.status_code == 422
    assert _conv(table) == before


def test_question_lane_writes_refuse_a_chat_question_row(table):
    # Taking over, replying to or resolving the queue row on its own would split
    # the case again; a chat request is handled through the help-request routes.
    _dispatch_to(table, TEACHER)
    client = _client()
    takeover = client.post(f"/teachers/questions/{REQUEST}/takeover")
    assert takeover.status_code == 409
    assert takeover.json()["detail"]["code"] == "chat_help_request_use_help_request_routes"

    assert _set_status(client, "in_progress").status_code == 200
    before = (dict(_conv(table)), dict(_question(table)))
    for response in (
        client.post(
            f"/teachers/questions/{REQUEST}/reply", json={"content": "Queue-side answer."}
        ),
        client.put(f"/teachers/questions/{REQUEST}/resolve"),
    ):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "chat_help_request_use_help_request_routes"
    assert (_conv(table), _question(table)) == before


# --- What the independent audit of the first version found ---


def _unchanged(table: FakeTable, before: tuple[dict, dict]) -> bool:
    return (_conv(table), _question(table)) == before


def _fail_queue_row_reads(table: FakeTable, monkeypatch) -> None:
    real_get = table.get_item

    def get_item(**kwargs):
        if kwargs.get("Key", {}).get("PK", "").startswith("QUESTION#"):
            raise RuntimeError("ProvisionedThroughputExceededException")
        return real_get(**kwargs)

    monkeypatch.setattr(table, "get_item", get_item)


@pytest.mark.parametrize("first_accept", [False, True], ids=["accepting", "holder"])
def test_a_failed_queue_row_read_writes_nothing(table, monkeypatch, first_accept):
    # A throttled read used to count as "no queue row", and the conversation
    # alone was written: the split this ticket exists to close.
    _dispatch_to(table, TEACHER)
    client = _client()
    if first_accept:
        assert _set_status(client, "in_progress").status_code == 200
    before = (dict(_conv(table)), dict(_question(table)))
    _fail_queue_row_reads(table, monkeypatch)

    assert _set_status(client, "resolved").status_code == 409
    if not first_accept:
        # Replying to the offer would accept it, so it is refused the same way.
        assert _reply(client).status_code == 409

    assert _unchanged(table, before)


def test_dispatch_retries_a_failed_queue_row_read_instead_of_writing_one_row(table, monkeypatch):
    before = (dict(_conv(table)), dict(_question(table)))
    _fail_queue_row_reads(table, monkeypatch)

    result = teacher_dispatch_service.dispatch_conversation(
        CONV, conversation=dict(_conv(table)), table=table
    )

    assert result["status"] == "claim_conflict"
    assert _unchanged(table, before)


def test_a_teacher_who_timed_out_is_not_offered_the_case_again(table):
    _dispatch_to(table, TEACHER)
    for row in (_conv(table), _question(table)):
        row["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"

    teacher_dispatch_service.reconcile_dispatches()

    assert TEACHER in _question(table)["previous_dispatch_teacher_ids"]
    conv = _conv(table)
    assert not (
        conv.get("dispatched_teacher_id") == TEACHER
        and conv.get("dispatch_deadline_at", "") > "2026-02-01"
    ), "the conversation lane offered the case back to the teacher who timed out"
    assert _set_status(_client(), "in_progress").status_code in {403, 404, 409}
    assert "teacher_id" not in _conv(table)


def test_accepting_refuses_a_teacher_the_queue_row_says_timed_out(table):
    _dispatch_to(table, TEACHER)
    _question(table)["previous_dispatch_teacher_ids"] = [TEACHER]
    before = (dict(_conv(table)), dict(_question(table)))

    assert _set_status(_client(), "in_progress").status_code == 409
    assert _unchanged(table, before)


def test_accepting_refuses_when_the_queue_row_carries_another_offer(table):
    # The question lane re-offered the queue row between the policy check and
    # the read; the conversation still shows the old offer.
    _dispatch_to(table, TEACHER)
    _question(table)["dispatch_id"] = "queue-lane-offer"
    before = (dict(_conv(table)), dict(_question(table)))

    assert _set_status(_client(), "in_progress").status_code == 409
    assert _unchanged(table, before)


def test_a_queue_row_changed_between_read_and_write_is_refused(table, monkeypatch):
    _dispatch_to(table, TEACHER)
    real_transact = account_deletion_repo.transact
    bumped = []

    def transact_after_a_queue_row_write(operations, *, table=None):
        if not bumped:
            bumped.append(True)
            row = table.rows[QUESTION_KEY]
            row["version"] = row["version"] + 1
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_a_queue_row_write)

    assert _set_status(_client(), "in_progress").status_code == 409
    assert "teacher_id" not in _conv(table)
    assert _question(table)["status"] == "escalated"


def test_an_offer_without_a_pending_conversation_is_refused(table):
    _dispatch_to(table, TEACHER)
    _conv(table)["escalation_status"] = "in_progress"
    before = (dict(_conv(table)), dict(_question(table)))

    assert _set_status(_client(), "resolved").status_code == 409
    assert _unchanged(table, before)


def test_a_holder_whose_account_is_being_deleted_cannot_resolve(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200
    table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")]["status"] = "deleting"
    before = (dict(_conv(table)), dict(_question(table)))

    assert _set_status(client, "resolved").status_code == 409
    assert _unchanged(table, before)


@pytest.mark.parametrize("fence", ["active", "deleting"])
def test_a_conversation_without_a_queue_row_binds_the_students_fence(table, fence):
    _dispatch_to(table, TEACHER)
    del table.rows[QUESTION_KEY]
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = fence

    response = _set_status(_client(), "in_progress")

    if fence == "active":
        assert response.status_code == 200
        assert _conv(table)["teacher_id"] == TEACHER
    else:
        assert response.status_code == 409
        assert "teacher_id" not in _conv(table)


def test_a_teacher_assigned_to_the_student_keeps_the_conversation_only_write(table, monkeypatch):
    # Characterises the assignment path this change leaves as it was: such a
    # teacher neither holds nor was offered the request, so the two-row move
    # does not apply to them. That this path still moves only the conversation
    # is recorded as its own ticket.
    from stoa.security.authorization import AuthorizationFacts, TeacherAuthorizationFacts
    from stoa.security.route_authorization import get_authorization_fact_repository

    _dispatch_to(table, TEACHER)
    assigned = "teacher-assigned"

    class AssignmentFacts:
        async def facts_for(self, actor, resource, action, purpose, value):
            return AuthorizationFacts(
                teacher=TeacherAuthorizationFacts(
                    question=value,
                    assignment={
                        "teacher_id": assigned,
                        "student_id": STUDENT,
                        "status": "active",
                        "resource_types": [resource.resource_type.value],
                        "actions": [action.value],
                        "purposes": [purpose.value],
                    },
                    teacher_account={"user_id": assigned, "role": "teacher", "account_status": "active"},
                    student_account={"user_id": STUDENT, "role": "student", "account_status": "active"},
                )
            )

    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": assigned, "role": "teacher"})
    app.dependency_overrides[get_authorization_fact_repository] = AssignmentFacts
    question_before = dict(_question(table))

    response = TestClient(app).patch(
        f"/teachers/me/help-requests/{REQUEST}", json={"status": "resolved"}
    )

    assert response.status_code == 200
    assert _conv(table)["escalation_status"] == "resolved"
    assert "teacher_id" not in _conv(table)
    assert _question(table) == question_before
