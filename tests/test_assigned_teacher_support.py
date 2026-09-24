"""Teacher support a student has by being a student here, with no parent in it.

Until this existed, the allowance came from one place: a parent's purchase.
Payments are frozen and STOA assigns accounts rather than selling them, so no
grant could be created and asking for a teacher was refused for every student on
the platform - the refusal told them to go and buy it. Measured in production on
2026-09-24: `POST /teacher-help/request` answered 403 for the only student
account there was.

The figure is seven cases a Zurich week, and an administrator can raise it.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from stoa.services import teacher_support_allowance_service as service

from test_teacher_support_allowances import AtomicSupportTable, _case_committer


NOW = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
STUDENT = "student-assigned-1"


def _profile(**overrides: object) -> dict[str, object]:
    return {
        "user_id": STUDENT,
        "role": "student",
        "account_status": "active",
        # The table returns every number as Decimal, and the fixtures that store
        # `int` are how four defects stayed invisible in this codebase.
        "version": Decimal("21"),
        **overrides,
    }


@pytest.fixture
def student(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    row = _profile()
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(row)
    )
    monkeypatch.setattr(
        service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    return row


def _seed_profile_row(table: AtomicSupportTable, student_id: str) -> None:
    """Put on the table the row the admission fences against.

    `get_user` is patched, so without this the profile the scope was resolved
    from exists only in the patch and the ConditionCheck on it has nothing to
    check. The double used to skip those checks, which is why no test needed
    this and why code that dropped the fence stayed green.
    """
    key = (f"USER#{student_id}", "PROFILE")
    if key in table.items:
        return
    profile = service.user_repo.get_user(student_id) or {}
    table.items[key] = {"PK": f"USER#{student_id}", "SK": "PROFILE", **dict(profile)}
    # `_case_committer` fences generation 6; the case repository contributes it,
    # so the row has to be here too or every admission is refused.
    table.items[(f"USER#{student_id}", "ACCOUNT_FENCE")] = {
        "PK": f"USER#{student_id}",
        "SK": "ACCOUNT_FENCE",
        "status": "active",
        "generation": Decimal("6"),
    }


def _admit(table: AtomicSupportTable, case_id: str, *, student_id: str = STUDENT):
    _seed_profile_row(table, student_id)
    return service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="question",
        beneficiary_id=student_id,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id=case_id, beneficiary_id=student_id
        ),
        table=table,
    )


def _raise_to(table: AtomicSupportTable, cases: int, *, version: int = 1) -> None:
    table.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{STUDENT}",
        "SK": service.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "teacher_support_assigned_allowance",
        "schema_version": service.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
        "weekly_cases": Decimal(cases),
        "state_version": Decimal(version),
    }


def test_a_student_with_no_parent_gets_seven_cases_a_week(student) -> None:
    table = AtomicSupportTable()

    admitted = [_admit(table, f"q-{index}") for index in range(7)]

    assert [result.disposition.value for result in admitted] == ["admitted"] * 7
    assert admitted[-1].admission.post_admission_count == 7
    assert admitted[-1].admission.limit == 7


def test_the_eighth_case_in_the_same_week_is_refused(student) -> None:
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")

    eighth = _admit(table, "q-8")

    assert eighth.disposition.value == "limit_exceeded"


def test_an_administrator_can_raise_the_figure(student) -> None:
    table = AtomicSupportTable()
    _raise_to(table, 9)

    admitted = [_admit(table, f"q-{index}") for index in range(9)]

    assert [result.disposition.value for result in admitted] == ["admitted"] * 9
    assert admitted[-1].admission.limit == 9
    assert _admit(table, "q-10").disposition.value == "limit_exceeded"


def test_raising_the_figure_mid_week_keeps_what_the_week_already_spent(student) -> None:
    """The counter carries the old figure, and it must not read as damage.

    The stored limit used to be compared for equality, so the moment an
    administrator raised it the week's own counter became "malformed" - a
    dependency failure, retried until the caller gave up, which reaches the
    student as a 503 for something somebody did to help them.
    """
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")
    assert _admit(table, "q-8").disposition.value == "limit_exceeded"

    _raise_to(table, 10)

    eighth = _admit(table, "q-8b")
    assert eighth.disposition.value == "admitted"
    # Seven were already spent this week; raising the cap does not refund them.
    assert eighth.admission.post_admission_count == 8
    assert eighth.admission.limit == 10


def test_lowering_the_figure_below_what_was_spent_refuses_rather_than_fails(
    student,
) -> None:
    """Negative control for the same widening: it must refuse, not report damage."""
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")

    _raise_to(table, 3, version=2)

    assert _admit(table, "q-after").disposition.value == "limit_exceeded"


def test_a_paid_grant_still_wins_where_one_exists(monkeypatch) -> None:
    """The assigned figure is a floor, not a replacement.

    A family that bought the wider budget keeps it, and the scope spent against
    is still the grant's - otherwise the counters would part company.
    """
    table = AtomicSupportTable()
    paid = object()
    monkeypatch.setattr(service, "_resolve_paid_scope", lambda *_a, **_k: paid)

    assert service._resolve_scope(STUDENT, table=table) is paid


def test_an_account_that_is_not_an_active_student_gets_nothing(
    monkeypatch, student
) -> None:
    for field, value in (("role", "parent"), ("account_status", "suspended")):
        row = _profile(**{field: value})
        monkeypatch.setattr(
            service.user_repo, "get_user", lambda _uid, r=row, **_kw: deepcopy(r)
        )
        assert service._resolve_assigned_scope(STUDENT, table=AtomicSupportTable()) is None


def test_the_fence_is_the_student_and_nothing_else(student) -> None:
    """What an assigned admission conditions on, read off the transaction.

    The fake table does not evaluate a ConditionCheck, so the conditions are
    read here directly. There must be no parent, no grant row and no
    relationship in them - and no account fence either, because the case
    repository contributes the student's and one transaction cannot target the
    same row twice.
    """
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-fence",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-fence", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    # What this service contributed, not what the case repository added around
    # it: the student's account fence is the repository's, and asserting on the
    # whole transaction would be asserting on somebody else's operation.
    checks = [op["ConditionCheck"] for op in calls[0] if "ConditionCheck" in op]
    keys = {(str(check["Key"]["PK"]), str(check["Key"]["SK"])) for check in checks}

    assert keys == {
        (f"USER#{STUDENT}", "PROFILE"),
        (f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK),
    }
    # And the fence is not among them, or the transaction would target one row
    # twice and be refused outright.
    assert (f"USER#{STUDENT}", "ACCOUNT_FENCE") not in keys
    profile_check = next(
        check for check in checks if check["Key"]["SK"] == "PROFILE"
    )
    assert ":parent_id" not in profile_check["ExpressionAttributeValues"]
    assert profile_check["ExpressionAttributeValues"][":version"] == 21


def test_a_raised_figure_is_fenced_on_the_row_it_was_read_from(student) -> None:
    """Negative control: the figure spent against has to still be in force."""
    table = AtomicSupportTable()
    _raise_to(table, 9, version=4)
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-raised",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-raised", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    check = next(
        op["ConditionCheck"]
        for op in calls[0]
        if "ConditionCheck" in op
        and op["ConditionCheck"]["Key"]["SK"] == service.ASSIGNED_ALLOWANCE_SK
    )
    assert check["ExpressionAttributeValues"] == {":version": 4, ":cases": 9}


def test_with_no_raised_row_the_absence_itself_is_fenced(student) -> None:
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-default",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-default", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    check = next(
        op["ConditionCheck"]
        for op in calls[0]
        if "ConditionCheck" in op
        and op["ConditionCheck"]["Key"]["SK"] == service.ASSIGNED_ALLOWANCE_SK
    )
    assert check["ConditionExpression"] == "attribute_not_exists(PK)"


def test_a_stored_figure_out_of_range_falls_back_to_seven(student) -> None:
    """A bad write must not become an open budget or a locked-out student."""
    table = AtomicSupportTable()
    for stored in (Decimal("-1"), Decimal(service.ASSIGNED_WEEKLY_CASES_MAXIMUM + 1)):
        assert service.assigned_weekly_cases({"weekly_cases": stored}) == 7
    assert service.assigned_weekly_cases({"weekly_cases": Decimal("0")}) == 0
    assert service.assigned_weekly_cases(None) == 7
    del table


def test_a_malformed_raised_row_is_a_dependency_failure_not_a_free_pass(
    student,
) -> None:
    """Negative control: an unreadable row must not silently mean seven."""
    table = AtomicSupportTable()
    table.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{STUDENT}",
        "SK": service.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "something_else",
    }

    assert _admit(table, "q-malformed").disposition.value == "retryable"


def test_two_students_do_not_share_a_week(student, monkeypatch) -> None:
    """Per beneficiary, so one student's week cannot spend another's."""
    table = AtomicSupportTable()
    first = service._resolve_assigned_scope(STUDENT, table=table)
    other_row = _profile(user_id="student-assigned-2")
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda _uid, **_kw: deepcopy(other_row)
    )
    second = service._resolve_assigned_scope("student-assigned-2", table=table)

    assert first.support_scope_id != second.support_scope_id


def test_the_counter_write_is_a_compare_and_set(student) -> None:
    """Two admissions racing are separated by the store, not by the read.

    A first attempt at this drove two threads through the fake with a barrier.
    It reported both admitted - and the trace said why: the barrier counts reads
    of the week counter, this path reads one row more than the paid path it was
    built for, and the threads came apart on the barrier rather than on the
    counter. It was measuring the harness.

    What can be read here is the operation that goes to the store: the counter
    is written against the exact version it was read at, so a second admission
    that read the same version is refused by the store. The paid path's own
    concurrency test covers the same code with a fake that matches its reads.
    """
    table = AtomicSupportTable()
    for index in range(3):
        _admit(table, f"q-{index}")

    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-cas",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-cas", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    counter_put = next(
        op["Put"]
        for op in calls[0]
        if "Put" in op and str(op["Put"]["Item"]["SK"]).startswith("WEEK#")
    )
    values = counter_put.get("ExpressionAttributeValues", {})
    assert ":expected_state_version" in values, "the counter is written unconditionally"
    # Three were already spent, so it was read at version 3 and writes version 4.
    assert values[":expected_state_version"] == 3
    assert counter_put["Item"]["state_version"] == 4
    assert counter_put["Item"]["admitted_cases"] == 4


# --- The administrator's side of the same figure -----------------------------
#
# The endpoint and the admission path are two programs reading one row, so the
# tests below do not stop at "the endpoint answered 200": they take the row the
# endpoint actually wrote and hand it to the service, because a figure stored in
# a shape the service falls back on would pass every assertion about the reply.

from fastapi.testclient import TestClient  # noqa: E402

from stoa.routers import conversations  # noqa: E402
from test_account_admin_endpoints import (  # noqa: E402
    _admin_user,
    _app,
    _seed_profile,
    table as _account_admin_table,
)

# Re-exported under a name of its own: `table` is already a parameter name in
# this module's helpers, and a fixture that shadows them silently changes what
# those helpers receive.
admin_table = _account_admin_table


ALLOWANCE_PATH = f"/admin/teacher-support/allowances/{STUDENT}"


def _admin_client(user: dict[str, Any] | None = None) -> TestClient:
    return TestClient(_app(user or _admin_user()))


def _stored(table_double: Any) -> dict[str, Any] | None:
    return table_double.rows.get((f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK))


def test_a_student_with_no_row_reads_as_the_assigned_default(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "student")

    body = _admin_client().get(ALLOWANCE_PATH).json()

    assert body["weeklyCases"] == service.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES == 7
    assert body["source"] == "default"


def test_the_figure_an_administrator_sets_is_the_figure_the_service_reads(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _admin_client()

    response = client.put(ALLOWANCE_PATH, json={"weekly_cases": 20, "reason": "exam week"})

    assert response.status_code == 200
    assert response.json()["weeklyCases"] == 20
    assert client.get(ALLOWANCE_PATH).json() == {
        "studentId": STUDENT,
        "weeklyCases": 20,
        "source": "administrator",
        "default": 7,
        "maximum": service.ASSIGNED_WEEKLY_CASES_MAXIMUM,
    }
    # The join: the stored row read by the admission path, not by the endpoint.
    assert service.assigned_weekly_cases(_stored(admin_table)) == 20


def test_the_raised_figure_is_what_the_student_may_actually_spend(admin_table) -> None:
    """The whole chain in one test: set two, spend two, be refused the third.

    Each half of this passes on its own while the row the endpoint writes is in a
    shape the service falls back on - it would simply hand out seven and nothing
    would go red.
    """
    _seed_profile(admin_table, STUDENT, "student")
    _admin_client().put(ALLOWANCE_PATH, json={"weekly_cases": 2, "reason": "pilot"})

    spend = AtomicSupportTable()
    written = _stored(admin_table)
    assert written is not None
    spend.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = deepcopy(written)

    spent = [_admit(spend, f"case-{index}").disposition.value for index in (1, 2)]
    third = _admit(spend, "case-3")

    assert spent == ["admitted", "admitted"]
    assert third.disposition.value == "limit_exceeded"


def test_a_second_administrator_writing_the_same_row_is_refused_not_merged(
    admin_table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write built against a figure somebody else has already replaced is refused.

    The interleave is forced rather than hoped for: the competing write lands
    between this caller's read and its put, which is the only window in which
    two administrators can both believe they set the figure.
    """
    _seed_profile(admin_table, STUDENT, "student")
    client = _admin_client()
    client.put(ALLOWANCE_PATH, json={"weekly_cases": 12, "reason": "first"})

    key = (f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)
    original = admin_table.get_item
    intruded: list[bool] = []

    def get_item_then_intrude(**kwargs: Any) -> dict[str, Any]:
        response = original(**kwargs)
        if (str(kwargs["Key"]["PK"]), str(kwargs["Key"]["SK"])) == key and not intruded:
            intruded.append(True)
            row = deepcopy(admin_table.rows[key])
            row["weekly_cases"] = Decimal("30")
            row["state_version"] = Decimal("2")
            admin_table.rows[key] = row
        return response

    monkeypatch.setattr(admin_table, "get_item", get_item_then_intrude)
    conflicting = client.put(ALLOWANCE_PATH, json={"weekly_cases": 5, "reason": "second"})

    assert intruded == [True]
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"]["code"] == "allowance_version_conflict"
    # The other administrator's figure is the one still standing.
    assert service.assigned_weekly_cases(_stored(admin_table)) == 30


