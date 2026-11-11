"""Owner registry rows written by the fenced write entry (#397, PR 1: dual-write).

Every Put/Update made through `db_table.fenced` registers the partition it went
into under the owner's own partition, in the same transaction, unless the
partition is one the owner's id determines. Deletion does not read the registry
yet; these tests pin only the write side.
"""

from __future__ import annotations

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo

STUDENT = "student-1"
TEACHER = "teacher-1"
PARENT = "parent-1"


def _fence(user_id: str, *, generation: int = 3, status: str = "active") -> dict:
    return {
        **account_deletion_repo.account_fence_key(user_id),
        "entity_type": "account_fence",
        "status": status,
        "generation": generation,
    }


@pytest.fixture
def table() -> FakeTable:
    double = FakeTable()
    double.seed(_fence(STUDENT), _fence(TEACHER, generation=5), _fence(PARENT, generation=7))
    return double


def _put(pk: str, sk: str = "META", **fields) -> dict:
    return {"Put": {"Item": {"PK": pk, "SK": sk, **fields}}}


def _update(pk: str, sk: str = "META") -> dict:
    return {
        "Update": {
            "Key": {"PK": pk, "SK": sk},
            "UpdateExpression": "SET touched=:t",
            "ExpressionAttributeValues": {":t": True},
        }
    }


def _registry(table: FakeTable, user_id: str) -> dict[str, str]:
    return {
        row["SK"]: row["role"]
        for (pk, _), row in table.rows.items()
        if pk == f"USER#{user_id}" and owner_registry.is_registry_row(row)
    }


def _transactions(table: FakeTable) -> list[list[dict]]:
    return [
        request["operations"]
        for name, request in table.requests
        if name == "transact_write_items"
    ]


# -- what is registered ----------------------------------------------------------------


def test_a_write_into_a_foreign_partition_registers_it_in_the_same_transaction(table):
    db_table.fenced(STUDENT, [_put("CONV#c1", "CONV", owner_id=STUDENT)], table=table)

    assert _registry(table, STUDENT) == {"OWNS#CONV#c1": "owner"}
    (sent,) = _transactions(table)
    assert sent[-1] == {"Put": {"Item": owner_registry.registry_item(STUDENT, "CONV#c1")}}
    row = table.rows[(f"USER#{STUDENT}", "OWNS#CONV#c1")]
    # Bookkeeping only: nothing a deletion predicate would take for the account's data.
    assert not {"user_id", "owner_id", "student_id"} & set(row)
    assert not account_deletion_repo._targets_user(row, STUDENT)


def test_an_update_registers_its_partition_as_well(table):
    db_table.fenced(STUDENT, [_update("REPORT#r1")], table=table)

    assert _registry(table, STUDENT) == {"OWNS#REPORT#r1": "owner"}


@pytest.mark.parametrize("prefix", owner_registry.DERIVED_PREFIXES)
def test_the_owners_own_derived_partitions_are_not_registered(table, prefix):
    db_table.fenced(STUDENT, [_put(f"{prefix}{STUDENT}", "ROW#1")], table=table)

    assert _registry(table, STUDENT) == {}
    (sent,) = _transactions(table)
    assert len(sent) == 2


def test_another_accounts_derived_partition_is_registered(table):
    # A parent writing into the student's partition: deleting the parent must
    # still find that row, so the parent registers the partition.
    db_table.fenced(PARENT, [_put(f"USER#{STUDENT}", "LINK#1")], table=table)

    assert _registry(table, PARENT) == {f"OWNS#USER#{STUDENT}": "owner"}


def test_push_token_partitions_carry_more_than_the_id_and_are_registered(table):
    pk = f"NOTIFICATION_PUSH_TOKEN#{STUDENT}#ref-1"

    db_table.fenced(STUDENT, [_put(pk, "TOKEN")], table=table)

    assert _registry(table, STUDENT) == {f"OWNS#{pk}": "owner"}


