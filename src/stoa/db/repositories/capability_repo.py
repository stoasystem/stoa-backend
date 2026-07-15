"""Authoritative capability grants with immutable history and one current pointer."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable, Mapping

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


TEACHER_IDENTITY_REVIEWER = "teacher_identity_reviewer"
ADMIN_IDENTITY_MANAGER = "admin_identity_manager"
STUDENT_SUPPORT_LOOKUP = "student_support_lookup"
STUDENT_CONTENT_REVIEW = "student_content_review"
STUDENT_SAFETY_REVIEW = "student_safety_review"
STUDENT_DATA_BREAK_GLASS = "student_data_break_glass"
CURRICULUM_AUTHOR = "curriculum_author"
CURRICULUM_REVIEWER = "curriculum_reviewer"
CURRICULUM_PUBLISHER = "curriculum_publisher"
MIGRATION_OPERATOR = "migration_operator"

KNOWN_CAPABILITIES = frozenset(
    {
        TEACHER_IDENTITY_REVIEWER,
        ADMIN_IDENTITY_MANAGER,
        STUDENT_SUPPORT_LOOKUP,
        STUDENT_CONTENT_REVIEW,
        STUDENT_SAFETY_REVIEW,
        STUDENT_DATA_BREAK_GLASS,
        CURRICULUM_AUTHOR,
        CURRICULUM_REVIEWER,
        CURRICULUM_PUBLISHER,
        MIGRATION_OPERATOR,
    }
)


class CapabilityVersionConflict(RuntimeError):
    """A capability transition was based on stale or conflicting state."""


def _scope_key(scope: str) -> str:
    return sha256(scope.strip().encode("utf-8")).hexdigest()[:24]


def _pk(user_id: str) -> str:
    return f"USER#{user_id.strip()}"


def _pointer_key(user_id: str, capability: str, scope: str) -> dict[str, str]:
    return {
        "PK": _pk(user_id),
        "SK": f"CAPABILITY_CURRENT#{capability.strip()}#{_scope_key(scope)}",
    }


def _version_key(
    user_id: str,
    capability: str,
    scope: str,
    generation: int,
    grant_id: str,
    version: int,
) -> dict[str, str]:
    return {
        "PK": _pk(user_id),
        "SK": (
            f"CAPABILITY_VERSION#{capability.strip()}#{_scope_key(scope)}#"
            f"{generation:020d}#{grant_id.strip()}#{version:020d}"
        ),
    }


def _grant_key(user_id: str, capability: str, scope: str, grant_id: str) -> dict[str, str]:
    """Legacy mutable-row key retained only for safe migration."""
    return {
        "PK": _pk(user_id),
        "SK": f"CAPABILITY#{capability.strip()}#{_scope_key(scope)}#{grant_id.strip()}",
    }


def grant_capability(
    *,
    user_id: str,
    command_id: str,
    grant_id: str,
    capability: str,
    scope: str,
    grantor_id: str,
    reason: str,
    effective_at: str,
    expected_generation: int,
    expires_at: str | None = None,
    table_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Create a new grant lineage, never restore an historical grant."""
    values = [user_id, command_id, grant_id, capability, scope, grantor_id, reason, effective_at]
    if any(not str(value).strip() for value in values) or expected_generation < 0:
        raise ValueError("complete capability grant command fields are required")
    if capability not in KNOWN_CAPABILITIES:
        raise ValueError("unknown capability")
    if capability == STUDENT_DATA_BREAK_GLASS and not expires_at:
        raise ValueError("break-glass grants must expire")

    table = (table_factory or get_table)()
    pointer_key = _pointer_key(user_id, capability, scope)
    pointer = _get(table, pointer_key)
    if pointer is None:
        if expected_generation != 0:
            raise CapabilityVersionConflict("stale expected capability generation")
        generation = 1
    else:
        if (
            pointer.get("status") != "revoked"
            or int(pointer.get("generation") or 0) != expected_generation
        ):
            raise CapabilityVersionConflict("replacement requires the exact revoked generation")
        if command_id in {pointer.get("command_id"), pointer.get("last_action_id")}:
            raise CapabilityVersionConflict("replacement requires a new approved command")
        if grant_id == pointer.get("current_grant_id"):
            raise CapabilityVersionConflict("replacement requires a new grant identity")
        generation = expected_generation + 1

    revision = {
        **_version_key(user_id, capability, scope, generation, grant_id, 1),
        "entity_type": "capability_grant_revision",
        "user_id": user_id,
        "command_id": command_id,
        "grant_id": grant_id,
        "capability": capability,
        "scope": scope,
        "scope_hash": _scope_key(scope),
        "grantor_id": grantor_id,
        "reason": reason,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "status": "active",
        "generation": generation,
        "version": 1,
        "updated_at": effective_at,
    }
    next_pointer = {
        **pointer_key,
        "entity_type": "capability_grant_current",
        "user_id": user_id,
        "capability": capability,
        "scope": scope,
        "scope_hash": _scope_key(scope),
        "current_grant_id": grant_id,
        "command_id": command_id,
        "generation": generation,
        "current_version": 1,
        "status": "active",
        "updated_at": effective_at,
    }
    _apply(
        table,
        [
            {"kind": "put", "item": revision, "condition": "absent"},
            {
                "kind": "put",
                "item": next_pointer,
                "condition": "absent" if pointer is None else "revoked_generation",
                "expected": {"generation": expected_generation, "status": "revoked"},
            },
        ],
    )
    return revision


def revoke_capability(
    *,
    user_id: str,
    grant_id: str,
    capability: str,
    scope: str,
    expected_generation: int,
    expected_version: int,
    actor_id: str,
    reason: str,
    changed_at: str,
    action_id: str,
    table_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Revoke the exact current pointer, with replay-safe immutable evidence."""
    if expected_generation < 1 or expected_version < 1:
        raise ValueError("expected generation and version are required")
    if not actor_id.strip() or not reason.strip() or not action_id.strip():
        raise ValueError("actor_id, reason and action_id are required")
    table = (table_factory or get_table)()
    pointer_key = _pointer_key(user_id, capability, scope)
    pointer = _get(table, pointer_key)
    if pointer is None:
        return _migrate_and_revoke_legacy(
            table=table,
            user_id=user_id,
            grant_id=grant_id,
            capability=capability,
            scope=scope,
            expected_version=expected_version,
            actor_id=actor_id,
            reason=reason,
            changed_at=changed_at,
            action_id=action_id,
        )
    if pointer.get("status") == "revoked" and pointer.get("last_action_id") == action_id:
        return _revision_for_pointer(table, pointer) or dict(pointer)
    expected = {
        "current_grant_id": grant_id,
        "generation": expected_generation,
        "current_version": expected_version,
        "status": "active",
    }
    if any(pointer.get(key) != value for key, value in expected.items()):
        raise CapabilityVersionConflict("stale capability current pointer")
    next_version = expected_version + 1
    revoked = {
        **_version_key(user_id, capability, scope, expected_generation, grant_id, next_version),
        "entity_type": "capability_grant_revision",
        "user_id": user_id,
        "command_id": pointer.get("command_id"),
        "grant_id": grant_id,
        "capability": capability,
        "scope": scope,
        "scope_hash": _scope_key(scope),
        "grantor_id": pointer.get("grantor_id"),
        "reason": reason,
        "status": "revoked",
        "generation": expected_generation,
        "version": next_version,
        "updated_at": changed_at,
        "updated_by": actor_id,
        "last_action_id": action_id,
    }
    next_pointer = {
        **pointer,
        "current_version": next_version,
        "status": "revoked",
        "updated_at": changed_at,
        "updated_by": actor_id,
        "last_action_id": action_id,
    }
    _apply(
        table,
        [
            {"kind": "put", "item": revoked, "condition": "absent"},
            {"kind": "put", "item": next_pointer, "condition": "exact", "expected": expected},
        ],
    )
    return revoked


def get_current_grants(
    user_id: str,
    *,
    now: datetime | None = None,
    table_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    """Authorize only exact active pointer/revision pairs, with fail-closed legacy fallback."""
    table = (table_factory or get_table)()
    items = [dict(item) for item in _query_user_capabilities(table, user_id)]
    pointers = [item for item in items if item.get("entity_type") == "capability_grant_current"]
    revisions = {
        (item["PK"], item["SK"]): item
        for item in items
        if item.get("entity_type") == "capability_grant_revision"
    }
    instant = now or datetime.now(UTC)
    current: list[dict[str, Any]] = []
    pointer_lineages: set[tuple[str, str]] = set()
    for pointer in pointers:
        lineage = (str(pointer.get("capability")), str(pointer.get("scope_hash")))
        pointer_lineages.add(lineage)
        if pointer.get("status") != "active":
            continue
        key = _version_key(
            user_id,
            str(pointer.get("capability")),
            str(pointer.get("scope")),
            int(pointer.get("generation") or 0),
            str(pointer.get("current_grant_id")),
            int(pointer.get("current_version") or 0),
        )
        revision = revisions.get((key["PK"], key["SK"])) or _get(table, key)
        if revision and _exact_revision(pointer, revision) and _effective(revision, instant):
            current.append(dict(revision))

    legacy: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        if item.get("entity_type") != "capability_grant":
            continue
        lineage = (str(item.get("capability")), _scope_key(str(item.get("scope") or "")))
        if lineage not in pointer_lineages:
            legacy.setdefault(lineage, []).append(item)
    for rows in legacy.values():
        valid = [row for row in rows if _valid_legacy(row, instant)]
        if len(rows) == 1 and len(valid) == 1:
            current.append(valid[0])
    return current


def _migrate_and_revoke_legacy(**values: Any) -> dict[str, Any]:
    table = values.pop("table")
    user_id = values["user_id"]
    capability = values["capability"]
    scope = values["scope"]
    grant_id = values["grant_id"]
    expected_version = values["expected_version"]
    rows = [
        row for row in _query_user_capabilities(table, user_id)
        if row.get("entity_type") == "capability_grant"
        and row.get("capability") == capability
        and _scope_key(str(row.get("scope") or "")) == _scope_key(scope)
    ]
    if len(rows) != 1:
        raise CapabilityVersionConflict("legacy capability lineage is ambiguous")
    legacy = dict(rows[0])
    if (
        legacy.get("grant_id") != grant_id
        or legacy.get("status") != "active"
        or int(legacy.get("version") or 0) != expected_version
    ):
        raise CapabilityVersionConflict("stale legacy capability grant")
    active = {
        **legacy,
        **_version_key(user_id, capability, scope, 1, grant_id, expected_version),
        "entity_type": "capability_grant_revision",
        "generation": 1,
    }
    revoked = {
        **active,
        **_version_key(user_id, capability, scope, 1, grant_id, expected_version + 1),
        "status": "revoked",
        "version": expected_version + 1,
        "reason": values["reason"],
        "updated_at": values["changed_at"],
        "updated_by": values["actor_id"],
        "last_action_id": values["action_id"],
    }
    pointer = {
        **_pointer_key(user_id, capability, scope),
        "entity_type": "capability_grant_current",
        "user_id": user_id,
        "capability": capability,
        "scope": scope,
        "scope_hash": _scope_key(scope),
        "current_grant_id": grant_id,
        "generation": 1,
        "current_version": expected_version + 1,
        "status": "revoked",
        "updated_at": values["changed_at"],
        "updated_by": values["actor_id"],
        "last_action_id": values["action_id"],
    }
    migrated = {**legacy, "status": "revoked", "migrated": True, "last_action_id": values["action_id"]}
    _apply(
        table,
        [
            {"kind": "put", "item": active, "condition": "absent"},
            {"kind": "put", "item": revoked, "condition": "absent"},
            {"kind": "put", "item": pointer, "condition": "absent"},
            {
                "kind": "put", "item": migrated, "condition": "exact",
                "expected": {"status": "active", "version": expected_version},
            },
        ],
    )
    return revoked


def _exact_revision(pointer: Mapping[str, Any], revision: Mapping[str, Any]) -> bool:
    return all(
        (
            revision.get("grant_id") == pointer.get("current_grant_id"),
            revision.get("capability") == pointer.get("capability"),
            revision.get("scope_hash") == pointer.get("scope_hash"),
            int(revision.get("generation") or 0) == int(pointer.get("generation") or 0),
            int(revision.get("version") or 0) == int(pointer.get("current_version") or 0),
            revision.get("status") == pointer.get("status") == "active",
        )
    )


def _effective(item: Mapping[str, Any], instant: datetime) -> bool:
    effective = _parse_time(item.get("effective_at"))
    expires = _parse_time(item.get("expires_at"))
    return not ((effective and effective > instant) or (expires and expires <= instant))


def _valid_legacy(item: Mapping[str, Any], instant: datetime) -> bool:
    return bool(
        item.get("status") == "active"
        and int(item.get("version") or 0) > 0
        and item.get("capability")
        and item.get("scope")
        and item.get("grant_id")
        and not item.get("migrated")
        and _effective(item, instant)
    )


def _revision_for_pointer(table: Any, pointer: Mapping[str, Any]) -> dict[str, Any] | None:
    key = _version_key(
        str(pointer["user_id"]), str(pointer["capability"]), str(pointer["scope"]),
        int(pointer["generation"]), str(pointer["current_grant_id"]), int(pointer["current_version"]),
    )
    return _get(table, key)


def _query_user_capabilities(table: Any, user_id: str) -> list[dict[str, Any]]:
    response = table.query(
        KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("CAPABILITY"),
        ConsistentRead=True,
    )
    return [dict(item) for item in response.get("Items", [])]


def _get(table: Any, key: Mapping[str, str]) -> dict[str, Any] | None:
    if hasattr(table, "get_item"):
        response = table.get_item(Key=dict(key), ConsistentRead=True)
        return dict(response["Item"]) if response.get("Item") else None
    rows = _query_user_capabilities(table, key["PK"].removeprefix("USER#"))
    return next((row for row in rows if row.get("SK") == key["SK"]), None)


def _apply(table: Any, operations: list[dict[str, Any]]) -> None:
    """Apply one atomic transaction; fakes may expose the same high-level contract."""
    try:
        if hasattr(table, "apply_capability_transaction"):
            table.apply_capability_transaction(operations)
            return
        serializer = TypeSerializer()
        table_name = table.name
        transact_items = []
        for operation in operations:
            item = operation["item"]
            names: dict[str, str] = {}
            values: dict[str, Any] = {}
            condition = operation.get("condition")
            if condition == "absent":
                expression = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
            else:
                clauses = []
                for index, (field, value) in enumerate(operation.get("expected", {}).items()):
                    names[f"#n{index}"] = field
                    values[f":v{index}"] = serializer.serialize(value)
                    clauses.append(f"#n{index} = :v{index}")
                expression = " AND ".join(clauses)
            put: dict[str, Any] = {
                "TableName": table_name,
                "Item": {key: serializer.serialize(value) for key, value in item.items() if value is not None},
                "ConditionExpression": expression,
            }
            if names:
                put["ExpressionAttributeNames"] = names
                put["ExpressionAttributeValues"] = values
            transact_items.append({"Put": put})
        table.meta.client.transact_write_items(TransactItems=transact_items)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "ConditionalCheckFailedException", "TransactionCanceledException"
        }:
            raise CapabilityVersionConflict("conditional capability transaction failed") from exc
        raise


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