def test_each_write_carries_the_version_it_read(admin_table, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _admin_client()
    puts: list[dict[str, Any]] = []
    original = admin_table.put_item

    def recording_put(**kwargs: Any) -> dict[str, Any]:
        if str(kwargs.get("Item", {}).get("SK")) == service.ASSIGNED_ALLOWANCE_SK:
            puts.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(admin_table, "put_item", recording_put)

    first = client.put(ALLOWANCE_PATH, json={"weekly_cases": 9, "reason": "a"}).json()
    second = client.put(ALLOWANCE_PATH, json={"weekly_cases": 11, "reason": "b"}).json()

    assert (first["stateVersion"], second["stateVersion"]) == (1, 2)
    # The first write may only create; the second may only replace version 1.
    assert puts[0]["ConditionExpression"] == "attribute_not_exists(PK)"
    assert "ExpressionAttributeValues" not in puts[0]
    assert puts[1]["ConditionExpression"] == "state_version = :expected"
    assert puts[1]["ExpressionAttributeValues"] == {":expected": 1}


def test_an_account_that_is_not_a_student_has_no_such_figure(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "teacher")

    response = _admin_client().put(
        ALLOWANCE_PATH, json={"weekly_cases": 40, "reason": "no"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_not_a_student"
    assert _stored(admin_table) is None


def test_an_account_that_does_not_exist_is_a_miss_not_a_new_row(admin_table) -> None:
    client = _admin_client()

    response = client.put(ALLOWANCE_PATH, json={"weekly_cases": 40, "reason": "no"})

    assert response.status_code == 404
    assert _stored(admin_table) is None
    # And the read says the same thing. Answering "7, by default" for an id that
    # is not an account made looking it up and changing it disagree.
    assert client.get(ALLOWANCE_PATH).status_code == 404


def test_reading_a_non_student_refuses_the_way_writing_one_does(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "teacher")

    response = _admin_client().get(ALLOWANCE_PATH)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_not_a_student"


def test_the_figure_cannot_be_set_past_what_the_service_will_read_back(admin_table) -> None:
    """Refused at the door rather than stored and silently ignored later.

    `assigned_weekly_cases` falls back to seven for anything out of range, so a
    stored 5000 would read as a *cut*, not a raise, and the administrator would
    have been told it worked.
    """
    _seed_profile(admin_table, STUDENT, "student")

    beyond = _admin_client().put(
        ALLOWANCE_PATH,
        json={"weekly_cases": service.ASSIGNED_WEEKLY_CASES_MAXIMUM + 1, "reason": "no"},
    )
    negative = _admin_client().put(ALLOWANCE_PATH, json={"weekly_cases": -1, "reason": "no"})

    assert (beyond.status_code, negative.status_code) == (422, 422)
    assert _stored(admin_table) is None


def test_setting_it_to_zero_takes_teacher_support_away_rather_than_using_it_up(
    admin_table,
) -> None:
    """Zero is "this account does not have teacher support", not "spent for now".

    The two refusals read differently to the student - one says come back next
    week, the other says ask an administrator - so which one a zero produces is
    part of what is being set here, not an implementation detail.
    """
    _seed_profile(admin_table, STUDENT, "student")
    _admin_client().put(ALLOWANCE_PATH, json={"weekly_cases": 0, "reason": "abuse"})

    spend = AtomicSupportTable()
    spend.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = deepcopy(
        _stored(admin_table)
    )

    assert _admit(spend, "case-1").disposition.value == "plan_denied"


def test_a_non_administrator_cannot_read_or_set_it(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _admin_client({"sub": "teacher-1", "role": "teacher", "accountStatus": "active"})

    assert client.get(ALLOWANCE_PATH).status_code == 403
    assert client.put(ALLOWANCE_PATH, json={"weekly_cases": 99, "reason": "x"}).status_code == 403
    assert _stored(admin_table) is None


def test_the_change_leaves_a_durable_administrator_event(admin_table) -> None:
    _seed_profile(admin_table, STUDENT, "student")

    _admin_client().put(ALLOWANCE_PATH, json={"weekly_cases": 15, "reason": "exam preparation"})

    events = [
        row
        for (pk, sk), row in admin_table.rows.items()
        if pk == f"SECURITY_AUDIT#{STUDENT}" and str(sk).startswith("EVENT#")
    ]
    assert [row["event_type"] for row in events] == ["teacher_support_allowance_set"]
    assert "weekly_cases=15" in str(events[0]["evidence_reference"])


def test_an_administrator_without_the_capability_may_look_but_not_raise(admin_table) -> None:
    """Reading is support work; changing what a student is owed is not.

    The two verbs ask for different capabilities on purpose, so this is the
    negative control for the one that grants the raise.
    """
    _seed_profile(admin_table, STUDENT, "student")
    limited = dict(_admin_user())
    limited["grantCapabilities"] = ("student_support_lookup",)
    client = _admin_client(limited)

    assert client.get(ALLOWANCE_PATH).status_code == 200
    assert client.put(ALLOWANCE_PATH, json={"weekly_cases": 99, "reason": "x"}).status_code == 403
    assert _stored(admin_table) is None


def test_an_administrator_raising_the_figure_mid_request_does_not_503_the_student(
    monkeypatch: pytest.MonkeyPatch, student
) -> None:
    """The scope is read again on each attempt, not once for the whole call.

    The fence an admission carries names the allowance version it read. An
    administrator who changes the figure between that read and the write
    invalidates it, and with the scope resolved once the same stale fence was
    replayed four times and ran out - which the student saw as a 503 for
    something somebody did to help them.
    """
    table = AtomicSupportTable()
    key = (f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)
    _seed_profile_row(table, STUDENT)
    _raise_to(table, 3, version=1)
    intruded: list[bool] = []

    def commit(allowance_operations: tuple[dict[str, Any], ...]) -> bool:
        if not intruded:
            intruded.append(True)
            _raise_to(table, 30, version=2)
        return _case_committer(
            table, kind="question", case_id="q-1", beneficiary_id=STUDENT
        )(allowance_operations)

    result = service.admit_teacher_support_case(
        support_case_id="q-1",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=commit,
        table=table,
    )

    assert intruded == [True]
    assert result.disposition.value == "admitted"
    # And it was admitted against the figure that is now in force, not the old one.
    counter = next(row for k, row in table.items.items() if k[1].startswith("WEEK#"))
    assert int(counter["limit"]) == 30
    assert int(table.items[key]["weekly_cases"]) == 30


def test_the_refusal_does_not_send_the_student_to_a_shop(admin_table) -> None:
    """Both lanes refuse the same way, and neither names a plan.

    Payments are frozen and an assigned account never had anything to buy, so
    "choose a paid plan" is an instruction the student cannot carry out.
    """
    import inspect

    from stoa.routers import questions

    for source in (
        inspect.getsource(conversations.request_teacher_help),
        inspect.getsource(questions.request_teacher),
    ):
        assert '"code": "teacher_support_not_included"' in source
        assert "choose_paid_plan" not in source
        assert '"action": "contact_administrator"' in source
