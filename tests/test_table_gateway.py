"""The table gateway: one serializer, one sender, two ways to fail (#296, #210).

Every repository's transaction reaches DynamoDB through `db_table.transact`. What
these tests pin is what it sends, and how it reads what comes back - in particular
the cancellation reasons, whose classification used to exist twice and disagree,
and whose catch-all once answered the same as its named cases (#271).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from fakes.dynamodb import FakeTable
from stoa.config import settings
from stoa.db import table as db_table

Kind = db_table.ReasonKind


# -- the reason classifier ------------------------------------------------------------


@pytest.mark.parametrize(
    "code,kind",
    [
        ("None", Kind.NOT_THE_CAUSE),
        ("ConditionalCheckFailed", Kind.CONDITION_FAILED),
        ("TransactionConflict", Kind.TRANSACTION_CONFLICT),
        ("ProvisionedThroughputExceeded", Kind.RETRYABLE),
        ("ThrottlingError", Kind.RETRYABLE),
        # Known, and not fixed by waiting: the request itself cannot succeed.
        ("ValidationError", Kind.OTHER),
        ("ItemCollectionSizeLimitExceeded", Kind.OTHER),
        # Not known at all. Not retryable either - nothing says waiting helps.
        ("SomethingNew", Kind.OTHER),
        ("", Kind.OTHER),
        (None, Kind.OTHER),
        (7, Kind.OTHER),
    ],
)
def test_every_reason_code_has_one_kind(code: object, kind: db_table.ReasonKind) -> None:
    assert db_table.classify_reason(code) is kind


def test_the_named_retryable_codes_and_the_fallback_are_told_apart() -> None:
    """#271: the named set and the catch-all used to return the same value."""
    named = {db_table.classify_reason(code) for code in db_table.RETRYABLE_REASON_CODES}
    assert named == {Kind.RETRYABLE}
    assert db_table.classify_reason("SomethingNew") is not Kind.RETRYABLE


@pytest.mark.parametrize(
    "response,count,expected",
    [
        (
            {"CancellationReasons": [{"Code": "None"}, {"Code": "ConditionalCheckFailed"}]},
            2,
            [("None", Kind.NOT_THE_CAUSE), ("ConditionalCheckFailed", Kind.CONDITION_FAILED)],
        ),
        (
            {"CancellationReasons": [{"Code": "SomethingNew"}, {"Message": "no code"}, "junk"]},
            3,
            [
                ("SomethingNew", Kind.OTHER),
                ("<unreadable>", Kind.OTHER),
                ("<unreadable>", Kind.OTHER),
            ],
        ),
        # Missing, empty, malformed, or not one per operation: nothing can be read.
        ({}, 1, []),
        ({"CancellationReasons": []}, 1, []),
        ({"CancellationReasons": "junk"}, 1, []),
        ({"CancellationReasons": [{"Code": "None"}]}, 2, []),
    ],
)
def test_reasons_are_read_one_per_operation_or_not_at_all(
    response: dict[str, Any], count: int, expected: list[tuple[str, db_table.ReasonKind]]
) -> None:
    reasons = db_table.cancellation_reasons(response, count)
    assert [(reason.code, reason.kind) for reason in reasons] == expected


# -- what is sent ---------------------------------------------------------------------


