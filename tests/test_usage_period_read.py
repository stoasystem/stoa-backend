"""#343: students and parents read their usage period.

Step 2 of #239 (the「#239 形状定完」shape, decision 14). The student reads their
effective period through `GET /students/me/entitlement`; a parent reads their own
and each child's through `GET /parents/me/usage-period`. Both carry the renewal
contact address. Refusing a question or a teacher request at expiry is #344's
(`tests/test_usage_period_enforcement.py`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import Settings, settings as app_settings
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import parents as parent_routes, students as student_routes
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import (
    account_operations_service,
    current_relationship,
    entitlement_service,
    usage_period,
)

STUDENT = "student-1"
PARENT = "parent-1"
OTHER_PARENT = "parent-2"

# 10:00 in Zurich on 9 November 2026.
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 9)


def _day(offset: int, *, today: date = TODAY) -> str:
    return (today + timedelta(days=offset)).isoformat()


def _profile(table, user_id: str, role: str, ends_on: str | None = None, **extra: Any) -> None:
    item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@example.ch",
        "subscription_tier": "student" if role == "student" else "free_trial",
        "version": 1,
        **extra,
    }
    if ends_on is not None:
        item[usage_period.PROFILE_FIELD] = ends_on
    table.put_item(Item=item)


def _period(student_id: str = STUDENT, *, now: datetime = NOW) -> dict[str, Any]:
    return entitlement_service.resolve_student_entitlement(
        student_id, settings=Settings(), now=now
    )["usagePeriod"]


# ---------------------------------------------------------------------------
# The student's effective period, in the entitlement
# ---------------------------------------------------------------------------


def test_a_student_paying_for_themself(fake_table) -> None:
    _profile(fake_table, STUDENT, "student", "2026-12-31")

    assert _period() == {
        "endsAt": "2026-12-31",
        "state": "active",
        "daysLeft": 52,
        "paidBy": "self",
        "payerId": STUDENT,
    }


def test_a_student_a_parent_pays_for(fake_table, link_rows) -> None:
    _profile(fake_table, STUDENT, "student")
    _profile(fake_table, PARENT, "parent", "2027-01-15")
    link_rows.link(PARENT, STUDENT)

    assert _period() == {
        "endsAt": "2027-01-15",
        "state": "active",
        "daysLeft": 67,
        "paidBy": "parent",
        "payerId": PARENT,
    }


def test_of_two_parents_the_later_period_wins(fake_table, link_rows) -> None:
    _profile(fake_table, STUDENT, "student", "2026-11-30")
    _profile(fake_table, PARENT, "parent", "2026-12-15")
    _profile(fake_table, OTHER_PARENT, "parent", "2027-02-01")
    link_rows.link(PARENT, STUDENT)
    link_rows.link(OTHER_PARENT, STUDENT)

    period = _period()

    assert (period["endsAt"], period["paidBy"], period["payerId"]) == (
        "2027-02-01",
        "parent",
        OTHER_PARENT,
    )


def test_the_students_own_period_wins_a_tie(fake_table, link_rows) -> None:
    _profile(fake_table, STUDENT, "student", "2026-12-15")
    _profile(fake_table, PARENT, "parent", "2026-12-15")
    link_rows.link(PARENT, STUDENT)

    assert (_period()["paidBy"], _period()["payerId"]) == ("self", STUDENT)


def test_a_student_without_any_period(fake_table) -> None:
    _profile(fake_table, STUDENT, "student")

    assert _period() == {
        "endsAt": None,
        "state": "none",
        "daysLeft": None,
        "paidBy": None,
        "payerId": None,
    }


def test_an_expired_period(fake_table) -> None:
    _profile(fake_table, STUDENT, "student", "2026-11-08")

    assert _period() == {
        "endsAt": "2026-11-08",
        "state": "expired",
        "daysLeft": 0,
        "paidBy": "self",
        "payerId": STUDENT,
    }


def test_the_end_day_itself_is_still_active(fake_table) -> None:
    _profile(fake_table, STUDENT, "student", "2026-11-09")

    period = _period()

    assert (period["state"], period["daysLeft"]) == ("active", 0)


def test_the_end_day_ends_at_midnight_in_zurich_not_utc(fake_table) -> None:
    _profile(fake_table, STUDENT, "student", "2026-11-09")

    # 23:30 UTC on the 9th is 00:30 on the 10th in Zurich: the period is over.
    late = datetime(2026, 11, 9, 23, 30, tzinfo=UTC)
    period = _period(now=late)

    assert (period["state"], period["daysLeft"]) == ("expired", 0)
    # 22:59 UTC is 23:59 in Zurich, still the last day.
    assert _period(now=datetime(2026, 11, 9, 22, 59, tzinfo=UTC))["state"] == "active"


@pytest.mark.parametrize("offset,days_left", [(8, 8), (7, 7), (1, 1)])
def test_days_left_counts_the_zurich_days_after_today(fake_table, offset, days_left) -> None:
    _profile(fake_table, STUDENT, "student", _day(offset))

    assert _period()["daysLeft"] == days_left


@pytest.mark.parametrize(
    "link",
    [
        {"status": "pending"},
        {"status": "revoked"},
        {"student_side_status": "revoked"},
    ],
)
def test_a_relationship_that_is_not_current_lends_no_period(fake_table, link_rows, link) -> None:
    _profile(fake_table, STUDENT, "student")
    _profile(fake_table, PARENT, "parent", "2027-01-15")
    link_rows.link(PARENT, STUDENT, **link)

    assert _period()["state"] == "none"


def test_an_expired_period_allows_no_new_usage(fake_table) -> None:
    """`newUsageAllowed` is the period alone; admission refuses on it (#344)."""
    _profile(fake_table, STUDENT, "student", "2026-10-01")

    entitlement = entitlement_service.resolve_student_entitlement(
        STUDENT, settings=Settings(), now=NOW
    )

    assert entitlement["usagePeriod"]["state"] == "expired"
    assert entitlement["newUsageAllowed"] is False


def test_the_period_is_judged_in_the_same_relationship_read(
    fake_table, link_rows, monkeypatch
) -> None:
    """Billing and the period share one `parents_of` and the parent of record's profile."""
    _profile(fake_table, STUDENT, "student")
    _profile(fake_table, PARENT, "parent", "2027-01-15")
    link_rows.link(PARENT, STUDENT)
    asked: list[str] = []
    judge = current_relationship.parents_of

    def counting(student_id, **kwargs):
        asked.append(student_id)
        return judge(student_id, **kwargs)

    monkeypatch.setattr(current_relationship, "parents_of", counting)

    assert _period()["payerId"] == PARENT
    assert asked == [STUDENT]


# ---------------------------------------------------------------------------
# A parent's view of a shared child's entitlement
# ---------------------------------------------------------------------------


def _entitlement_paid_by(payer_id: str) -> dict[str, Any]:
    return {
        "parentId": None,
        "usagePeriod": {
            "endsAt": "2027-01-15",
            "state": "active",
            "daysLeft": 67,
            "paidBy": "parent",
            "payerId": payer_id,
        },
    }


def test_a_parent_is_not_told_which_other_parent_pays() -> None:
    seen = entitlement_service.for_parent_viewer(_entitlement_paid_by(OTHER_PARENT), PARENT)

    assert seen["usagePeriod"] == {
        "endsAt": "2027-01-15",
        "state": "active",
        "daysLeft": 67,
        "paidBy": "parent",
        "payerId": None,
    }


def test_a_parent_who_pays_still_sees_themself() -> None:
    seen = entitlement_service.for_parent_viewer(_entitlement_paid_by(PARENT), PARENT)

    assert seen["usagePeriod"]["payerId"] == PARENT


def test_the_parents_account_operations_go_through_the_viewer_projection(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        current_relationship,
        "children_of",
        lambda parent_id, **_k: [
            current_relationship.Verdict(
                current_relationship.Standing.CURRENT, parent_id, STUDENT, relationship="child"
            )
        ],
    )
    monkeypatch.setattr(
        account_operations_service,
        "_child_operation_row",
        lambda *_a, **_k: {"studentId": STUDENT, "entitlement": _entitlement_paid_by(OTHER_PARENT)},
    )

    rows = account_operations_service._current_child_operation_rows(
        PARENT, settings=Settings(), day=None
    )

    assert rows[0]["entitlement"]["usagePeriod"]["payerId"] is None
    assert OTHER_PARENT not in repr(rows)


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


def _actor(role: CanonicalRole, user_id: str) -> Actor:
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )


def _client(actor: Actor) -> TestClient:
    app = FastAPI()
    app.include_router(student_routes.router, prefix="/students")
    app.include_router(parent_routes.router, prefix="/parents")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _today() -> date:
    return usage_period.zurich_today()


def test_the_student_route_says_self_or_parent_but_never_who(fake_table, link_rows) -> None:
    ends = _day(6, today=_today())
    _profile(fake_table, STUDENT, "student", name="Mia")
    _profile(fake_table, PARENT, "parent", ends)
    link_rows.link(PARENT, STUDENT)

    response = _client(_actor(CanonicalRole.STUDENT, STUDENT)).get("/students/me/entitlement")

    assert response.status_code == 200
    body = response.json()
    assert body["usagePeriod"] == {
        "endsAt": ends,
        "state": "active",
        "daysLeft": 6,
        "paidBy": "parent",
    }
    assert body["renewalContactEmail"] == "info@stoaedu.ch"
    assert "freeTrialActive" not in body and "freeTrialEndsAt" not in body
    assert PARENT not in response.text


def test_the_student_route_without_a_period(fake_table) -> None:
    _profile(fake_table, STUDENT, "student")

    body = _client(_actor(CanonicalRole.STUDENT, STUDENT)).get("/students/me/entitlement").json()

    assert body["usagePeriod"] == {
        "endsAt": None,
        "state": "none",
        "daysLeft": None,
        "paidBy": None,
    }


