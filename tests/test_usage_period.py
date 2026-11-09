"""#342: an account's usage period - its storage, the rules, and the admin console.

Step 1 of #239. The period is stored and administered here; nothing in this step
refuses a student anything (#343 reads it, #344 enforces it).
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable

from test_account_admin_endpoints import (
    AccountAdminTable,
    _admin_user,
    _app,
    _seed_profile,
    table as _account_admin_table,
)

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service, usage_period
from stoa.services.usage_period import (
    PaidBy,
    PeriodSource,
    PeriodState,
    PeriodUnit,
    add_months,
    extended_end,
    latest_period,
    state_on,
)
from rule_violation_helpers import assert_violation

admin_table = _account_admin_table

STUDENT = "student-1"
PARENT = "parent-1"
OTHER_PARENT = "parent-2"
TEACHER = "teacher-1"


def D(value: str) -> date:  # noqa: N802 - reads as a literal in the tables below
    return date.fromisoformat(value)


# ---------------------------------------------------------------------------
# The rules on their own
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "current,today,unit,amount,expected",
    [
        # From today when there is no period yet.
        (None, "2026-11-09", PeriodUnit.MONTHS, 1, "2026-12-09"),
        # Month end: the last day of a shorter month, leap year included.
        (None, "2026-01-31", PeriodUnit.MONTHS, 1, "2026-02-28"),
        (None, "2028-01-31", PeriodUnit.MONTHS, 1, "2028-02-29"),
        ("2026-03-31", "2026-03-01", PeriodUnit.MONTHS, 1, "2026-04-30"),
        (None, "2026-08-31", PeriodUnit.MONTHS, 6, "2027-02-28"),
        # Across the year.
        (None, "2026-12-15", PeriodUnit.MONTHS, 2, "2027-02-15"),
        ("2026-12-31", "2026-11-09", PeriodUnit.MONTHS, 12, "2027-12-31"),
        # From the current end while it is still running...
        ("2026-12-20", "2026-11-09", PeriodUnit.MONTHS, 1, "2027-01-20"),
        # ...including on its very last day...
        ("2026-11-09", "2026-11-09", PeriodUnit.MONTHS, 1, "2026-12-09"),
        # ...and from today once it has ended.
        ("2026-10-01", "2026-11-09", PeriodUnit.MONTHS, 1, "2026-12-09"),
        # Days.
        (None, "2026-11-09", PeriodUnit.DAYS, 14, "2026-11-23"),
        ("2026-12-25", "2026-11-09", PeriodUnit.DAYS, 10, "2027-01-04"),
        ("2026-10-01", "2026-11-09", PeriodUnit.DAYS, 7, "2026-11-16"),
    ],
)
def test_an_extension_counts_from_today_or_the_current_end_whichever_is_later(
    current: str | None, today: str, unit: PeriodUnit, amount: int, expected: str
) -> None:
    assert extended_end(D(current) if current else None, D(today), unit, amount) == D(expected)


def test_an_extension_is_at_least_one_unit() -> None:
    with pytest.raises(ValueError):
        extended_end(None, D("2026-11-09"), PeriodUnit.DAYS, 0)


def test_adding_months_lands_on_the_last_day_of_a_shorter_month() -> None:
    assert [add_months(D("2026-01-31"), n).isoformat() for n in range(1, 5)] == [
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
        "2026-05-31",
    ]


@pytest.mark.parametrize(
    "ends_on,today,expected",
    [
        (None, "2026-11-09", PeriodState.NONE),
        ("2026-11-10", "2026-11-09", PeriodState.ACTIVE),
        # The end date is a whole day: it ends at 23:59:59 that day.
        ("2026-11-09", "2026-11-09", PeriodState.ACTIVE),
        ("2026-11-08", "2026-11-09", PeriodState.EXPIRED),
    ],
)
def test_the_state_of_a_period(ends_on: str | None, today: str, expected: PeriodState) -> None:
    assert state_on(D(ends_on) if ends_on else None, D(today)) is expected


def test_the_day_is_zurichs_not_utcs() -> None:
    # 23:30 UTC on 9 November is already the 10th in Zurich.
    assert usage_period.zurich_today(datetime(2026, 11, 9, 23, 30, tzinfo=UTC)) == D("2026-11-10")
    # 23:30 UTC on 9 July is the 10th in summer time too.
    assert usage_period.zurich_today(datetime(2026, 7, 9, 22, 30, tzinfo=UTC)) == D("2026-07-10")


@pytest.mark.parametrize(
    "own,parents,ends_on,paid_by,parent_id",
    [
        # Nobody holds a period.
        (None, [], None, None, None),
        (None, [(PARENT, None)], None, None, None),
        # The student's own.
        ("2026-12-01", [], "2026-12-01", PaidBy.SELF, None),
        # One parent's.
        (None, [(PARENT, "2027-01-01")], "2027-01-01", PaidBy.PARENT, PARENT),
        ("2026-12-01", [(PARENT, "2027-01-01")], "2027-01-01", PaidBy.PARENT, PARENT),
        ("2027-02-01", [(PARENT, "2027-01-01")], "2027-02-01", PaidBy.SELF, None),
        # Two parents: the later one.
        (
            "2026-12-01",
            [(PARENT, "2027-01-01"), (OTHER_PARENT, "2027-03-01")],
            "2027-03-01",
            PaidBy.PARENT,
            OTHER_PARENT,
        ),
        (None, [(PARENT, "2027-03-01"), (OTHER_PARENT, None)], "2027-03-01", PaidBy.PARENT, PARENT),
        # A tie goes to the student's own.
        ("2027-01-01", [(PARENT, "2027-01-01")], "2027-01-01", PaidBy.SELF, None),
    ],
)
def test_a_students_effective_period_is_the_latest(
    own: str | None,
    parents: list[tuple[str, str | None]],
    ends_on: str | None,
    paid_by: PaidBy | None,
    parent_id: str | None,
) -> None:
    effective = latest_period(
        D(own) if own else None,
        [(pid, D(end) if end else None) for pid, end in parents],
        today=D("2026-11-09"),
    )

    assert effective.ends_on == (D(ends_on) if ends_on else None)
    assert effective.paid_by == paid_by
    assert effective.parent_id == parent_id


def test_a_period_that_has_ended_still_wins_as_the_latest_and_reads_expired() -> None:
    effective = latest_period(D("2026-10-01"), [(PARENT, D("2026-09-01"))], today=D("2026-11-09"))

    assert (effective.ends_on, effective.state, effective.paid_by) == (
        D("2026-10-01"),
        PeriodState.EXPIRED,
        PaidBy.SELF,
    )


# ---------------------------------------------------------------------------
# The console
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(_app(_admin_user()))


def _today() -> date:
    return usage_period.zurich_today()


def _records(table: AccountAdminTable, user_id: str) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == f"USER#{user_id}" and sk.startswith(usage_period.RECORD_SK_PREFIX)
    ]


def _extend(
    client: TestClient,
    user_id: str,
    *,
    version: int = 1,
    unit: str = "months",
    amount: int = 1,
    source: str = "paid",
    reference: str | None = "Bank transfer 2026-11-09 #A17",
    note: str | None = None,
) -> Any:
    body: dict[str, Any] = {
        "unit": unit,
        "amount": amount,
        "source": source,
        "expectedVersion": version,
    }
    if reference is not None:
        body["paymentReference"] = reference
    if note is not None:
        body["note"] = note
    return client.post(f"/admin/users/{user_id}/usage-period/extensions", json=body)


def _link(client: TestClient, parent_id: str, student_id: str) -> None:
    response = client.post(
        "/admin/users/parent-links", json={"parent_id": parent_id, "student_id": student_id}
    )
    assert response.status_code == 200, response.text


def test_an_account_without_a_period_reads_as_none(admin_table: AccountAdminTable) -> None:
    _seed_profile(admin_table, STUDENT, "student")

    response = _client().get(f"/admin/users/{STUDENT}/usage-period")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "userId": STUDENT,
        "role": "student",
        "endsOn": None,
        "state": "none",
        "version": 1,
        "effective": {"endsOn": None, "state": "none", "paidBy": None, "parentId": None},
        "records": [],
        "nextPageToken": None,
    }


def test_a_paid_extension_moves_the_profile_and_keeps_one_record(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]["subscription_tier"] = "basic"
    expected = add_months(_today(), 3).isoformat()

    response = _extend(_client(), STUDENT, amount=3, note="Q1 school term")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["endsOn"], body["state"], body["version"]) == (expected, "active", 2)
    record = body["record"]
    assert {key: record[key] for key in record if key not in {"recordId", "recordedAt"}} == {
        "actorId": "admin-1",
        "kind": "extend",
        "unit": "months",
        "amount": 3,
        "previousEndsOn": None,
        "newEndsOn": expected,
        "source": "paid",
        "paymentReference": "Bank transfer 2026-11-09 #A17",
        "note": "Q1 school term",
        "reason": None,
        "subscriptionTier": "basic",
    }
    profile = admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]
    assert profile["usage_period_ends_at"] == expected
    assert profile["version"] == 2
    (stored,) = _records(admin_table, STUDENT)
    assert stored["SK"] == f"USAGE_PERIOD#{record['recordedAt']}#{record['recordId']}"
    assert stored["entity_type"] == "usage_period_record"
    assert stored["user_id"] == STUDENT


def test_a_second_extension_counts_from_the_end_the_first_one_set(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, PARENT, "parent")
    client = _client()

    first = _extend(client, PARENT, version=1, amount=1).json()
    second = _extend(
        client, PARENT, version=2, unit="days", amount=10, source="gifted", reference=None
    ).json()

    assert second["endsOn"] == (date.fromisoformat(first["endsOn"]) + timedelta(days=10)).isoformat()
    assert second["record"]["previousEndsOn"] == first["endsOn"]
    assert second["record"]["source"] == "gifted"
    assert second["record"]["paymentReference"] is None


def test_changing_the_end_date_states_a_reason_and_keeps_a_record(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _client()
    extended = _extend(client, STUDENT, amount=12).json()
    earlier = (_today() - timedelta(days=1)).isoformat()

    response = client.put(
        f"/admin/users/{STUDENT}/usage-period",
        json={"endsOn": earlier, "reason": "Refunded, ended early", "expectedVersion": 2},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["endsOn"], body["state"], body["version"]) == (earlier, "expired", 3)
    assert body["record"]["kind"] == "set"
    assert body["record"]["reason"] == "Refunded, ended early"
    assert body["record"]["previousEndsOn"] == extended["endsOn"]
    assert body["record"]["unit"] is None and body["record"]["source"] is None
    assert len(_records(admin_table, STUDENT)) == 2


@pytest.mark.parametrize("reason", ["", "   "])
def test_changing_the_end_date_without_a_reason_is_refused(
    admin_table: AccountAdminTable, reason: str
) -> None:
    _seed_profile(admin_table, STUDENT, "student")

    response = _client().put(
        f"/admin/users/{STUDENT}/usage-period",
        json={"endsOn": "2027-01-01", "reason": reason, "expectedVersion": 1},
    )

    assert response.status_code == 422
    assert _records(admin_table, STUDENT) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"reference": None},
        {"reference": "   "},
        {"reference": "x" * 201},
        {"unit": "days"},
        {"amount": 0},
        {"unit": "weeks"},
        {"source": "free"},
    ],
    ids=["paid-without-reference", "blank-reference", "reference-too-long", "paid-by-day",
         "zero", "unknown-unit", "unknown-source"],
)
def test_an_extension_the_rules_do_not_allow_is_refused_and_writes_nothing(
    admin_table: AccountAdminTable, overrides: dict[str, Any]
) -> None:
    _seed_profile(admin_table, STUDENT, "student")

    response = _extend(_client(), STUDENT, **overrides)

    assert response.status_code == 422, response.text
    assert _records(admin_table, STUDENT) == []
    assert "usage_period_ends_at" not in admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]


def test_a_stale_version_is_refused_and_nothing_is_written(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _client()
    _extend(client, STUDENT, version=1)

    response = _extend(client, STUDENT, version=1)

    assert_violation(response, "usage_period_version_conflict")
    assert len(_records(admin_table, STUDENT)) == 1
    assert admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]["version"] == 2


def test_two_administrators_with_the_same_version_only_one_wins(
    admin_table: AccountAdminTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both read version 1 before either writes; the transaction decides, not the pre-check."""
    _seed_profile(admin_table, STUDENT, "student")
    both_read = threading.Barrier(2, timeout=5)
    original = admin_table.get_item

    def get_item(**kwargs: Any) -> dict[str, Any]:
        response = original(**kwargs)
        if kwargs["Key"] == {"PK": f"USER#{STUDENT}", "SK": "PROFILE"}:
            both_read.wait()
        return response

    monkeypatch.setattr(admin_table, "get_item", get_item)
    outcomes: list[str] = []

    def write(source: PeriodSource, reference: str | None) -> None:
        try:
            usage_period.extend(
                STUDENT,
                actor_id=f"admin-{source.value}",
                unit=PeriodUnit.MONTHS,
                amount=1,
                source=source,
                payment_reference=reference,
                note=None,
                expected_version=1,
            )
            outcomes.append("written")
        except usage_period.AccountViolation as exc:
            outcomes.append(exc.code.value)

    threads = [
        threading.Thread(target=write, args=(PeriodSource.PAID, "Receipt 1")),
        threading.Thread(target=write, args=(PeriodSource.GIFTED, None)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ["usage_period_version_conflict", "written"]
    assert len(_records(admin_table, STUDENT)) == 1
    profile = admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]
    assert profile["version"] == 2
    assert profile["usage_period_ends_at"] == add_months(_today(), 1).isoformat()


@pytest.mark.parametrize("role", ["teacher", "admin"])
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("GET", "", None),
        ("POST", "/extensions", {"unit": "months", "amount": 1, "source": "gifted",
                                 "expectedVersion": 1}),
        ("PUT", "", {"endsOn": "2027-01-01", "reason": "fix", "expectedVersion": 1}),
    ],
)
def test_only_students_and_parents_hold_a_period(
    admin_table: AccountAdminTable, role: str, method: str, suffix: str, body: Any
) -> None:
    _seed_profile(admin_table, TEACHER, role)

    response = _client().request(
        method, f"/admin/users/{TEACHER}/usage-period{suffix}", json=body
    )

    assert_violation(response, "usage_period_role_invalid")
    assert _records(admin_table, TEACHER) == []
    assert "usage_period_ends_at" not in admin_table.rows[(f"USER#{TEACHER}", "PROFILE")]


