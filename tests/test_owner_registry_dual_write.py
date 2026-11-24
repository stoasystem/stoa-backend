"""Owner registry rows written by the fenced write entry (#397, PR 1: dual-write).

Every Put/Update made through `db_table.fenced` registers the partition it went
into under the owner's own partition, in the same transaction, unless the
partition is one the owner's id determines. Deletion does not read the registry
yet; these tests pin only the write side. Whom a write registers is the data
type catalog's answer (#589).
"""

from __future__ import annotations

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import data_catalog, owner_registry
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
    assert not data_catalog.names(row, STUDENT)


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

    # Each side's own partition is derived; the other side's is registered, for
    # the fence owner and for the `also=` account. These rows carry no
    # `entity_type`, so the catalog names nobody else in them (#589).
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


def test_a_recovery_audit_event_registers_the_parent_and_student_it_names(table):
    """A target's parent is first named by the event that records the target (#573)."""
    from stoa.db.repositories import report_repo

    db_table.install(table)
    try:
        report_repo.put_recovery_job_audit_event(
            "job-1",
            {
                "event_id": "event-1",
                "event_at": "2026-11-21T10:00:00+00:00",
                "job_id": "job-1",
                "action": "resend_email_target",
                "result": "success",
                "metadata": {"target_id": "t1", "parent_id": PARENT, "student_id": STUDENT},
            },
        )
    finally:
        db_table.install(None)

    assert ("REPORT_RECOVERY_JOB#job-1", "AUDIT#2026-11-21T10:00:00+00:00#event-1") in table.rows
    assert _registry(table, PARENT) == {"OWNS#REPORT_RECOVERY_JOB#job-1": "owner"}
    assert _registry(table, STUDENT) == {"OWNS#REPORT_RECOVERY_JOB#job-1": "owner"}
    assert _registry(table, TEACHER) == {}


# -- accounts a row names: the data type catalog, and nothing else (#589) ----------------

NOTIFICATION = {"PK": "NOTIFICATION#e1", "SK": "META", "entity_type": "notification_event"}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            {**NOTIFICATION, "owner_id": STUDENT, "actor_id": TEACHER,
             "metadata": {"teacher_id": PARENT}},
            {STUDENT: "owner", TEACHER: "reference", PARENT: "reference"},
        ),
        # A notification about a student is tombstoned with them (#574): owner.
        (
            {**NOTIFICATION, "owner_id": PARENT, "metadata": {"student_id": STUDENT}},
            {PARENT: "owner", STUDENT: "owner"},
        ),
        (
            {"PK": "CONV#c1", "SK": "HELP_REQUEST", "entity_type": "help_request",
             "student_id": STUDENT, "dispatched_teacher_id": TEACHER,
             "previous_dispatch_teacher_ids": [PARENT]},
            {STUDENT: "owner", TEACHER: "reference", PARENT: "reference"},
        ),
        (
            {"PK": f"USER#{TEACHER}", "SK": "CAPABILITY#teacher_support",
             "entity_type": "capability_grant_current", "user_id": TEACHER,
             "scope": f"student:{STUDENT}"},
            {TEACHER: "owner", STUDENT: "owner"},
        ),
        # No generic owner fields: a kind the catalog does not know names nobody,
        # and neither does a field its entry does not declare.
        ({"PK": "NEW#x", "SK": "ROW", "entity_type": "brand_new_kind", "owner_id": STUDENT}, {}),
        ({"PK": "PARITY#x", "SK": "ROW", "entity_type": "help_request",
          "target_user_id": STUDENT, "scope": STUDENT}, {}),
        # A field the catalog lists as no pointer is a mention: nobody (#586 decision 1).
        ({"PK": "INVITATION#d", "SK": "META", "entity_type": "account_invitation",
          "account_id": STUDENT, "invited_by": TEACHER}, {STUDENT: "owner"}),
        ({"PK": "USAGE_PERIOD#r", "SK": "RECORD", "entity_type": "usage_period_record",
          "user_id": STUDENT, "actor_id": TEACHER}, {STUDENT: "owner"}),
        ({"PK": "ACCOUNT_NUMBER#S-1", "SK": "CLAIM", "entity_type": "account_number",
          "account_id": STUDENT}, {}),
    ],
)
def test_a_write_registers_exactly_whom_the_catalog_says_its_row_names(table, row, expected):
    assert {
        account: role for account, role in data_catalog.mentions(row).items()
    } == expected
    db_table.registered([{"Put": {"Item": row}}], table=table)

    for account in (STUDENT, TEACHER, PARENT):
        # An account's own derived partitions are never registered.
        role = None if owner_registry.is_derived_for(row["PK"], account) else expected.get(account)
        prefix = owner_registry.OWNER_PREFIX if role == "owner" else owner_registry.REFERENCE_PREFIX
        assert _registry(table, account) == ({f"{prefix}{row['PK']}": role} if role else {}), account


