"""Durable claim records for permanently assigned account numbers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table, stored_int


CLAIM_SK = "ACCOUNT_NUMBER"
ALLOCATION_HINT_SK = "ACCOUNT_NUMBER_SEQUENCE"

CLAIM_CONDITION = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
HINT_CONDITION = "attribute_not_exists(PK) OR last_sequence < :sequence"


type NumberItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _response(value: object) -> NumberItem:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("account number dependency unavailable")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _get_item(table: object, **kwargs: object) -> NumberItem:
    if not isinstance(table, _GetTable):
        raise ValueError("account number dependency unavailable")
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise ValueError("account number dependency unavailable")
    return table.put_item(**kwargs)


def _conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def claim_key(account_number: str) -> dict[str, str]:
    """Primary key of the placeholder item that owns one account number."""
    return {"PK": f"ACCOUNT_NUMBER#{account_number}", "SK": CLAIM_SK}


def allocation_hint_key(*, role: str, year: int) -> dict[str, str]:
    """Primary key of the per-role, per-year allocation cursor."""
    return {"PK": f"ACCOUNT_NUMBER_SEQUENCE#{role}#{year}", "SK": ALLOCATION_HINT_SK}


def claim_account_number(
    *,
    account_number: str,
    role: str,
    year: int,
    sequence: int,
    account_id: str,
    created_at: str,
    table: object | None = None,
) -> bool:
    """Take permanent ownership of one number, returning False when already taken."""
    item = {
        **claim_key(account_number),
        "entity_type": "account_number",
        "account_number": account_number,
        "role": role,
        "year": year,
        "sequence": sequence,
        "account_id": account_id,
        "created_at": created_at,
    }
    try:
        _put_item(_table(table), Item=item, ConditionExpression=CLAIM_CONDITION)
    except ClientError as exc:
        if _conditional_failure(exc):
            return False
        raise
    return True


def get_account_number_claim(
    account_number: str, *, table: object | None = None
) -> NumberItem | None:
    """Read one claim item, or None when the number was never assigned."""
    response = _get_item(
        _table(table), Key=claim_key(account_number), ConsistentRead=True
    )
    item = response.get("Item")
    if not isinstance(item, dict):
        return None
    return _response(item)


def read_allocation_hint(*, role: str, year: int, table: object | None = None) -> int:
    """Highest sequence known to be taken.

    Advisory only: uniqueness comes from the conditional claim write, never from
    this value.
    """
    response = _get_item(
        _table(table), Key=allocation_hint_key(role=role, year=year), ConsistentRead=True
    )
    item = response.get("Item")
    if not isinstance(item, dict):
        return 0
    last = stored_int(item.get("last_sequence"))
    if last is None:
        return 0
    return max(last, 0)


def advance_allocation_hint(
    *, role: str, year: int, sequence: int, table: object | None = None
) -> None:
    """Move the cursor forward, ignoring losers of a concurrent advance."""
    item = {
        **allocation_hint_key(role=role, year=year),
        "entity_type": "account_number_sequence",
        "role": role,
        "year": year,
        "last_sequence": sequence,
    }
    try:
        _put_item(
            _table(table),
            Item=item,
            ConditionExpression=HINT_CONDITION,
            ExpressionAttributeValues={":sequence": sequence},
        )
    except ClientError as exc:
        if _conditional_failure(exc):
            return
        raise
