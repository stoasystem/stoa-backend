"""Role-neutral single-use invitations for administrator-provisioned accounts.

Kept apart from the teacher application repository on purpose: that key space carries
review semantics (application id and immutable version) that an administrator-issued
invitation does not have, and merging the two would make a plain invitation look like
an approved candidacy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import owner_registry
from stoa.db import table as db_table


class AccountInvitationConflict(RuntimeError):
    """A single-use invitation row already exists."""


type InvitationItem = dict[str, object]


ENTITY_TYPE = "account_invitation"
INVITATION_SK = "META"
POINTER_SK = "POINTER"
# GSI-Email is keyed on the address alone; a page of it ends on the base key and that.
EMAIL_INDEX_KEY = ("PK", "SK", "email")

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
    return candidate or db_table.table()


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


def _put_item(table: object, **kwargs: object) -> None:
    """A conditional put through the gateway: a condition that does not hold is
    `db_table.WriteRefused`, any other answer `db_table.TableUnavailable`."""
    if not isinstance(table, _PutTable):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    db_table.put(table=table, **kwargs)


def _update_item(table: object, **kwargs: object) -> None:
    """A conditional update through the gateway, with `_put_item`'s outcomes."""
    if not isinstance(table, _UpdateTable):
        raise AccountInvitationConflict("account invitation dependency unavailable")
    db_table.update(table=table, **kwargs)


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
        "entity_type": ENTITY_TYPE,
        **dict(item),
    }
    # Written outside `fenced` (an administrator's write, before the invited
    # person has signed in), so the registry rows are written here, before the
    # row that names the accounts (#397): the invited account, whose deletion
    # removes the invitation, and the inviter, whom the daily sweep would
    # otherwise report as named in an unregistered partition.
    for field in ("account_id", "invited_by"):
        account = row.get(field)
        if isinstance(account, str) and account.strip():
            _put_item(
                target,
                Item=owner_registry.registry_item(
                    account.strip(), str(row["PK"]), owner_registry.ROLE_REFERENCE
                ),
            )
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


def issued_invitation_ids(
    accounts: Iterable[Mapping[str, object]], *, table: object | None = None
) -> dict[str, str]:
    """The live invitation each invited account can be reissued from, by account id.

    Card 002-D / B5: reissue resolves an invitation id, not an account id, so the
    console needs the former. Neither the profile nor any key carries it; the only
    way in is the address both rows repeat, through GSI-Email. One call takes a
    whole page of accounts and asks once per distinct address, so two accounts on
    one address cost one query. DynamoDB cannot query several partitions at once,
    so a page of N addresses is still N queries; fewer needs a key that leads from
    the account to its invitation. An account with no issued invitation is absent
    from the answer. The invitation id is a handle, not a credential.
    """
    by_email: dict[str, set[str]] = {}
    for account in accounts:
        email = str(account.get("email") or "").strip()
        account_id = str(account.get("user_id") or "").strip()
        if email and account_id:
            by_email.setdefault(email, set()).add(account_id)
    target = _table(table)
    latest: dict[str, tuple[str, str]] = {}
    for email, account_ids in by_email.items():
        request: dict[str, object] = {
            "IndexName": "GSI-Email",
            "KeyConditionExpression": Key("email").eq(email),
            "FilterExpression": (
                Attr("entity_type").eq("account_invitation")
                & Attr("status").eq(ISSUED_STATUS)
            ),
        }
        try:
            for page in db_table.pages("query", table=target, key=EMAIL_INDEX_KEY, **request):
                for row in map(_response, page.items):
                    account_id = str(row.get("account_id") or "")
                    invitation_id = str(row.get("invitation_id") or "")
                    if account_id not in account_ids or not invitation_id:
                        continue
                    issued_at = str(row.get("issued_at") or "")
                    if account_id not in latest or issued_at >= latest[account_id][0]:
                        latest[account_id] = (issued_at, invitation_id)
        except db_table.TableUnavailable as exc:
            raise AccountInvitationConflict("account invitation dependency unavailable") from exc
    return {account_id: invitation_id for account_id, (_, invitation_id) in latest.items()}


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
    except db_table.WriteRefused:
        return False
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
    except db_table.WriteRefused:
        return False
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
    except db_table.WriteRefused:
        return False
    return True


def _conditional_put(row: InvitationItem, *, table: object) -> None:
    try:
        _put_item(table, Item=row, ConditionExpression=CREATE_CONDITION)
    except db_table.WriteRefused as exc:
        raise AccountInvitationConflict("account invitation already exists") from exc
