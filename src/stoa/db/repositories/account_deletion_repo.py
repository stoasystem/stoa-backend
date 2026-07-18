"""Permanent account lifecycle fence and resumable deletion command persistence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class AccountDeletionConflict(RuntimeError):
    """A lifecycle mutation did not match the permanent fence generation."""


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


def branch_results_digest(results: Mapping[str, Any]) -> str:
    if not isinstance(results, Mapping):
        raise AccountDeletionConflict("invalid deletion branch results")
    try:
        canonical = json.dumps(
            dict(results),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
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
    return DeletionCommandClaim(
        command_id=_required(command.get("command_id"), "command_id"),
        generation=_positive_int(command.get("generation"), "generation"),
        lease_owner=owner,
        lease_expires_at=_positive_int(
            command.get("lease_expires_at"), "lease expiry"
        ),
        command_version=_positive_int(
            command.get("command_version") or command.get("version"),
            "command version",
        ),
        branch_results_digest=digest,
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


def account_fence_key(user_id: str) -> dict[str, str]:
    value = _required(user_id, "user_id")
    return {"PK": f"USER#{value}", "SK": "ACCOUNT_FENCE"}


def deletion_command_key(user_id: str, command_id: str) -> dict[str, str]:
    return {
        "PK": f"USER#{_required(user_id, 'user_id')}",
        "SK": f"DELETE_COMMAND#{_required(command_id, 'command_id')}",
    }


def active_fence_condition(
    user_id: str, generation: int | None = None
) -> dict[str, Any]:
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
    response = (table or get_table()).get_item(
        Key=account_fence_key(user_id), ConsistentRead=True
    )
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(item) if isinstance(item, Mapping) else None


def require_active_account_fence(
    user_id: str,
    generation: int | None = None,
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    fence = get_account_fence(user_id, table=table)
    if (
        not fence
        or fence.get("status") != "active"
        or type(fence.get("generation")) is not int
        or int(fence["generation"]) <= 0
        or (generation is not None and fence["generation"] != generation)
    ):
        raise AccountDeletionConflict("account is not writable")
    return fence


def ensure_active_account_fence(
    user_id: str,
    *,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    """Backfill only one existing active canonical profile; never infer missing as active."""
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or get_table()
    existing = get_account_fence(user_id, table=target)
    if existing:
        return require_active_account_fence(user_id, table=target)
    profile_response = target.get_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"}, ConsistentRead=True
    )
    profile = profile_response.get("Item") if isinstance(profile_response, Mapping) else None
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
    transact(operations, table=target)
    return require_active_account_fence(user_id, table=target)


def materialize_profile_with_fence(
    profile: dict[str, Any], *, now_iso: str, table: Any | None = None
) -> None:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    user_id = _required(profile.get("user_id"), "user_id")
    target = table or get_table()
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
    hook = getattr(target, "put_profile_with_fence", None)
    if callable(hook):
        hook(dict(profile), fence)
        return
    transact(
        [
            {
                "Put": {
                    "Item": {"PK": f"USER#{user_id}", "SK": "PROFILE", **profile},
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
            {
                "Put": {
                    "Item": fence,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ],
        table=target,
    )


def get_deletion_command(
    user_id: str, command_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(
        Key=deletion_command_key(user_id, command_id), ConsistentRead=True
    )
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(item) if isinstance(item, Mapping) else None


def begin_account_deletion(
    *,
    user_id: str,
    command: dict[str, Any],
    now_iso: str,
    table: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or get_table()
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
    if current.get("status") != "active" or type(current.get("generation")) is not int:
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
        transact(
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
    target = table or get_table()
    current = _validated_cursor(cursor) if cursor is not None else None
    seen_rows: set[tuple[str, str]] = set()
    seen_cursors: set[tuple[str, str]] = set()
    if current is not None:
        seen_cursors.add((current["PK"], current["SK"]))
    rows: list[dict[str, Any]] = []
    for _ in range(maximum_pages):
        request: dict[str, Any] = {"ConsistentRead": True, "Limit": page_limit}
        if current:
            request["ExclusiveStartKey"] = current
        response = target.scan(**request)
        if not isinstance(response, Mapping) or not isinstance(response.get("Items", []), list):
            raise AccountDeletionConflict("malformed private row page")
        for raw in response.get("Items", []):
            if not isinstance(raw, Mapping):
                raise AccountDeletionConflict("malformed private row")
            item = dict(raw)
            if not _targets_user(item, user_id):
                continue
            identity = (str(item.get("PK") or ""), str(item.get("SK") or ""))
            if not all(identity):
                raise AccountDeletionConflict("malformed private row key")
            if identity not in seen_rows:
                seen_rows.add(identity)
                rows.append(item)
        raw_cursor = response.get("LastEvaluatedKey")
        if raw_cursor is None:
            return OwnedPrivatePage(tuple(rows), None)
        next_cursor = _validated_cursor(raw_cursor)
        identity = (next_cursor["PK"], next_cursor["SK"])
        if identity in seen_cursors:
            raise AccountDeletionConflict("repeating private row cursor")
        seen_cursors.add(identity)
        current = next_cursor
    return OwnedPrivatePage(tuple(rows), current)


def get_command_by_id(
    command_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    target = table or get_table()
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
    """Recover the one replay command after its active binding is terminalized."""
    matches = _scan_commands(
        table or get_table(),
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
    cursor: dict[str, str] | None = None
    seen: set[tuple[str, str]] = set()
    matches: list[dict[str, Any]] = []
    for _ in range(maximum_pages):
        request: dict[str, Any] = {
            "ConsistentRead": True,
            "Limit": 100,
            "FilterExpression": filter_expression,
            "ExpressionAttributeValues": dict(values),
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        response = target.scan(**request)
        if not isinstance(response, Mapping) or not isinstance(
            response.get("Items", []), list
        ):
            raise AccountDeletionConflict("malformed deletion command page")
        matches.extend(
            dict(item) for item in response.get("Items", []) if isinstance(item, Mapping)
        )
        raw_cursor = response.get("LastEvaluatedKey")
        if raw_cursor is None:
            return matches
        cursor = _validated_cursor(raw_cursor)
        identity = (cursor["PK"], cursor["SK"])
        if identity in seen:
            raise AccountDeletionConflict("repeating deletion command cursor")
        seen.add(identity)
    raise AccountDeletionConflict("deletion command scan bound exceeded")


def replace_with_deletion_tombstone(
    item: Mapping[str, Any],
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    """Replace one private row with a strict noncontent tombstone."""
    target = table or get_table()
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
        hook(dict(item), tombstone, user_id, generation)
        return
    transact(
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
        ],
        table=target,
    )


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
    target = table or get_table()
    hook = getattr(target, "delete_owned_row", None)
    if callable(hook):
        hook(dict(item), user_id, generation)
        return
    transact(
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
    """Remove one closing child from embedded parent summaries without deleting parent."""
    parent_id = _required(item.get("user_id"), "parent user_id")
    if parent_id == child_user_id:
        raise AccountDeletionConflict("student profile requires tombstone replacement")
    target = table or get_table()
    parent_fence = require_active_account_fence(parent_id, table=target)
    expected_version = item.get("version")
    if expected_version is not None:
        expected_version = _positive_int(expected_version, "parent profile version")
    scrubbed = deepcopy(dict(item))
    for field in ("child_user_id", "student_id", "child_id"):
        if scrubbed.get(field) == child_user_id:
            scrubbed.pop(field, None)
    for field in ("children", "child_summaries", "student_summaries"):
        value = scrubbed.get(field)
        if isinstance(value, list):
            scrubbed[field] = [
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
        elif isinstance(value, Mapping):
            scrubbed[field] = {
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
    if scrubbed == dict(item):
        raise AccountDeletionRowConflict("closing child reference changed")
    hook = getattr(target, "scrub_parent_profile_child", None)
    if callable(hook):
        hook(
            dict(item),
            scrubbed,
            child_user_id,
            generation,
            int(parent_fence["generation"]),
            expected_version=expected_version,
        )
        return
    if expected_version is None:
        # A narrow first write gives a legacy row a version without replacing any
        # concurrently mutable parent field. The caller must strongly rescan.
        transact(
            [
                deletion_fence_condition(child_user_id, generation),
                active_fence_condition(parent_id, int(parent_fence["generation"])),
                {
                    "Update": {
                        "Key": {"PK": item["PK"], "SK": item["SK"]},
                        "UpdateExpression": "SET #version=:one",
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK) AND "
                            "user_id=:parent AND attribute_not_exists(#version)"
                        ),
                        "ExpressionAttributeNames": {"#version": "version"},
                        "ExpressionAttributeValues": {
                            ":parent": parent_id,
                            ":one": 1,
                        },
                    }
                },
            ],
            table=target,
        )
        raise AccountDeletionRowConflict("legacy parent profile normalized; rescan")
    scrubbed["version"] = expected_version + 1
    transact(
        [
            deletion_fence_condition(child_user_id, generation),
            active_fence_condition(parent_id, int(parent_fence["generation"])),
            {
                "Put": {
                    "Item": scrubbed,
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) AND "
                        "user_id=:parent AND #version=:expected_version"
                    ),
                    "ExpressionAttributeNames": {"#version": "version"},
                    "ExpressionAttributeValues": {
                        ":parent": parent_id,
                        ":expected_version": expected_version,
                    },
                }
            },
        ],
        table=target,
    )


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
    target = table or get_table()
    hook = getattr(target, "replace_with_deletion_tombstone", None)
    if callable(hook):
        hook(dict(item), evidence, user_id, generation)
        return
    transact(
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
        "operations": ("attributes", "groups", "sessions"),
        "created_at": now_iso,
    }
    target = table or get_table()
    hook = getattr(target, "create_provider_revoke_debt", None)
    if callable(hook):
        hook(item)
        return
    try:
        transact(
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
        response = target.get_item(
            Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True
        )
        existing = response.get("Item") if isinstance(response, Mapping) else None
        if not isinstance(existing, Mapping) or any(
            existing.get(field) != item[field]
            for field in ("user_id", "generation", "entity_type", "operations")
        ):
            raise


def complete_provider_revoke_debt(
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> None:
    now_iso = _valid_lifecycle_timestamp(now_iso)
    target = table or get_table()
    key = {"PK": f"USER#{user_id}", "SK": f"PROVIDER_REVOKE#{generation:020d}"}
    hook = getattr(target, "complete_provider_revoke_debt", None)
    if callable(hook):
        hook(key, user_id, generation, now_iso)
        return
    try:
        transact(
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
        response = target.get_item(Key=key, ConsistentRead=True)
        existing = response.get("Item") if isinstance(response, Mapping) else None
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
    target = table or get_table()
    hook = getattr(target, "scan_pending_deletion_commands", None)
    if callable(hook):
        items, next_cursor = hook(limit=limit, exclusive_start_key=cursor)
        return OwnedPrivatePage(tuple(dict(item) for item in items), next_cursor)
    request: dict[str, Any] = {
        "ConsistentRead": True,
        "Limit": min(max(int(limit), 1), 100),
        "FilterExpression": "entity_type=:entity AND #status IN (:pending,:running)",
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":entity": "account_deletion_command",
            ":pending": "pending",
            ":running": "running",
        },
    }
    if cursor:
        request["ExclusiveStartKey"] = _validated_cursor(cursor)
    response = target.scan(**request)
    items = response.get("Items", []) if isinstance(response, Mapping) else []
    if not isinstance(items, list):
        raise AccountDeletionConflict("malformed pending command page")
    return OwnedPrivatePage(
        tuple(dict(item) for item in items if isinstance(item, Mapping)),
        _validated_cursor(response.get("LastEvaluatedKey"))
        if response.get("LastEvaluatedKey")
        else None,
    )


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
    target = table or get_table()
    hook = getattr(target, "claim_deletion_command", None)
    if callable(hook):
        claimed = hook(
            dict(command),
            lease_owner=lease_owner,
            now_epoch=now_epoch,
            lease_expires_at=lease_expires_at,
            now_iso=now_iso,
        )
        if claimed is None or isinstance(claimed, DeletionCommandClaim):
            return claimed
        if isinstance(claimed, Mapping):
            return _claim_from_command(claimed)
        raise AccountDeletionConflict("malformed deletion claim")
    initial_version = _positive_int(
        command.get("command_version") or command.get("version"), "command version"
    )
    empty_digest = branch_results_digest({})
    try:
        response = target.update_item(
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
    except ClientError as exc:
        if _conditional(exc):
            return None
        raise AccountDeletionConflict("deletion claim unavailable") from exc
    attributes = response.get("Attributes") if isinstance(response, Mapping) else None
    if not isinstance(attributes, Mapping):
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
    target = table or get_table()
    hook = getattr(target, "renew_deletion_command_claim", None)
    if callable(hook):
        renewed = hook(
            dict(command),
            claim=claim,
            now_epoch=now_epoch,
            lease_expires_at=lease_expires_at,
            now_iso=now_iso,
        )
        if isinstance(renewed, DeletionCommandClaim):
            return renewed
        if isinstance(renewed, Mapping):
            return _claim_from_command(renewed)
        raise DeletionCommandClaimLost("deletion renewal lost")
    try:
        target.update_item(
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
    except ClientError as exc:
        if _conditional(exc):
            raise DeletionCommandClaimLost("deletion renewal lost") from exc
        raise AccountDeletionConflict("deletion renewal unavailable") from exc
    return DeletionCommandClaim(
        command_id=claim.command_id,
        generation=claim.generation,
        lease_owner=claim.lease_owner,
        lease_expires_at=lease_expires_at,
        command_version=claim.command_version + 1,
        branch_results_digest=claim.branch_results_digest,
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
    prior_result_version = previous.get("result_version", 0)
    if isinstance(prior_result_version, bool) or not isinstance(
        prior_result_version, int
    ) or prior_result_version < 0:
        raise AccountDeletionConflict("invalid branch result version")
    if expected_result_version is None:
        expected_result_version = prior_result_version
    if expected_result_version != prior_result_version:
        raise DeletionCommandClaimLost("branch result version changed")
    target = table or get_table()
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
        target.update_item(
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
    except ClientError as exc:
        if _conditional(exc):
            raise DeletionCommandClaimLost("branch result claim lost") from exc
        raise AccountDeletionConflict("branch result unavailable") from exc
    return DeletionCommandClaim(
        command_id=claim.command_id,
        generation=claim.generation,
        lease_owner=claim.lease_owner,
        lease_expires_at=claim.lease_expires_at,
        command_version=claim.command_version + 1,
        branch_results_digest=next_digest,
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

    target = table or get_table()
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
        or not isinstance(command.get("lease_expires_at"), int)
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
    generation = command.get("generation")
    command_version = command.get("command_version")
    storage_version = command.get("version")
    fence_version = fence.get("version")
    if (
        isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
        or isinstance(command_version, bool)
        or not isinstance(command_version, int)
        or command_version <= 0
        or isinstance(storage_version, bool)
        or not isinstance(storage_version, int)
        or storage_version <= 0
        or isinstance(fence_version, bool)
        or not isinstance(fence_version, int)
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
    for field in (
        "issuer_hash",
        "subject_hash",
        "fingerprint",
        "method",
        "path",
        "request_body_sha256",
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
        transact(
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


def create_teacher_escalation_intent(
    *,
    owner_id: str,
    question_id: str,
    operation_id: str,
    generation: int,
    table: Any | None = None,
) -> None:
    """Persist opaque delivery debt before the external queue mutation."""
    item = {
        "PK": f"TEACHER_ESCALATION#{_required(operation_id, 'operation_id')}",
        "SK": "INTENT",
        "entity_type": "teacher_escalation_intent",
        "operation_id": operation_id,
        "question_id": _required(question_id, "question_id"),
        "owner_id": _required(owner_id, "owner_id"),
        "generation": generation,
        "status": "pending_delivery",
        "version": 1,
    }
    transact(
        [
            active_fence_condition(owner_id, generation),
            {
                "Put": {
                    "Item": item,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ],
        table=table,
    )


def transact(operations: Iterable[dict[str, Any]], *, table: Any | None = None) -> None:
    target = table or get_table()
    hook = getattr(target, "transact_account_deletion", None)
    if callable(hook):
        hook(list(operations))
        return
    client = getattr(getattr(target, "meta", None), "client", None)
    table_name = getattr(target, "name", None)
    if client is None or not table_name:
        raise AccountDeletionConflict("atomic lifecycle persistence unavailable")
    serializer = TypeSerializer()
    try:
        client.transact_write_items(
            TransactItems=[
                _serialize_operation(operation, table_name, serializer)
                for operation in operations
            ]
        )
    except ClientError as exc:
        if _conditional(exc):
            raise AccountDeletionConflict("conditional account lifecycle conflict") from exc
        raise AccountDeletionConflict("account lifecycle dependency unavailable") from exc


def _serialize_operation(
    operation: dict[str, Any], table_name: str, serializer: TypeSerializer
) -> dict[str, Any]:
    name, raw = next(iter(operation.items()))
    value = dict(raw)
    value["TableName"] = table_name
    for key in ("Item", "Key", "ExpressionAttributeValues"):
        if key in value:
            value[key] = {
                field: serializer.serialize(field_value)
                for field, field_value in value[key].items()
                if field_value is not None
            }
    return {name: value}


def _validated_cursor(value: Any) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"PK", "SK"}
        or any(not isinstance(value[field], str) or not value[field] for field in ("PK", "SK"))
    ):
        raise AccountDeletionConflict("invalid continuation cursor")
    return {"PK": value["PK"], "SK": value["SK"]}


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountDeletionConflict(f"{name} is required")
    return value.strip()


def _targets_user(item: Mapping[str, Any], user_id: str) -> bool:
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
    for field in ("children", "child_summaries", "student_summaries"):
        value = item.get(field)
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


def _conditional(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }
