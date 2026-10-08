"""The shared table double is only worth having if it is held to the real semantics.

Each test below pins one rule that a hand-written double got wrong at least once, and
whose looseness let a real defect through with the suite green. Relaxing any of them
re-opens the corresponding hole, so they are written against the double itself rather
than against any route that happens to use it.
"""

from __future__ import annotations

from decimal import Decimal

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
import pytest

from fakes.dynamodb import (
    DEFAULT_INDEXES,
    FakeTable,
    IndexSchema,
    apply_update_expression,
    as_stored,
)
from stoa.db.repositories.account_deletion_repo import AccountDeletionConflict
from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict
from test_index_keys_are_never_empty import INDEX_KEY_ATTRIBUTES


def _table_with_profiles(noise: int = 40, profiles: int = 3) -> FakeTable:
    """Noise rows first, profiles behind them - the layout the real table has."""
    table = FakeTable()
    for index in range(noise):
        table.seed({"PK": f"PRACTICE#{index:04d}", "SK": "CHALLENGE", "entity_type": "practice"})
    for index in range(profiles):
        table.seed(
            {
                "PK": f"USER#u{index}",
                "SK": "PROFILE",
                "entity_type": "user_profile",
                "email": f"u{index}@stoa.test",
            }
        )
    return table


# -- rule 1: Limit counts rows read, and the filter runs after it --------------------


def test_limit_counts_rows_read_so_a_full_page_can_come_back_empty() -> None:
    table = _table_with_profiles()

    page = table.scan(
        Limit=10,
        FilterExpression="#e = :profile",
        ExpressionAttributeNames={"#e": "entity_type"},
        ExpressionAttributeValues={":profile": "user_profile"},
    )

    assert page["Items"] == []
    assert page["ScannedCount"] == 10
    assert "LastEvaluatedKey" in page, "a page that stopped early must say where it stopped"


def test_following_the_continuation_key_eventually_reaches_every_match() -> None:
    table = _table_with_profiles()
    seen: list[str] = []
    cursor: dict[str, object] | None = None

    for _page in range(20):
        request: dict[str, object] = {
            "Limit": 10,
            "FilterExpression": "#e = :profile",
            "ExpressionAttributeNames": {"#e": "entity_type"},
            "ExpressionAttributeValues": {":profile": "user_profile"},
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        page = table.scan(**request)
        seen.extend(str(row["PK"]) for row in page["Items"])
        cursor = page.get("LastEvaluatedKey")
        if cursor is None:
            break

    assert seen == ["USER#u0", "USER#u1", "USER#u2"]
    assert cursor is None, "the walk has to end, not loop on a repeating cursor"


def test_a_read_that_finishes_the_table_returns_no_continuation_key() -> None:
    table = _table_with_profiles(noise=2, profiles=1)

    page = table.scan(Limit=50)

    assert len(page["Items"]) == 3
    assert "LastEvaluatedKey" not in page


def test_exclusive_start_key_resumes_after_the_named_row_not_at_it() -> None:
    table = _table_with_profiles(noise=3, profiles=0)

    first = table.scan(Limit=1)
    second = table.scan(Limit=1, ExclusiveStartKey=first["LastEvaluatedKey"])

    assert first["Items"][0]["PK"] == "PRACTICE#0000"
    assert second["Items"][0]["PK"] == "PRACTICE#0001"


def test_query_applies_limit_before_the_filter_too() -> None:
    table = FakeTable()
    for index in range(10):
        table.seed({"PK": "CONV#1", "SK": f"MSG#{index:03d}", "role": "student"})
    table.seed({"PK": "CONV#1", "SK": "MSG#999", "role": "teacher"})

    page = table.query(
        KeyConditionExpression=Key("PK").eq("CONV#1"),
        FilterExpression=Attr("role").eq("teacher"),
        Limit=5,
    )

    assert page["Items"] == []
    assert page["ScannedCount"] == 5
    assert "LastEvaluatedKey" in page


def test_a_scan_with_no_limit_still_stops_at_the_response_cap() -> None:
    """`/admin/stats` counted one unlimited scan of a 3.76 MB table as the total.

    A double that answers an unlimited scan with the whole table cannot fail that
    way, so it would have called the census complete however large the table grew.
    """
    table = FakeTable(page_size_bytes=200)
    for index in range(40):
        table.seed({"PK": f"ROW#{index:03d}", "SK": "META", "entity_type": "practice"})

    page = table.scan()

    assert len(page["Items"]) < 40
    assert "LastEvaluatedKey" in page


def test_the_response_cap_never_returns_an_empty_page_it_could_not_advance_from() -> None:
    table = FakeTable(page_size_bytes=1)
    table.seed({"PK": "A", "SK": "1", "padding": "x" * 500})
    table.seed({"PK": "B", "SK": "1", "padding": "y" * 500})

    page = table.scan()

    assert len(page["Items"]) == 1
    assert page["LastEvaluatedKey"] == {"PK": "A", "SK": "1"}


def test_the_row_cap_shortens_a_page_but_never_lengthens_one() -> None:
    table = FakeTable(page_item_cap=3)
    for index in range(10):
        table.seed({"PK": f"ROW#{index}", "SK": "META"})

    assert table.scan()["ScannedCount"] == 3
    assert table.scan(Limit=2)["ScannedCount"] == 2


# -- rule 2: every stored number comes back as Decimal ------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [(3, Decimal(3)), (1.5, Decimal("1.5")), (True, True), (False, False), ("7", "7")],
)
def test_numbers_come_back_as_decimal_and_booleans_stay_booleans(
    written: object, expected: object
) -> None:
    table = FakeTable()
    table.put_item(Item={"PK": "ROW", "SK": "META", "value": written})

    stored = table.get_item(Key={"PK": "ROW", "SK": "META"})["Item"]["value"]

    assert stored == expected
    assert type(stored) is type(expected)