def test_who_opened_an_account_is_not_registered(table):
    from stoa.db.repositories import user_repo

    profile = {"PK": f"USER#{STUDENT}", "SK": "PROFILE", "user_id": STUDENT, "role": "student",
               "created_by": TEACHER, "created_at": "2026-11-24T10:00:00+00:00"}
    table.rows.pop(tuple(account_deletion_repo.account_fence_key(STUDENT).values()))
    db_table.install(table)
    try:
        user_repo.put_user_with_email_claim(profile, claim_operation={"Put": {"Item": {
            "PK": "EMAIL#digest", "SK": "CLAIM", "entity_type": "account_email_claim",
            "account_id": STUDENT,
        }}})
    finally:
        db_table.install(None)

    assert (f"USER#{STUDENT}", "PROFILE") in table.rows
    assert _registry(table, STUDENT) == {}
    assert _registry(table, TEACHER) == {}


def test_an_invitation_registers_the_invited_account_not_the_inviter(table):
    from stoa.db.repositories import account_invitation_repo

    account_invitation_repo.create_invitation(
        {"invitation_id": "inv-1", "token_digest": "digest-1", "account_id": STUDENT,
         "invited_by": TEACHER, "status": "pending", "role": "student"},
        table=table,
    )

    assert _registry(table, STUDENT) == {"OWNS#ACCOUNT_INVITATION#digest-1": "owner"}
    assert _registry(table, TEACHER) == {}


# -- an Update that changes whom a row names (#589) ----------------------------------------


def _pointer_update(teacher: str = TEACHER) -> dict:
    return {
        "Update": {
            "Key": {"PK": "CONV#c1", "SK": "HELP_REQUEST"},
            "UpdateExpression": "SET #t = :t, dispatch_status = :s",
            "ExpressionAttributeNames": {"#t": "dispatched_teacher_id"},
            "ExpressionAttributeValues": {":t": teacher, ":s": "dispatched"},
        }
    }


def test_an_update_that_sets_an_account_pointer_must_pass_its_row(table):
    before = dict(table.rows)
    with pytest.raises(ValueError, match="rows="):
        db_table.fenced(STUDENT, [_pointer_update()], table=table)
    with pytest.raises(ValueError, match="rows="):
        db_table.registered([_pointer_update()], table=table)
    assert table.rows == before


def test_an_update_registers_whom_its_row_will_name(table):
    row = {"PK": "CONV#c1", "SK": "HELP_REQUEST", "entity_type": "help_request",
           "student_id": STUDENT}
    table.seed(row)
    update = _pointer_update()

    db_table.fenced(
        STUDENT, [update], rows=owner_registry.rows_after(row, [update]), table=table
    )

    assert table.rows[("CONV#c1", "HELP_REQUEST")]["dispatched_teacher_id"] == TEACHER
    assert _registry(table, TEACHER) == {"REFERENCED_IN#CONV#c1": "reference"}


def test_an_update_of_other_fields_needs_no_row(table):
    db_table.fenced(STUDENT, [_update("CONV#c1")], table=table)

    assert _registry(table, STUDENT) == {"OWNS#CONV#c1": "owner"}