def test_the_renewal_address_comes_from_the_configuration(fake_table, monkeypatch) -> None:
    _profile(fake_table, STUDENT, "student")
    _profile(fake_table, PARENT, "parent")
    monkeypatch.setattr(app_settings, "renewal_contact_email", "renew@example.ch")

    student = _client(_actor(CanonicalRole.STUDENT, STUDENT)).get("/students/me/entitlement")

    assert student.json()["renewalContactEmail"] == "renew@example.ch"


def _family(fake_table, link_rows) -> dict[str, str]:
    """A parent with four children, each covered a different way.

    - `student-you`: the viewer's period is the latest.
    - `student-self`: the child's own period is later than the viewer's.
    - `student-other`: another parent's later period covers them.
    - `student-shared`: no period of their own; their other parent has none
      either, so the viewer's covers them.
    And one pending child, who is not listed.
    """
    today = _today()
    dates = {
        "parent": _day(10, today=today),
        "self": _day(40, today=today),
        "other": _day(90, today=today),
    }
    _profile(fake_table, PARENT, "parent", dates["parent"])
    _profile(fake_table, OTHER_PARENT, "parent", dates["other"], name="Hidden Parent")
    _profile(fake_table, "student-you", "student", _day(-3, today=today), name="Ana")
    _profile(fake_table, "student-self", "student", dates["self"], name="Ben")
    _profile(fake_table, "student-other", "student", name="Cleo")
    _profile(fake_table, "student-shared", "student", name="Dev")
    _profile(fake_table, "student-pending", "student", name="Eve")
    for child in ("student-you", "student-self", "student-other"):
        link_rows.link(PARENT, child)
    link_rows.link(OTHER_PARENT, "student-other")
    link_rows.link("parent-3", "student-shared")  # a parent who is not the viewer
    link_rows.link(PARENT, "student-shared")
    link_rows.link(PARENT, "student-pending", status="pending")
    return dates