def test_nested_numbers_are_converted_too() -> None:
    table = FakeTable()
    table.put_item(Item={"PK": "ROW", "SK": "META", "body": {"counts": [1, 2], "n": 3}})

    stored = table.get_item(Key={"PK": "ROW", "SK": "META"})["Item"]["body"]

    assert stored == {"counts": [Decimal(1), Decimal(2)], "n": Decimal(3)}
    assert all(isinstance(value, Decimal) for value in stored["counts"])


def test_seeding_a_row_converts_it_as_a_write_would() -> None:
    """`seed` is the arranging shortcut; it must not be the way `int` gets back in."""
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "version": 4})

    assert table.get_item(Key={"PK": "ROW", "SK": "META"})["Item"]["version"] == Decimal(4)
    assert isinstance(table.rows[("ROW", "META")]["version"], Decimal)


def test_as_stored_leaves_bool_alone() -> None:
    assert as_stored({"flag": True, "n": 1}) == {"flag": True, "n": Decimal(1)}


# -- rule 3: conditions are evaluated, not guessed from bound placeholders ----------


def test_conditional_put_refuses_an_existing_row() -> None:
    table = FakeTable()
    table.put_item(Item={"PK": "USER#a", "SK": "PROFILE"})

    with pytest.raises(ClientError) as raised:
        table.put_item(
            Item={"PK": "USER#a", "SK": "PROFILE"},
            ConditionExpression="attribute_not_exists(PK)",
        )

    assert raised.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
    assert raised.value.operation_name == "PutItem"


def test_a_bound_placeholder_is_not_enough_to_pass_a_condition() -> None:
    """Incident 5: a double that looked only at which values were bound.

    Both writes below bind `:expected`. Only the one whose value matches the stored
    row may go through.
    """
    table = FakeTable()
    table.seed({"PK": "JOB#1", "SK": "META", "status": "pending"})

    table.update_item(
        Key={"PK": "JOB#1", "SK": "META"},
        UpdateExpression="SET #s = :next",
        ConditionExpression="#s = :expected",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":expected": "pending", ":next": "running"},
    )

    with pytest.raises(ClientError):
        table.update_item(
            Key={"PK": "JOB#1", "SK": "META"},
            UpdateExpression="SET #s = :next",
            ConditionExpression="#s = :expected",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":expected": "pending", ":next": "done"},
        )

    assert table.get_item(Key={"PK": "JOB#1", "SK": "META"})["Item"]["status"] == "running"


def test_a_filter_naming_a_row_kind_stops_returning_the_other_kinds() -> None:
    """Incident 5 on the read side: the filter text has to decide, not the bindings."""
    table = FakeTable()
    table.seed({"PK": "A", "SK": "1", "entity_type": "report"})
    table.seed({"PK": "B", "SK": "1", "entity_type": "practice"})

    page = table.scan(
        FilterExpression="#e = :kind",
        ExpressionAttributeNames={"#e": "entity_type"},
        ExpressionAttributeValues={":kind": "report"},
    )

    assert [row["PK"] for row in page["Items"]] == ["A"]


def test_condition_expressions_evaluate_and_or_and_the_attribute_predicates() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "status": "active", "version": 2})

    table.update_item(
        Key={"PK": "ROW", "SK": "META"},
        UpdateExpression="SET #v = :next",
        ConditionExpression=(
            "(#s = :active OR #s = :pending) AND #v < :ceiling AND attribute_not_exists(sealed)"
        ),
        ExpressionAttributeNames={"#s": "status", "#v": "version"},
        ExpressionAttributeValues={
            ":active": "active",
            ":pending": "pending",
            ":ceiling": 5,
            ":next": 3,
        },
    )
    assert table.rows[("ROW", "META")]["version"] == Decimal(3)

    table.update_item(
        Key={"PK": "ROW", "SK": "META"},
        UpdateExpression="SET sealed = :yes",
        ExpressionAttributeValues={":yes": True},
    )
    with pytest.raises(ClientError):
        table.update_item(
            Key={"PK": "ROW", "SK": "META"},
            UpdateExpression="SET #v = :next",
            ConditionExpression="attribute_not_exists(sealed)",
            ExpressionAttributeNames={"#v": "version"},
            ExpressionAttributeValues={":next": 4},
        )


def test_a_version_guard_written_against_decimal_holds_after_a_round_trip() -> None:
    """Rules 2 and 3 together: the guard compares a `Decimal` against a bound `int`."""
    table = FakeTable()
    table.put_item(Item={"PK": "ROW", "SK": "META", "version": 1})

    table.update_item(
        Key={"PK": "ROW", "SK": "META"},
        UpdateExpression="SET #v = #v + :one",
        ConditionExpression="#v = :current",
        ExpressionAttributeNames={"#v": "version"},
        ExpressionAttributeValues={":current": 1, ":one": 1},
    )

    assert table.rows[("ROW", "META")]["version"] == Decimal(2)


def test_conditional_delete_refuses_and_leaves_the_row() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "status": "running"})

    with pytest.raises(ClientError) as raised:
        table.delete_item(
            Key={"PK": "ROW", "SK": "META"},
            ConditionExpression="#s = :done",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":done": "done"},
        )

    assert raised.value.operation_name == "DeleteItem"
    assert ("ROW", "META") in table.rows


# -- rule 4: writes go through a write path, updates are really applied -------------


def test_update_expression_supports_the_forms_this_codebase_writes() -> None:
    item: dict[str, object] = {"count": Decimal(5), "name": "old", "stale": "x"}

    apply_update_expression(
        item,
        "SET #c = #c - :one, ttl = if_not_exists(ttl, :exp), #n = :new REMOVE stale ADD hits :one",
        {"#c": "count", "#n": "name"},
        {":one": 1, ":exp": 99, ":new": "fresh"},
    )

    assert item == {
        "count": Decimal(4),
        "ttl": Decimal(99),
        "name": "fresh",
        "hits": Decimal(1),
    }


def test_a_transaction_that_fails_one_condition_writes_none_of_its_effects() -> None:
    table = FakeTable()
    table.seed({"PK": "USER#a", "SK": "PROFILE", "status": "active"})

    with pytest.raises(ClientError) as raised:
        table.transact_write_items(
            [
                {"Put": {"Item": {"PK": "USER#b", "SK": "PROFILE"}}},
                {
                    "ConditionCheck": {
                        "Key": {"PK": "USER#a", "SK": "PROFILE"},
                        "ConditionExpression": "#s = :sealed",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {":sealed": "sealed"},
                    }
                },
            ]
        )

    assert raised.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert ("USER#b", "PROFILE") not in table.rows


# -- rule 6: query honours key conditions, ordering and index projection ------------


def test_query_key_condition_narrows_to_one_partition_and_prefix() -> None:
    table = FakeTable()
    table.seed({"PK": "CONV#1", "SK": "MSG#001"})
    table.seed({"PK": "CONV#1", "SK": "NOTE#001"})
    table.seed({"PK": "CONV#2", "SK": "MSG#001"})

    page = table.query(
        KeyConditionExpression=Key("PK").eq("CONV#1") & Key("SK").begins_with("MSG#")
    )

    assert [(row["PK"], row["SK"]) for row in page["Items"]] == [("CONV#1", "MSG#001")]


def test_scan_index_forward_false_really_reverses_the_order() -> None:
    table = FakeTable()
    for index in range(3):
        table.seed({"PK": "CONV#1", "SK": f"MSG#{index:03d}"})

    descending = table.query(
        KeyConditionExpression=Key("PK").eq("CONV#1"), ScanIndexForward=False
    )

    assert [row["SK"] for row in descending["Items"]] == ["MSG#002", "MSG#001", "MSG#000"]


def test_an_index_only_carries_rows_holding_every_one_of_its_key_attributes() -> None:
    """`parent_link_repo` depends on this: its link rows omit `created_at` on purpose."""
    table = FakeTable()
    table.seed(
        {"PK": "QUESTION#1", "SK": "META", "student_id": "s1", "created_at": "2026-01-01"}
    )
    table.seed({"PK": "PARENT#p1", "SK": "CHILD#s1", "student_id": "s1", "parent_id": "p1"})

    page = table.query(
        IndexName="GSI-StudentId", KeyConditionExpression=Key("student_id").eq("s1")
    )

    assert [row["PK"] for row in page["Items"]] == ["QUESTION#1"]


def test_an_index_query_orders_by_the_index_sort_key_not_the_table_key() -> None:
    table = FakeTable()
    table.seed({"PK": "Z", "SK": "META", "student_id": "s1", "created_at": "2026-01-01"})
    table.seed({"PK": "A", "SK": "META", "student_id": "s1", "created_at": "2026-02-01"})

    page = table.query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq("s1"),
        ScanIndexForward=False,
    )

    assert [row["PK"] for row in page["Items"]] == ["A", "Z"]


def test_an_index_query_does_not_return_other_partitions() -> None:
    table = FakeTable()
    table.seed({"PK": "Q#1", "SK": "META", "student_id": "s1", "created_at": "2026-01-01"})
    table.seed({"PK": "Q#2", "SK": "META", "student_id": "s2", "created_at": "2026-01-01"})

    page = table.query(
        IndexName="GSI-StudentId", KeyConditionExpression=Key("student_id").eq("s1")
    )

    assert [row["PK"] for row in page["Items"]] == ["Q#1"]


def test_an_index_page_carries_the_index_key_in_its_continuation_key() -> None:
    table = FakeTable()
    for index in range(3):
        table.seed(
            {
                "PK": f"Q#{index}",
                "SK": "META",
                "student_id": "s1",
                "created_at": f"2026-01-0{index + 1}",
            }
        )

    page = table.query(
        IndexName="GSI-StudentId", KeyConditionExpression=Key("student_id").eq("s1"), Limit=2
    )

    assert set(page["LastEvaluatedKey"]) == {"PK", "SK", "created_at"}
    resumed = table.query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq("s1"),
        ExclusiveStartKey=page["LastEvaluatedKey"],
    )
    assert [row["PK"] for row in resumed["Items"]] == ["Q#2"]


def test_an_unknown_index_is_refused_rather_than_silently_scanned() -> None:
    table = FakeTable(indexes={"GSI-Email": IndexSchema("email")})

    with pytest.raises(AssertionError, match="unknown index"):
        table.query(IndexName="GSI-Nope", KeyConditionExpression=Key("email").eq("a@b.test"))


# -- rule 7: an index key is never written as an empty string -----------------------
#
# The sixth time a double was wider than the table: on 2026-09-24 an assigned
# teacher-support admission was written with `parent_id=""`, DynamoDB refused the
# whole `TransactWriteItems` with a ValidationException, and every request 503'd. The
# double stored the row without complaint, so the suite was green on the defect.


def _assert_refused_for_an_empty_index_key(raised: pytest.ExceptionInfo[ClientError]) -> None:
    error = raised.value.response["Error"]
    assert error["Code"] == "ValidationException"
    assert "A value specified for a secondary index key is not supported" in error["Message"]