class _Recording:
    name = "stoa-recorded"

    def __init__(self, error: BaseException | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.error = error

    def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
        self.sent.extend(TransactItems)
        if self.error is not None:
            raise self.error


def test_none_is_left_out_of_every_value_map_and_the_table_is_named() -> None:
    table = _Recording()

    db_table.transact(
        [
            {
                "Update": {
                    "Key": {"PK": "P", "SK": "S", "stray": None},
                    "UpdateExpression": "SET a = :a",
                    "ExpressionAttributeValues": {":a": 1, ":unused": None},
                }
            },
            {"Put": {"Item": {"PK": "Q", "SK": "S", "parent_id": None, "nested": {"x": None}}}},
        ],
        table=table,
    )

    assert table.sent == [
        {
            "Update": {
                "Key": {"PK": {"S": "P"}, "SK": {"S": "S"}},
                "UpdateExpression": "SET a = :a",
                "ExpressionAttributeValues": {":a": {"N": "1"}},
                "TableName": "stoa-recorded",
            }
        },
        {
            "Put": {
                "Item": {
                    "PK": {"S": "Q"},
                    "SK": {"S": "S"},
                    "nested": {"M": {"x": {"NULL": True}}},
                },
                "TableName": "stoa-recorded",
            }
        },
    ]


def test_a_double_without_a_name_is_sent_the_configured_table() -> None:
    table = FakeTable()
    db_table.transact([{"Put": {"Item": {"PK": "P", "SK": "S"}}}], table=table)
    ((_, request),) = [entry for entry in table.requests if entry[0] == "transact_write_items"]
    assert request["operations"] == [{"Put": {"Item": {"PK": "P", "SK": "S"}}}]
    assert table.rows[("P", "S")] == {"PK": "P", "SK": "S"}


@pytest.mark.parametrize(
    "operation",
    [
        {"Put": {"Item": {"PK": "P"}}, "Delete": {"Key": {"PK": "P"}}},
        {"Upsert": {"Item": {"PK": "P"}}},
        {"Put": "not a body"},
        {"Put": {"Item": ["not", "a", "map"]}},
    ],
)
def test_a_malformed_operation_is_a_programming_error(operation: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        db_table.transact([operation], table=_Recording())


def test_the_real_table_is_sent_on_the_gateways_own_client(monkeypatch) -> None:
    """Never the resource's `meta.client`: it would serialize the wire format again."""
    gateway_client = _Recording()
    resource_client = _Recording(AssertionError("the resource's client was used"))

    class _ResourceTable:
        name = "stoa-main"
        meta = type("Meta", (), {"client": resource_client})()

    monkeypatch.setattr(db_table, "client", lambda: gateway_client)
    db_table.transact([{"Put": {"Item": {"PK": "P", "SK": "S"}}}], table=_ResourceTable())

    assert gateway_client.sent == [
        {"Put": {"Item": {"PK": {"S": "P"}, "SK": {"S": "S"}}, "TableName": "stoa-main"}}
    ]
    assert resource_client.sent == []


def test_the_client_is_built_once_in_the_configured_region(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    db_table.client.cache_clear()
    try:
        first = db_table.client()
        assert db_table.client() is first
    finally:
        db_table.client.cache_clear()
    assert first.meta.service_model.service_name == "dynamodb"
    assert first.meta.region_name == settings.aws_region


def test_something_with_no_transaction_entry_is_unavailable() -> None:
    class _ReadOnly:
        def get_item(self, **_kwargs: Any) -> dict[str, Any]:
            return {}

    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.transact([{"Put": {"Item": {"PK": "P", "SK": "S"}}}], table=_ReadOnly())
    assert unavailable.value.code == "no_transaction_entry"


def test_the_installed_table_is_the_default(fake_table: FakeTable) -> None:
    assert db_table.table() is fake_table

    db_table.transact([{"Put": {"Item": {"PK": "P", "SK": "S"}}}])

    assert ("P", "S") in fake_table.rows


# -- what comes back ------------------------------------------------------------------


def _cancelled(*codes: object) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
            "CancellationReasons": [{"Code": code} for code in codes],
        },
        "TransactWriteItems",
    )


_TWO_PUTS = [
    {"Put": {"Item": {"PK": "A", "SK": "S"}}},
    {"Put": {"Item": {"PK": "B", "SK": "S"}}},
]


@pytest.mark.parametrize(
    "codes,causes,failed",
    [
        (("None", "ConditionalCheckFailed"), {Kind.CONDITION_FAILED}, (1,)),
        (("TransactionConflict", "None"), {Kind.TRANSACTION_CONFLICT}, ()),
        (("ThrottlingError", "None"), {Kind.RETRYABLE}, ()),
        (("ValidationError", "None"), {Kind.OTHER}, ()),
        (("SomethingNew", "ConditionalCheckFailed"), {Kind.OTHER, Kind.CONDITION_FAILED}, (1,)),
    ],
)
def test_a_cancellation_is_refused_with_each_operations_reason(
    codes: tuple[str, ...], causes: set[db_table.ReasonKind], failed: tuple[int, ...]
) -> None:
    error = _cancelled(*codes)

    with pytest.raises(db_table.WriteRefused) as refused:
        db_table.transact(_TWO_PUTS, table=_Recording(error))

    assert refused.value.code == "TransactionCanceledException"
    assert [reason.code for reason in refused.value.reasons] == list(codes)
    assert refused.value.causes == causes
    assert refused.value.failed_conditions == failed
    assert refused.value.__cause__ is error


def test_a_cancellation_without_readable_reasons_is_still_refused() -> None:
    with pytest.raises(db_table.WriteRefused) as refused:
        db_table.transact(_TWO_PUTS, table=_Recording(_cancelled("None")))
    assert refused.value.reasons == ()
    assert refused.value.causes == frozenset()


def test_a_single_conditional_failure_is_refused_without_reasons() -> None:
    error = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "no"}}, "PutItem"
    )
    with pytest.raises(db_table.WriteRefused) as refused:
        db_table.transact(_TWO_PUTS, table=_Recording(error))
    assert refused.value.code == "ConditionalCheckFailedException"
    assert refused.value.reasons == ()


