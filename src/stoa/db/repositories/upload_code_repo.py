"""Phone upload code rows (#146): one row per code, keyed by its public id.

A row holds the SHA-256 of the code's secret and, once a phone has redeemed it, of
the upload token it was exchanged for; never either secret. `expires_at` is the
table's TTL attribute, so a row nobody redeemed disappears on its own. The row
carries `owner_id`, which is what account deletion's sweep of the attachment branch
finds it by, and no `student_id`, which would put it in GSI-StudentId.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


ENTITY_TYPE = "upload_code"


def code_key(code_id: str) -> dict[str, str]:
    return {"PK": f"UPLOADCODE#{code_id}", "SK": "CODE"}


def put_code(item: dict[str, Any], *, table: Any | None = None) -> None:
    (table or get_table()).put_item(
        Item={**item, **code_key(str(item["code_id"])), "entity_type": ENTITY_TYPE},
        ConditionExpression="attribute_not_exists(PK)",
    )


def get_code(code_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(Key=code_key(code_id), ConsistentRead=True)
    item = response.get("Item") if isinstance(response, dict) else None
    return item if isinstance(item, dict) else None


def claim_code(
    code_id: str,
    *,
    now_epoch: int,
    upload_id: str,
    token_sha256: str,
    token_expires_at: int,
    redeemed_at: str,
    table: Any | None = None,
) -> bool:
    """Spend the code: true for exactly one caller, while it is unspent and unexpired.

    The row then lives as long as the upload it started may, so the computer can
    still read where the phone got to.
    """
    try:
        (table or get_table()).update_item(
            Key=code_key(code_id),
            UpdateExpression=(
                "SET #status = :redeemed, upload_id = :upload, token_sha256 = :token, "
                "token_expires_at = :token_expires, redeemed_at = :redeemed_at, "
                "expires_at = :token_expires"
            ),
            ConditionExpression="#status = :issued AND expires_at > :now",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":redeemed": "redeemed",
                ":issued": "issued",
                ":now": now_epoch,
                ":upload": upload_id,
                ":token": token_sha256,
                ":token_expires": token_expires_at,
                ":redeemed_at": redeemed_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def delete_code(code_id: str, *, table: Any | None = None) -> None:
    (table or get_table()).delete_item(Key=code_key(code_id))


def get_conversation(conversation_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(
        Key={"PK": f"CONV#{conversation_id}", "SK": "CONV"}, ConsistentRead=True
    )
    item = response.get("Item") if isinstance(response, dict) else None
    return item if isinstance(item, dict) else None