def test_put_item_refuses_an_empty_index_key() -> None:
    table = FakeTable()

    with pytest.raises(ClientError) as raised:
        table.put_item(Item={"PK": "X", "SK": "Y", "parent_id": ""})

    _assert_refused_for_an_empty_index_key(raised)
    assert raised.value.operation_name == "PutItem"
    assert ("X", "Y") not in table.rows


def test_update_item_refuses_to_set_an_index_key_to_an_empty_string() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "parent_id": "p-1", "week_start": "2026-09-21"})

    with pytest.raises(ClientError) as raised:
        table.update_item(
            Key={"PK": "ROW", "SK": "META"},
            UpdateExpression="SET #p = :none",
            ExpressionAttributeNames={"#p": "parent_id"},
            ExpressionAttributeValues={":none": ""},
        )

    _assert_refused_for_an_empty_index_key(raised)
    assert raised.value.operation_name == "UpdateItem"
    assert table.rows[("ROW", "META")]["parent_id"] == "p-1"


def test_a_conversation_transaction_with_an_empty_index_key_is_refused_like_production() -> None:
    """The 2026-09-24 shape: a Put in the conversation transaction carrying `parent_id=""`.

    Production sends it through `account_deletion_repo.transact`, which reports the
    ValidationException as an `AccountDeletionConflict`, and the two callers of this
    seam report that as an `AttachmentRepositoryConflict("conditional_conflict")`.
    The chain is kept so the refusal is still visible, and nothing lands.
    """
    table = FakeTable()

    with pytest.raises(AttachmentRepositoryConflict) as conflict:
        table.transact_conversation_write(
            [
                {"Put": {"Item": {"PK": "CONV#1", "SK": "META", "status": "open"}}},
                {
                    "Put": {
                        "Item": {"PK": "ADMISSION#1", "SK": "RECEIPT", "parent_id": ""},
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
            ]
        )

    wrapped = conflict.value.__cause__
    assert isinstance(wrapped, AccountDeletionConflict)
    assert isinstance(wrapped.__cause__, ClientError)
    _assert_refused_for_an_empty_index_key(pytest.ExceptionInfo.from_exception(wrapped.__cause__))
    assert wrapped.__cause__.operation_name == "TransactWriteItems"
    assert table.rows == {}


def test_an_account_transaction_that_empties_an_index_key_is_refused_like_production() -> None:
    """An Update inside the lifecycle transaction, judged on the row it would leave.

    Production's `account_deletion_repo.transact` reports every ClientError as an
    `AccountDeletionConflict` - a cancellation as the conditional kind, a
    ValidationException as a dependency failure - and keeps the cause. So does
    this seam, which is how a caller that answers every conflict the same way is
    seen doing so here.
    """
    table = FakeTable()
    table.seed({"PK": "USER#a", "SK": "PROFILE", "email": "a@stoa.test"})

    with pytest.raises(AccountDeletionConflict, match="dependency unavailable") as conflict:
        table.transact_account_deletion(
            [
                {"Put": {"Item": {"PK": "USER#a", "SK": "TOMBSTONE"}}},
                {
                    "Update": {
                        "Key": {"PK": "USER#a", "SK": "PROFILE"},
                        "UpdateExpression": "SET email = :none",
                        "ExpressionAttributeValues": {":none": ""},
                    }
                },
            ]
        )

    cause = conflict.value.__cause__
    assert isinstance(cause, ClientError)
    _assert_refused_for_an_empty_index_key(pytest.ExceptionInfo.from_exception(cause))
    assert table.rows[("USER#a", "PROFILE")]["email"] == "a@stoa.test"
    assert ("USER#a", "TOMBSTONE") not in table.rows


def test_seed_refuses_a_row_the_real_table_could_not_hold() -> None:
    """Otherwise a fixture can arrange a state no write path could ever reach."""
    with pytest.raises(ClientError) as raised:
        FakeTable().seed({"PK": "X", "SK": "Y", "email": ""})

    _assert_refused_for_an_empty_index_key(raised)


@pytest.mark.parametrize("attribute", sorted(INDEX_KEY_ATTRIBUTES))
def test_every_key_attribute_of_every_real_index_is_refused_empty(attribute: str) -> None:
    """Partition and sort keys alike, for each index `stoa-main` really carries."""
    with pytest.raises(ClientError) as raised:
        FakeTable().put_item(Item={"PK": "X", "SK": "Y", attribute: ""})

    _assert_refused_for_an_empty_index_key(raised)


def test_the_double_carries_the_key_attributes_of_every_real_index() -> None:
    """`INDEX_KEY_ATTRIBUTES` is pinned to `stoa-infra/stacks/database_stack.py`.

    The double was missing `GSI-TeacherId`, so `teacher_id=""` would have been stored
    here and refused in production.
    """
    carried = {
        attribute
        for schema in DEFAULT_INDEXES.values()
        for attribute in (schema.partition_key, schema.sort_key)
        if attribute is not None
    }

    assert carried == INDEX_KEY_ATTRIBUTES


def test_an_absent_index_key_and_an_empty_ordinary_attribute_are_both_fine() -> None:
    """The control: sparse rows and empty non-key strings are what the real table allows."""
    table = FakeTable()

    table.put_item(Item={"PK": "X", "SK": "Y", "note": "", "student_id": "s1"})
    table.update_item(
        Key={"PK": "X", "SK": "Y"},
        UpdateExpression="SET note = :none REMOVE student_id",
        ExpressionAttributeValues={":none": ""},
    )
    table.transact_write_items([{"Put": {"Item": {"PK": "Z", "SK": "Y", "note": ""}}}])

    assert table.rows[("X", "Y")] == {"PK": "X", "SK": "Y", "note": ""}
    assert table.rows[("Z", "Y")]["note"] == ""


# -- rule 8: an index key written as None is a NULL, and each seam sends what its --
# -- repository sends -----------------------------------------------------------
#
# The seventh time: on 2026-07-09 the usage ledger's `put_item` carried
# `parent_id: None`, the resource interface sent it as NULL, and the table refused
# the type mismatch five times. The transaction serializers leave a Put's top-level
# None out, so the same row goes through there. The double does both, each where
# production does.


def _assert_refused_for_a_null_index_key(raised: pytest.ExceptionInfo[ClientError]) -> None:
    error = raised.value.response["Error"]
    assert error["Code"] == "ValidationException"
    assert "Type mismatch for Index Key parent_id Expected: S Actual: NULL" in error["Message"]
    assert "IndexName: GSI-ParentId" in error["Message"]


def test_put_item_refuses_a_null_index_key() -> None:
    table = FakeTable()

    with pytest.raises(ClientError) as raised:
        table.put_item(Item={"PK": "X", "SK": "Y", "parent_id": None})

    _assert_refused_for_a_null_index_key(raised)
    assert raised.value.operation_name == "PutItem"
    assert ("X", "Y") not in table.rows


def test_update_item_refuses_to_set_an_index_key_to_null() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "parent_id": "p-1", "week_start": "2026-09-21"})

    with pytest.raises(ClientError) as raised:
        table.update_item(
            Key={"PK": "ROW", "SK": "META"},
            UpdateExpression="SET parent_id = :none",
            ExpressionAttributeValues={":none": None},
        )

    _assert_refused_for_a_null_index_key(raised)
    assert table.rows[("ROW", "META")]["parent_id"] == "p-1"


