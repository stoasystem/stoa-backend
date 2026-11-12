"""#385: an agent reads, extends and sets a usage period (#239) through an operator call."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from test_operator_calls import (
    _assert_no_secrets,
    _audit_rows,
    _business_rows_added,
    _call,
    _rows,
    _seed_account,
)

from stoa.operator_calls import catalog
from stoa.services import usage_period


PAYMENT = "Invoice 2026-114"
REASON = "Entered the wrong month on the 3rd."


def _today() -> date:
    return usage_period.zurich_today(None)


def _in(days: int) -> str:
    return (_today() + timedelta(days=days)).isoformat()


def _records(table, user_id: str) -> list[dict[str, Any]]:
    return [
        row
        for (pk, sk), row in table.rows.items()
        if pk == f"USER#{user_id}" and sk.startswith(usage_period.RECORD_SK_PREFIX)
    ]


def _account_events(table, user_id: str) -> list[dict[str, Any]]:
    return [
        row for (pk, _sk), row in table.rows.items() if pk == f"SECURITY_AUDIT#{user_id}"
    ]


def _extend(number: str, *, dry: bool, **fields: Any) -> dict:
    arguments: dict[str, Any] = {
        "accountNumber": number,
        "unit": "months",
        "amount": 1,
        "source": "paid",
        "paymentReference": PAYMENT,
        "dryRun": dry,
    }
    arguments.update(fields)
    return _call("extend_usage_period", arguments)


def _set(number: str, ends_on: str, *, dry: bool, **fields: Any) -> dict:
    arguments: dict[str, Any] = {
        "accountNumber": number,
        "endsOn": ends_on,
        "reason": REASON,
        "dryRun": dry,
    }
    arguments.update(fields)
    return _call("set_usage_period", arguments)


@pytest.fixture
def family(fake_table, link_rows):
    """A parent paying for two children; one child also holds a longer period of its own."""
    _seed_account(
        fake_table, "parent-1", "parent", "P26-0001", usage_period_ends_at=_in(10), version=3
    )
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    _seed_account(
        fake_table, "student-2", "student", "S26-0002", usage_period_ends_at=_in(200)
    )
    link_rows.link("parent-1", "student-1")
    link_rows.link("parent-1", "student-2")
    return fake_table


# -- the catalog ----------------------------------------------------------------------


def test_the_three_operations_say_what_they_do() -> None:
    read = catalog.OPERATIONS_BY_NAME["get_usage_period"]
    assert read.effect is catalog.Effect.READ
    for name in ("extend_usage_period", "set_usage_period"):
        spec = catalog.OPERATIONS_BY_NAME[name]
        assert spec.effect is catalog.Effect.WRITE
        assert spec.description.startswith("Changes data.")
        assert "confirm with the person" in spec.description
        assert "dryRun=true first" in spec.description
        assert "expectedVersion" in spec.description
        assert spec.destructive is (name == "set_usage_period")


def test_the_catalog_speaks_the_services_vocabulary() -> None:
    schema = catalog.ExtendUsagePeriodArguments.model_json_schema()["properties"]
    assert set(schema["unit"]["enum"]) == {unit.value for unit in usage_period.PeriodUnit}
    assert set(schema["source"]["enum"]) == {
        source.value for source in usage_period.PeriodSource
    }
    assert (
        schema["paymentReference"]["anyOf"][0]["maxLength"]
        == usage_period.PAYMENT_REFERENCE_MAX_LENGTH
    )


# -- get_usage_period ------------------------------------------------------------------


def test_reading_a_parent_shows_its_period_and_the_children_it_covers(family) -> None:
    before = _rows(family)

    answer = _call("get_usage_period", {"accountNumber": "P26-0001"})

    result = answer["result"]
    assert result["accountNumber"] == "P26-0001"
    assert result["role"] == "parent"
    assert result["endsOn"] == _in(10)
    assert result["state"] == "active"
    assert result["version"] == 3
    covered = {child["accountNumber"]: child for child in result["students"]}
    assert covered["S26-0001"]["effective"] == {
        "endsOn": _in(10),
        "state": "active",
        "paidBy": "parent",
        "parentId": "parent-1",
    }
    # The child's own longer period wins; the parent's does not reach it.
    assert covered["S26-0002"]["effective"]["paidBy"] == "self"
    assert result["records"] == []
    assert _business_rows_added(family, before) == set()
    (row,) = _audit_rows(family)
    assert row["action"] == "get_usage_period"
    assert row["target_id"] == "parent-1"
    _assert_no_secrets(answer, family)


def test_reading_a_student_shows_its_effective_period(family) -> None:
    result = _call("get_usage_period", {"accountNumber": "S26-0001"})["result"]

    assert result["endsOn"] is None
    assert result["state"] == "none"
    (student,) = result["students"]
    assert student["userId"] == "student-1"
    assert student["effective"]["paidBy"] == "parent"


def test_a_teacher_has_no_usage_period_to_read(fake_table) -> None:
    _seed_account(fake_table, "teacher-1", "teacher", "T26-0001")

    answer = _call("get_usage_period", {"accountNumber": "T26-0001"})

    assert answer["error"]["code"] == "usage_period_role_invalid"


def test_an_unknown_number_is_not_found(fake_table) -> None:
    answer = _call("get_usage_period", {"accountNumber": "S26-9999"})

    assert answer["error"]["code"] == "account_not_found"


# -- extend_usage_period ---------------------------------------------------------------


def test_a_dry_run_extension_shows_before_after_and_the_children_and_writes_nothing(
    family,
) -> None:
    before = _rows(family)

    answer = _extend("P26-0001", dry=True)

    result = answer["result"]
    new_end = usage_period.add_months(_today() + timedelta(days=10), 1).isoformat()
    assert result["dryRun"] is True
    assert result["before"] == {"endsOn": _in(10), "state": "active", "version": 3}
    assert result["after"] == {"endsOn": new_end, "state": "active"}
    affected = {item["accountNumber"]: item for item in result["students"]}
    assert affected["S26-0001"]["before"]["endsOn"] == _in(10)
    assert affected["S26-0001"]["after"]["endsOn"] == new_end
    assert affected["S26-0001"]["changes"] is True
    # Its own period still ends later, so the extension does not reach this child.
    assert affected["S26-0002"]["after"]["endsOn"] == _in(200)
    assert affected["S26-0002"]["changes"] is False
    assert "Nothing was changed" in result["summary"]
    assert _business_rows_added(family, before) == set()
    assert family.rows[("USER#parent-1", "PROFILE")] == before[("USER#parent-1", "PROFILE")]
    (row,) = _audit_rows(family)
    assert row["dry_run"] is True
    assert row["action"] == "extend_usage_period"
    assert row["evidence_reference"].startswith("would_extend:usage-period:")
    _assert_no_secrets(answer, family)


def test_a_real_extension_writes_the_one_record_as_the_operator(family) -> None:
    answer = _extend("P26-0001", dry=False, expectedVersion=3, note="Paid by bank transfer")

    result = answer["result"]
    new_end = usage_period.add_months(_today() + timedelta(days=10), 1).isoformat()
    assert result["dryRun"] is False
    assert result["after"] == {"endsOn": new_end, "state": "active", "version": 4}
    assert family.rows[("USER#parent-1", "PROFILE")]["usage_period_ends_at"] == new_end
    (record,) = _records(family, "parent-1")
    assert record["actor_id"] == catalog.OPERATOR_ACTOR_ID
    assert record["kind"] == "extend"
    assert record["source"] == "paid"
    assert record["payment_reference"] == PAYMENT
    assert result["record"]["recordId"] == record["record_id"]
    assert result["record"]["actorId"] == catalog.OPERATOR_ACTOR_ID
    # The console's account event, named for the operator, never a web account.
    (event,) = _account_events(family, "parent-1")
    assert event["event_type"] == "usage_period_extended"
    assert event["actor_id"] == catalog.OPERATOR_ACTOR_ID
    assert event["reason_code"] == "paid:1:months"
    # The operator row joins the SSO session's fingerprint to the record.
    (row,) = _audit_rows(family)
    assert row["dry_run"] is False
    assert row["actor_fingerprint"]
    assert row["evidence_reference"].endswith(f"record:{record['record_id']}")
    # get_usage_period now shows the record.
    shown = _call("get_usage_period", {"accountNumber": "P26-0001"})["result"]
    assert [item["recordId"] for item in shown["records"]] == [record["record_id"]]


def test_a_real_run_needs_the_version_the_dry_run_showed(family) -> None:
    before = _rows(family)

    missing = _extend("P26-0001", dry=False)
    stale = _extend("P26-0001", dry=False, expectedVersion=2)
    stale_dry = _extend("P26-0001", dry=True, expectedVersion=2)

    assert missing["error"]["code"] == "expected_version_required"
    assert stale["error"]["code"] == "usage_period_version_conflict"
    assert stale_dry["error"]["code"] == "usage_period_version_conflict"
    assert "Would be refused" in stale_dry["error"]["message"]
    assert _business_rows_added(family, before) == set()


@pytest.mark.parametrize(
    "fields",
    [
        {"source": "paid", "paymentReference": None},
        {"source": "paid", "paymentReference": "   "},
        {"source": "paid", "unit": "days", "amount": 14},
    ],
)
def test_a_paid_extension_is_months_and_names_its_payment(family, fields) -> None:
    answer = _extend("P26-0001", dry=True, **fields)

    assert answer["error"]["code"] == "invalid_arguments"
    assert PAYMENT not in answer["error"]["message"]


def test_a_gift_may_be_days(family) -> None:
    answer = _extend(
        "S26-0001", dry=True, source="gifted", unit="days", amount=14, paymentReference=None
    )

    assert answer["result"]["after"]["endsOn"] == _in(14)


def test_a_teacher_period_is_not_extended(fake_table) -> None:
    _seed_account(fake_table, "teacher-1", "teacher", "T26-0001")

    answer = _extend("T26-0001", dry=True)

    assert answer["error"]["code"] == "usage_period_role_invalid"


def test_an_account_being_deleted_is_refused_in_the_dry_run_too(fake_table) -> None:
    _seed_account(fake_table, "student-1", "student", "S26-0001")
    fake_table.rows[("USER#student-1", "ACCOUNT_FENCE")]["status"] = "deleting"

    answer = _extend("S26-0001", dry=True)

    assert answer["error"]["code"] == "account_state_invalid"


# -- set_usage_period ------------------------------------------------------------------


def test_a_dry_run_set_ending_early_shows_who_loses_access(family) -> None:
    yesterday = _in(-1)
    before = _rows(family)

    result = _set("P26-0001", yesterday, dry=True)["result"]

    assert result["before"]["endsOn"] == _in(10)
    assert result["after"] == {"endsOn": yesterday, "state": "expired"}
    affected = {item["accountNumber"]: item for item in result["students"]}
    assert affected["S26-0001"]["after"]["state"] == "expired"
    assert affected["S26-0001"]["changes"] is True
    assert affected["S26-0002"]["changes"] is False
    assert _business_rows_added(family, before) == set()


def test_a_real_set_writes_the_record_with_its_reason(family) -> None:
    result = _set("P26-0001", _in(40), dry=False, expectedVersion=3)["result"]

    assert result["after"]["endsOn"] == _in(40)
    (record,) = _records(family, "parent-1")
    assert record["kind"] == "set"
    assert record["reason"] == REASON
    assert record["actor_id"] == catalog.OPERATOR_ACTOR_ID
    (event,) = _account_events(family, "parent-1")
    assert event["event_type"] == "usage_period_set"
    assert event["actor_id"] == catalog.OPERATOR_ACTOR_ID


def test_a_set_states_its_reason(family) -> None:
    answer = _set("P26-0001", _in(40), dry=True, reason="   ")

    assert answer["error"]["code"] == "invalid_arguments"
