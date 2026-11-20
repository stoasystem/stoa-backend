"""#482: a text answer and an online classroom are two weekly allowances.

The student chooses how a teacher helps (#480). Each way has its own figure a
Zurich week and its own counter, so spending one never uses up the other:

- `teacher_supported`: two text answers, no classroom;
- `online_classroom` (which replaces `family`): two text answers and two
  classrooms, for one child;
- a student with no paid plan has the figures they were assigned: seven text
  answers and two classrooms unless an administrator set otherwise.

A paid plan decides both figures: a `teacher_supported` child does not get the
assigned classroom figure through the back door.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from fakes.dynamodb import FakeTable
from stoa.models.allowance import LOCKED_BUDGETS, TeacherSupportScope
from stoa.models.billing import BillingPlanId, CheckoutIntent, PurchasablePlanId
from stoa.services import allowance_service
from stoa.services import teacher_support_allowance_service as service

from test_teacher_support_allowances import AtomicSupportTable, _case_committer, _grant
from test_teacher_support_allowances import grants as grants  # noqa: F401 - the fixture
from test_teacher_help_weekly_allowance_read import (  # noqa: F401 - fixtures
    NEXT_MONDAY,
    _conversation,
    _student,
    _usage_period_active,
)
from test_teacher_help_weekly_allowance_read import table as _route_table
from test_teacher_help_weekly_allowance_read import STUDENT as ROUTE_STUDENT

# Re-exported under a name of its own, as `test_assigned_teacher_support.py`
# does: `table` is the name of every local table here.
route_table = _route_table


NOW = datetime(2026, 3, 25, 12, tzinfo=timezone.utc)


# --- The plans --------------------------------------------------------------


def test_family_is_gone_and_online_classroom_is_a_plan_one_can_buy() -> None:
    assert "family" not in {plan.value for plan in BillingPlanId}
    assert "family" not in {plan.value for plan in PurchasablePlanId}
    assert BillingPlanId("online_classroom") is BillingPlanId.ONLINE_CLASSROOM
    assert PurchasablePlanId("online_classroom") is PurchasablePlanId.ONLINE_CLASSROOM
    assert {scope.value for scope in TeacherSupportScope} == {"none", "per_beneficiary"}


def test_each_plan_has_a_text_figure_and_a_classroom_figure() -> None:
    def figures(plan: BillingPlanId) -> tuple[int, int, int, int, str]:
        budget = allowance_service.plan_allowance_budget(plan, allowance_version=1)
        return (
            budget.input_tokens,
            budget.output_tokens,
            budget.teacher_support_text_cases,
            budget.teacher_support_classroom_cases,
            budget.teacher_support_scope.value,
        )

    assert figures(BillingPlanId.FREE_TRIAL) == (50_000, 10_000, 0, 0, "none")
    assert figures(BillingPlanId.STUDENT) == (500_000, 100_000, 0, 0, "none")
    assert figures(BillingPlanId.TEACHER_SUPPORTED) == (
        1_000_000, 200_000, 2, 0, "per_beneficiary"
    )
    assert figures(BillingPlanId.ONLINE_CLASSROOM) == (
        1_000_000, 200_000, 2, 2, "per_beneficiary"
    )
    assert set(LOCKED_BUDGETS) == set(BillingPlanId)


def test_the_classroom_plan_is_bought_for_one_child() -> None:
    def intent(*children: str) -> CheckoutIntent:
        return CheckoutIntent.model_validate(
            {
                "commandId": "command-1",
                "parentId": "parent-1",
                "idempotencyKey": "key-1",
                "planId": "online_classroom",
                "beneficiaryIds": list(children),
                "priceCatalogVersion": 1,
                "planVersion": 1,
                "createdAt": NOW,
            }
        )

    assert intent("child-1").beneficiary_ids == ("child-1",)
    with pytest.raises(ValidationError):
        intent("child-1", "child-2")


# --- A paid plan ------------------------------------------------------------


def _admit(
    table: AtomicSupportTable,
    case_id: str,
    *,
    mode: str,
    student_id: str = "student-1",
):
    return service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="conversation",
        beneficiary_id=student_id,
        mode=mode,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="conversation", case_id=case_id, beneficiary_id=student_id
        ),
        table=table,
    )


def test_the_classroom_plan_spends_text_and_classroom_apart(grants) -> None:
    grants["student-1"] = _grant("student-1", plan_id="online_classroom")
    table = AtomicSupportTable()

    text = [_admit(table, f"text-{index}", mode="text") for index in range(3)]
    classroom = [_admit(table, f"room-{index}", mode="classroom") for index in range(3)]

    assert [result.disposition.value for result in text] == [
        "admitted", "admitted", "limit_exceeded"
    ]
    assert [result.disposition.value for result in classroom] == [
        "admitted", "admitted", "limit_exceeded"
    ]
    counters = table.support_rows("teacher_support_counter")
    assert sorted(counter["admitted_cases"] for counter in counters) == [2, 2]
    assert len({counter["support_scope_id"] for counter in counters}) == 2


def test_each_receipt_says_which_allowance_it_was_spent_from(grants) -> None:
    grants["student-1"] = _grant("student-1", plan_id="online_classroom")
    table = AtomicSupportTable()

    _admit(table, "text-1", mode="text")
    _admit(table, "room-1", mode="classroom")

    receipts = table.support_rows("teacher_support_admission")
    assert sorted(receipt["mode"] for receipt in receipts) == ["classroom", "text"]


def test_teacher_supported_has_no_classroom(grants) -> None:
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()

    classroom = _admit(table, "room-1", mode="classroom")
    text = _admit(table, "text-1", mode="text")

    assert classroom.disposition.value == "plan_denied"
    assert text.disposition.value == "admitted"


def test_a_paid_plan_without_classroom_does_not_fall_back_to_the_assigned_one(
    grants,
) -> None:
    """The plan decides both figures; the assigned two classrooms are not a back door."""
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()

    standing = service.get_student_teacher_support_standing(
        beneficiary_id="student-1", observed_at=NOW, table=table
    )

    assert standing["classroom"] == {
        "canRequest": False,
        "blockedReason": "teacher_support_not_included",
        "remainingCases": 0,
        "weeklyCases": 0,
        "resetsAt": None,
    }
    assert standing["text"]["weeklyCases"] == 2


def test_the_projection_carries_the_classroom_figures(grants) -> None:
    grants["student-1"] = _grant("student-1", plan_id="online_classroom")
    table = AtomicSupportTable()
    _admit(table, "text-1", mode="text")
    _admit(table, "room-1", mode="classroom")
    _admit(table, "room-2", mode="classroom")

    projection = service.get_teacher_support_projection(
        beneficiary_id="student-1", observed_at=NOW, table=table
    )

    assert projection == {
        "schemaVersion": "teacher_support_projection.v1",
        "planId": "online_classroom",
        "supportScope": "per_beneficiary",
        "weekIdentity": "2026-W13",
        "admittedCases": 1,
        "remainingCases": 1,
        "limit": 2,
        "classroom": {"admittedCases": 2, "remainingCases": 0, "limit": 2},
    }


def test_an_unknown_mode_is_refused_before_anything_is_read(grants) -> None:
    grants["student-1"] = _grant("student-1", plan_id="online_classroom")

    with pytest.raises(ValueError):
        _admit(AtomicSupportTable(), "x-1", mode="video")


# --- An assigned student ----------------------------------------------------


ASSIGNED = "student-assigned-modes"


@pytest.fixture
def assigned(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "user_id": ASSIGNED,
        "role": "student",
        "account_status": "active",
        # `seed_fenced_rows` stores the profile at version 1 when there is no grant.
        "version": Decimal("1"),
    }
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(profile)
    )
    monkeypatch.setattr(
        service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )


def _assigned_row(table: AtomicSupportTable, **figures: int) -> None:
    table.items[(f"USER#{ASSIGNED}", service.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{ASSIGNED}",
        "SK": service.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "teacher_support_assigned_allowance",
        "schema_version": service.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
        "state_version": Decimal(1),
        **{name: Decimal(value) for name, value in figures.items()},
    }


def test_an_assigned_student_has_two_classrooms_a_week_beside_seven_texts(assigned) -> None:
    table = AtomicSupportTable()

    rooms = [
        _admit(table, f"room-{index}", mode="classroom", student_id=ASSIGNED)
        for index in range(3)
    ]
    texts = [
        _admit(table, f"text-{index}", mode="text", student_id=ASSIGNED)
        for index in range(7)
    ]

    assert service.ASSIGNED_WEEKLY_CLASSROOM_CASES == 2
    assert [result.disposition.value for result in rooms] == [
        "admitted", "admitted", "limit_exceeded"
    ]
    assert [result.disposition.value for result in texts] == ["admitted"] * 7


def test_the_text_counter_keeps_the_scope_it_had_before_the_split(assigned) -> None:
    """A week already under way goes on counting on the row it was counting on."""
    table = AtomicSupportTable()

    text = _admit(table, "text-1", mode="text", student_id=ASSIGNED)

    assert text.admission is not None
    assert text.admission.support_scope_id == service._domain_digest(
        b"stoa.teacher-support.scope.v1", service.SUPPORT_SOURCE_ASSIGNED, ASSIGNED
    )


def test_an_assigned_classroom_figure_of_zero_takes_only_the_classroom_away(
    assigned,
) -> None:
    table = AtomicSupportTable()
    _assigned_row(table, weekly_cases=7, weekly_classroom_cases=0)

    room = _admit(table, "room-1", mode="classroom", student_id=ASSIGNED)
    text = _admit(table, "text-1", mode="text", student_id=ASSIGNED)

    assert room.disposition.value == "plan_denied"
    assert text.disposition.value == "admitted"


def test_a_row_written_before_the_split_reads_the_classroom_default(assigned) -> None:
    table = AtomicSupportTable()
    _assigned_row(table, weekly_cases=3)

    rooms = [
        _admit(table, f"room-{index}", mode="classroom", student_id=ASSIGNED)
        for index in range(3)
    ]

    assert [result.disposition.value for result in rooms] == [
        "admitted", "admitted", "limit_exceeded"
    ]


def test_a_classroom_figure_changed_between_read_and_write_is_not_spent_against(
    assigned,
) -> None:
    table = AtomicSupportTable()
    _assigned_row(table, weekly_cases=7, weekly_classroom_cases=2)
    calls: list[tuple[dict[str, Any], ...]] = []

    service.admit_teacher_support_case(
        support_case_id="room-fenced",
        case_kind="conversation",
        beneficiary_id=ASSIGNED,
        mode="classroom",
        observed_at=NOW,
        persist_case=_case_committer(
            table,
            kind="conversation",
            case_id="room-fenced",
            beneficiary_id=ASSIGNED,
            calls=calls,
        ),
        table=table,
    )

    fence = next(
        operation["ConditionCheck"]
        for operation in calls[0]
        if "ConditionCheck" in operation
        and operation["ConditionCheck"]["Key"]["SK"] == service.ASSIGNED_ALLOWANCE_SK
    )
    assert "#version=:version" in fence["ConditionExpression"]
    assert fence["ExpressionAttributeValues"][":version"] == 1


def test_the_administrator_sets_the_classroom_figure_beside_the_text_one() -> None:
    table = FakeTable()

    written = service.set_assigned_weekly_cases(
        ASSIGNED, 5, weekly_classroom_cases=1, actor_id="admin-1", now=NOW, table=table
    )
    read = service.read_assigned_weekly_cases(ASSIGNED, table=table)

    assert written.state_version == 1
    assert (read.weekly_cases, read.weekly_classroom_cases) == (5, 1)


def test_setting_only_the_text_figure_keeps_the_classroom_figure() -> None:
    table = FakeTable()
    service.set_assigned_weekly_cases(
        ASSIGNED, 5, weekly_classroom_cases=1, actor_id="admin-1", now=NOW, table=table
    )

    service.set_assigned_weekly_cases(ASSIGNED, 9, actor_id="admin-1", now=NOW, table=table)
    read = service.read_assigned_weekly_cases(ASSIGNED, table=table)

    assert (read.weekly_cases, read.weekly_classroom_cases) == (9, 1)


def test_nobody_has_set_it_reads_the_classroom_default() -> None:
    read = service.read_assigned_weekly_cases(ASSIGNED, table=FakeTable())

    assert read.weekly_classroom_cases == service.ASSIGNED_WEEKLY_CLASSROOM_CASES


@pytest.mark.parametrize("cases", [-1, service.ASSIGNED_WEEKLY_CASES_MAXIMUM + 1, True])
def test_a_classroom_figure_out_of_range_is_not_written(cases: object) -> None:
    with pytest.raises(ValueError):
        service.set_assigned_weekly_cases(
            ASSIGNED, 3, weekly_classroom_cases=cases, actor_id="a", now=NOW,  # type: ignore[arg-type]
            table=FakeTable(),
        )


# --- What the student reads and what the request route does -----------------


def _ask(table: FakeTable, conversation_id: str, mode: str):
    _conversation(table, conversation_id)
    return _student().post(
        "/teacher-help/request",
        json={"conversationId": conversation_id, "message": "Step 2?", "mode": mode},
    )


def _standing() -> dict:
    response = _student().get("/teacher-help/availability")
    assert response.status_code == 200, response.text
    return response.json()["teacherSupport"]


def _route_figures(table: FakeTable, **figures: int) -> None:
    table.seed(
        {
            "PK": f"USER#{ROUTE_STUDENT}",
            "SK": service.ASSIGNED_ALLOWANCE_SK,
            "entity_type": "teacher_support_assigned_allowance",
            "schema_version": service.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
            "state_version": Decimal(1),
            **{name: Decimal(value) for name, value in figures.items()},
        }
    )


def test_the_student_reads_both_ways_and_the_old_fields_mean_text(route_table) -> None:
    standing = _standing()

    text = {
        "canRequest": True,
        "blockedReason": None,
        "remainingCases": 7,
        "weeklyCases": 7,
        "resetsAt": NEXT_MONDAY,
    }
    assert standing == {
        **text,
        "text": text,
        "classroom": {
            "canRequest": True,
            "blockedReason": None,
            "remainingCases": 2,
            "weeklyCases": 2,
            "resetsAt": NEXT_MONDAY,
        },
    }


def test_a_classroom_request_spends_a_classroom_and_no_text(route_table) -> None:
    assert _ask(route_table, "conv-482-a", "classroom").status_code == 200

    standing = _standing()

    assert standing["classroom"]["remainingCases"] == 1
    assert standing["text"]["remainingCases"] == 7


def test_spent_classrooms_are_told_apart_from_a_plan_without_them(route_table) -> None:
    _route_figures(route_table, weekly_cases=7, weekly_classroom_cases=1)
    assert _ask(route_table, "conv-482-a", "classroom").status_code == 200

    standing = _standing()

    assert standing["classroom"]["blockedReason"] == "teacher_support_allowance_exhausted"
    assert standing["classroom"]["resetsAt"] == NEXT_MONDAY
    assert standing["canRequest"] is True
    refused = _ask(route_table, "conv-482-b", "classroom")
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "teacher_support_allowance_exhausted"
    # The text way is untouched.
    assert _ask(route_table, "conv-482-c", "text").status_code == 200


def test_a_classroom_the_student_does_not_have_is_refused_as_not_included(route_table) -> None:
    _route_figures(route_table, weekly_cases=7, weekly_classroom_cases=0)

    standing = _standing()
    refused = _ask(route_table, "conv-482-a", "classroom")

    assert standing["classroom"] == {
        "canRequest": False,
        "blockedReason": "teacher_support_not_included",
        "remainingCases": 0,
        "weeklyCases": 0,
        "resetsAt": None,
    }
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "teacher_support_not_included"
    assert ("CONV#conv-482-a", "HELP") not in route_table.rows