def test_an_account_that_does_not_exist_is_a_404(admin_table: AccountAdminTable) -> None:
    response = _extend(_client(), "nobody")

    assert_violation(response, "account_not_found")
    assert _records(admin_table, "nobody") == []


@pytest.mark.parametrize("role", ["student", "parent", "teacher"])
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", f"/admin/users/{STUDENT}/usage-period", None),
        ("POST", f"/admin/users/{STUDENT}/usage-period/extensions",
         {"unit": "months", "amount": 1, "source": "gifted", "expectedVersion": 1}),
        ("PUT", f"/admin/users/{STUDENT}/usage-period",
         {"endsOn": "2027-01-01", "reason": "fix", "expectedVersion": 1}),
        ("GET", "/admin/usage-periods", None),
    ],
)
def test_nobody_but_an_administrator_reaches_the_console(
    admin_table: AccountAdminTable, role: str, method: str, path: str, body: Any
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = TestClient(_app({"sub": "someone", "role": role, "accountStatus": "active"}))

    response = client.request(method, path, json=body)

    assert response.status_code == 403
    assert _records(admin_table, STUDENT) == []


def test_every_write_leaves_one_admin_audit_event(admin_table: AccountAdminTable) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _client()
    extended = _extend(client, STUDENT).json()
    client.put(
        f"/admin/users/{STUDENT}/usage-period",
        json={"endsOn": "2027-06-30", "reason": "typo", "expectedVersion": 2},
    )

    events = sorted(admin_table.audit_events(), key=lambda event: event["created_at"])
    period_events = [e for e in events if str(e.get("event_type", "")).startswith("usage_period")]

    assert [e["event_type"] for e in period_events] == ["usage_period_extended", "usage_period_set"]
    assert all(e["target_id"] == STUDENT and e["actor_id"] == "admin-1" for e in period_events)
    assert period_events[0]["evidence_reference"] == (
        f"usage-period:none->{extended['endsOn']};record:{extended['record']['recordId']}"
    )


def test_records_are_newest_first_and_page_through(admin_table: AccountAdminTable) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    client = _client()
    for version in range(1, 6):
        assert _extend(client, STUDENT, version=version, unit="days", amount=1,
                       source="gifted", reference=None).status_code == 200

    first = client.get(f"/admin/users/{STUDENT}/usage-period", params={"limit": 2}).json()
    second = client.get(
        f"/admin/users/{STUDENT}/usage-period",
        params={"limit": 2, "pageToken": first["nextPageToken"]},
    ).json()
    third = client.get(
        f"/admin/users/{STUDENT}/usage-period",
        params={"limit": 2, "pageToken": second["nextPageToken"]},
    ).json()

    seen = [r["recordedAt"] for page in (first, second, third) for r in page["records"]]
    assert len(seen) == 5 and seen == sorted(seen, reverse=True)
    assert first["records"][0]["newEndsOn"] == first["endsOn"]


def test_a_page_token_from_another_accounts_records_is_refused(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    _seed_profile(admin_table, PARENT, "parent")
    client = _client()
    for version in (1, 2):
        _extend(client, PARENT, version=version)
    token = client.get(
        f"/admin/users/{PARENT}/usage-period", params={"limit": 1}
    ).json()["nextPageToken"]

    response = client.get(f"/admin/users/{STUDENT}/usage-period", params={"pageToken": token})

    assert_violation(response, "page_token_invalid")


# ---------------------------------------------------------------------------
# A student's effective period, through the relationships
# ---------------------------------------------------------------------------


def _set(client: TestClient, user_id: str, ends_on: date, version: int) -> None:
    response = client.put(
        f"/admin/users/{user_id}/usage-period",
        json={"endsOn": ends_on.isoformat(), "reason": "test", "expectedVersion": version},
    )
    assert response.status_code == 200, response.text


def _effective(client: TestClient) -> dict[str, Any]:
    return client.get(f"/admin/users/{STUDENT}/usage-period").json()["effective"]


def test_a_current_parents_later_period_covers_the_child_until_the_link_is_revoked(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    _seed_profile(admin_table, PARENT, "parent")
    _seed_profile(admin_table, OTHER_PARENT, "parent")
    client = _client()
    own = _today() + timedelta(days=5)
    _set(client, STUDENT, own, 1)

    assert _effective(client) == {
        "endsOn": own.isoformat(), "state": "active", "paidBy": "self", "parentId": None,
    }

    # A parent with a later period, not yet linked, lends nothing.
    _set(client, PARENT, own + timedelta(days=30), 1)
    assert _effective(client)["paidBy"] == "self"

    _link(client, PARENT, STUDENT)
    assert _effective(client) == {
        "endsOn": (own + timedelta(days=30)).isoformat(),
        "state": "active",
        "paidBy": "parent",
        "parentId": PARENT,
    }

    # Two parents: the later of the two.
    _set(client, OTHER_PARENT, own + timedelta(days=60), 1)
    _link(client, OTHER_PARENT, STUDENT)
    assert _effective(client)["parentId"] == OTHER_PARENT

    # The parent extends; the child follows without anything copied onto it.
    _extend(client, PARENT, version=2, amount=6)
    assert _effective(client)["parentId"] == PARENT
    assert "usage_period_ends_at" in admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]
    assert admin_table.rows[(f"USER#{STUDENT}", "PROFILE")]["usage_period_ends_at"] == own.isoformat()

    revoked = client.post(
        "/admin/parent-links/revoke",
        json={"parent_id": PARENT, "student_id": STUDENT, "reason": "test"},
    )
    assert revoked.status_code == 200, revoked.text
    assert _effective(client)["parentId"] == OTHER_PARENT

    client.post(
        "/admin/parent-links/revoke",
        json={"parent_id": OTHER_PARENT, "student_id": STUDENT, "reason": "test"},
    )
    assert _effective(client)["paidBy"] == "self"


def test_a_parents_account_has_no_effective_period_of_its_own(
    admin_table: AccountAdminTable,
) -> None:
    _seed_profile(admin_table, PARENT, "parent")

    body = _client().get(f"/admin/users/{PARENT}/usage-period").json()

    assert body["effective"] is None


# ---------------------------------------------------------------------------
# The account list and the ending-soon list
# ---------------------------------------------------------------------------


def test_the_account_list_shows_each_accounts_own_end_date(admin_table: AccountAdminTable) -> None:
    _seed_profile(admin_table, STUDENT, "student")
    _seed_profile(admin_table, TEACHER, "teacher")
    client = _client()
    _set(client, STUDENT, date(2027, 3, 31), 1)

    rows = {row["userId"]: row for row in client.get("/admin/users").json()["items"]}

    assert rows[STUDENT]["usagePeriodEndsAt"] == "2027-03-31"
    assert rows[TEACHER]["usagePeriodEndsAt"] is None


def test_the_ending_soon_list(admin_table: AccountAdminTable) -> None:
    today = _today()
    seeded = {
        "ends-today": ("student", today),
        "ends-in-14": ("parent", today + timedelta(days=14)),
        "ends-in-15": ("student", today + timedelta(days=15)),
        "ended-30-ago": ("student", today - timedelta(days=30)),
        "ended-31-ago": ("student", today - timedelta(days=31)),
        "teacher-oddly": ("teacher", today),
    }
    for user_id, (role, ends_on) in seeded.items():
        _seed_profile(admin_table, user_id, role)
        admin_table.rows[(f"USER#{user_id}", "PROFILE")]["usage_period_ends_at"] = ends_on.isoformat()
    _seed_profile(admin_table, "no-period", "student")
    _seed_profile(admin_table, STUDENT, "student", account_number="S26-0001")
    client = _client()
    _link(client, "ends-in-14", STUDENT)

    body = client.get("/admin/usage-periods").json()

    assert [(row["userId"], row["state"]) for row in body["items"]] == [
        ("ended-30-ago", "expired"),
        ("ends-today", "active"),
        ("ends-in-14", "active"),
    ]
    parent_row = body["items"][2]
    assert parent_row["role"] == "parent"
    assert parent_row["endsOn"] == (today + timedelta(days=14)).isoformat()
    assert parent_row["children"] == [
        {"userId": STUDENT, "accountNumber": "S26-0001", "name": STUDENT}
    ]
    assert body["items"][0]["children"] == []

    wider = client.get("/admin/usage-periods", params={"endingWithinDays": 15}).json()
    assert "ends-in-15" in [row["userId"] for row in wider["items"]]


# ---------------------------------------------------------------------------
# The records go with the account
# ---------------------------------------------------------------------------



def _record_row(user_id: str) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "USAGE_PERIOD#2026-11-09T10:00:00.000000+00:00#abc",
        "entity_type": usage_period.RECORD_ENTITY_TYPE,
        "user_id": user_id,
        "kind": "extend",
        "new_ends_on": "2026-12-09",
    }


def _run_profile_branch(user_id: str, passes: int) -> Any:
    previous: dict[str, Any] = {}
    result = None
    for _ in range(passes):
        result = account_deletion_service._account_profile_branch(
            command={"user_id": user_id, "generation": 7}, previous=previous
        )
        previous = {"cursor": result.cursor, "debt_counts": result.debt_counts,
                    "epoch": result.epoch}
    return result


def _deletion_world(fence_status: str) -> FakeTable:
    """The shared double, the deleting account's fence, and two accounts' records.

    The real `delete_owned_row` runs here, fenced transaction and all: the delete
    holds only while the fence says this deletion, at this generation, is pending.
    """
    table = FakeTable()
    table.seed(
        {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE", "status": fence_status, "generation": 7},
        _record_row(STUDENT),
        _record_row(PARENT),
    )
    return table


def test_account_deletion_clears_the_usage_period_records(fake_table: FakeTable) -> None:
    table = _deletion_world("deletion_pending")
    db_table.install(table)

    result = _run_profile_branch(STUDENT, passes=4)

    assert result is not None and result.status == "complete"
    remaining = {key for key in table.rows if key[1].startswith(usage_period.RECORD_SK_PREFIX)}
    assert remaining == {(f"USER#{PARENT}", _record_row(PARENT)["SK"])}


def test_a_record_is_not_deleted_behind_a_fence_that_is_not_this_deletions(
    fake_table: FakeTable,
) -> None:
    """Negative control: the delete above held because the fence allowed it."""
    table = _deletion_world("active")
    db_table.install(table)

    with pytest.raises(
        account_deletion_repo.AccountDeletionConflict, match="conditional"
    ):
        _run_profile_branch(STUDENT, passes=1)

    assert (f"USER#{STUDENT}", _record_row(STUDENT)["SK"]) in table.rows
