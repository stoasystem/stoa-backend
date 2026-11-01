"""A help request, from the offer to the end (#66, #189).

A help request is one record in its conversation's partition (#189); before,
it was the conversation's fields and a queue row in the question table, and
these tests checked that the two moved together. Dispatch is the real
`help_requests.dispatch`; routes, repositories and the teacher policy are real,
over the shared table double.
"""

from __future__ import annotations

import json
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable
import pytest

from actor_helpers import install_actor_overrides
from stoa.db.repositories import account_deletion_repo
from stoa.routers import teachers
from stoa.services import help_requests

TEACHER = "teacher-66"
OTHER_TEACHER = "teacher-66-other"
STUDENT = "student-66"
CONV = "conv-66"
# A request's id is its conversation's (#189).
REQUEST = CONV
CREATED = "2026-09-28T12:00:00+00:00"
CONV_KEY = (f"CONV#{CONV}", "CONV")
HELP_KEY = (f"CONV#{CONV}", "HELP")


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


def build_table(monkeypatch) -> FakeTable:
    """The production-shaped rows these tests share; other files build on it too."""
    table = FakeTable()
    table.seed(
        {
            "PK": f"CONV#{CONV}",
            "SK": "CONV",
            "account_fence_generation": 1,
            "conversation_id": CONV,
            "created_at": CREATED,
            "entity_type": "conversation",
            "grade": "6",
            "owner_id": STUDENT,
            "student_id": STUDENT,
            "subject": "mathematics",
            "title": "Fractions",
            "updated_at": CREATED,
        },
        {
            "PK": f"CONV#{CONV}",
            "SK": "HELP",
            "entity_type": "help_request",
            "schema_version": "help-request.v1",
            "conversation_id": CONV,
            "escalation_request_id": REQUEST,
            "student_id": STUDENT,
            "owner_id": STUDENT,
            "account_fence_generation": 1,
            "version": 1265,
            "escalated": True,
            "escalation_status": "pending",
            "escalated_at": CREATED,
            "created_at": CREATED,
            "updated_at": CREATED,
            "escalation_message": "Step 2 makes no sense to me.",
            "subject": "mathematics",
            "grade": "6",
            "dispatch_status": "no_candidate",
            "dispatch_no_candidate_reason": "not_available",
            "dispatch_no_candidate_since": CREATED,
            "dispatch_updated_at": CREATED,
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


def keep_waiting(monkeypatch) -> None:
    """Let the sweep, on the real clock, leave these fixed-date rows waiting.

    They were asked for on a fixed date, so past the waiting limit the sweep
    would expire them (#87). A test that is not about expiry opts in to this;
    the expiry tests set the clock and the limit themselves.
    """
    from stoa.config import settings

    monkeypatch.setattr(settings, "teacher_help_expiry_seconds", 10 * 365 * 24 * 60 * 60)


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = build_table(monkeypatch)
    keep_waiting(monkeypatch)
    return built


def _dispatch_to(table: FakeTable, teacher_id: str) -> None:
    # Only the named teacher is on dispatch when the offer is made.
    for other in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{other}", "PROFILE")]["dispatch_availability"] = (
            "available" if other == teacher_id else "paused"
        )
    written = help_requests.dispatch(dict(table.rows[HELP_KEY]), table=table)
    assert written["dispatch_status"] == "dispatched"
    assert written["dispatched_teacher_id"] == teacher_id


def _client(teacher_id: str = TEACHER) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": teacher_id, "role": "teacher"})
    return TestClient(app)


def _conv(table: FakeTable) -> dict:
    return table.rows[CONV_KEY]


def _help(table: FakeTable) -> dict:
    """The request's record (#189)."""
    return table.rows[HELP_KEY]


def _nothing_waits() -> None:
    outcome = help_requests.sweep()
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
    record = _help(table)
    assert record["teacher_id"] == TEACHER
    assert record["escalation_status"] == "in_progress"
    assert record["dispatch_status"] == "accepted"
    assert record["accepted_at"]
    # Taking a request is not its first response; the first reply is (#189).
    assert "first_teacher_action_at" not in record
    assert record["version"] == 1267  # dispatch + accept, each through the CAS
    _nothing_waits()


def test_an_accepted_request_takes_replies_and_resolving_ends_it(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200

    assert _reply(client).status_code in {200, 201}
    assert _help(table)["first_teacher_action_at"]
    resolved = _set_status(client, "resolved", resolutionNote="Worked through it together.")

    assert resolved.status_code == 200
    record = _help(table)
    assert record["escalation_status"] == "resolved"
    assert record["escalation_resolved_at"]
    assert record["resolution_note"] == "Worked through it together."
    _nothing_waits()
    stats = client.get("/teachers/me/stats").json()
    assert stats["pendingRequests"] == 0
    assert stats["resolvedToday"] == 1


def test_resolving_straight_from_the_offer_accepts_and_resolves_in_one_write(table):
    _dispatch_to(table, TEACHER)
    before = int(_help(table)["version"])

    response = _set_status(_client(), "resolved", resolutionNote="Answered in one go.")

    assert response.status_code == 200
    record = _help(table)
    assert record["teacher_id"] == TEACHER
    assert record["escalation_status"] == "resolved"
    assert record["dispatch_status"] == "accepted"
    assert int(record["version"]) == before + 1
    _nothing_waits()


def test_replying_to_an_offer_accepts_it_with_the_reply(table):
    _dispatch_to(table, TEACHER)

    response = _reply(_client())

    assert response.status_code in {200, 201}
    record = _help(table)
    assert record["teacher_id"] == TEACHER
    assert record["escalation_status"] == "in_progress"
    # The reply is the request's first response (#189).
    assert record["first_teacher_action_at"] == record["accepted_at"]
    notes = [row for key, row in table.rows.items() if key[0] == f"CONV#{CONV}" and key[1].startswith("NOTE#")]
    assert len(notes) == 1
    assert notes[0]["teacher_id"] == TEACHER


def test_another_teacher_cannot_take_an_offer_made_to_someone_else(table):
    _dispatch_to(table, TEACHER)
    before = (dict(_conv(table)), dict(_help(table)))

    for attempt in (
        _set_status(_client(OTHER_TEACHER), "in_progress"),
        _set_status(_client(OTHER_TEACHER), "resolved"),
        _reply(_client(OTHER_TEACHER)),
    ):
        assert attempt.status_code == 404

    assert (_conv(table), _help(table)) == before


def test_an_expired_offer_cannot_be_accepted(table):
    _dispatch_to(table, TEACHER)
    _help(table)["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    before = (dict(_conv(table)), dict(_help(table)))

    response = _set_status(_client(), "in_progress")

    assert response.status_code in {403, 404}
    assert (_conv(table), _help(table)) == before


def test_an_offer_moved_on_between_the_check_and_the_write_is_refused(table, monkeypatch):
    # Authorization saw a live offer; by the time the write lands the sweep
    # has re-offered the case. The write must be bound to the offer it checked.
    _dispatch_to(table, TEACHER)
    real_transact = account_deletion_repo.transact
    moved = []

    def transact_after_a_redispatch(operations, *, table=None):
        if not moved:
            moved.append(True)
            table.rows[HELP_KEY]["dispatch_id"] = "a-newer-offer"
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_a_redispatch)

    response = _set_status(_client(), "in_progress")

    assert moved
    assert response.status_code == 409
    assert "teacher_id" not in _help(table)
    assert _help(table)["escalation_status"] == "pending"


def test_a_resolved_request_is_not_reopened(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "resolved").status_code == 200

    assert _set_status(client, "in_progress").status_code == 409
    assert _set_status(client, "resolved").status_code == 409
    assert _help(table)["escalation_status"] == "resolved"


def test_only_in_progress_and_resolved_are_accepted(table):
    _dispatch_to(table, TEACHER)
    before = (dict(_conv(table)), dict(_help(table)))

    response = _set_status(_client(), "done")

    assert response.status_code == 422
    assert (_conv(table), _help(table)) == before


# --- What the independent audit of the first version found ---


def _unchanged(table: FakeTable, before: tuple[dict, dict]) -> bool:
    return (_conv(table), _help(table)) == before


def _fail_request_reads(table: FakeTable, monkeypatch) -> None:
    real_get = table.get_item

    def get_item(**kwargs):
        if kwargs.get("Key", {}).get("SK") == "HELP":
            raise RuntimeError("ProvisionedThroughputExceededException")
        return real_get(**kwargs)

    monkeypatch.setattr(table, "get_item", get_item)


@pytest.mark.parametrize("first_accept", [False, True], ids=["accepting", "holder"])
def test_a_failed_request_read_writes_nothing(table, monkeypatch, first_accept):
    # A throttled read used to count as "no request", and a write went ahead
    # on what was not read. Unknown is not absent (#189): nothing is written.
    _dispatch_to(table, TEACHER)
    client = TestClient(_client().app, raise_server_exceptions=False)
    if first_accept:
        assert _set_status(client, "in_progress").status_code == 200
    before = (dict(_conv(table)), dict(_help(table)))
    rows_before = set(table.rows)
    _fail_request_reads(table, monkeypatch)

    # Unavailable, to be tried again - not "no such request", and not a write.
    assert _set_status(client, "resolved").status_code == 503
    assert _reply(client).status_code == 503

    assert _unchanged(table, before)
    assert set(table.rows) == rows_before


def test_a_teacher_who_timed_out_is_not_offered_the_case_again(table):
    _dispatch_to(table, TEACHER)
    _help(table)["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"

    help_requests.sweep()

    record = _help(table)
    assert TEACHER in record["previous_dispatch_teacher_ids"]
    assert record.get("dispatched_teacher_id") != TEACHER, (
        "the sweep offered the case back to the teacher who timed out"
    )
    assert _set_status(_client(), "in_progress").status_code in {403, 404, 409}
    assert "teacher_id" not in _help(table)


def test_accepting_refuses_a_teacher_the_request_says_timed_out(table):
    _dispatch_to(table, TEACHER)
    _help(table)["previous_dispatch_teacher_ids"] = [TEACHER]
    before = (dict(_conv(table)), dict(_help(table)))

    # The policy now reads the same record, so it may refuse before the write does.
    assert _set_status(_client(), "in_progress").status_code in {403, 409}
    assert _unchanged(table, before)


def test_a_request_changed_between_read_and_write_is_refused(table, monkeypatch):
    # Any write to the request moves its version; a write decided on the
    # version before it is refused (#189).
    _dispatch_to(table, TEACHER)
    real_transact = account_deletion_repo.transact
    bumped = []

    def transact_after_another_write(operations, *, table=None):
        if not bumped:
            bumped.append(True)
            row = table.rows[HELP_KEY]
            row["version"] = row["version"] + 1
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_another_write)

    assert _set_status(_client(), "in_progress").status_code == 409
    assert "teacher_id" not in _help(table)
    assert _help(table)["escalation_status"] == "pending"


def test_an_offer_on_a_request_no_longer_pending_is_refused(table):
    # An offer is taken only while the request waits; a request that moved on
    # without a holder is not taken by the offer it still shows.
    _dispatch_to(table, TEACHER)
    _help(table)["escalation_status"] = "in_progress"
    before = (dict(_conv(table)), dict(_help(table)))

    assert _set_status(_client(), "resolved").status_code in {403, 409}
    assert _unchanged(table, before)


def test_a_holder_whose_account_is_being_deleted_cannot_resolve(table):
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200
    table.rows[(f"USER#{TEACHER}", "ACCOUNT_FENCE")]["status"] = "deleting"
    before = (dict(_conv(table)), dict(_help(table)))

    assert _set_status(client, "resolved").status_code == 409
    assert _unchanged(table, before)


def test_a_conversation_without_a_request_cannot_be_taken(table):
    # Nothing to take: the teacher's routes answer from the request, so a
    # conversation that never asked has nothing a teacher can write (#189).
    del table.rows[HELP_KEY]
    before = dict(_conv(table))
    rows_before = set(table.rows)

    for attempt in (
        _set_status(_client(), "in_progress"),
        _set_status(_client(), "resolved"),
        _reply(_client()),
    ):
        assert attempt.status_code == 404

    assert _conv(table) == before
    assert set(table.rows) == rows_before


@pytest.mark.parametrize("held", [False, True], ids=["offered_to_another", "held_by_another"])
def test_a_teacher_assigned_to_the_student_cannot_write_a_request_they_do_not_hold(
    table, monkeypatch, held
):
    # User decision on #73 (2026-09-28): a teacher the policy admits through an
    # assignment, who neither holds the request nor was offered it, may read
    # it but not write it. The write they used to get could strand a request
    # offered to someone else, or reopen a resolved one.
    from stoa.security.authorization import AuthorizationFacts, TeacherAuthorizationFacts
    from stoa.security.route_authorization import get_authorization_fact_repository

    _dispatch_to(table, TEACHER)
    if held:
        assert _set_status(_client(), "in_progress").status_code == 200
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
    client = TestClient(app)
    before = (dict(_conv(table)), dict(_help(table)))
    rows_before = set(table.rows)

    for attempt in (
        client.patch(f"/teachers/me/help-requests/{REQUEST}", json={"status": "in_progress"}),
        client.patch(f"/teachers/me/help-requests/{REQUEST}", json={"status": "resolved"}),
        client.post(f"/teachers/me/help-requests/{REQUEST}/notes", json={"content": "Hi"}),
    ):
        assert attempt.status_code == 409, attempt.text
        # Refused because they do not hold it, not because the request moved.
        assert attempt.json()["detail"]["code"] == "help_request_not_held"

    assert _unchanged(table, before)
    assert set(table.rows) == rows_before
    # Reading is still allowed.
    assert client.get(f"/teachers/me/help-requests/{REQUEST}").status_code == 200


def test_an_offer_that_expires_between_the_check_and_the_write_is_refused(table, monkeypatch):
    # The policy saw a live offer on its own clock; the write happens after the
    # deadline. Found by the second independent audit: the deadline was checked
    # by the policy only, so the late write still took the offer. The write
    # binds it.
    _dispatch_to(table, TEACHER)
    assert _help(table)["dispatch_deadline_at"] < "2099"
    monkeypatch.setattr(teachers, "_now", lambda: "2099-01-01T00:00:00+00:00")
    before = (dict(_conv(table)), dict(_help(table)))

    for attempt in (_set_status(_client(), "in_progress"), _reply(_client())):
        assert attempt.status_code == 409

    assert _unchanged(table, before)


# --- Deleting a teacher returns their open chat requests to waiting (#72) ---
#
# User decision 2026-09-28: when a teacher account is deleted, a chat help
# request they took or were offered goes back to waiting, so the sweep offers
# it to someone else. A closed one keeps its outcome and loses only the
# teacher references. These drive the real deletion branch until it reports
# complete.

from dataclasses import asdict  # noqa: E402

from stoa.services import account_deletion_service  # noqa: E402

_TEACHER_FIELDS = (
    "teacher_id",
    "dispatched_teacher_id",
    "dispatch_id",
    "dispatch_deadline_at",
    "accepted_at",
)


def _delete_teacher(table: FakeTable, teacher_id: str = TEACHER) -> list:
    table.rows[(f"USER#{teacher_id}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    branch = account_deletion_service.BRANCH_HANDLERS["question_ocr_session"]
    command = {"user_id": teacher_id, "generation": 1}
    previous: dict = {}
    results = []
    for _ in range(6):
        result = branch(command=command, previous=previous)
        results.append(result)
        previous = asdict(result)
        if result.status == "complete":
            break
    return results


def _assert_waiting_without(table: FakeTable, teacher_id: str, *, dispatch: str = "unassigned") -> None:
    record = _help(table)
    assert record["escalation_status"] == "pending"
    assert record["dispatch_status"] == dispatch
    for field in _TEACHER_FIELDS:
        assert field not in record, field
    assert teacher_id not in record.get("previous_dispatch_teacher_ids", [])
    # The student's own content is untouched.
    assert record["escalation_message"] == "Step 2 makes no sense to me."


@pytest.mark.parametrize("accepted", [True, False], ids=["accepted", "offered"])
def test_deleting_the_teacher_returns_an_open_request_to_waiting(table, accepted):
    _dispatch_to(table, TEACHER)
    if accepted:
        assert _reply(_client()).status_code in {200, 201}

    results = _delete_teacher(table)

    assert results[-1].status == "complete", [asdict(r) for r in results]
    _assert_waiting_without(table, TEACHER)

    # Nothing is stuck: the sweep offers it to another teacher, who ends it.
    table.rows[(f"USER#{OTHER_TEACHER}", "PROFILE")]["dispatch_availability"] = "available"
    help_requests.sweep()
    assert _help(table)["dispatched_teacher_id"] == OTHER_TEACHER
    assert _set_status(_client(OTHER_TEACHER), "resolved").status_code == 200
    assert _help(table)["escalation_status"] == "resolved"
    _nothing_waits()


def test_deleting_the_teacher_after_a_timeout_clears_the_lapsed_offer(table):
    _dispatch_to(table, TEACHER)
    _help(table)["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    help_requests.sweep()
    assert TEACHER in _help(table)["previous_dispatch_teacher_ids"]

    # The sweep found nobody else and took the lapsed offer off itself (#86),
    # so the scrub has only the history of who was tried left to clear.
    assert _help(table)["dispatch_status"] == "no_candidate"

    results = _delete_teacher(table)

    assert results[-1].status == "complete", [asdict(r) for r in results]
    _assert_waiting_without(table, TEACHER, dispatch="no_candidate")


def test_deleting_the_teacher_keeps_a_resolved_request_resolved(table):
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "resolved", resolutionNote="Done together.").status_code == 200

    results = _delete_teacher(table)

    assert results[-1].status == "complete", [asdict(r) for r in results]
    record = _help(table)
    assert record["escalation_status"] == "resolved"
    assert record["resolution_note"] == "Done together."
    for field in ("teacher_id", "dispatched_teacher_id"):
        assert field not in record, field
    _nothing_waits()


def test_a_request_that_moves_during_the_scrub_is_retried_not_overwritten(table, monkeypatch):
    # The request is resolved between the scrub's read and its write (a real
    # write, so its version moves); the scrub is bound to what it read, so the
    # pass is retried, then completes.
    _dispatch_to(table, TEACHER)
    assert _reply(_client()).status_code in {200, 201}
    real_transact = account_deletion_repo.transact
    moved = []

    def transact_after_the_request_moves(operations, *, table=None):
        touches_request = any(
            (op.get("Update") or {}).get("Key") == {"PK": f"CONV#{CONV}", "SK": "HELP"}
            for op in operations
        )
        if touches_request and not moved:
            moved.append(True)
            row = table.rows[HELP_KEY]
            row.update(escalation_status="resolved", version=row["version"] + 1)
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_the_request_moves)

    results = _delete_teacher(table)

    assert moved
    assert results[0].status == "retryable"
    assert results[0].debt_counts.get("row_conflict") == 1
    assert results[-1].status == "complete", [asdict(r) for r in results]
    # The later pass saw the request as resolved and kept that outcome.
    assert _help(table)["escalation_status"] == "resolved"
    assert "teacher_id" not in _help(table)


def _race_once(monkeypatch, mutate) -> list:
    """Apply `mutate(table)` once, just before the scrub's transaction lands."""
    real_transact = account_deletion_repo.transact
    fired = []

    def transact(operations, *, table=None):
        scrubbing = any(
            (op.get("ConditionCheck") or {}).get("ExpressionAttributeValues", {}).get(":pending")
            == "deletion_pending"
            for op in operations
        )
        if scrubbing and not fired:
            fired.append(True)
            mutate(table)
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact)
    return fired


def test_a_request_whose_version_moves_during_the_scrub_is_retried(table, monkeypatch):
    _dispatch_to(table, TEACHER)
    assert _reply(_client()).status_code in {200, 201}

    def bump(t):
        t.rows[HELP_KEY]["version"] = t.rows[HELP_KEY]["version"] + 1

    fired = _race_once(monkeypatch, bump)
    results = _delete_teacher(table)

    assert fired
    assert results[0].status == "retryable"
    assert results[0].debt_counts.get("row_conflict") == 1
    assert results[-1].status == "complete", [asdict(r) for r in results]
    _assert_waiting_without(table, TEACHER)


def test_a_request_re_offered_to_another_teacher_during_the_scrub_keeps_that_offer(
    table, monkeypatch
):
    # Between the scrub's read and its write, the request is offered to
    # another teacher (a write, so its version moves). The scrub is bound to
    # the version it read, so it is refused, and the new offer is not wiped.
    _dispatch_to(table, TEACHER)

    def reoffer(t):
        row = t.rows[HELP_KEY]
        row.update(
            dispatched_teacher_id=OTHER_TEACHER,
            dispatch_id="an-offer-to-someone-else",
            version=row["version"] + 1,
        )

    fired = _race_once(monkeypatch, reoffer)
    results = _delete_teacher(table)

    assert fired
    assert results[0].status == "retryable"
    assert results[0].debt_counts.get("row_conflict") == 1
    assert results[-1].status == "complete", [asdict(r) for r in results]
    record = _help(table)
    assert record["dispatched_teacher_id"] == OTHER_TEACHER
    assert record["dispatch_id"] == "an-offer-to-someone-else"
    assert TEACHER != record.get("teacher_id")


def test_a_conversation_the_students_deletion_tombstoned_counts_as_gone(table):
    # A student's deletion replaced the conversation first; the teacher's
    # deletion must not wait forever on an identity it can no longer match.
    _dispatch_to(table, TEACHER)
    table.rows[CONV_KEY] = {
        "PK": f"CONV#{CONV}",
        "SK": "CONV",
        "owner_id": STUDENT,
        "student_id": STUDENT,
        "status": "deleted",
        "owner_deletion_generation": 1,
        "deleted_at": CREATED,
    }
    tombstone = dict(table.rows[CONV_KEY])

    results = _delete_teacher(table)

    assert results[-1].status == "complete", [asdict(r) for r in results]
    assert table.rows[CONV_KEY] == tombstone
    assert "dispatched_teacher_id" not in _help(table)


# --- The student reads the teacher's reply (#66 production acceptance) ---


def _student_client() -> TestClient:
    from stoa.routers import conversations
    from stoa.security.route_authorization import get_authorization_fact_repository

    app = FastAPI()
    app.include_router(conversations.router, prefix="/conversations")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    # The real fact repository, so the student's read is authorised as in production.
    app.dependency_overrides.pop(get_authorization_fact_repository, None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("accept_first", [False, True], ids=["reply_accepts", "accepted_then_reply"])
def test_the_student_reads_the_teachers_reply_before_and_after_resolving(table, accept_first):
    # The student's history reader refuses the whole conversation if any message
    # breaks the message contract. The teacher's message was written without it,
    # so in production on 2026-09-28 the student could no longer open the
    # conversation at all once a teacher replied.
    _dispatch_to(table, TEACHER)
    teacher, student = _client(), _student_client()
    assert student.get(f"/conversations/{CONV}").status_code == 200
    if accept_first:
        assert _set_status(teacher, "in_progress").status_code == 200

    assert _reply(teacher, "Probier jetzt 15 : 5.").status_code in {200, 201}
    after_reply = student.get(f"/conversations/{CONV}")

    assert after_reply.status_code == 200, after_reply.text
    teacher_messages = [m for m in after_reply.json()["messages"] if m["role"] == "teacher"]
    assert [m["content"] for m in teacher_messages] == ["Probier jetzt 15 : 5."]

    assert _set_status(teacher, "resolved").status_code == 200
    after_resolve = student.get(f"/conversations/{CONV}")
    assert after_resolve.status_code == 200, after_resolve.text
    assert [m["role"] for m in after_resolve.json()["messages"]].count("teacher") == 1


# --- #73: only a request is offered, and the sweep offers it ---


def test_a_conversation_without_a_request_is_not_offered(table):
    # Such a conversation has nothing a teacher could take, so offering it
    # would only re-offer it forever to teachers who get 404.
    del table.rows[HELP_KEY]
    before = dict(_conv(table))

    outcome = help_requests.sweep()

    assert outcome["conversationsWaiting"] == 0
    assert outcome["conversationsDispatched"] == []
    assert _conv(table) == before
    assert HELP_KEY not in table.rows


def test_the_sweep_offers_a_waiting_request_and_re_offers_it_when_the_offer_lapses(table):
    # One sweep offers a waiting request to a free teacher; once that offer
    # lapses, the next records the lapse and offers it to the other teacher in
    # the same write (stoasystem/stoa-backend#75, #189), who can then end it.
    table.rows[(f"USER#{OTHER_TEACHER}", "PROFILE")]["dispatch_availability"] = "paused"

    help_requests.sweep()

    record = _help(table)
    assert record["dispatch_status"] == "dispatched"
    assert record["dispatched_teacher_id"] == TEACHER
    first_offer = record["dispatch_id"]

    record["dispatch_deadline_at"] = "2026-01-01T00:00:00+00:00"
    table.rows[(f"USER#{OTHER_TEACHER}", "PROFILE")]["dispatch_availability"] = "available"

    help_requests.sweep()

    record = _help(table)
    assert TEACHER in record["previous_dispatch_teacher_ids"]
    assert record["dispatched_teacher_id"] == OTHER_TEACHER
    assert record["dispatch_id"] != first_offer
    assert _set_status(_client(OTHER_TEACHER), "resolved").status_code == 200
    _nothing_waits()


# --- A teacher's reply belongs to the student's conversation (#74) ---
#
# NOTE# rows carried no owner, so deleting the student left the teacher's
# replies about them in the table. They are now stamped like every other
# conversation row and written behind the student's account fence, so the
# student's deletion removes them and cannot be outrun by a late reply. On a
# teacher's deletion they are kept as they are (user decision, 2026-09-28).


def _notes(table: FakeTable) -> list[dict]:
    return [row for key, row in table.rows.items() if key[0] == f"CONV#{CONV}" and key[1].startswith("NOTE#")]


@pytest.mark.parametrize("held", [False, True], ids=["reply_accepts", "holder_replies"])
def test_a_reply_is_stamped_as_the_students_conversation_row(table, held):
    _dispatch_to(table, TEACHER)
    client = _client()
    if held:
        assert _set_status(client, "in_progress").status_code == 200

    assert _reply(client).status_code in {200, 201}

    (note,) = _notes(table)
    assert note["entity_type"] == "conversation_teacher_note"
    assert note["owner_id"] == note["student_id"] == STUDENT
    assert int(note["account_fence_generation"]) == 1
    assert note["teacher_id"] == TEACHER  # kept, per the user's decision


def test_a_holders_reply_is_refused_once_the_students_deletion_has_begun(table):
    # Without the fence a reply written after the deletion swept the
    # conversation would bring the student's data back.
    _dispatch_to(table, TEACHER)
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    rows_before = set(table.rows)

    assert _reply(client).status_code == 409

    assert set(table.rows) == rows_before


def test_deleting_the_student_removes_the_teachers_replies_from_their_conversation(table):
    _dispatch_to(table, TEACHER)
    assert _reply(_client(), "Probier jetzt 15 : 5.").status_code in {200, 201}
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    branch = account_deletion_service.BRANCH_HANDLERS["conversation_messages"]

    # The real branch, over the real scan, runs until it seals (#78: it used to
    # re-scan its own tombstones and never finish).
    results, previous = [], {}
    for _ in range(8):
        result = branch(command={"user_id": STUDENT, "generation": 1}, previous=previous)
        results.append((result.status, result.epoch))
        previous = asdict(result)
        if result.status == "complete":
            break

    assert results[-1] == ("complete", 2), results
    assert result.quiescent is True
    (note,) = _notes(table)
    assert "content" not in note
    assert "teacher_name" not in note
    assert "Probier" not in json.dumps(note, default=str)


def test_a_reply_that_would_accept_is_refused_once_the_students_deletion_has_begun(table):
    # The accepting reply is written behind the student's fence, as every
    # write that puts rows in the student's conversation is (#189).
    _dispatch_to(table, TEACHER)
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    rows_before = set(table.rows)
    before = (dict(_conv(table)), dict(_help(table)))

    assert _reply(_client()).status_code == 409

    assert set(table.rows) == rows_before
    assert _unchanged(table, before)


def test_a_reply_is_stamped_with_the_generation_its_fence_checks(table):
    # A conversation row carrying a stale generation must not put that stale
    # value on the reply: the stamp is what the transaction checked.
    _dispatch_to(table, TEACHER)
    _conv(table)["account_fence_generation"] = 2
    client = _client()
    assert _set_status(client, "in_progress").status_code == 200

    assert _reply(client).status_code in {200, 201}

    (note,) = _notes(table)
    assert int(note["account_fence_generation"]) == 1
    assert _reply(client, "Second reply.").status_code in {200, 201}


def test_opening_a_request_writes_nothing(table):
    # The detail GET used to record the teacher's first action, and so could
    # land a write on a conversation the student's deletion had just
    # tombstoned. The first response is now the first reply (#189), and
    # opening the request writes nothing at all.
    _dispatch_to(table, TEACHER)
    before = (dict(_conv(table)), dict(_help(table)))
    writes = {
        operation: table.calls[operation]
        for operation in ("put_item", "update_item", "delete_item", "transact_write_items")
    }

    response = _client().get(f"/teachers/me/help-requests/{REQUEST}")

    assert response.status_code == 200, response.text
    assert response.json()["firstTeacherActionAt"] is None
    assert {operation: table.calls[operation] for operation in writes} == writes
    assert _unchanged(table, before)
