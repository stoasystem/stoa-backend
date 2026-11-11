"""Permanent account lifecycle fence and resumable deletion command persistence."""

from __future__ import annotations

import logging

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from hashlib import sha256
import json
from collections.abc import Callable, Iterator
from itertools import islice
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_email_claim_repo


type AccountDeletionItem = dict[str, object]


logger = logging.getLogger(__name__)


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


def _dependency_mapping(value: object) -> AccountDeletionItem:
    if not isinstance(value, Mapping):
        raise AccountDeletionConflict("malformed account deletion dependency response")
    result: AccountDeletionItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise AccountDeletionConflict(
                "malformed account deletion dependency response"
            )
        result[key] = member
    return result


def _get_item(table: object, **kwargs: object) -> AccountDeletionItem:
    if not isinstance(table, _GetTable):
        raise AccountDeletionConflict("account deletion dependency unavailable")
    return _dependency_mapping(table.get_item(**kwargs))


def _update_item(table: object, **kwargs: object) -> dict[str, Any]:
    """One conditional update through the gateway; the attributes it hands back.

    A condition that does not hold is `db_table.WriteRefused`; anything else the
    table answers is `db_table.TableUnavailable`.
    """
    if not isinstance(table, _UpdateTable):
        raise AccountDeletionConflict("account deletion dependency unavailable")
    return db_table.update(table=table, **kwargs)


class AccountDeletionConflict(RuntimeError):
    """A lifecycle mutation did not match the permanent fence generation."""


class AccountNotWritable(AccountDeletionConflict):
    """The owner's account fence is missing, not active, or not the generation the
    write was made under. Nothing was written. `stoa.db.table.fenced` raises it,
    whether it found this out reading the fence or from the transaction itself.
    """


class DeletionCommandClaimLost(AccountDeletionConflict):
    """The deletion worker no longer owns the exact durable command state."""


class AccountDeletionRowConflict(AccountDeletionConflict):
    """A scanned private row changed before its narrow deletion mutation."""


@dataclass(frozen=True, slots=True)
class DeletionCommandClaim:
    """Opaque lease/CAS coordinates; never contains student content."""

    command_id: str
    generation: int
    lease_owner: str
    lease_expires_at: int
    command_version: int
    branch_results_digest: str
    # The command's account, so the command is read by its key rather than found
    # by a scan of the whole table (#397). A claim made from a row without one
    # (only test doubles) falls back to the lookup by id.
    user_id: str | None = None


@dataclass(frozen=True, slots=True)
class OwnedPrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None


def _valid_lifecycle_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountDeletionConflict("invalid lifecycle timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AccountDeletionConflict("invalid lifecycle timestamp") from exc
    offset = parsed.utcoffset() if parsed.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        raise AccountDeletionConflict("invalid lifecycle timestamp")
    return value


def _canonical_number(value: object) -> object:
    """A stored number written the way it was before the table returned it.

    The digest is computed on the way in from `int`, and checked on the way
    back out against `Decimal`, which `json.dumps` refuses outright. So the
    check could never pass against a real table: every continuation raised
    "invalid deletion branch results" and no deletion ever advanced past the
    pass the request itself made. Rendering a whole Decimal as the `int` it was
    reproduces the digest that was stored.
    """
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def branch_results_digest(results: Mapping[str, Any]) -> str:
    if not isinstance(results, Mapping):
        raise AccountDeletionConflict("invalid deletion branch results")
    try:
        canonical = json.dumps(
            dict(results),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=_canonical_number,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AccountDeletionConflict("invalid deletion branch results") from exc
    return sha256(canonical).hexdigest()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AccountDeletionConflict(f"invalid {field}")
    return value


def _claim_from_command(command: Mapping[str, Any]) -> DeletionCommandClaim:
    owner = _required(command.get("lease_owner"), "lease_owner")
    digest = _required(command.get("branch_results_digest"), "branch_results_digest")
    if len(digest) != 64:
        raise AccountDeletionConflict("invalid branch results digest")
    raw_version = command.get("command_version") or command.get("version")
    user_id = command.get("user_id")
    return DeletionCommandClaim(
        command_id=_required(command.get("command_id"), "command_id"),
        generation=_positive_int(stored_int(command.get("generation")), "generation"),
        lease_owner=owner,
        lease_expires_at=_positive_int(
            stored_int(command.get("lease_expires_at")), "lease expiry"
        ),
        command_version=_positive_int(stored_int(raw_version), "command version"),
        branch_results_digest=digest,
        user_id=user_id.strip() if isinstance(user_id, str) and user_id.strip() else None,
    )


PRIVATE_QUESTION_SESSION_FIELDS = frozenset(
    {
        "content",
        "original_content",
        "corrected_text",
        "attachment_id",
        "attachment_ids",
        "attachment_source_identity",
        "image_s3_key",
        "has_image",
        "ocr_text",
        "ocr_metadata",
        "ai_response",
        "teacher_response",
        "teacher_response_text",
        "teacher_response_rich",
        "teacher_response_format",
        "student_feedback",
        "knowledge_points",
        "topic_seeds",
        "subject",
        "student_id",
        "teacher_id",
        "notes",
        "resolution_note",
        "help_text",
        "private_diagnostics",
        "entitlement",
        "previous_dispatch_teacher_ids",
        "dispatch_reason",
        "dispatch_no_candidate_reason",
        "teacher_requested_at",
        "queue_visible_at",
        "teacher_started_at",
        "teacher_taken_over_at",
        "teacher_first_replied_at",
        "teacher_first_reply_seconds",
        "teacher_first_reply_sla_bucket",
        "resolved_at",
        "started_at",
    }
)

QUESTION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "question_id",
        "status",
        "owner_deletion_generation",
        "created_at",
        "deleted_at",
    }
)
SESSION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "session_id",
        "question_id",
        "status",
        "owner_deletion_generation",
        "created_at",
        "deleted_at",
    }
)

# Cross-account identities are deliberately enumerated by persisted entity and
# field.  Do not replace this registry with recursive payload inspection: only
# reviewed relationship, teacher, and notification coordinates may make an
# otherwise foreign-owned row part of an account-deletion scan.
CROSS_ACCOUNT_IDENTITY_REFERENCE_REGISTRY: Mapping[
    str, tuple[frozenset[str], frozenset[str], frozenset[str]]
] = {
    # The forward link row is PK=PARENT#<parent> / SK=CHILD#<student>, so the
    # student is found by student_id and the SK, but the parent is found by
    # neither. Without this the row survives its own parent's deletion while
    # the reverse row is tombstoned, leaving the half link the pairing exists
    # to prevent. created_by is deliberately absent: it is usually an admin,
    # and their deletion must not sweep links they merely issued.
    "parent_student_link": (
        frozenset({"parent_id"}),
        frozenset(),
        frozenset(),
    ),
    "question": (
        frozenset({"teacher_id", "dispatched_teacher_id"}),
        frozenset({"previous_dispatch_teacher_ids"}),
        frozenset(),
    ),
    # A student's request for a teacher names the teacher it is with, the one
    # it is offered to and the ones who let it lapse (#189).
    "help_request": (
        frozenset({"teacher_id", "dispatched_teacher_id"}),
        frozenset({"previous_dispatch_teacher_ids"}),
        frozenset(),
    ),
    "teacher_session": (frozenset({"teacher_id"}), frozenset(), frozenset()),
    "notification_event": (
        frozenset({"actor_id"}),
        frozenset(),
        frozenset({"owner_id", "student_id", "teacher_id"}),
    ),
}


def account_fence_key(user_id: str) -> dict[str, str]:
    value = _required(user_id, "user_id")
    return {"PK": f"USER#{value}", "SK": "ACCOUNT_FENCE"}


def deletion_command_key(user_id: str, command_id: str) -> dict[str, str]:
    return {
        "PK": f"USER#{_required(user_id, 'user_id')}",
        "SK": f"DELETE_COMMAND#{_required(command_id, 'command_id')}",
    }


# Every accepted, unfinished deletion has one row in this partition, written in
# the transaction that accepts it and deleted in the one that finalizes it, so
# the scheduled job finds them all with one strong query instead of a cursor
# walk over the whole table (#397). Commands accepted before the registry
# existed have no row; the job's old discovery scan still finds those and
# writes their row on the way (`register_pending_deletion`).
PENDING_REGISTRY_PK = "ACCOUNT_DELETION_PENDING"


def pending_registry_key(user_id: str, command_id: str) -> dict[str, str]:
    return {
        "PK": PENDING_REGISTRY_PK,
        "SK": f"{_required(user_id, 'user_id')}#{_required(command_id, 'command_id')}",
    }


def _pending_registry_item(
    user_id: str, command_id: str, accepted_at: str | None
) -> dict[str, Any]:
    # The account is named under attributes of its own, never `user_id` or
    # `owner_id`: the deletion's sweeps match rows on those, and this row is
    # bookkeeping, not the account's data.
    item: dict[str, Any] = {
        **pending_registry_key(user_id, command_id),
        "entity_type": "account_deletion_pending",
        "deletion_user_id": user_id,
        "deletion_command_id": command_id,
    }
    if isinstance(accepted_at, str) and accepted_at:
        item["accepted_at"] = accepted_at
    return item


@dataclass(frozen=True, slots=True)
class PendingDeletion:
    user_id: str
    command_id: str


def list_pending_deletions(*, table: Any | None = None) -> list[PendingDeletion]:
    """Every registered unfinished deletion: a strong query of one small partition."""
    target = table or db_table.table()
    found: list[PendingDeletion] = []
    seen: set[tuple[str, str]] = set()
    try:
        for page in db_table.pages(
            "query",
            table=target,
            ConsistentRead=True,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": PENDING_REGISTRY_PK},
        ):
            for item in page.items:
                user_id = item.get("deletion_user_id")
                command_id = item.get("deletion_command_id")
                if not isinstance(user_id, str) or not user_id:
                    continue
                if not isinstance(command_id, str) or not command_id:
                    continue
                if (user_id, command_id) not in seen:
                    seen.add((user_id, command_id))
                    found.append(PendingDeletion(user_id, command_id))
            if page.last_key is None:
                break
    except (db_table.PageTokenInvalid, db_table.TableUnavailable) as exc:
        raise AccountDeletionConflict("pending deletion registry unavailable") from exc
    return found


def register_pending_deletion(
    *,
    user_id: str,
    command_id: str,
    accepted_at: str | None = None,
    table: Any | None = None,
) -> None:
    """Write the registry row of a command accepted before the registry existed."""
    target = table or db_table.table()
    if not isinstance(target, _PutTable):
        raise AccountDeletionConflict("account deletion dependency unavailable")
    try:
        db_table.put(
            table=target, Item=_pending_registry_item(user_id, command_id, accepted_at)
        )
    except (db_table.WriteRefused, db_table.TableUnavailable) as exc:
        raise AccountDeletionConflict("pending deletion registry unavailable") from exc


def unregister_pending_deletion(
    *, user_id: str, command_id: str, table: Any | None = None
) -> None:
    """Drop a registry row whose command is finished or gone."""
    try:
        db_table.delete(
            table=table or db_table.table(), Key=pending_registry_key(user_id, command_id)
        )
    except (db_table.WriteRefused, db_table.TableUnavailable) as exc:
        raise AccountDeletionConflict("pending deletion registry unavailable") from exc


def query_account_partition(
    user_id: str, *, table: Any | None = None
) -> list[dict[str, Any]]:
    """Every row under `USER#{user_id}`, read strongly from the base table.

    The rows whose key the account itself determines: its profile, fence,
    identity inventory and deletion bookkeeping. The deletion's first run acts
    on some of these at once (#397); completeness still rests on the full scans.
    """
    target = table or db_table.table()
    rows: list[dict[str, Any]] = []
    try:
        for page in db_table.pages(
            "query",
            table=target,
            ConsistentRead=True,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": f"USER#{_required(user_id, 'user_id')}"},
        ):
            rows.extend(dict(item) for item in page.items)
            if page.last_key is None:
                break
    except (db_table.PageTokenInvalid, db_table.TableUnavailable) as exc:
        raise AccountDeletionConflict("account partition unavailable") from exc
    return rows