def test_deletes_and_condition_checks_register_nothing(table):
    table.seed({"PK": "CONV#c1", "SK": "MSG#1"})
    db_table.fenced(
        STUDENT,
        [
            {"Delete": {"Key": {"PK": "CONV#c1", "SK": "MSG#1"}}},
            {"ConditionCheck": {"Key": {"PK": "REPORT#r1", "SK": "META"},
                                "ConditionExpression": "attribute_not_exists(PK)"}},
        ],
        table=table,
    )

    assert _registry(table, STUDENT) == {}


def test_one_registry_row_per_partition_however_many_rows(table):
    db_table.fenced(
        STUDENT,
        [_put("CONV#c1", "CONV"), _put("CONV#c1", "MSG#1"), _put("CONV#c1", "MSG#2")],
        table=table,
    )

    (sent,) = _transactions(table)
    assert [op for op in sent if op.get("Put", {}).get("Item", {}).get("entity_type") == "owner_registry"] == [
        {"Put": {"Item": owner_registry.registry_item(STUDENT, "CONV#c1")}}
    ]


def test_writing_again_is_idempotent(table):
    for _ in range(3):
        db_table.fenced(STUDENT, [_put("CONV#c1", "CONV")], table=table)

    assert _registry(table, STUDENT) == {"OWNS#CONV#c1": "owner"}


# -- `also=` accounts ------------------------------------------------------------------


def test_also_accounts_are_registered_as_references(table):
    db_table.fenced(
        STUDENT,
        [_put("TEACHER_SUPPORT_CASE#x", "CASE", student_id=STUDENT, teacher_id=TEACHER)],
        also={TEACHER: None},
        table=table,
    )

    assert _registry(table, STUDENT) == {"OWNS#TEACHER_SUPPORT_CASE#x": "owner"}
    assert _registry(table, TEACHER) == {"REFERENCED_IN#TEACHER_SUPPORT_CASE#x": "reference"}


def test_a_reference_never_overwrites_an_owner_registration(table):
    db_table.fenced(TEACHER, [_put("MODERATION#m1", "CASE")], table=table)
    db_table.fenced(STUDENT, [_put("MODERATION#m1", "EVENT#1")], also={TEACHER: None}, table=table)

    assert _registry(table, TEACHER) == {
        "OWNS#MODERATION#m1": "owner",
        "REFERENCED_IN#MODERATION#m1": "reference",
    }


def test_a_parent_link_registers_each_side_where_the_other_wrote(table):
    db_table.fenced(
        PARENT,
        [_put(f"PARENT#{PARENT}", f"CHILD#{STUDENT}"), _put(f"STUDENT#{STUDENT}", f"PARENT#{PARENT}")],
        also={STUDENT: None},
        table=table,
    )

    # Each side's own partition is derived; the other side's is registered as a reference.
    assert _registry(table, PARENT) == {f"OWNS#STUDENT#{STUDENT}": "owner"}
    assert _registry(table, STUDENT) == {f"REFERENCED_IN#PARENT#{PARENT}": "reference"}


# -- the fence still decides -----------------------------------------------------------


def test_a_closed_fence_writes_neither_the_row_nor_its_registry(table):
    table.seed(_fence(STUDENT, status="deletion_pending"))

    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(STUDENT, [_put("CONV#c1", "CONV")], table=table)

    assert ("CONV#c1", "CONV") not in table.rows
    assert _registry(table, STUDENT) == {}


def test_a_refused_own_operation_reports_only_its_own_reasons(table):
    table.seed({"PK": "CONV#c1", "SK": "CONV"})
    create = {
        "Put": {
            "Item": {"PK": "CONV#c1", "SK": "CONV"},
            "ConditionExpression": "attribute_not_exists(PK)",
        }
    }

    with pytest.raises(db_table.WriteRefused) as raised:
        db_table.fenced(STUDENT, [create], table=table)

    assert len(raised.value.reasons) == 1
    assert raised.value.failed_conditions == (0,)
    assert _registry(table, STUDENT) == {}


# -- transaction size and duplicate keys -----------------------------------------------


