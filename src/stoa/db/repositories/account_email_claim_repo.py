"""Durable claims that make `(address, role)` the account uniqueness key.

Shaped after `account_number_repo`: one placeholder row per claimed pair, taken by a
conditional write that no read can stand in for. A query on `GSI-Email` is eventually
consistent, so two administrators opening the same person in the same second both see
the address free; only the store can break that tie.

The key is the pair, not the address alone. One person legitimately holds a teacher
account and a parent account on the same address - a teacher at the school whose own
child studies there - so `(address, teacher)` and `(address, parent)` are two claims,
while a second `(address, teacher)` is the duplicate this row exists to refuse.

Two differences from the number claim, both deliberate:

* a number is never recycled, an address always is, so this row also knows how to be
  given back when an opening dies part-way (`release_operation`);
* the address is stored as `claimed_email`, never as `email`, so the placeholder stays
  out of `GSI-Email` and cannot be mistaken for the profile that holds the address.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from stoa.db.dynamodb import get_table


CLAIM_SK = "EMAIL_CLAIM"

CLAIM_CONDITION = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
# An opening that never wrote its claim, or one already given back, must not turn the
# compensation itself into a failure; a claim held by another account must survive it.
RELEASE_CONDITION = "attribute_not_exists(PK) OR account_id = :account_id"


type ClaimItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _response(value: object) -> ClaimItem:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("account email claim dependency unavailable")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _get_item(table: object, **kwargs: object) -> ClaimItem:
    if not isinstance(table, _GetTable):
        raise ValueError("account email claim dependency unavailable")
    return _response(table.get_item(**kwargs))


def normalize_email(value: object) -> str:
    """One address in the single form the key is built from."""
    address = str(value or "").strip().casefold()
    if not address or "@" not in address:
        raise ValueError("account email claim requires a normalized address")
    return address


def _role(value: object) -> str:
    """One role that cannot smuggle the separator into the key.

    Roles come from a closed set upstream. Refusing `#` here is what keeps the pair
    unambiguous even if that set ever grows.
    """
    role = str(value or "").strip()
    if not role or "#" in role:
        raise ValueError("account email claim requires a plain role")
    return role


def claim_key(*, email: str, role: str) -> dict[str, str]:
    """Primary key of the placeholder that owns one `(address, role)` pair."""
    return {"PK": f"EMAIL#{normalize_email(email)}#{_role(role)}", "SK": CLAIM_SK}


def claim_item(
    *, email: str, role: str, account_id: str, created_at: str
) -> dict[str, Any]:
    """The stored placeholder, address included under a name the index ignores."""
    return {
        **claim_key(email=email, role=role),
        "entity_type": "account_email_claim",
        "claimed_email": normalize_email(email),
        "role": _role(role),
        "account_id": str(account_id),
        "created_at": str(created_at),
    }


def claim_operation(
    *, email: str, role: str, account_id: str, created_at: str
) -> dict[str, Any]:
    """Take the pair, for a transaction that also writes the profile holding it.

    Returned rather than written: the claim and the profile are one commit, so an
    address that is already taken leaves no half-opened account behind.
    """
    return {
        "Put": {
            "Item": claim_item(
                email=email, role=role, account_id=account_id, created_at=created_at
            ),
            "ConditionExpression": CLAIM_CONDITION,
        }
    }


def release_operation(*, email: str, role: str, account_id: str) -> dict[str, Any]:
    """Give the pair back, for the transaction that parks the failed account."""
    return {
        "Delete": {
            "Key": claim_key(email=email, role=role),
            "ConditionExpression": RELEASE_CONDITION,
            "ExpressionAttributeValues": {":account_id": str(account_id)},
        }
    }


def get_claim(
    *, email: str, role: str, table: object | None = None
) -> ClaimItem | None:
    """Read one claim, or None when the pair was never taken."""
    response = _get_item(
        _table(table), Key=claim_key(email=email, role=role), ConsistentRead=True
    )
    item = response.get("Item")
    if not isinstance(item, dict):
        return None
    return _response(item)
