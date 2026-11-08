"""How an attachment transaction speaks to DynamoDB and reads its answer.

`attachment_repo.transact` classifies a refusal from the error code and the
ordered cancellation reasons alone - a conflict it conceals, a quota it names, a
dependency the caller may retry - and lets nothing of the provider's message
through. The quota condition and the read beside the write are checked against
moto, a real parser, since the table doubles never parse a condition or
serialize twice. Moved here from `test_attachment_security.py` (#254).
"""

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo


def _transaction_cancel_error(
    codes: list[str], *, include_private_diagnostics: bool = True
) -> ClientError:
    reasons: list[dict[str, object]] = []
    for index, code in enumerate(codes):
        reason: dict[str, object] = {"Code": code}
        if include_private_diagnostics:
            reason.update(
                {
                    "Message": f"provider-message-private-canary-{index}",
                    "Item": {
                        "PK": {"S": "UPLOAD#private-key-canary"},
                        "owner_id": {"S": "foreign-owner-private-canary"},
                        "immutable_object_key": {"S": "provider/private-coordinate"},
                    },
                }
            )
        reasons.append(reason)
    error = ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "Amazon DynamoDB private-provider-canary",
            },
        },
        "TransactWriteItems",
    )
    object.__setattr__(
        error,
        "response",
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "Amazon DynamoDB private-provider-canary",
            },
            "CancellationReasons": reasons,
        },
    )
    return error


class _CancellationClient:
    def __init__(self, error: ClientError) -> None:
        self.error = error
        self.items = None

    def transact_write_items(self, *, TransactItems):
        self.items = TransactItems
        raise self.error


class _HighLevelCancellationTable:
    name = "private-table-name-canary"

    def __init__(self, error: ClientError) -> None:
        self.client = _CancellationClient(error)

    def transact_write_items(self, *, TransactItems):
        return self.client.transact_write_items(TransactItems=TransactItems)


class _LowLevelCancellationTable:
    name = "private-table-name-canary"

    def __init__(self, error: ClientError) -> None:
        self.client = _CancellationClient(error)
        self.meta = type("Meta", (), {"client": self.client})()


def _cancellation_table(error: ClientError, *, low_level: bool):
    if low_level:
        return _LowLevelCancellationTable(error)
    return _HighLevelCancellationTable(error)


@pytest.mark.parametrize("low_level", [False, True])
@pytest.mark.parametrize(
    "failed_kind,expected",
    [
        *[
            (kind, attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT)
            for kind in attachment_repo.TransactionOperationKind
            if kind is not attachment_repo.TransactionOperationKind.STORAGE_QUOTA_UPDATE
        ],
        (
            attachment_repo.TransactionOperationKind.STORAGE_QUOTA_UPDATE,
            attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED,
        ),
    ],
)
def test_transaction_operation_index_classification_is_closed_and_redacted(
    low_level, failed_kind, expected, monkeypatch
) -> None:
    operations = [
        attachment_repo.TransactionOperation(kind, {"Put": {"Item": {"PK": kind.value}}})
        for kind in attachment_repo.TransactionOperationKind
    ]
    failed_index = [operation.kind for operation in operations].index(failed_kind)
    codes = ["None"] * len(operations)
    codes[failed_index] = "ConditionalCheckFailed"
    table = _cancellation_table(_transaction_cancel_error(codes), low_level=low_level)
    if low_level:
        # Transactions go through a client built for the purpose, so the double
        # is supplied the same way rather than through the table's own client.
        monkeypatch.setattr(db_table, "client", lambda: table.client)
    with pytest.raises(attachment_repo.AttachmentTransactionError) as error:
        attachment_repo.transact(operations, table=table)
    assert error.value.outcome is expected
    rendered = str(error.value)
    for canary in (
        "provider-message-private-canary",
        "private-key-canary",
        "foreign-owner-private-canary",
        "provider/private-coordinate",
        "Amazon DynamoDB",
        "private-table-name-canary",
    ):
        assert canary not in rendered