def test_registry_rows_that_do_not_fit_are_committed_first_under_the_same_fence(table):
    operations = [_put(f"CONV#c{index}", "CONV") for index in range(60)]

    db_table.fenced(STUDENT, operations, table=table)

    transactions = _transactions(table)
    assert all(len(sent) <= db_table.TRANSACTION_ITEM_LIMIT for sent in transactions)
    fence = account_deletion_repo.active_fence_condition(STUDENT, 3)
    assert all(sent[0] == fence for sent in transactions)
    # Registry first, the caller's own last.
    assert transactions[-1][1:] == operations
    assert len(_registry(table, STUDENT)) == 60
    assert all(("CONV#c%d" % index, "CONV") in table.rows for index in range(60))


def test_registry_ahead_is_still_refused_by_a_closed_fence(table):
    table.seed(_fence(STUDENT, status="deletion_pending"))
    operations = [_put(f"CONV#c{index}", "CONV") for index in range(60)]

    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(STUDENT, operations, generation=3, table=table)

    assert _registry(table, STUDENT) == {}
    assert not any(pk.startswith("CONV#") for pk, _ in table.rows)


def test_a_transaction_never_names_one_key_twice(table):
    # A caller that writes a registry row itself (a backfill, say) is not
    # given a second operation on the same key.
    own = {"Put": {"Item": owner_registry.registry_item(STUDENT, "CONV#c1")}}

    db_table.fenced(STUDENT, [_put("CONV#c1", "CONV"), own], table=table)

    (sent,) = _transactions(table)
    keys = [
        (body.get("Key") or body.get("Item"))["PK"] + "|" + (body.get("Key") or body.get("Item"))["SK"]
        for operation in sent
        for body in operation.values()
    ]
    assert len(keys) == len(set(keys))


# -- the derived list -------------------------------------------------------------------


def test_derived_partitions_are_exactly_prefix_and_id():
    assert owner_registry.derived_partitions("u1") == tuple(
        f"{prefix}u1" for prefix in owner_registry.DERIVED_PREFIXES
    )
    assert owner_registry.is_derived_for("USER#u1", "u1")
    assert not owner_registry.is_derived_for("USER#u10", "u1")
    assert not owner_registry.is_derived_for("NOTIFICATION_PUSH_TOKEN#u1#r", "u1")


def test_the_derived_prefixes_match_the_repositories_that_build_them():
    from stoa.db.repositories import attachment_repo, notification_repo, parent_link_repo
    from stoa.db.repositories import practice_repo, review_repo

    user = "u1"
    built = {
        attachment_repo.storage_key(user)["PK"],
        notification_repo.preference_pk(user),
        notification_repo.delivery_intent_pk(user),
        parent_link_repo.parent_side_key(user, "x")["PK"],
        parent_link_repo.student_side_key(user, "x")["PK"],
        practice_repo.activity_partition(user),
        review_repo.card_partition(user),
    }
    assert built <= set(owner_registry.derived_partitions(user))


# -- writers outside `fenced` that open a partition deletion acts on --------------------


def test_a_phone_upload_code_registers_its_partition_for_its_owner(table):
    from stoa.db.repositories import upload_code_repo

    upload_code_repo.put_code(
        {"code_id": "code-1", "owner_id": STUDENT, "status": "issued", "expires_at": 1},
        table=table,
    )

    assert ("UPLOADCODE#code-1", "CODE") in table.rows
    assert _registry(table, STUDENT) == {"OWNS#UPLOADCODE#code-1": "owner"}


def test_a_recovery_job_registers_its_partition_for_each_targeted_student(table):
    from stoa.db.repositories import report_repo

    db_table.install(table)
    try:
        report_repo.put_recovery_job(
            {"job_id": "job-1", "status": "pending"},
            [
                {"target_id": "t1", "student_id": STUDENT},
                {"target_id": "t2", "student_id": STUDENT},
                {"target_id": "t3", "student_id": TEACHER},
            ],
        )
    finally:
        db_table.install(None)

    assert _registry(table, STUDENT) == {"OWNS#REPORT_RECOVERY_JOB#job-1": "owner"}
    assert _registry(table, TEACHER) == {"OWNS#REPORT_RECOVERY_JOB#job-1": "owner"}
