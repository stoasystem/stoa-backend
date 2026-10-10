"""#102 against moto: a day's chat counter that reads 0 because its row holds 0.

The claim reads the counter, and on 0 it took the row to be missing and
conditioned the increment on `attribute_not_exists(#count)`. A row that exists
with `count = 0` fails that every time, so every message for the rest of the day
answered 503 `upload_service_unavailable`. Such a row is what the compensation
for a rejected first message leaves (`SET #count=#count-:one`, 1 -> 0), and what
a hand reset to 0 left on 2026-10-10 (stoa-frontend#26).

The hand-written claim doubles do not evaluate condition expressions, which is
how this passed them; moto does.
"""

from __future__ import annotations

from typing import Any

import boto3
from moto import mock_aws

from stoa.db.repositories import attachment_repo

OWNER = "student-1"
PERIOD = "2026-10-10"
EXPIRES = 1791767772


def _table():
    table = boto3.resource("dynamodb", region_name="eu-central-2").create_table(
        TableName="chat-quota-zero",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                              {"AttributeName": "SK", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(Item={"PK": f"USER#{OWNER}", "SK": "ACCOUNT_FENCE",
                         "status": "active", "generation": 1})
    return table


def _command(key: str) -> dict[str, Any]:
    message = f"student-message-{key}"
    return {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": f"command-{key}",
        "conversation_id": "conv-1",
        "owner_id": OWNER,
        "idempotency_key": key,
        "fingerprint": "f" * 64,
        "status": "claimed",
        "student_message_id": message,
        "assistant_message_id": f"assistant-message-{key}",
        "deterministic_attachment_ids": [],
        "requested_attachments": [],
        "quota_period": PERIOD,
        "usage_action": "chat_message",
        "usage_resource_id": message,
        "usage_idempotency_key": f"chat_message:{message}",
        "usage_event_id": f"{OWNER}:chat_message:{PERIOD}:chat_message:{message}",
        "history_anchor_message_id": message,
        "history_anchor_created_at": "2026-10-10T08:55:00+00:00",
        "attempt": 0,
        "created_at": "2026-10-10T08:55:00+00:00",
        "expires_at": EXPIRES,
    }


def _claim(table, key: str) -> attachment_repo.MessageCommandResult:
    return attachment_repo.claim_message_command_and_quota(
        command=_command(key),
        owner_id=OWNER,
        quota_period=PERIOD,
        limit=8,
        expires_at=EXPIRES,
        table=table,
    )


def _count(table) -> int | None:
    item = table.get_item(Key=attachment_repo.chat_quota_key(OWNER, PERIOD),
                          ConsistentRead=True).get("Item")
    return None if item is None else int(item["count"])


@mock_aws
def test_a_day_with_no_counter_row_claims_and_starts_it_at_one():
    table = _table()

    result = _claim(table, "first")

    assert result.disposition is attachment_repo.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_a_counter_row_that_holds_zero_claims_like_a_missing_one():
    table = _table()
    table.put_item(Item={**attachment_repo.chat_quota_key(OWNER, PERIOD),
                         "count": 0, "expires_at": EXPIRES})

    result = _claim(table, "after-reset")

    assert result.disposition is attachment_repo.MessageCommandDisposition.CLAIMED
    assert result.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_the_next_message_claims_after_the_first_was_rejected_and_compensated():
    table = _table()
    assert _claim(table, "first").disposition is attachment_repo.MessageCommandDisposition.CLAIMED

    rejected = attachment_repo.reject_message_command_and_compensate(
        conversation_id="conv-1",
        idempotency_key="first",
        owner_id=OWNER,
        fingerprint="f" * 64,
        error_code="upload_not_found",
        now_iso="2026-10-10T08:55:01+00:00",
        table=table,
    )
    assert rejected.disposition is attachment_repo.MessageCommandDisposition.REJECTED
    assert _count(table) == 0

    second = _claim(table, "second")

    assert second.disposition is attachment_repo.MessageCommandDisposition.CLAIMED
    assert second.counter_value == 1
    assert _count(table) == 1


@mock_aws
def test_a_zero_row_still_refuses_a_claim_that_raced_past_it():
    # The compare-and-set still holds at zero: once another claim has moved the
    # row to 1, a claim built on the 0 it read cannot write 1 over it.
    table = _table()
    table.put_item(Item={**attachment_repo.chat_quota_key(OWNER, PERIOD),
                         "count": 0, "expires_at": EXPIRES})
    stale = attachment_repo.build_message_command_claim_transaction(
        command=_command("stale"),
        owner_id=OWNER,
        quota_period=PERIOD,
        expected_counter=0,
        limit=8,
        expires_at=EXPIRES,
    )
    assert _claim(table, "winner").counter_value == 1

    try:
        attachment_repo.transact(stale, table=table)
    except attachment_repo.AttachmentTransactionError:
        pass
    else:
        raise AssertionError("a claim built on a stale 0 was written")
    assert _count(table) == 1