@pytest.mark.parametrize(
    ("expression", "names", "changed"),
    [
        ("SET #s = :s, updated_at = :now", {"#s": "status"}, []),
        ("SET #t = if_not_exists(#t, :t) ADD previous_dispatch_teacher_ids :x",
         {"#t": "teacher_id"}, ["teacher_id", "previous_dispatch_teacher_ids"]),
        ("SET metadata.read_at = :r", {}, []),
        ("SET metadata = :m", {}, ["metadata"]),
        ("SET children.#c = :entry", {"#c": STUDENT}, [f"children.{STUDENT}"]),
        ("REMOVE scope, owner_id", {}, []),
    ],
)
def test_the_pointer_paths_an_update_sets(expression, names, changed):
    update = {"UpdateExpression": expression, "ExpressionAttributeNames": names}
    assert owner_registry.updated_pointer_paths(update) == changed


def test_rows_after_applies_simple_assignments_and_refuses_the_rest():
    key = {"PK": "USAGE#s", "SK": "VOICE#2026-11"}
    update = {
        "Key": key,
        "UpdateExpression": (
            "SET #c = :next, owner_id = if_not_exists(owner_id, :owner), "
            "entity_type = if_not_exists(entity_type, :kind) ADD tally :one REMOVE stale"
        ),
        "ExpressionAttributeNames": {"#c": "count"},
        "ExpressionAttributeValues": {":next": 2, ":owner": STUDENT, ":kind": "rate_counter",
                                      ":one": 1},
    }
    (after,) = owner_registry.rows_after({**key, "tally": 1, "stale": True}, [{"Update": update}])
    assert after == {**key, "count": 2, "owner_id": STUDENT, "entity_type": "rate_counter",
                     "tally": 2}
    # A row already owned keeps its owner under if_not_exists.
    (kept,) = owner_registry.rows_after({**key, "owner_id": TEACHER}, [{"Update": update}])
    assert kept["owner_id"] == TEACHER
    # Another key's Update is not this row's.
    assert owner_registry.rows_after({"PK": "x", "SK": "y"}, [{"Update": update}]) == []
    appended = {**update, "UpdateExpression": "SET children = list_append(children, :c)",
                "ExpressionAttributeValues": {":c": []}}
    with pytest.raises(ValueError):
        owner_registry.rows_after(key, [{"Update": appended}])


def test_registered_with_no_operations_registers_ahead(table):
    row = {"PK": "REPORT_RECOVERY_JOB#j", "SK": "SUMMARY", "entity_type": "REPORT_RECOVERY_JOB",
           "filters": {"student_id": STUDENT}}

    db_table.registered((), rows=[row], table=table)

    assert ("REPORT_RECOVERY_JOB#j", "SUMMARY") not in table.rows
    assert _registry(table, STUDENT) == {"OWNS#REPORT_RECOVERY_JOB#j": "owner"}


def test_a_fenced_put_registers_every_account_its_row_names(table):
    event = {
        "PK": "NOTIFICATION#e1", "SK": "EVENT", "entity_type": "notification_event",
        "owner_id": STUDENT, "actor_id": TEACHER, "metadata": {"teacher_id": TEACHER},
    }

    db_table.fenced(STUDENT, [_put(event["PK"], event["SK"], **event)], table=table)

    assert _registry(table, STUDENT) == {"OWNS#NOTIFICATION#e1": "owner"}
    # The teacher's fence is not a condition of the write; only its reference row.
    assert _registry(table, TEACHER) == {"REFERENCED_IN#NOTIFICATION#e1": "reference"}
    (sent,) = _transactions(table)
    assert [op for op in sent if "ConditionCheck" in op] == [
        account_deletion_repo.active_fence_condition(STUDENT, 3)
    ]


@pytest.mark.parametrize("field", ["parent_id", "actor_id"])
def test_a_notification_registers_the_account_its_metadata_mentions(table, field):
    """Through the notification write path, a Put and a later Update alike (#574)."""
    from stoa.db.repositories import notification_repo

    db_table.install(table)
    try:
        notification_repo.put_event({
            "event_id": "e1", "entity_type": "notification_event",
            "schema_version": "notification-event.v2", "owner_id": STUDENT,
            "account_fence_generation": 3, "status": "created", "event_version": 1,
            "metadata": {field: PARENT},
        })
        assert _registry(table, PARENT) == {"REFERENCED_IN#NOTIFICATION#e1": "reference"}

        notification_repo.update_event("e1", {"metadata": {field: TEACHER}})
    finally:
        db_table.install(None)

    # (The notification write hands `fenced` the mentioned accounts' registry
    # Puts, which it then counts as writes into their `USER#` partitions; only
    # the notification's own partition is the point here.)
    def notification(user_id: str) -> dict[str, str]:
        return {
            sk: role for sk, role in _registry(table, user_id).items()
            if sk.endswith("NOTIFICATION#e1")
        }

    assert notification(STUDENT) == {"OWNS#NOTIFICATION#e1": "owner"}
    assert notification(PARENT) == {"REFERENCED_IN#NOTIFICATION#e1": "reference"}
    assert notification(TEACHER) == {"REFERENCED_IN#NOTIFICATION#e1": "reference"}


def test_a_capability_grant_registers_the_student_it_is_scoped_to(table):
    from stoa.db.repositories import capability_repo

    grant = {"PK": f"USER#{TEACHER}", "SK": "CAPABILITY#teacher_support#1", "scope": f"student:{STUDENT}",
             "entity_type": "capability_grant_current", "user_id": TEACHER}
    capability_repo._apply(table, [{"kind": "put", "item": grant, "condition": "absent"}])

    # The student's deletion terminalizes a grant scoped to them: owner (#586 decision 7).
    assert _registry(table, STUDENT) == {f"OWNS#USER#{TEACHER}": "owner"}


def test_closing_a_link_registers_each_side_for_the_other(table):
    from stoa.db.repositories import parent_link_repo

    side = {"parent_id": PARENT, "student_id": STUDENT, "status": "active",
            "entity_type": parent_link_repo.ENTITY_TYPE}
    forward = {**parent_link_repo.parent_side_key(PARENT, STUDENT), **side}
    reverse = {**parent_link_repo.student_side_key(STUDENT, PARENT), **side}
    table.seed(forward, reverse)
    parent_link_repo.close_link(
        parent_id=PARENT, student_id=STUDENT, parent_side=forward, student_side=reverse,
        updated_by="admin-1", link_updated_at="2026-11-11T10:00:00+00:00", table=table,
    )

    assert table.rows[(f"PARENT#{PARENT}", f"CHILD#{STUDENT}")]["status"] != "active"
    # Either side's deletion deletes both rows: each owns the other's (#586 decision 7).
    assert _registry(table, STUDENT) == {f"OWNS#PARENT#{PARENT}": "owner"}
    assert _registry(table, PARENT) == {f"OWNS#STUDENT#{STUDENT}": "owner"}


def test_a_help_request_written_without_a_fence_registers_its_lapsed_teachers(table):
    from stoa.services import help_requests

    table.seed({"PK": "CONV#c1", "SK": "HELP", "conversation_id": "c1", "student_id": STUDENT,
                "entity_type": "help_request", "escalation_status": "pending", "version": 1})
    record = dict(table.rows[("CONV#c1", "HELP")])

    help_requests._write(
        record, {"previous_dispatch_teacher_ids": [TEACHER], "dispatch_status": "no_candidate"},
        table=table,
    )

    assert table.rows[("CONV#c1", "HELP")]["previous_dispatch_teacher_ids"] == [TEACHER]
    assert _registry(table, TEACHER) == {"REFERENCED_IN#CONV#c1": "reference"}


def test_generation_progress_cannot_be_written_once_the_owner_is_closing(table):
    from stoa.services.ask_question import _store

    def write() -> bool:
        return _store.record_generation_progress(
            "c1", owner_id=STUDENT, steps=["a"], now_iso="2026-11-11T10:00:00+00:00",
            expires_at=1, table=table,
        )

    assert write() is True
    assert table.rows[("CONV#c1", "GENERATION")]["owner_id"] == STUDENT
    del table.rows[("CONV#c1", "GENERATION")]
    table.seed(_fence(STUDENT, status="deletion_pending"))

    assert write() is False
    assert ("CONV#c1", "GENERATION") not in table.rows