@pytest.mark.parametrize(
    "code", ["ValidationException", "ThrottlingException", "InternalServerError", "Unknown"]
)
def test_any_other_provider_error_is_unavailable(code: str) -> None:
    error = ClientError({"Error": {"Code": code, "Message": "no"}}, "TransactWriteItems")
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.transact(_TWO_PUTS, table=_Recording(error))
    assert unavailable.value.code == code
    assert unavailable.value.__cause__ is error


def test_an_unreachable_table_is_unavailable() -> None:
    error = EndpointConnectionError(endpoint_url="https://dynamodb.invalid")
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.transact(_TWO_PUTS, table=_Recording(error))
    assert unavailable.value.code == "EndpointConnectionError"


def test_anything_else_a_double_raises_is_passed_on_untouched() -> None:
    with pytest.raises(TimeoutError):
        db_table.transact(_TWO_PUTS, table=_Recording(TimeoutError("slow")))


def test_neither_outcome_is_a_deletion_conflict() -> None:
    """`AccountDeletionConflict` means the deletion flow lost a race, and nothing else."""
    from stoa.db.repositories.account_deletion_repo import AccountDeletionConflict

    assert not issubclass(db_table.WriteRefused, AccountDeletionConflict)
    assert not issubclass(db_table.TableUnavailable, AccountDeletionConflict)


def test_a_reason_that_waiting_will_not_fix_is_logged_as_an_error(caplog) -> None:
    owner = "11111111-2222-3333-4444-555555555555"
    operations = [
        {"Put": {"Item": {"PK": f"ATTACHMENT#{owner}", "SK": "META"}}},
        {"Put": {"Item": {"PK": f"OWNER#{owner}", "SK": "STORAGE"}}},
    ]
    with caplog.at_level(logging.INFO, logger=db_table.__name__):
        with pytest.raises(db_table.WriteRefused):
            db_table.transact(operations, table=_Recording(_cancelled("None", "ValidationError")))

    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "transaction_refused_for_good" in message
    assert "Put:ATTACHMENT/META Put:OWNER/STORAGE" in message
    assert owner not in message


def test_a_condition_race_is_not_logged_as_an_error(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=db_table.__name__):
        with pytest.raises(db_table.WriteRefused):
            db_table.transact(
                _TWO_PUTS, table=_Recording(_cancelled("None", "ConditionalCheckFailed"))
            )
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


