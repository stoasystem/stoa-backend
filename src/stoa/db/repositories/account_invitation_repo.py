"""Role-neutral single-use invitations for administrator-provisioned accounts.

Kept apart from the teacher application repository on purpose: that key space carries
review semantics (application id and immutable version) that an administrator-issued
invitation does not have, and merging the two would make a plain invitation look like
an approved candidacy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class AccountInvitationConflict(RuntimeError):
    """A single-use invitation row already exists."""


type InvitationItem = dict[str, object]


INVITATION_SK = "META"
POINTER_SK = "POINTER"

CREATE_CONDITION = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
ISSUED_CONDITION = "#status = :issued AND #version = :expected_version"
BURNED_CONDITION = "#status = :used AND #version = :expected_version"
# The revocation stamp is part of the identity on purpose: it is what makes this the
# revocation one caller performed rather than any revocation the row has ever carried.
RETIRED_CONDITION = (
    "#status = :revoked AND #version = :expected_version AND #revoked_at = :revoked_at"
)

ISSUED_STATUS = "issued"
USED_STATUS = "used"
REVOKED_STATUS = "revoked"


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _response(value: object) -> InvitationItem:
    if not isinstance(value, Mapping):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    item: InvitationItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise AccountInvitationConflict("account invitation dependency unavailable")
        item[key] = member
    return item


def _get_item(table: object, **kwargs: object) -> InvitationItem:
    if not isinstance(table, _GetTable):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    return table.put_item(**kwargs)


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    return table.update_item(**kwargs)


def _conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _required_text(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AccountInvitationConflict("invalid account invitation input")
    return value


# Same-shaped stand-in for a digest that is not on file. Returning it through the
# ordinary projection keeps a miss and a hit on the same code path, so the caller
# cannot tell them apart by how long the lookup took.
ABSENT_INVITATION: Mapping[str, object] = {
    "PK": "ACCOUNT_INVITATION#absent",
    "SK": INVITATION_SK,
    "entity_type": "account_invitation",
    "invitation_id": "",
    "token_digest": "",
    "account_id": "",
    "role": "",
    "email": "",
    "full_name": "",
    "account_number": "",
    "status": ISSUED_STATUS,
    "version": 1,
    "invited_by": "",
    "issued_at": "1970-01-01T00:00:00+00:00",
    "expires_at": 0,
    "expires_at_iso": "1970-01-01T00:00:00+00:00",
}


def absent_invitation(*, token_digest: str) -> InvitationItem:
    """Project one stand-in row whose digest never matches the digest asked for."""
    return {**_response(ABSENT_INVITATION), "token_digest": f"absent:{token_digest}"}


def invitation_key(token_digest: str) -> dict[str, str]:
    """Primary key of the invitation row, addressed by token digest only."""
    return {"PK": f"ACCOUNT_INVITATION#{token_digest}", "SK": INVITATION_SK}


def pointer_key(invitation_id: str) -> dict[str, str]:
    """Primary key of the administrative pointer from invitation id to digest."""
    return {"PK": f"ACCOUNT_INVITATION_ID#{invitation_id}", "SK": POINTER_SK}


def create_invitation(item: Mapping[str, object], *, table: object | None = None) -> InvitationItem:
    """Write one issued invitation plus the pointer administrators revoke it by.

    The pointer goes first: a dangling pointer reads as a missing invitation, while a
    dangling invitation would be unrevocable.
    """
    token_digest = _required_text(item, "token_digest")
    invitation_id = _required_text(item, "invitation_id")
    target = _table(table)
    pointer = {
        **pointer_key(invitation_id),
        "entity_type": "account_invitation_pointer",
        "invitation_id": invitation_id,
        "token_digest": token_digest,
    }
    _conditional_put(pointer, table=target)
    row = {
        **invitation_key(token_digest),
        "entity_type": "account_invitation",
        **dict(item),
    }
    _conditional_put(row, table=target)
    return row


def get_invitation(token_digest: str, *, table: object | None = None) -> InvitationItem | None:
    """Read one invitation by token digest, or None when no such digest exists."""
    response = _get_item(
        _table(table), Key=invitation_key(token_digest), ConsistentRead=True
    )
    item = response.get("Item")
    if not isinstance(item, Mapping):
        return None
    return _response(item)


def get_invitation_by_id(
    invitation_id: str, *, table: object | None = None
) -> InvitationItem | None:
    """Resolve an administrative invitation id to its stored invitation."""
    target = _table(table)
    response = _get_item(target, Key=pointer_key(invitation_id), ConsistentRead=True)
    pointer = response.get("Item")
    if not isinstance(pointer, Mapping):
        return None
    digest = pointer.get("token_digest")
    if not isinstance(digest, str) or not digest:
        return None
    return get_invitation(digest, table=target)


def claim_invitation(
    token_digest: str, *, used_at: str, table: object | None = None
) -> bool:
    """Burn one invitation, returning False when it was already burned or revoked."""
    return _transition(
        token_digest,
        next_status=USED_STATUS,
        stamp_field="used_at",
        stamp=used_at,
        table=table,
    )


def revoke_invitation(
    token_digest: str, *, revoked_at: str, table: object | None = None
) -> bool:
    """Retire one unused invitation, returning False when it already moved on."""
    return _transition(
        token_digest,
        next_status=REVOKED_STATUS,
        stamp_field="revoked_at",
        stamp=revoked_at,
        table=table,
    )


def restore_invitation(
    token_digest: str, *, restored_at: str, table: object | None = None
) -> bool:
    """Hand one burned invitation back when the activation it was burned for failed.

    Conditional on the exact row this caller burned - `used` and still at version 2 -
    so a restore can never resurrect an invitation somebody else has since moved on,
    and never reopens one that was revoked. The original expiry is left untouched, so
    giving the token back is not a way to extend it.
    """
    try:
        _update_item(
            _table(table),
            Key=invitation_key(token_digest),
            UpdateExpression=(
                "SET #status = :issued, restored_at = :stamp, #version = :next_version"
            ),
            ConditionExpression=BURNED_CONDITION,
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":used": USED_STATUS,
                ":issued": ISSUED_STATUS,
                ":stamp": restored_at,
                ":expected_version": 2,
                ":next_version": 1,
            },
        )
    except ClientError as exc:
        if _conditional_failure(exc):
            return False
        raise
    return True


def restore_revoked_invitation(
    token_digest: str, *, revoked_at: str, restored_at: str, table: object | None = None
) -> bool:
    """Undo one revocation whose replacement was never written.

    Conditional on the exact row this caller retired - `revoked`, still at version 2
    and still carrying the stamp that retirement wrote - so it can only give back a
    revocation this same operation performed. Every other revoked invitation stays
    revoked, which is what keeps a reissue from becoming a second live token.
    """
    try:
        _update_item(
            _table(table),
            Key=invitation_key(token_digest),
            UpdateExpression=(
                "SET #status = :issued, restored_at = :stamp, #version = :next_version"
            ),
            ConditionExpression=RETIRED_CONDITION,
            ExpressionAttributeNames={
                "#status": "status",
                "#version": "version",
                "#revoked_at": "revoked_at",
            },
            ExpressionAttributeValues={
                ":revoked": REVOKED_STATUS,
                ":issued": ISSUED_STATUS,
                ":revoked_at": revoked_at,
                ":stamp": restored_at,
                ":expected_version": 2,
                ":next_version": 1,
            },
        )
    except ClientError as exc:
        if _conditional_failure(exc):
            return False
        raise
    return True


def _transition(
    token_digest: str,
    *,
    next_status: str,
    stamp_field: str,
    stamp: str,
    table: object | None,
) -> bool:
    try:
        _update_item(
            _table(table),
            Key=invitation_key(token_digest),
            UpdateExpression=(
                "SET #status = :next_status, #stamp_field = :stamp, "
                "#version = :next_version"
            ),
            ConditionExpression=ISSUED_CONDITION,
            ExpressionAttributeNames={
                "#status": "status",
                "#stamp_field": stamp_field,
                "#version": "version",
            },
            ExpressionAttributeValues={
                ":issued": ISSUED_STATUS,
                ":next_status": next_status,
                ":stamp": stamp,
                ":expected_version": 1,
                ":next_version": 2,
            },
        )
    except ClientError as exc:
        if _conditional_failure(exc):
            return False
        raise
    return True


def _conditional_put(row: InvitationItem, *, table: object) -> None:
    try:
        _put_item(table, Item=row, ConditionExpression=CREATE_CONDITION)
    except ClientError as exc:
        if _conditional_failure(exc):
            raise AccountInvitationConflict("account invitation already exists") from exc
        raise
