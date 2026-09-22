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

from fakes.dynamodb import FakeTable, IndexSchema, apply_update_expression, as_stored


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


def test_every_round_trip_is_counted() -> None:
    table = FakeTable()
    table.seed({"PK": "ROW", "SK": "META"})

    table.get_item(Key={"PK": "ROW", "SK": "META"})
    table.scan()
    table.scan()

    assert table.calls == {"get_item": 1, "scan": 2}