@pytest.mark.parametrize(
    "response,expected",
    [
        (
            {"codes": ["TransactionConflict"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"codes": ["ProvisionedThroughputExceeded"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"codes": ["ThrottlingError"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        # A reason that waiting will not fix, and one nobody has named yet: the
        # client is still told to retry - it has nothing better to do - and the
        # gateway writes the refusal down as an error (#271).
        (
            {"codes": ["ValidationError"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"codes": ["ItemCollectionSizeLimitExceeded"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"codes": ["SomethingNew"]},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"codes": []},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
        (
            {"missing": True},
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY,
        ),
    ],
)
def test_transaction_cancellation_dependency_categories_are_retryable(response, expected) -> None:
    operation = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.MESSAGE_PUT,
        {"Put": {"Item": {"PK": "MESSAGE#opaque"}}},
    )
    if response.get("missing"):
        error = ClientError(
            {"Error": {"Code": "TransactionCanceledException", "Message": "private"}},
            "TransactWriteItems",
        )
    else:
        error = _transaction_cancel_error(response["codes"])
    with pytest.raises(attachment_repo.AttachmentTransactionError) as captured:
        attachment_repo.transact([operation], table=_cancellation_table(error, low_level=False))
    assert captured.value.outcome is expected


def test_generic_transaction_client_error_is_retryable_and_redacted() -> None:
    error = ClientError(
        {
            "Error": {
                "Code": "InternalServerError",
                "Message": "raw-provider-reason-private-canary",
            }
        },
        "TransactWriteItems",
    )
    operation = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.MESSAGE_PUT,
        {"Put": {"Item": {"PK": "QUESTION#opaque"}}},
    )
    with pytest.raises(attachment_repo.AttachmentTransactionError) as captured:
        attachment_repo.transact([operation], table=_cancellation_table(error, low_level=False))
    assert (
        captured.value.outcome is attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
    )
    assert "raw-provider-reason-private-canary" not in str(captured.value)


def test_described_transaction_generic_transport_is_retryable_and_redacted() -> None:
    class TransportTable:
        def transact_write_items(self, **_kwargs):
            raise TimeoutError("generic-transaction-provider-table-private-canary")

    operation = attachment_repo.TransactionOperation(
        attachment_repo.TransactionOperationKind.MESSAGE_PUT,
        {"Put": {"Item": {"PK": "MESSAGE#opaque"}}},
    )

    with pytest.raises(attachment_repo.AttachmentTransactionError) as captured:
        attachment_repo.transact([operation], table=TransportTable())

    assert (
        captured.value.outcome
        is attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
    )
    assert "private-canary" not in str(captured.value)


@mock_aws
def test_the_quota_condition_is_a_dialect_the_provider_speaks():
    """Against a parser, not a double: the condition must actually be valid.

    `used_bytes+:size<=:limit` is a syntax error - DynamoDB allows arithmetic
    only in an UpdateExpression's SET - so every attempt to attach a file to a
    message was answered 503 and the production table has never held one
    attachment row. The hand-written table doubles never parse a condition,
    which is how this shipped and stayed green.
    """
    table = boto3.resource("dynamodb", region_name="eu-central-2").create_table(
        TableName="quota-dialect",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    def charge(owner: str, size: int, limit: int) -> None:
        condition, headroom = attachment_repo._storage_quota_condition(limit, size)
        table.update_item(
            Key=attachment_repo.storage_key(owner),
            UpdateExpression=(
                "SET used_bytes=if_not_exists(used_bytes,:zero)+:size, limit_bytes=:limit"
            ),
            ConditionExpression=condition,
            ExpressionAttributeValues={
                ":zero": 0,
                ":size": size,
                ":limit": limit,
                ":headroom": headroom,
            },
        )

    charge("first-upload", 40, 100)
    assert table.get_item(Key=attachment_repo.storage_key("first-upload"))["Item"][
        "used_bytes"
    ] == 40

    # It still fits, and then it does not.
    charge("first-upload", 50, 100)
    with pytest.raises(ClientError) as refused:
        charge("first-upload", 50, 100)
    assert refused.value.response["Error"]["Code"] == "ConditionalCheckFailedException"

    # A file bigger than the whole quota is refused even with no usage row yet:
    # "nothing used so far" must not be what lets it through.
    with pytest.raises(ClientError) as oversized:
        charge("never-used", 200, 100)
    assert oversized.value.response["Error"]["Code"] == "ConditionalCheckFailedException"


@mock_aws
def test_reading_attachments_survives_the_resource_clients_second_serialization():
    """The read beside the write kept the client that serializes twice.

    `db_table.client` exists because the resource table's own client carries
    request transformations, so items already in wire format have every key
    turned into a map. That was known and worked around for `transact` while
    `get_attachments` went on using `target.meta.client`, and the fault sat
    unreachable until the first attachment row in the production table's
    history was written - then reading that conversation answered 500.

    A hand-written double cannot show this: the transformation belongs to
    boto3's resource, so the table has to be a real one.
    """
    resource = boto3.resource("dynamodb", region_name="eu-central-2")
    resource.create_table(
        TableName="stoa-main",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table = resource.Table("stoa-main")
    attachment_id = "be47a9e0-0db5-52ea-937a-2a8dcea1baf7"
    table.put_item(
        Item={
            **attachment_repo.attachment_key(attachment_id),
            "entity_type": "attachment",
            "attachment_id": attachment_id,
            "owner_id": "student-1",
            "status": "active",
        }
    )

    found = attachment_repo.get_attachments([attachment_id], table=table)
    assert list(found) == [attachment_id]
    assert found[attachment_id]["owner_id"] == "student-1"