def test_a_parent_reads_their_own_period_and_each_childs(fake_table, link_rows) -> None:
    dates = _family(fake_table, link_rows)
    # The viewer's own period does not reach a child they are not related to.
    _profile(fake_table, "parent-3", "parent")

    response = _client(_actor(CanonicalRole.PARENT, PARENT)).get("/parents/me/usage-period")

    assert response.status_code == 200
    body = response.json()
    assert body["own"] == {"endsAt": dates["parent"], "state": "active", "daysLeft": 10}
    assert body["renewalContactEmail"] == "info@stoaedu.ch"
    children = {child["studentId"]: child for child in body["children"]}
    assert set(children) == {"student-you", "student-self", "student-other", "student-shared"}
    assert children["student-you"] == {
        "studentId": "student-you",
        "name": "Ana",
        "endsAt": dates["parent"],
        "state": "active",
        "paidBy": "you",
    }
    assert children["student-self"] == {
        "studentId": "student-self",
        "name": "Ben",
        "endsAt": dates["self"],
        "state": "active",
        "paidBy": "self",
    }
    assert children["student-other"] == {
        "studentId": "student-other",
        "name": "Cleo",
        "endsAt": dates["other"],
        "state": "active",
        "paidBy": "other_parent",
    }
    # The viewer's period covers this child too.
    assert children["student-shared"]["paidBy"] == "you"
    # The other parent is never named.
    assert OTHER_PARENT not in response.text and "Hidden Parent" not in response.text


def test_a_parent_and_children_without_any_period(fake_table, link_rows) -> None:
    _profile(fake_table, PARENT, "parent")
    _profile(fake_table, STUDENT, "student", name="Mia")
    link_rows.link(PARENT, STUDENT)

    body = _client(_actor(CanonicalRole.PARENT, PARENT)).get("/parents/me/usage-period").json()

    assert body == {
        "own": {"endsAt": None, "state": "none", "daysLeft": None},
        "children": [
            {
                "studentId": STUDENT,
                "name": "Mia",
                "endsAt": None,
                "state": "none",
                "paidBy": None,
            }
        ],
        "renewalContactEmail": "info@stoaedu.ch",
    }


def test_a_parent_whose_period_ended(fake_table, link_rows) -> None:
    ended = _day(-1, today=_today())
    _profile(fake_table, PARENT, "parent", ended)
    _profile(fake_table, STUDENT, "student", name="Mia")
    link_rows.link(PARENT, STUDENT)

    body = _client(_actor(CanonicalRole.PARENT, PARENT)).get("/parents/me/usage-period").json()

    assert body["own"] == {"endsAt": ended, "state": "expired", "daysLeft": 0}
    assert body["children"][0]["state"] == "expired"
    assert body["children"][0]["paidBy"] == "you"


def test_another_parent_with_the_same_end_day_is_not_named(fake_table, link_rows) -> None:
    ends = _day(20, today=_today())
    _profile(fake_table, PARENT, "parent", ends)
    _profile(fake_table, "parent-0", "parent", ends)  # sorts first among the parents
    _profile(fake_table, STUDENT, "student", name="Mia")
    link_rows.link(PARENT, STUDENT)
    link_rows.link("parent-0", STUDENT)

    body = _client(_actor(CanonicalRole.PARENT, PARENT)).get("/parents/me/usage-period").json()

    assert body["children"][0]["paidBy"] == "you"


def test_the_parent_route_is_not_frozen_with_billing(fake_table) -> None:
    """Billing stays frozen (card 007); the period is offline and stays readable."""
    from stoa.routers import billing

    assert billing.BILLING_AND_SUBSCRIPTION_ENABLED is False
    _profile(fake_table, PARENT, "parent")

    response = _client(_actor(CanonicalRole.PARENT, PARENT)).get("/parents/me/usage-period")

    assert response.status_code == 200


@pytest.mark.parametrize("role,user_id", [(CanonicalRole.STUDENT, STUDENT)])
def test_only_a_parent_reads_the_parent_route(fake_table, role, user_id) -> None:
    _profile(fake_table, user_id, role.value)

    response = _client(_actor(role, user_id)).get("/parents/me/usage-period")

    assert response.status_code == 403