def get_row(key: Mapping[str, Any], *, table: Any | None = None) -> dict[str, Any] | None:
    """One row by its full key, strongly."""
    response = _get_item(
        table or db_table.table(),
        Key={"PK": _required(key.get("PK"), "PK"), "SK": _required(key.get("SK"), "SK")},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if isinstance(item, Mapping) else None


def active_fence_condition(
    user_id: str, generation: int | None = None
) -> dict[str, Any]:
    """The condition a write behind `user_id`'s fence carries.

    Writes call `stoa.db.table.fenced`, which adds it; only the deletion flow,
    whose transactions also hold a closing account's deletion fence, uses it
    directly.
    """
    values: dict[str, Any] = {":active": "active"}
    expression = "#status=:active"
    if generation is not None:
        if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
            raise AccountDeletionConflict("invalid fence generation")
        expression += " AND generation=:generation"
        values[":generation"] = generation
    return {
        "ConditionCheck": {
            "Key": account_fence_key(user_id),
            "ConditionExpression": expression,
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": values,
        }
    }


def get_account_fence(
    user_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    response = _get_item(
        table or db_table.table(),
        Key=account_fence_key(user_id), ConsistentRead=True
    )
    item = response.get("Item")
    return dict(item) if isinstance(item, Mapping) else None


def require_active_account_fence(
    user_id: str,
    generation: int | None = None,
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    fence = get_account_fence(user_id, table=table)
    raw_gen = fence.get("generation") if fence else None
    try:
        fence_generation = int(raw_gen) if raw_gen is not None else 0
    except (TypeError, ValueError):
        fence_generation = 0
    if (
        not fence
        or fence.get("status") != "active"
        or fence_generation <= 0
        or (generation is not None and fence_generation != generation)
    ):
        raise AccountNotWritable("account is not writable")
    # Return a fence dict with a normalised int generation so callers don't
    # receive a Decimal from DynamoDB.
    return {**fence, "generation": fence_generation}


def ensure_active_account_fence(
    user_id: str,
    *,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    """Backfill only one existing active canonical profile; never infer missing as active."""
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or db_table.table()
    existing = get_account_fence(user_id, table=target)
    if existing:
        return require_active_account_fence(user_id, table=target)
    profile_response = _get_item(
        target,
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}, ConsistentRead=True
    )
    profile = profile_response.get("Item")
    if (
        not isinstance(profile, Mapping)
        or profile.get("user_id") != user_id
        or profile.get("role") not in {"student", "parent", "teacher", "admin"}
        or (profile.get("account_status") or profile.get("status")) != "active"
    ):
        raise AccountDeletionConflict("legacy account fence cannot be backfilled")
    item = {
        **account_fence_key(user_id),
        "entity_type": "account_fence",
        "schema_version": "account-fence.v1",
        "user_id": user_id,
        "status": "active",
        "generation": 1,
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    hook = getattr(target, "backfill_account_fence", None)
    if callable(hook):
        persisted = hook(item)
        return require_active_account_fence(user_id, table=target) if persisted else persisted
    operations = [
        {
            "ConditionCheck": {
                "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
                "ConditionExpression": (
                    "attribute_exists(PK) AND user_id=:user AND "
                    "#role IN (:student,:parent,:teacher,:admin) AND "
                    "account_status=:active"
                ),
                "ExpressionAttributeNames": {"#role": "role"},
                "ExpressionAttributeValues": {
                    ":user": user_id,
                    ":student": "student",
                    ":parent": "parent",
                    ":teacher": "teacher",
                    ":admin": "admin",
                    ":active": "active",
                },
            }
        },
        {
            "Put": {
                "Item": item,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
    ]
    db_table.transact(operations, table=target)
    return require_active_account_fence(user_id, table=target)


def materialize_profile_with_fence(
    profile: dict[str, Any], *, now_iso: str
) -> list[dict[str, Any]]:
    """The operations that create one profile row and its active account fence.

    Returned, not committed: the caller sends them in one transaction with whatever
    else has to be decided in the same commit, such as the email claim that makes the
    profile unique. This module stays the only one that knows the two rows' shape.
    """
    now_iso = _valid_lifecycle_timestamp(now_iso)
    user_id = _required(profile.get("user_id"), "user_id")
    profile_item = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        **profile,
        "version": 1,
    }
    fence = {
        **account_fence_key(user_id),
        "entity_type": "account_fence",
        "schema_version": "account-fence.v1",
        "user_id": user_id,
        "status": "active",
        "generation": 1,
        "version": 1,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    return [
        {
            "Put": {
                "Item": profile_item,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
        {
            "Put": {
                "Item": fence,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
    ]


def get_deletion_command(
    user_id: str, command_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    response = _get_item(
        table or db_table.table(),
        Key=deletion_command_key(user_id, command_id), ConsistentRead=True
    )
    item = response.get("Item")
    return dict(item) if isinstance(item, Mapping) else None


def begin_account_deletion(
    *,
    user_id: str,
    command: dict[str, Any],
    now_iso: str,
    table: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or db_table.table()
    current = get_account_fence(user_id, table=target)
    if not current:
        raise AccountDeletionConflict("missing account fence")
    bound_command_id = current.get("command_id")
    if current.get("status") in {"deletion_pending", "deleted"} and isinstance(
        bound_command_id, str
    ):
        persisted = get_deletion_command(user_id, bound_command_id, table=target)
        if persisted and persisted.get("fingerprint") == command.get("fingerprint"):
            return current, persisted
        raise AccountDeletionConflict("deletion replay conflict")
    if current.get("status") != "active" or stored_int(current.get("generation")) is None:
        raise AccountDeletionConflict("account is not deletable")
    generation = int(current["generation"])
    command = {
        **deletion_command_key(user_id, str(command["command_id"])),
        **command,
        "entity_type": "account_deletion_command",
        "schema_version": "account-deletion-command.v1",
        "user_id": user_id,
        "generation": generation,
        "status": "pending",
        "accepted_at": now_iso,
        "created_at": now_iso,
        "updated_at": now_iso,
        "version": 1,
        "command_version": 1,
        "branch_results": {},
        "branch_results_digest": branch_results_digest({}),
    }
    next_fence = {
        **current,
        "status": "deletion_pending",
        "command_id": command["command_id"],
        "command_fingerprint": command["fingerprint"],
        "deletion_accepted_at": now_iso,
        "updated_at": now_iso,
        "version": int(current.get("version") or 1) + 1,
    }
    hook = getattr(target, "begin_account_deletion", None)
    if callable(hook):
        try:
            return hook(next_fence, command)
        except Exception as exc:
            raise AccountDeletionConflict("deletion command conflict") from exc
    try:
        _transact(
            [
                {
                    "Put": {
                        "Item": next_fence,
                        "ConditionExpression": (
                            "#status=:active AND generation=:generation AND #version=:version"
                        ),
                        "ExpressionAttributeNames": {"#status": "status", "#version": "version"},
                        "ExpressionAttributeValues": {
                            ":active": "active",
                            ":generation": generation,
                            ":version": int(current.get("version") or 1),
                        },
                    }
                },
                {
                    "Put": {
                        "Item": command,
                        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                    }
                },
                # Accepted and registered in one commit: the scheduled job
                # finds every unfinished command by this row (#397).
                {
                    "Put": {
                        "Item": _pending_registry_item(
                            user_id, str(command["command_id"]), now_iso
                        )
                    }
                },
            ],
            table=target,
        )
    except AccountDeletionConflict:
        raced = get_account_fence(user_id, table=target)
        command_id = raced.get("command_id") if raced else None
        persisted = (
            get_deletion_command(user_id, str(command_id), table=target)
            if command_id
            else None
        )
        if persisted and persisted.get("fingerprint") == command.get("fingerprint"):
            return dict(raced), persisted  # type: ignore[arg-type]
        raise
    return next_fence, command


def scan_owned_private_rows(
    user_id: str,
    *,
    table: Any | None = None,
    cursor: dict[str, str] | None = None,
    maximum_pages: int = 20,
    page_limit: int = 100,
) -> OwnedPrivatePage:
    """Strong base-table discovery; GSIs never establish deletion completeness."""
    if maximum_pages <= 0 or page_limit <= 0:
        raise AccountDeletionConflict("invalid private row scan bound")
    target = table or db_table.table()
    current = continuation_key(cursor, "private row") if cursor is not None else None
    seen_rows: set[tuple[str, str]] = set()
    seen_cursors: set[tuple[str, str]] = set()
    if current is not None:
        seen_cursors.add((current["PK"], current["SK"]))
    rows: list[dict[str, Any]] = []
    for page in sweep_pages(
        "private row",
        table=target,
        cursor=current,
        page_limit=page_limit,
        maximum_pages=maximum_pages,
    ):
        for item in page.items:
            if not _targets_user(item, user_id):
                continue
            identity = (str(item.get("PK") or ""), str(item.get("SK") or ""))
            if not all(identity):
                raise AccountDeletionConflict("malformed private row key")
            if identity not in seen_rows:
                seen_rows.add(identity)
                rows.append(item)
        if page.last_key is None:
            return OwnedPrivatePage(tuple(rows), None)
        identity = (page.last_key["PK"], page.last_key["SK"])
        if identity in seen_cursors:
            raise AccountDeletionConflict("repeating private row cursor")
        seen_cursors.add(identity)
        current = page.last_key
    return OwnedPrivatePage(tuple(rows), current)


def sweep_pages(
    name: str,
    *,
    table: object,
    cursor: Mapping[str, object] | None,
    maximum_pages: int,
    page_limit: int | None = None,
    conflict: Callable[[str], Exception] | None = None,
    **request: object,
) -> Iterator[db_table.Page]:
    """Up to `maximum_pages` strong base-table pages from `cursor`, for a deletion sweep.

    The paging is the gateway's. A cursor it cannot continue from, or a table
    that does not answer with a page, is a conflict (`AccountDeletionConflict`
    unless the caller names its own): a sweep stops rather than skip rows.
    Whether a cursor has come round again is the sweep's own rule and stays
    with it.
    """
    refuse = conflict or AccountDeletionConflict
    if page_limit is not None:
        request["Limit"] = page_limit
    try:
        source = db_table.pages("scan", start=cursor, table=table, ConsistentRead=True, **request)
    except db_table.PageTokenInvalid as exc:
        raise refuse(f"invalid {name} cursor") from exc
    except db_table.TableUnavailable as exc:
        raise refuse(f"{name} dependency unavailable") from exc
    taken = islice(source, maximum_pages)
    while True:
        try:
            page = next(taken)
        except StopIteration:
            return
        except db_table.TableUnavailable as exc:
            raise refuse(f"malformed {name} page") from exc
        yield page


def continuation_key(value: object, name: str = "continuation") -> dict[str, str]:
    """A sweep's cursor, checked as the gateway checks every key; a refusal is a conflict."""
    try:
        return db_table.page_key(value)
    except db_table.PageTokenInvalid as exc:
        raise AccountDeletionConflict(f"invalid {name} cursor") from exc


def get_command_by_id(
    command_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    target = table or db_table.table()
    hook = getattr(target, "get_command_by_id", None)
    if callable(hook):
        value = hook(command_id)
        return dict(value) if value else None
    matches = _scan_commands(
        target,
        filter_expression="entity_type=:entity AND command_id=:command",
        values={":entity": "account_deletion_command", ":command": command_id},
    )
    if len(matches) > 1:
        raise AccountDeletionConflict("ambiguous deletion command")
    return matches[0] if matches else None


def find_deletion_command_for_identity(
    issuer_hash: str, subject_hash: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    """Recover the one replay command after its active binding is terminalized.

    Still a scan (#397): it runs only when `DELETE /auth/me` is replayed after
    the deletion terminalized the token's binding, and by then nothing keyed by
    the token's issuer and subject names the account - the binding's evidence
    row deliberately keeps no account id. It is not on the deletion's own path,
    which reads its command by key.
    """
    matches = _scan_commands(
        table or db_table.table(),
        filter_expression=(
            "entity_type=:entity AND issuer_hash=:issuer AND subject_hash=:subject"
        ),
        values={
            ":entity": "account_deletion_command",
            ":issuer": _required(issuer_hash, "issuer_hash"),
            ":subject": _required(subject_hash, "subject_hash"),
        },
    )
    if len(matches) > 1:
        raise AccountDeletionConflict("ambiguous deletion identity")
    return matches[0] if matches else None


def _scan_commands(
    target: Any,
    *,
    filter_expression: str,
    values: Mapping[str, Any],
    maximum_pages: int = 100,
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    matches: list[dict[str, Any]] = []
    # No `Limit`: each page is the table's own (up to 1 MB), so the bound is a
    # hundred of those rather than ten thousand rows (#397). The deletion
    # itself no longer comes here: it reads its command by key.
    for page in sweep_pages(
        "deletion command",
        table=target,
        cursor=None,
        maximum_pages=maximum_pages,
        FilterExpression=filter_expression,
        ExpressionAttributeValues=dict(values),
    ):
        matches.extend(page.items)
        if page.last_key is None:
            return matches
        identity = (page.last_key["PK"], page.last_key["SK"])
        if identity in seen:
            raise AccountDeletionConflict("repeating deletion command cursor")
        seen.add(identity)
    raise AccountDeletionConflict("deletion command scan bound exceeded")


def _email_claim_release(
    item: Mapping[str, Any], user_id: str, *, table: Any
) -> list[dict[str, Any]]:
    """Give the address back in the same commit that ends the account holding it.

    The tombstone drops `email`, so once it lands nothing in the table can derive the
    claim key again and the pair stays taken by an account that no longer exists. A
    pair the claim repository refuses to spell was never claimable, so there is
    nothing to release.

    A claim standing in another account's name is read out here rather than left for
    the condition to refuse: inside a transaction a refusal cancels the tombstone too,
    and the branch would retry the same commit forever. Skipping it converges, and the
    condition still decides the gap between this read and the commit.
    """
    if item.get("SK") != "PROFILE" or item.get("user_id") != user_id:
        return []
    email = str(item.get("email") or "")
    role = str(item.get("role") or "")
    try:
        account_email_claim_repo.claim_key(email=email, role=role)
    except ValueError:
        # The pair cannot be spelled, so it was never claimable. A claim store
        # that is merely unavailable must not land here: that would read as
        # "nothing to give back" and leave the address taken for good.
        return []
    claim = account_email_claim_repo.get_claim(email=email, role=role, table=table)
    if claim is None or claim.get("account_id") != user_id:
        return []
    return [
        account_email_claim_repo.release_operation(
            email=email, role=role, account_id=user_id
        )
    ]


def replace_with_deletion_tombstone(
    item: Mapping[str, Any],
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    """Replace one private row with a strict noncontent tombstone."""
    target = table or db_table.table()
    pk = _required(item.get("PK"), "PK")
    sk = _required(item.get("SK"), "SK")
    entity = str(item.get("entity_type") or "private_row")
    is_session = pk.startswith("SESSION#") or entity == "teacher_session"
    allowlist = SESSION_TOMBSTONE_ALLOWLIST if is_session else QUESTION_TOMBSTONE_ALLOWLIST
    candidate = {
        "PK": pk,
        "SK": sk,
        "entity_type": f"{entity}_deletion_tombstone",
        "schema_version": "account-deletion-tombstone.v1",
        "status": "deleted",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
    }
    for field in ("question_id", "session_id", "created_at"):
        if field in item:
            candidate[field] = item[field]
    tombstone = {key: value for key, value in candidate.items() if key in allowlist}
    if not set(tombstone) <= allowlist:
        raise AccountDeletionConflict("private tombstone allowlist violation")
    hook = getattr(target, "replace_with_deletion_tombstone", None)
    if callable(hook):
        # A table that emulates this write owns the whole of it, including the
        # claim release below. Production never takes this path - a boto3 Table
        # has no such attribute - but a fake that grows one stops testing it.
        hook(dict(item), tombstone, user_id, generation)
        return
    _transact(
        [
            deletion_fence_condition(user_id, generation),
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) AND "
                        "(owner_id=:owner OR student_id=:owner OR user_id=:owner)"
                    ),
                    "ExpressionAttributeValues": {":owner": user_id},
                }
            },
            *_email_claim_release(item, user_id, table=target),
        ],
        table=target,
    )


_TEACHER_QUESTION_LINK_FIELDS = (
    "teacher_id",
    "teacher_takeover_claim_id",
    "session_id",
    "teacher_started_at",
    "teacher_taken_over_at",
    "teacher_first_replied_at",
    "teacher_first_reply_seconds",
    "teacher_first_reply_sla_bucket",
)
_TEACHER_DISPATCH_LINK_FIELDS = (
    "dispatched_teacher_id",
    "dispatch_accepted_at",
    "dispatch_deadline_at",
)


def scrub_teacher_question_reference(
    item: Mapping[str, Any],
    *,
    teacher_user_id: str,
    generation: int,
    table: Any | None = None,
) -> None:
    """CAS-remove one deleting teacher without deleting student question data."""
    teacher_id = _teacher_reference_coordinate(teacher_user_id, "teacher user_id")
    pk = _teacher_reference_coordinate(item.get("PK"), "question PK")
    sk = _teacher_reference_coordinate(item.get("SK"), "question SK")
    question_id = _teacher_reference_coordinate(
        item.get("question_id"), "question_id"
    )
    student_id = _teacher_reference_coordinate(item.get("student_id"), "student_id")
    status = _teacher_reference_coordinate(item.get("status"), "question status")
    if (
        pk != f"QUESTION#{question_id}"
        or sk != "META"
        or item.get("entity_type") != "question"
        or item.get("schema_version") != "question.v1"
        or student_id == teacher_id
    ):
        raise AccountDeletionRowConflict("teacher question identity changed")
    version = _teacher_reference_version(item.get("version"), "question version")
    history_value = item.get("previous_dispatch_teacher_ids", [])
    if not isinstance(history_value, (list, tuple)) or any(
        not isinstance(value, str) or not value for value in history_value
    ):
        raise AccountDeletionRowConflict("invalid teacher dispatch history")
    history = list(history_value)
    owns_question = item.get("teacher_id") == teacher_id
    owns_dispatch = item.get("dispatched_teacher_id") == teacher_id
    in_history = teacher_id in history
    if not (owns_question or owns_dispatch or in_history):
        raise AccountDeletionRowConflict("teacher question reference changed")

    names: dict[str, str] = {"#status": "status", "#version": "version"}
    values: dict[str, Any] = {
        ":pk": pk,
        ":sk": sk,
        ":entity": "question",
        ":schema": "question.v1",
        ":student": student_id,
        ":teacher": teacher_id,
        ":status": status,
        ":version": version,
        ":next_version": version + 1,
    }
    set_parts = ["#version=:next_version"]
    remove_fields: list[str] = []
    if owns_question:
        remove_fields.extend(_TEACHER_QUESTION_LINK_FIELDS)
    if owns_dispatch or owns_question:
        remove_fields.extend(_TEACHER_DISPATCH_LINK_FIELDS)
        if "dispatch_status" in item:
            names["#dispatch_status"] = "dispatch_status"
            values[":closed_dispatch"] = "revoked"
            set_parts.append("#dispatch_status=:closed_dispatch")
    if owns_question or owns_dispatch:
        values[":next_status"] = "resolved"
        set_parts.append("#status=:next_status")

    next_history = [value for value in history if value != teacher_id]
    if next_history != history:
        if next_history:
            names["#previous_dispatch_teacher_ids"] = "previous_dispatch_teacher_ids"
            values[":next_history"] = next_history
            set_parts.append("#previous_dispatch_teacher_ids=:next_history")
        else:
            remove_fields.append("previous_dispatch_teacher_ids")
    for field in dict.fromkeys(remove_fields):
        names[f"#{field}"] = field
    expression = "SET " + ", ".join(set_parts)
    if remove_fields:
        expression += " REMOVE " + ", ".join(
            f"#{field}" for field in dict.fromkeys(remove_fields)
        )
    try:
        _transact(
            [
                deletion_fence_condition(teacher_id, generation),
                {
                    "Update": {
                        "Key": {"PK": pk, "SK": sk},
                        "UpdateExpression": expression,
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK) AND "
                            "PK=:pk AND SK=:sk AND entity_type=:entity AND "
                            "schema_version=:schema AND student_id=:student AND "
                            "#status=:status AND #version=:version AND "
                            "(teacher_id=:teacher OR dispatched_teacher_id=:teacher OR "
                            "contains(previous_dispatch_teacher_ids,:teacher))"
                        ),
                        "ExpressionAttributeNames": names,
                        "ExpressionAttributeValues": values,
                    }
                },
            ],
            table=table or db_table.table(),
        )
    except AccountDeletionConflict as exc:
        raise AccountDeletionRowConflict(
            "teacher question changed during cleanup"
        ) from exc


def replace_teacher_session_with_tombstone(
    item: Mapping[str, Any],
    *,
    teacher_user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    """CAS-minimize one foreign-owned session that names a deleting teacher."""
    teacher_id = _teacher_reference_coordinate(teacher_user_id, "teacher user_id")
    pk = _teacher_reference_coordinate(item.get("PK"), "session PK")
    sk = _teacher_reference_coordinate(item.get("SK"), "session SK")
    session_id = _teacher_reference_coordinate(item.get("session_id"), "session_id")
    question_id = _teacher_reference_coordinate(
        item.get("question_id"), "question_id"
    )
    student_id = _teacher_reference_coordinate(item.get("student_id"), "student_id")
    claim_id = _teacher_reference_coordinate(
        item.get("teacher_takeover_claim_id"), "teacher takeover claim"
    )
    if (
        pk != f"SESSION#{session_id}"
        or sk != "META"
        or item.get("entity_type") != "teacher_session"
        or item.get("teacher_id") != teacher_id
        or student_id == teacher_id
    ):
        raise AccountDeletionRowConflict("teacher session identity changed")
    question_version = _teacher_reference_version(
        item.get("question_version"), "session question version"
    )
    tombstone = {
        "PK": pk,
        "SK": sk,
        "entity_type": "teacher_session_deletion_tombstone",
        "schema_version": "account-deletion-tombstone.v1",
        "session_id": session_id,
        "question_id": question_id,
        "status": "deleted",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
    }
    if not set(tombstone) <= SESSION_TOMBSTONE_ALLOWLIST:
        raise AccountDeletionConflict("session tombstone allowlist violation")
    values = {
        ":pk": pk,
        ":sk": sk,
        ":entity": "teacher_session",
        ":session_id": session_id,
        ":question_id": question_id,
        ":student": student_id,
        ":teacher": teacher_id,
        ":claim": claim_id,
        ":question_version": question_version,
    }
    try:
        _transact(
            [
                deletion_fence_condition(teacher_id, generation),
                {
                    "Put": {
                        "Item": tombstone,
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK) AND "
                            "PK=:pk AND SK=:sk AND entity_type=:entity AND "
                            "session_id=:session_id AND question_id=:question_id AND "
                            "student_id=:student AND teacher_id=:teacher AND "
                            "teacher_takeover_claim_id=:claim AND "
                            "question_version=:question_version"
                        ),
                        "ExpressionAttributeValues": values,
                    }
                },
            ],
            table=table or db_table.table(),
        )
    except AccountDeletionConflict as exc:
        raise AccountDeletionRowConflict(
            "teacher session changed during cleanup"
        ) from exc


def is_deletion_tombstone(row: Mapping[str, Any]) -> bool:
    """Whether a row is a tombstone an account deletion left in a row's place.

    Every deletion tombstone marks itself `status=deleted` with the deletion's
    generation; live rows never carry `owner_deletion_generation`. Some keep
    the row's keys and even its owner (the conversation and practice
    tombstones), so a deletion scan that matches on keys or owner alone finds
    its own tombstones again unless it skips them (stoasystem/stoa-backend#78).
    """
    return row.get("status") == "deleted" and row.get("owner_deletion_generation") is not None


def _teacher_reference_version(value: object, field: str) -> int:
    parsed = stored_int(value)
    if parsed is None or parsed <= 0:
        raise AccountDeletionRowConflict(f"invalid {field}")
    return parsed


def _teacher_reference_coordinate(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AccountDeletionRowConflict(f"invalid {field}")
    return value


def deletion_fence_condition(user_id: str, generation: int) -> dict[str, Any]:
    return {
        "ConditionCheck": {
            "Key": account_fence_key(user_id),
            "ConditionExpression": "#status=:pending AND generation=:generation",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {
                ":pending": "deletion_pending",
                ":generation": generation,
            },
        }
    }


def require_deletion_account_fence(
    user_id: str, generation: int, *, table: Any | None = None
) -> dict[str, Any]:
    fence = get_account_fence(user_id, table=table)
    if (
        not fence
        or fence.get("status") != "deletion_pending"
        or fence.get("generation") != generation
    ):
        raise AccountDeletionConflict("account deletion fence changed")
    return fence


def delete_owned_row(
    item: Mapping[str, Any],
    *,
    user_id: str,
    generation: int,
    table: Any | None = None,
) -> None:
    """Remove one owned row, and never the profile.

    A profile is replaced by a tombstone, never deleted: the tombstone is what
    a replayed deletion recognises and what stops the address being handed to
    the next account by accident. Nothing here refused that before, and the
    only thing keeping it from happening was the order of the branches in the
    caller's if/elif. A rearrangement there would have deleted profiles
    silently, and no scanner that reads literals could have seen it coming.
    """
    if str(item.get("SK") or "") == "PROFILE":
        raise AccountDeletionConflict("a profile row is tombstoned, never deleted")
    target = table or db_table.table()
    hook = getattr(target, "delete_owned_row", None)
    if callable(hook):
        hook(dict(item), user_id, generation)
        return
    _transact(
        [
            deletion_fence_condition(user_id, generation),
            {
                "Delete": {
                    "Key": {"PK": item["PK"], "SK": item["SK"]},
                    "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
                }
            },
        ],
        table=target,
    )


def scrub_parent_profile_child(
    item: Mapping[str, Any],
    *,
    child_user_id: str,
    generation: int,
    table: Any | None = None,
) -> None:
    """CAS-remove one closing child without replacing any unrelated profile field."""
    parent_id = _required(item.get("user_id"), "parent user_id")
    if parent_id == child_user_id:
        raise AccountDeletionConflict("student profile requires tombstone replacement")
    target: Any = table or db_table.table()
    current = dict(item)
    for attempt in range(1, 4):
        require_deletion_account_fence(child_user_id, generation, table=target)
        parent_fence = require_active_account_fence(parent_id, table=target)
        if current.get("user_id") != parent_id:
            raise AccountDeletionRowConflict("parent profile identity changed")
        removed, replacements = _parent_profile_child_scrub_changes(
            current, child_user_id
        )
        if not removed and not replacements:
            if attempt == 1:
                raise AccountDeletionRowConflict("closing child reference changed")
            return
        expected_version = current.get("version")
        if expected_version is not None:
            expected_version = _positive_int(
                stored_int(expected_version), "parent profile version"
            )
        scrubbed = deepcopy(current)
        for field in removed:
            scrubbed.pop(field, None)
        scrubbed.update(replacements)
        hook = getattr(target, "scrub_parent_profile_child", None)
        try:
            if callable(hook):
                hook(
                    dict(current),
                    scrubbed,
                    child_user_id,
                    generation,
                    int(parent_fence["generation"]),
                    expected_version=expected_version,
                )
                return
            operations = [
                deletion_fence_condition(child_user_id, generation),
                active_fence_condition(parent_id, int(parent_fence["generation"])),
                _parent_profile_scrub_operation(
                    current,
                    parent_id=parent_id,
                    expected_version=expected_version,
                    removed=removed,
                    replacements=replacements,
                ),
            ]
            _transact(operations, table=target)
            return
        except AccountDeletionConflict as exc:
            if attempt == 3:
                raise AccountDeletionRowConflict(
                    "parent profile changed during bounded scrub"
                ) from exc
            response = _get_item(
                target,
                Key={"PK": f"USER#{parent_id}", "SK": "PROFILE"},
                ConsistentRead=True,
            )
            refreshed = response.get("Item")
            if not isinstance(refreshed, Mapping):
                raise AccountDeletionRowConflict("parent profile disappeared") from exc
            current = dict(refreshed)


def _parent_profile_child_scrub_changes(
    profile: Mapping[str, Any], child_user_id: str
) -> tuple[tuple[str, ...], dict[str, Any]]:
    removed = tuple(
        field
        for field in ("child_user_id", "student_id", "child_id")
        if profile.get(field) == child_user_id
    )
    replacements: dict[str, Any] = {}
    for field in ("children", "child_summaries", "student_summaries"):
        value = profile.get(field)
        if isinstance(value, list):
            filtered = [
                entry
                for entry in value
                if not (
                    isinstance(entry, Mapping)
                    and child_user_id
                    in {
                        entry.get("user_id"),
                        entry.get("student_id"),
                        entry.get("child_id"),
                    }
                )
            ]
            if filtered != value:
                replacements[field] = filtered
        elif isinstance(value, Mapping):
            filtered_map = {
                key: entry
                for key, entry in value.items()
                if key != child_user_id
                and not (
                    isinstance(entry, Mapping)
                    and child_user_id
                    in {
                        entry.get("user_id"),
                        entry.get("student_id"),
                        entry.get("child_id"),
                    }
                )
            }
            if filtered_map != value:
                replacements[field] = filtered_map
    return removed, replacements


def _parent_profile_scrub_operation(
    profile: Mapping[str, Any],
    *,
    parent_id: str,
    expected_version: int | None,
    removed: tuple[str, ...],
    replacements: Mapping[str, Any],
) -> dict[str, Any]:
    names = {"#version": "version"}
    values: dict[str, Any] = {":parent": parent_id}
    identity_condition = "user_id=:parent AND "
    set_parts: list[str] = []
    for index, (field, value) in enumerate(replacements.items()):
        name = f"#scrub_set_{index}"
        token = f":scrub_set_{index}"
        names[name] = field
        values[token] = value
        set_parts.append(f"{name}={token}")
    remove_parts: list[str] = []
    for index, field in enumerate(removed):
        name = f"#scrub_remove_{index}"
        names[name] = field
        remove_parts.append(name)
    if expected_version is None:
        condition = "attribute_not_exists(#version)"
        next_version = 1
    else:
        condition = "#version=:expected_version"
        values[":expected_version"] = expected_version
        next_version = expected_version + 1
    values[":next_version"] = next_version
    expression = "SET #version=:next_version"
    if set_parts:
        expression += ", " + ", ".join(set_parts)
    if remove_parts:
        expression += " REMOVE " + ", ".join(remove_parts)
    return {
        "Update": {
            "Key": {"PK": profile["PK"], "SK": profile["SK"]},
            "UpdateExpression": expression,
            "ConditionExpression": (
                "attribute_exists(PK) AND attribute_exists(SK) AND "
                + identity_condition
                + condition
            ),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def terminalize_identity_row(
    item: Mapping[str, Any],
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    """Retain only keyed, scope-free security evidence for old identity state."""
    now_iso = _valid_lifecycle_timestamp(now_iso)
    evidence = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": "identity_deletion_evidence",
        "status": "terminalized",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
        "version": int(item.get("version") or 1) + 1,
    }
    target = table or db_table.table()
    hook = getattr(target, "replace_with_deletion_tombstone", None)
    if callable(hook):
        hook(dict(item), evidence, user_id, generation)
        return
    _transact(
        [
            deletion_fence_condition(user_id, generation),
            {
                "Put": {
                    "Item": evidence,
                    "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
                }
            },
        ],
        table=target,
    )


def create_provider_revoke_debt(
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"PROVIDER_REVOKE#{generation:020d}",
        "entity_type": "provider_identity_revoke_debt",
        "user_id": user_id,
        "generation": generation,
        "status": "pending",
        "operations": ["attributes", "groups", "sessions"],
        "created_at": now_iso,
    }
    target = table or db_table.table()
    hook = getattr(target, "create_provider_revoke_debt", None)
    if callable(hook):
        hook(item)
        return
    try:
        _transact(
            [
                deletion_fence_condition(user_id, generation),
                {
                    "Put": {
                        "Item": item,
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
            ],
            table=target,
        )
    except AccountDeletionConflict:
        response = _get_item(
            target,
            Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True
        )
        existing = response.get("Item")
        # A replay compares what was stored with what would be written. The
        # operations come back from the table as a list whatever sequence
        # wrote them; comparing a tuple against that list never matched, so
        # every pass after the first refused its own debt and the identity
        # branch could never finish (stoasystem/stoa-backend#78).
        if not isinstance(existing, Mapping) or any(
            existing.get(field) != item[field]
            for field in ("user_id", "generation", "entity_type")
        ) or list(existing.get("operations") or ()) != list(item["operations"]):
            raise


def complete_provider_revoke_debt(
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or db_table.table()
    key = {"PK": f"USER#{user_id}", "SK": f"PROVIDER_REVOKE#{generation:020d}"}
    hook = getattr(target, "complete_provider_revoke_debt", None)
    if callable(hook):
        hook(key, user_id, generation, now_iso)
        return
    try:
        _transact(
            [
                deletion_fence_condition(user_id, generation),
                {
                    "Update": {
                        "Key": key,
                        "UpdateExpression": "SET #status=:complete, completed_at=:now",
                        "ConditionExpression": (
                            "user_id=:user AND generation=:generation AND #status=:pending"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":user": user_id,
                            ":generation": generation,
                            ":pending": "pending",
                            ":complete": "complete",
                            ":now": now_iso,
                        },
                    }
                },
            ],
            table=target,
        )
    except AccountDeletionConflict:
        response = _get_item(target, Key=key, ConsistentRead=True)
        existing = response.get("Item")
        if (
            not isinstance(existing, Mapping)
            or existing.get("user_id") != user_id
            or existing.get("generation") != generation
            or existing.get("status") != "complete"
        ):
            raise


def scan_pending_deletion_commands(
    *,
    limit: int = 25,
    cursor: dict[str, str] | None = None,
    table: Any | None = None,
) -> OwnedPrivatePage:
    # Always the real scan, never a same-named method on the table: discovery
    # is what the sweep's cursor walks (ticket 13).
    target = table or db_table.table()
    page = next(
        sweep_pages(
            "pending command",
            table=target,
            cursor=cursor or None,
            page_limit=min(max(int(limit), 1), 100),
            maximum_pages=1,
            FilterExpression="entity_type=:entity AND #status IN (:pending,:running)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":entity": "account_deletion_command",
                ":pending": "pending",
                ":running": "running",
            },
        )
    )
    return OwnedPrivatePage(tuple(page.items), page.last_key)


# Where the scheduled sweep stopped. A scan's `Limit` counts rows read, so one
# run covers a bounded slice of the table; the next run carries on from here,
# and reaching the end of the table starts the next cycle from the top. The
# version rises on every write, the reset included, so a run that read an older
# place cannot overwrite a newer one.
DELETION_SCAN_CURSOR_KEY = {"PK": "JOB#account_deletion", "SK": "SCAN_CURSOR"}


@dataclass(frozen=True, slots=True)
class DeletionScanCursor:
    cursor: dict[str, str] | None
    # None when no row is stored yet, which the next write must tell apart from
    # a stored row at version 0.
    version: int | None
    cycle_started_at: str | None
    # Consecutive runs that kept this place because a command in its slice
    # failed; the sweep moves past the slice once this reaches its limit.
    held_runs: int = 0


def get_deletion_scan_cursor(*, table: Any | None = None) -> DeletionScanCursor:
    """The stored place, or the top of the table when there is none.

    A stored cursor that is not a valid key is read as the top of the table:
    starting a cycle over costs one rescan, while refusing would stop the
    schedule until someone repaired the row. The version is kept so the next
    write still applies. A version that is not a whole number is refused: the
    next write is conditional on it, so there is nothing safe to write against.
    """
    target = table or db_table.table()
    item = _get_item(target, Key=dict(DELETION_SCAN_CURSOR_KEY), ConsistentRead=True).get(
        "Item"
    )
    if not isinstance(item, Mapping):
        return DeletionScanCursor(cursor=None, version=None, cycle_started_at=None)
    version = stored_int(item.get("version"))
    if version is None or version < 0:
        raise AccountDeletionConflict("invalid deletion scan cursor version")
    try:
        cursor = continuation_key(item["cursor"], "deletion scan") if item.get("cursor") else None
    except AccountDeletionConflict:
        cursor = None
    # Only an observation: a malformed start time is dropped rather than
    # allowed to fail the write that carries the scan forward.
    try:
        started: str | None = _valid_lifecycle_timestamp(item.get("cycle_started_at"))
    except AccountDeletionConflict:
        started = None
    held_runs = stored_int(item.get("held_runs"))
    return DeletionScanCursor(
        cursor=cursor,
        version=version,
        cycle_started_at=started,
        held_runs=held_runs if held_runs is not None and held_runs > 0 else 0,
    )


def advance_deletion_scan_cursor(
    *,
    expected_version: int | None,
    cursor: dict[str, str] | None,
    cycle_started_at: str | None,
    updated_at: str,
    held_runs: int = 0,
    table: Any | None = None,
) -> bool:
    """Store the sweep's new place if nobody has moved it since it was read.

    `expected_version` is None when the read found no row. False means another
    run stored a place first; its place stands.
    """
    if expected_version is not None and (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 0
    ):
        raise AccountDeletionConflict("invalid deletion scan cursor version")
    if isinstance(held_runs, bool) or not isinstance(held_runs, int) or held_runs < 0:
        raise AccountDeletionConflict("invalid deletion scan held run count")
    item: dict[str, Any] = {
        **DELETION_SCAN_CURSOR_KEY,
        "entity_type": "account_deletion_scan_cursor",
        "version": (expected_version or 0) + 1,
        "updated_at": _valid_lifecycle_timestamp(updated_at),
        "held_runs": held_runs,
    }
    if cursor is not None:
        item["cursor"] = continuation_key(cursor, "deletion scan")
    if cycle_started_at is not None:
        item["cycle_started_at"] = _valid_lifecycle_timestamp(cycle_started_at)
    request: dict[str, Any] = {"Item": item}
    if expected_version is None:
        request["ConditionExpression"] = "attribute_not_exists(PK)"
    else:
        request["ConditionExpression"] = "#version = :expected"
        request["ExpressionAttributeNames"] = {"#version": "version"}
        request["ExpressionAttributeValues"] = {":expected": expected_version}
    target = table or db_table.table()
    if not isinstance(target, _PutTable):
        raise AccountDeletionConflict("account deletion dependency unavailable")
    try:
        db_table.put(table=target, **request)
    except db_table.WriteRefused:
        return False
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("deletion scan cursor unavailable") from exc
    return True


def claim_deletion_command(
    command: Mapping[str, Any],
    *,
    lease_owner: str,
    now_epoch: int,
    lease_expires_at: int,
    now_iso: str,
    table: Any | None = None,
) -> DeletionCommandClaim | None:
    lease_owner = _required(lease_owner, "lease_owner")
    now_epoch = _positive_int(now_epoch, "current epoch")
    lease_expires_at = _positive_int(lease_expires_at, "lease expiry")
    if lease_expires_at <= now_epoch:
        raise AccountDeletionConflict("lease must expire after current epoch")
    now_iso = _valid_lifecycle_timestamp(now_iso)
    # Always the conditional update on the table, never a same-named method:
    # the claim is what lets exactly one run continue a command (ticket 13).
    target = table or db_table.table()
    initial_version = _positive_int(
        stored_int(command.get("command_version") or command.get("version")),
        "command version",
    )
    empty_digest = branch_results_digest({})
    try:
        attributes = _update_item(
            target,
            Key={"PK": command["PK"], "SK": command["SK"]},
            UpdateExpression=(
                "SET #status=:running, lease_owner=:owner, lease_expires_at=:expiry, "
                "updated_at=:now, branch_results=if_not_exists(branch_results,:empty), "
                "branch_results_digest=if_not_exists(branch_results_digest,:empty_digest), "
                "command_version=if_not_exists(command_version,:initial_version)+:one, "
                "#version=#version+:one"
            ),
            ConditionExpression=(
                "generation=:generation AND (#status=:pending OR "
                "(#status=:running AND lease_expires_at<:now_epoch))"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":running": "running",
                ":pending": "pending",
                ":generation": int(command["generation"]),
                ":owner": lease_owner,
                ":expiry": lease_expires_at,
                ":now_epoch": now_epoch,
                ":now": now_iso,
                ":one": 1,
                ":empty": {},
                ":empty_digest": empty_digest,
                ":initial_version": initial_version,
            },
            ReturnValues="ALL_NEW",
        )
    except db_table.WriteRefused:
        return None
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("deletion claim unavailable") from exc
    if not attributes:
        raise AccountDeletionConflict("malformed deletion claim")
    return _claim_from_command(attributes)


def renew_deletion_command_claim(
    command: Mapping[str, Any],
    *,
    claim: DeletionCommandClaim,
    now_epoch: int,
    lease_expires_at: int,
    now_iso: str,
    table: Any | None = None,
) -> DeletionCommandClaim:
    if not isinstance(claim, DeletionCommandClaim):
        raise DeletionCommandClaimLost("opaque deletion claim required")
    now_epoch = _positive_int(now_epoch, "current epoch")
    lease_expires_at = _positive_int(lease_expires_at, "lease expiry")
    if lease_expires_at <= now_epoch:
        raise AccountDeletionConflict("lease must expire after current epoch")
    now_iso = _valid_lifecycle_timestamp(now_iso)
    # Always the conditional update on the table: the renewal keeps the claim
    # alive, so it is guarded the way the claim is.
    target = table or db_table.table()
    try:
        _update_item(
            target,
            Key={"PK": command["PK"], "SK": command["SK"]},
            UpdateExpression=(
                "SET lease_expires_at=:expiry, updated_at=:now, "
                "command_version=command_version+:one, #version=#version+:one"
            ),
            ConditionExpression=(
                "#status=:running AND generation=:generation AND lease_owner=:owner "
                "AND command_version=:command_version "
                "AND branch_results_digest=:branch_results_digest "
                "AND lease_expires_at>=:now_epoch"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":running": "running",
                ":generation": claim.generation,
                ":owner": claim.lease_owner,
                ":command_version": claim.command_version,
                ":branch_results_digest": claim.branch_results_digest,
                ":now_epoch": now_epoch,
                ":expiry": lease_expires_at,
                ":now": now_iso,
                ":one": 1,
            },
        )
    except db_table.WriteRefused as exc:
        raise DeletionCommandClaimLost("deletion renewal lost") from exc
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("deletion renewal unavailable") from exc
    return DeletionCommandClaim(
        command_id=claim.command_id,
        generation=claim.generation,
        lease_owner=claim.lease_owner,
        lease_expires_at=lease_expires_at,
        command_version=claim.command_version + 1,
        branch_results_digest=claim.branch_results_digest,
        user_id=claim.user_id,
    )


def release_deletion_command_claim(
    command: Mapping[str, Any],
    *,
    claim: DeletionCommandClaim,
    now_epoch: int,
    updated_at: str,
    table: Any | None = None,
) -> DeletionCommandClaim:
    """End this run's lease now, so the next run need not wait for it to expire.

    Guarded exactly as the renewal is: only the holder of the current version
    can give it up. The command stays `running`, and a claim takes a running
    command whose lease has passed (#397). The time is validated as every
    lifecycle writer's is.
    """
    if not isinstance(claim, DeletionCommandClaim):
        raise DeletionCommandClaimLost("opaque deletion claim required")
    now_epoch = _positive_int(now_epoch, "current epoch")
    released_at = _positive_int(max(now_epoch - 1, 1), "lease expiry")
    updated_at = _valid_lifecycle_timestamp(updated_at)
    target = table or db_table.table()
    try:
        _update_item(
            target,
            Key={"PK": command["PK"], "SK": command["SK"]},
            UpdateExpression=(
                "SET lease_expires_at=:released, updated_at=:now, "
                "command_version=command_version+:one, #version=#version+:one"
            ),
            ConditionExpression=(
                "#status=:running AND generation=:generation AND lease_owner=:owner "
                "AND command_version=:command_version "
                "AND branch_results_digest=:branch_results_digest "
                "AND lease_expires_at>=:now_epoch"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":running": "running",
                ":generation": claim.generation,
                ":owner": claim.lease_owner,
                ":command_version": claim.command_version,
                ":branch_results_digest": claim.branch_results_digest,
                ":now_epoch": now_epoch,
                ":released": released_at,
                ":now": updated_at,
                ":one": 1,
            },
        )
    except db_table.WriteRefused as exc:
        raise DeletionCommandClaimLost("deletion release lost") from exc
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("deletion release unavailable") from exc
    return DeletionCommandClaim(
        command_id=claim.command_id,
        generation=claim.generation,
        lease_owner=claim.lease_owner,
        lease_expires_at=released_at,
        command_version=claim.command_version + 1,
        branch_results_digest=claim.branch_results_digest,
        user_id=claim.user_id,
    )


def persist_branch_result(
    command: Mapping[str, Any],
    branch_id: str,
    result: Mapping[str, Any],
    *,
    claim: DeletionCommandClaim,
    expected_branch_results_digest: str,
    now_epoch: int,
    expected_result_version: int | None = None,
    table: Any | None = None,
) -> DeletionCommandClaim:
    if not isinstance(claim, DeletionCommandClaim):
        raise DeletionCommandClaimLost("opaque deletion claim required")
    if expected_branch_results_digest != claim.branch_results_digest:
        raise DeletionCommandClaimLost("branch result digest changed")
    now_epoch = _positive_int(now_epoch, "current epoch")
    updated_at = _valid_lifecycle_timestamp(result.get("updated_at"))
    current_results = command.get("branch_results") or {}
    if not isinstance(current_results, Mapping):
        raise AccountDeletionConflict("invalid deletion branch results")
    if branch_results_digest(current_results) != expected_branch_results_digest:
        raise DeletionCommandClaimLost("durable branch proof changed")
    previous = current_results.get(branch_id) or {}
    if not isinstance(previous, Mapping):
        raise AccountDeletionConflict("invalid prior branch result")
    # Read back from the command, so a `Decimal`. An `int` check here refused
    # every branch result a real table had ever stored, which is the last of
    # the reasons a deletion could not advance.
    prior_result_version = stored_int(previous.get("result_version", 0))
    if prior_result_version is None or prior_result_version < 0:
        raise AccountDeletionConflict("invalid branch result version")
    if expected_result_version is None:
        expected_result_version = prior_result_version
    if expected_result_version != prior_result_version:
        raise DeletionCommandClaimLost("branch result version changed")
    target = table or db_table.table()
    safe_result = {
        key: value
        for key, value in result.items()
        if key
        in {
            "status",
            "cursor",
            "debt_counts",
            "quiescent",
            "epoch",
            "generation",
            "handler_version",
            "subfamilies",
            "legal_retention_blocked",
            "external_receipts",
            "updated_at",
        }
    }
    safe_result["updated_at"] = updated_at
    safe_result["result_version"] = prior_result_version + 1
    next_results = {key: dict(value) for key, value in current_results.items()}
    next_results[branch_id] = safe_result
    next_digest = branch_results_digest(next_results)
    hook = getattr(target, "persist_branch_result", None)
    if callable(hook):
        persisted = hook(
            dict(command),
            branch_id,
            safe_result,
            claim=claim,
            expected_branch_results_digest=expected_branch_results_digest,
            expected_result_version=expected_result_version,
            next_branch_results_digest=next_digest,
            now_epoch=now_epoch,
        )
        if isinstance(persisted, DeletionCommandClaim):
            return persisted
        if isinstance(persisted, Mapping):
            return _claim_from_command(persisted)
        raise DeletionCommandClaimLost("branch result claim lost")
    result_condition = (
        "attribute_not_exists(branch_results.#branch)"
        if expected_result_version == 0
        else "branch_results.#branch.result_version=:result_version"
    )
    values: dict[str, Any] = {
        ":result": safe_result,
        ":generation": claim.generation,
        ":running": "running",
        ":owner": claim.lease_owner,
        ":command_version": claim.command_version,
        ":branch_results_digest": expected_branch_results_digest,
        ":next_digest": next_digest,
        ":now_epoch": now_epoch,
        ":now": updated_at,
        ":one": 1,
    }
    if expected_result_version:
        values[":result_version"] = expected_result_version
    try:
        _update_item(
            target,
            Key={"PK": command["PK"], "SK": command["SK"]},
            UpdateExpression=(
                "SET branch_results.#branch=:result, updated_at=:now, "
                "branch_results_digest=:next_digest, "
                "command_version=command_version+:one, #version=#version+:one"
            ),
            ConditionExpression=(
                "generation=:generation AND #status=:running AND lease_owner=:owner "
                "AND command_version=:command_version "
                "AND branch_results_digest=:branch_results_digest "
                "AND lease_expires_at>=:now_epoch AND " + result_condition
            ),
            ExpressionAttributeNames={
                "#branch": branch_id,
                "#status": "status",
                "#version": "version",
            },
            ExpressionAttributeValues=values,
        )
    except db_table.WriteRefused as exc:
        raise DeletionCommandClaimLost("branch result claim lost") from exc
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("branch result unavailable") from exc
    return DeletionCommandClaim(
        command_id=claim.command_id,
        generation=claim.generation,
        lease_owner=claim.lease_owner,
        lease_expires_at=claim.lease_expires_at,
        command_version=claim.command_version + 1,
        branch_results_digest=next_digest,
        user_id=claim.user_id,
    )


def finalize_account_deletion(
    *,
    command: Mapping[str, Any],
    fence: Mapping[str, Any],
    seal: Mapping[str, Any],
    claim: DeletionCommandClaim,
    now_epoch: int,
    now_iso: str,
    table: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Permanently terminalize one fully sealed command and fence exactly once."""
    now_iso = _valid_lifecycle_timestamp(now_iso)
    now_epoch = _positive_int(now_epoch, "current epoch")
    if not isinstance(claim, DeletionCommandClaim):
        raise DeletionCommandClaimLost("opaque deletion claim required")
    if (
        command.get("status") == "complete"
        and fence.get("status") == "deleted"
        and command.get("command_id") == fence.get("command_id")
        and command.get("generation") == fence.get("generation")
        and command.get("inventory_sha256") == seal.get("inventory_sha256")
    ):
        return dict(command), dict(fence)

    target = table or db_table.table()
    loader = getattr(target, "get_deletion_command", None)
    if callable(loader):
        loaded = loader(str(command["user_id"]), str(command["command_id"]))
        if not isinstance(loaded, Mapping):
            raise DeletionCommandClaimLost("deletion command disappeared")
        command = dict(loaded)
    elif not callable(getattr(target, "finalize_account_deletion", None)):
        loaded = get_deletion_command(
            str(command["user_id"]), str(command["command_id"]), table=target
        )
        if not loaded:
            raise DeletionCommandClaimLost("deletion command disappeared")
        command = loaded

    durable_results = command.get("branch_results")
    durable_digest = command.get("branch_results_digest")
    if (
        not isinstance(durable_results, Mapping)
        or branch_results_digest(durable_results) != durable_digest
        or durable_digest != claim.branch_results_digest
        or command.get("command_id") != claim.command_id
        or command.get("generation") != claim.generation
        or command.get("lease_owner") != claim.lease_owner
        or command.get("command_version") != claim.command_version
        or stored_int(command.get("lease_expires_at")) is None
        or int(command["lease_expires_at"]) < now_epoch
    ):
        raise DeletionCommandClaimLost("terminal deletion claim lost")

    # Local import avoids a repository/service import cycle while still making
    # the lower transactional boundary independently reject a weak caller.
    from stoa.services import account_deletion_service

    if not account_deletion_service.validate_deletion_seal(
        command=command, fence=fence, seal=seal
    ):
        raise AccountDeletionConflict("account deletion seal is incomplete")
    user_id = _required(command.get("user_id"), "user_id")
    command_id = _required(command.get("command_id"), "command_id")
    generation = stored_int(command.get("generation"))
    command_version = stored_int(command.get("command_version"))
    storage_version = stored_int(command.get("version"))
    fence_version = stored_int(fence.get("version"))
    if (
        generation is None
        or generation <= 0
        or command_version is None
        or command_version <= 0
        or storage_version is None
        or storage_version <= 0
        or fence_version is None
        or fence_version <= 0
    ):
        raise AccountDeletionConflict("invalid terminal lifecycle version")

    external_result = command["branch_results"]["external_delivery_debt"]
    receipts = external_result.get("external_receipts") or []
    minimal_receipts = [
        {
            key: receipt[key]
            for key in ("channel", "status", "count", "claim")
            if key in receipt
        }
        for receipt in receipts
        if isinstance(receipt, Mapping)
    ]
    terminal_command: dict[str, Any] = {
        "PK": command["PK"],
        "SK": command["SK"],
        "entity_type": "account_deletion_command",
        "schema_version": "account-deletion-command.v2",
        "command_id": command_id,
        "user_id": user_id,
        "generation": generation,
        "status": "complete",
        "accepted_at": command.get("accepted_at", ""),
        "completed_at": now_iso,
        "inventory_sha256": seal["inventory_sha256"],
        "receipt": {
            "command_id": command_id,
            "status": "deleted",
            "completed_at": now_iso,
        },
        "accounting_identity": command.get("accounting_identity")
        or f"DELETE_ACCOUNTING#{command_id}",
        "external_receipts": minimal_receipts,
        "evidence_references": list(command.get("evidence_references") or []),
        "version": storage_version + 1,
        "command_version": command_version + 1,
        "branch_results_digest": durable_digest,
    }
    # Who asked, kept for replay and accountability: a self-deletion's token
    # hashes and request, or an operator's id and its one-sentence reason (#396).
    for field in (
        "issuer_hash",
        "subject_hash",
        "fingerprint",
        "method",
        "path",
        "request_body_sha256",
        "initiated_by",
        "reason",
    ):
        if field in command:
            terminal_command[field] = command[field]
    terminal_fence = {
        "PK": fence["PK"],
        "SK": fence["SK"],
        "entity_type": "account_fence",
        "schema_version": "account-fence.v2",
        "user_id": user_id,
        "status": "deleted",
        "generation": generation,
        "command_id": command_id,
        "inventory_sha256": seal["inventory_sha256"],
        "deletion_accepted_at": fence.get("deletion_accepted_at")
        or command.get("accepted_at", ""),
        "deleted_at": now_iso,
        "updated_at": now_iso,
        "version": fence_version + 1,
    }
    expected = {
        "user_id": user_id,
        "command_id": command_id,
        "generation": generation,
        "inventory_sha256": seal["inventory_sha256"],
        "command_version": command_version,
        "branch_results_digest": durable_digest,
        "lease_owner": claim.lease_owner,
        "lease_expires_at": claim.lease_expires_at,
        "fence_version": fence_version,
    }
    hook = getattr(target, "finalize_account_deletion", None)
    if callable(hook):
        persisted_command, persisted_fence = hook(
            expected, terminal_command, terminal_fence
        )
        return dict(persisted_command), dict(persisted_fence)
    try:
        _transact(
            [
                {
                    "Put": {
                        "Item": terminal_command,
                        "ConditionExpression": (
                            "#status=:running AND generation=:generation "
                            "AND command_version=:command_version "
                            "AND branch_results_digest=:branch_results_digest "
                            "AND lease_owner=:lease_owner "
                            "AND lease_expires_at>=:now_epoch "
                            "AND inventory_sha256=:inventory"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                        },
                        "ExpressionAttributeValues": {
                            ":running": "running",
                            ":generation": generation,
                            ":command_version": command_version,
                            ":branch_results_digest": durable_digest,
                            ":lease_owner": claim.lease_owner,
                            ":now_epoch": now_epoch,
                            ":inventory": seal["inventory_sha256"],
                        },
                    }
                },
                {
                    "Put": {
                        "Item": terminal_fence,
                        "ConditionExpression": (
                            "#status=:pending AND generation=:generation AND "
                            "#version=:fence_version AND command_id=:command"
                        ),
                        "ExpressionAttributeNames": {
                            "#status": "status",
                            "#version": "version",
                        },
                        "ExpressionAttributeValues": {
                            ":pending": "deletion_pending",
                            ":generation": generation,
                            ":fence_version": fence_version,
                            ":command": command_id,
                        },
                    }
                },
                # Finished, so no longer pending. A command accepted before the
                # registry has no row, which an unconditional delete tolerates.
                {"Delete": {"Key": pending_registry_key(user_id, command_id)}},
            ],
            table=target,
        )
    except AccountDeletionConflict:
        replay_command = get_deletion_command(user_id, command_id, table=target)
        replay_fence = get_account_fence(user_id, table=target)
        if (
            replay_command
            and replay_fence
            and replay_command.get("status") == "complete"
            and replay_fence.get("status") == "deleted"
            and replay_command.get("inventory_sha256") == seal["inventory_sha256"]
            and replay_command.get("command_id") == command_id
            and replay_fence.get("command_id") == command_id
            and replay_command.get("branch_results_digest") == durable_digest
        ):
            return replay_command, replay_fence
        raise
    return terminal_command, terminal_fence


def _transact(operations: Iterable[dict[str, Any]], *, table: Any | None = None) -> None:
    """One deletion-flow transaction: here a refusal is a deletion conflict.

    The deletion worker and its replays tell outcomes apart by re-reading the rows
    they meant to change, not by the table's reasons, so both outcomes are reported
    the one way the flow already handles.
    """
    try:
        db_table.transact(operations, table=table)
    except db_table.WriteRefused as exc:
        raise AccountDeletionConflict("conditional account lifecycle conflict") from exc
    except db_table.TableUnavailable as exc:
        raise AccountDeletionConflict("account lifecycle dependency unavailable") from exc


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountDeletionConflict(f"{name} is required")
    return value.strip()


def _targets_user(item: Mapping[str, Any], user_id: str) -> bool:
    user_id = _required(user_id, "user_id")
    if user_id in {
        item.get("owner_id"),
        item.get("student_id"),
        item.get("user_id"),
        item.get("child_id"),
        item.get("child_user_id"),
        item.get("target_user_id"),
    }:
        return True
    sk = str(item.get("SK") or "")
    if sk in {f"CHILD#{user_id}", f"PARENT#{user_id}"}:
        return True
    scalar_fields, collection_fields, metadata_fields = (
        CROSS_ACCOUNT_IDENTITY_REFERENCE_REGISTRY.get(
            str(item.get("entity_type") or ""),
            (frozenset(), frozenset(), frozenset()),
        )
    )
    if any(item.get(field) == user_id for field in scalar_fields):
        return True
    if any(
        isinstance(item.get(field), (list, tuple, set, frozenset))
        and user_id in item[field]
        for field in collection_fields
    ):
        return True
    metadata = item.get("metadata")
    if isinstance(metadata, Mapping) and any(
        metadata.get(field) == user_id for field in metadata_fields
    ):
        return True
    for field in ("children", "child_summaries", "student_summaries"):
        value = item.get(field)
        entries: Iterable[object]
        if isinstance(value, Mapping):
            if user_id in value:
                return True
            entries = value.values()
        elif isinstance(value, (list, tuple)):
            entries = value
        else:
            continue
        for entry in entries:
            if isinstance(entry, Mapping) and user_id in {
                entry.get("user_id"),
                entry.get("student_id"),
                entry.get("child_id"),
            }:
                return True
    scope = str(item.get("scope") or "")
    return scope in {f"student:{user_id}", f"student/{user_id}", user_id}


def normalized_identity_hash(value: str) -> str:
    return sha256(_required(value, "identity").encode("utf-8")).hexdigest()