def test_seed_refuses_a_null_index_key() -> None:
    with pytest.raises(ClientError) as raised:
        FakeTable().seed({"PK": "X", "SK": "Y", "parent_id": None})

    _assert_refused_for_a_null_index_key(raised)


def test_the_low_level_transaction_refuses_a_null_index_key_it_is_given() -> None:
    """Called as the table, it judges the item as sent - no repository rule applies."""
    table = FakeTable()

    with pytest.raises(ClientError) as raised:
        table.transact_write_items([{"Put": {"Item": {"PK": "X", "SK": "Y", "parent_id": None}}}])

    _assert_refused_for_a_null_index_key(raised)
    assert table.rows == {}


def test_the_low_level_transaction_refuses_a_null_index_key_in_the_keyword_shape_too() -> None:
    """`TransactItems=` is also how `subscription_service._transact_write` calls, and its
    serializer keeps None - so this entry must not drop it for anyone."""
    table = FakeTable()

    with pytest.raises(ClientError) as raised:
        table.transact_write_items(
            TransactItems=[{"Put": {"Item": {"PK": "X", "SK": "Y", "student_id": None}}}]
        )

    assert "Type mismatch for Index Key student_id" in raised.value.response["Error"]["Message"]
    assert table.rows == {}


def test_the_attachment_seam_leaves_a_puts_top_level_none_out() -> None:
    """`attachment_repo._serialize_transactions`: the item loses its None, nothing else does."""
    table = FakeTable()

    table.transact_attachment_write(
        [
            {
                "Put": {
                    "Item": {
                        "PK": "X",
                        "SK": "Y",
                        "parent_id": None,
                        "metadata": {"subject": None},
                    }
                }
            }
        ]
    )

    assert table.rows[("X", "Y")] == {"PK": "X", "SK": "Y", "metadata": {"subject": None}}


def test_attachment_repo_classifies_the_seams_refusals_itself() -> None:
    """Through the real entry: the seam hands the ClientError over, and
    `attachment_repo.transact` sorts it as production does - a cancellation is a
    conditional conflict, an invalid request a dependency failure."""
    from stoa.db.repositories import attachment_repo

    table = FakeTable()
    table.seed({"PK": "X", "SK": "Y"})

    with pytest.raises(AttachmentRepositoryConflict) as cancelled:
        attachment_repo.transact(
            [{"Put": {"Item": {"PK": "X", "SK": "Y"}, "ConditionExpression": "attribute_not_exists(PK)"}}],
            table=table,
        )
    with pytest.raises(AttachmentRepositoryConflict) as invalid:
        attachment_repo.transact(
            [{"Put": {"Item": {"PK": "Z", "SK": "Y", "parent_id": ""}}}], table=table
        )

    assert cancelled.value.args == ()
    assert invalid.value.args == ("dependency_failure",)


def test_attachment_repo_reads_the_seams_cancellation_reasons_per_operation() -> None:
    """Described operations are classified by which one refused: a quota update
    that failed its condition is `quota_exceeded`, a message put that did is a
    concealed resource conflict. A wrapper in the seam would make both
    `retryable_dependency`."""
    from stoa.db.repositories import attachment_repo

    Kind = attachment_repo.TransactionOperationKind
    Outcome = attachment_repo.AttachmentTransactionOutcome
    table = FakeTable()
    table.seed({"PK": "QUOTA#s1", "SK": "STORAGE", "used": 10})
    table.seed({"PK": "CONV#1", "SK": "MSG#m1"})

    def described(kind, operation):
        return attachment_repo.TransactionOperation(kind, operation)

    with pytest.raises(attachment_repo.AttachmentTransactionError) as over_quota:
        attachment_repo.transact(
            [
                described(
                    Kind.STORAGE_QUOTA_UPDATE,
                    {
                        "Update": {
                            "Key": {"PK": "QUOTA#s1", "SK": "STORAGE"},
                            "UpdateExpression": "SET used = used + :n",
                            "ConditionExpression": "used < :cap",
                            "ExpressionAttributeValues": {":n": 1, ":cap": 5},
                        }
                    },
                ),
                described(Kind.MESSAGE_PUT, {"Put": {"Item": {"PK": "CONV#1", "SK": "MSG#new"}}}),
            ],
            table=table,
        )
    with pytest.raises(attachment_repo.AttachmentTransactionError) as concealed:
        attachment_repo.transact(
            [
                described(
                    Kind.MESSAGE_PUT,
                    {
                        "Put": {
                            "Item": {"PK": "CONV#1", "SK": "MSG#m1"},
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                )
            ],
            table=table,
        )

    assert over_quota.value.args == (Outcome.QUOTA_EXCEEDED,)
    assert concealed.value.args == (Outcome.CONCEALED_RESOURCE_CONFLICT,)


def test_attachment_repo_reaches_its_seam_and_stores_its_put_sparse() -> None:
    """The real function reaches `transact_attachment_write`: what production would store."""
    from stoa.db.repositories import attachment_repo

    table = FakeTable()

    attachment_repo.transact(
        [{"Put": {"Item": {"PK": "X", "SK": "Y", "parent_id": None, "note": "kept"}}}],
        table=table,
    )

    assert table.rows[("X", "Y")] == {"PK": "X", "SK": "Y", "note": "kept"}


def test_the_raw_transaction_still_refuses_a_null_that_reaches_the_row() -> None:
    """An expression value is sent as given, so an Update to None is a NULL on the row."""
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "parent_id": "p-1"})

    with pytest.raises(ClientError) as raised:
        table.transact_write_items(
            [
                {
                    "Update": {
                        "Key": {"PK": "ROW", "SK": "META"},
                        "UpdateExpression": "SET parent_id = :none",
                        "ExpressionAttributeValues": {":none": None},
                    }
                }
            ]
        )

    _assert_refused_for_a_null_index_key(raised)
    assert table.rows[("ROW", "META")]["parent_id"] == "p-1"


def test_the_account_transaction_leaves_none_out_like_account_deletion_repo() -> None:
    """`_serialize_operation` drops None from the item, so the row is stored sparse."""
    table = FakeTable()
    table.seed_active_account("a")

    table.transact_account_deletion(
        [
            {
                "ConditionCheck": {
                    "Key": {"PK": "USER#a", "SK": "ACCOUNT_FENCE"},
                    "ConditionExpression": "generation = :g",
                    "ExpressionAttributeValues": {":g": 1},
                }
            },
            {"Put": {"Item": {"PK": "X", "SK": "Y", "parent_id": None, "note": "kept"}}},
        ]
    )

    assert table.rows[("X", "Y")] == {"PK": "X", "SK": "Y", "note": "kept"}


def test_the_account_transaction_refuses_an_expression_naming_a_dropped_value() -> None:
    """`_serialize_operation` drops a None expression value but not the expression."""
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META", "parent_id": "p-1"})

    with pytest.raises(AccountDeletionConflict, match="dependency unavailable") as conflict:
        table.transact_account_deletion(
            [
                {
                    "Update": {
                        "Key": {"PK": "ROW", "SK": "META"},
                        "UpdateExpression": "SET parent_id = :none",
                        "ExpressionAttributeValues": {":none": None},
                    }
                }
            ]
        )

    cause = conflict.value.__cause__
    assert isinstance(cause, ClientError)
    assert cause.response["Error"]["Code"] == "ValidationException"
    assert "attribute value: :none" in cause.response["Error"]["Message"]
    assert table.rows[("ROW", "META")]["parent_id"] == "p-1"


def test_the_account_transaction_reports_a_cancellation_as_a_conditional_conflict() -> None:
    table = FakeTable()
    table.seed({"PK": "X", "SK": "Y"})

    with pytest.raises(AccountDeletionConflict, match="conditional") as conflict:
        table.transact_account_deletion(
            [
                {
                    "Put": {
                        "Item": {"PK": "X", "SK": "Y"},
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                }
            ]
        )

    cause = conflict.value.__cause__
    assert isinstance(cause, ClientError)
    assert cause.response["Error"]["Code"] == "TransactionCanceledException"


def test_the_conversation_transaction_leaves_none_out_the_same_way() -> None:
    """Production sends it through `account_deletion_repo.transact` too."""
    table = FakeTable()

    table.transact_conversation_write(
        [{"Put": {"Item": {"PK": "CONV#1", "SK": "META", "parent_id": None, "status": "open"}}}]
    )

    assert table.rows[("CONV#1", "META")] == {"PK": "CONV#1", "SK": "META", "status": "open"}


def test_every_round_trip_is_counted() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META"})

    table.get_item(Key={"PK": "ROW", "SK": "META"})
    table.scan()
    table.scan()

    assert table.calls == {"get_item": 1, "scan": 2}


def test_is_in_matches_any_of_the_listed_values() -> None:
    """`Attr(...).is_in([...])` keeps its whole list in one slot.

    Read as `values[1:]`, the stored value was compared against a list and
    never matched: every `is_in` filter in this suite returned nothing, and
    `curriculum_ops_repo.list_active_assignment_refs` — which asks whether a
    lesson still has live assignments — looked covered while being answered
    "no" by the double no matter what the table held.
    """
    table = FakeTable()
    table.seed(
        {"PK": "A#1", "SK": "META", "status": "assigned"},
        {"PK": "A#2", "SK": "META", "status": "finished"},
    )

    matched = table.scan(
        FilterExpression=Attr("status").is_in(["recommended", "assigned", "started"])
    )

    assert [row["PK"] for row in matched["Items"]] == ["A#1"]
    assert table.scan(FilterExpression=Attr("status").is_in(["cancelled"]))["Items"] == []