# -- one item (#330) --------------------------------------------------------------------


def test_one_item_is_read_written_and_deleted_through_the_gateway(fake_table) -> None:
    key = {"PK": "UPLOADCODE#c1", "SK": "CODE"}

    assert db_table.get(Key=key) is None
    assert db_table.put(Item={**key, "status": "issued"}) == {}
    assert db_table.get(Key=key, ConsistentRead=True) == {**key, "status": "issued"}
    updated = db_table.update(
        Key=key,
        UpdateExpression="SET #status = :redeemed",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":redeemed": "redeemed"},
        ReturnValues="ALL_NEW",
    )
    assert updated == {**key, "status": "redeemed"}
    db_table.delete(Key=key)
    assert db_table.get(Key=key) is None


def test_a_single_write_whose_condition_fails_is_refused_by_its_condition(fake_table) -> None:
    key = {"PK": "UPLOADCODE#c1", "SK": "CODE"}
    db_table.put(Item=key)

    with pytest.raises(db_table.WriteRefused) as refused:
        db_table.put(Item=key, ConditionExpression="attribute_not_exists(PK)")

    assert refused.value.condition_failed
    assert refused.value.reasons == ()
    assert isinstance(refused.value.__cause__, ClientError)


def test_a_transaction_refusal_says_whether_a_condition_was_the_cause() -> None:
    reason = db_table.CancellationReason
    by_condition = db_table.WriteRefused(
        "TransactionCanceledException",
        [reason("None", Kind.NOT_THE_CAUSE), reason("ConditionalCheckFailed", Kind.CONDITION_FAILED)],
    )
    by_conflict = db_table.WriteRefused(
        "TransactionCanceledException", [reason("TransactionConflict", Kind.TRANSACTION_CONFLICT)]
    )

    assert by_condition.condition_failed
    assert not by_conflict.condition_failed
    assert not db_table.WriteRefused("TransactionCanceledException").condition_failed


class _Answers:
    def __init__(self, answer: object = None, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error

    def _call(self, **_request: object) -> object:
        if self.error is not None:
            raise self.error
        return self.answer

    get_item = put_item = update_item = delete_item = _call


@pytest.mark.parametrize("write", [db_table.put, db_table.update, db_table.delete])
def test_a_single_write_the_table_could_not_take_is_unavailable(write) -> None:
    throttled = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow"}},
        "UpdateItem",
    )
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        write(table=_Answers(error=throttled), Key={"PK": "A", "SK": "B"})
    assert unavailable.value.code == "ProvisionedThroughputExceededException"

    with pytest.raises(db_table.TableUnavailable):
        write(table=_Answers(error=EndpointConnectionError(endpoint_url="x")), Key={})


def test_a_read_passes_the_tables_own_errors_through_untouched() -> None:
    throttled = ClientError({"Error": {"Code": "ThrottlingException"}}, "GetItem")

    with pytest.raises(ClientError):
        db_table.get(table=_Answers(error=throttled), Key={"PK": "A", "SK": "B"})


@pytest.mark.parametrize(
    "call,answer",
    [
        (db_table.get, ["not", "a", "response"]),
        (db_table.get, {"Item": "not an item"}),
        (db_table.update, {"Attributes": ["not", "attributes"]}),
        (db_table.put, "not a response"),
    ],
)
def test_an_answer_that_is_not_an_item_is_unavailable(call, answer) -> None:
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        call(table=_Answers(answer), Key={"PK": "A", "SK": "B"})
    assert unavailable.value.code == "malformed_response"


def test_a_double_without_the_entry_is_unavailable() -> None:
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.update(table=object(), Key={"PK": "A", "SK": "B"})
    assert unavailable.value.code == "no_update_item_entry"


def test_a_write_answered_with_nothing_hands_back_nothing() -> None:
    assert db_table.put(table=_Answers(None), Item={"PK": "A", "SK": "B"}) == {}
