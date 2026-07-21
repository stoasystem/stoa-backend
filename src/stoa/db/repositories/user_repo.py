"""DynamoDB access patterns for the User entity."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from boto3.dynamodb.conditions import Attr, Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


type UserItem = dict[str, object]
type TransactionOperation = dict[str, object]


class ParentBindingDisposition(StrEnum):
    """Closed outcomes for one atomic parent/student relationship write."""

    CREATED = "created"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ParentBindingResult:
    disposition: ParentBindingDisposition
    binding: UserItem | None = None
    profile: UserItem | None = None


@dataclass(frozen=True, slots=True)
class _ParentBindingSnapshot:
    profile: UserItem | None
    forward: UserItem | None
    reverse: UserItem | None
    reverse_rows: tuple[UserItem, ...]


def put_user(item: Mapping[str, object]) -> None:
    created_at = item.get("created_at")
    if created_at is None or created_at == "":
        timestamp = datetime.now(UTC).isoformat()
    elif isinstance(created_at, str):
        timestamp = created_at
    else:
        raise ValueError("malformed user profile timestamp")
    account_deletion_repo.materialize_profile_with_fence(
        dict(item), now_iso=timestamp, table=get_table()
    )


def get_user(user_id: str) -> UserItem | None:
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def get_user_by_email(email: str) -> UserItem | None:
    table = get_table()
    resp = table.query(
        IndexName="GSI-Email",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    items = _items(resp.get("Items", []))
    return items[0] if items else None


def list_children_by_parent_scan(parent_id: str) -> list[UserItem]:
    """Return student profiles that still use the legacy parent_id profile link."""
    table = get_table()
    scan_kwargs = {
        "FilterExpression": Attr("parent_id").eq(parent_id) & Attr("role").eq("student"),
    }
    children: list[UserItem] = []
    while True:
        resp = table.scan(**scan_kwargs)
        children.extend(_items(resp.get("Items", [])))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return children
        scan_kwargs["ExclusiveStartKey"] = last_key


def update_locale_preference(user_id: str, locale: str, updated_at: str) -> UserItem:
    return update_profile_fields(
        user_id,
        update_expression=(
            "SET preferred_locale = :locale, preferredLocale = :locale, "
            "#language = :locale, locale_updated_at = :updated_at, updated_at = :updated_at"
        ),
        expression_attribute_names={"#language": "language"},
        expression_attribute_values={
            ":locale": locale,
            ":updated_at": updated_at,
        },
    )


def update_teacher_availability(
    user_id: str,
    *,
    subjects: list[str],
    weekly_availability: list[Mapping[str, object]],
    updated_at: str,
) -> UserItem:
    return update_profile_fields(
        user_id,
        update_expression=(
            "SET subjects = :subjects, primary_subjects = :subjects, "
            "dispatch_subjects = :subjects, weekly_availability = :weekly_availability, "
            "weeklyAvailability = :weekly_availability, availability_status = :availability, "
            "dispatch_availability = :availability, updated_at = :updated_at"
        ),
        expression_attribute_values={
            ":subjects": subjects,
            ":weekly_availability": weekly_availability,
            ":availability": "available",
            ":updated_at": updated_at,
        },
    )


def update_email_verification_state(
    user_id: str, fields: Mapping[str, object]
) -> UserItem:
    """Update bounded email verification metadata on a user profile."""
    if not fields:
        return get_user(user_id) or {}
    update_parts = []
    attr_names: dict[str, str] = {}
    attr_values: dict[str, object] = {}
    for idx, (field, value) in enumerate(fields.items()):
        name_key = f"#f{idx}"
        value_key = f":v{idx}"
        attr_names[name_key] = field
        attr_values[value_key] = value
        update_parts.append(f"{name_key} = {value_key}")
    return update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(update_parts),
        expression_attribute_names=attr_names,
        expression_attribute_values=attr_values,
    )


def build_profile_update_transaction(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    expected_generation: int,
) -> list[TransactionOperation]:
    """Build one exact-generation profile update that cannot ghost-upsert."""
    return [
        account_deletion_repo.active_fence_condition(user_id, expected_generation),
        {
            "Update": {
                "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
                "UpdateExpression": update_expression,
                "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
                **(
                    {"ExpressionAttributeNames": dict(expression_attribute_names)}
                    if expression_attribute_names
                    else {}
                ),
                "ExpressionAttributeValues": dict(expression_attribute_values),
            }
        },
    ]


def update_profile_fields(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
) -> UserItem:
    table = get_table()
    fence = account_deletion_repo.require_active_account_fence(user_id, table=table)
    account_deletion_repo.transact(
        build_profile_update_transaction(
            user_id,
            update_expression=update_expression,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            expected_generation=_required_positive_integer(fence.get("generation")),
        ),
        table=table,
    )
    return get_user(user_id) or {}


def build_parent_binding_transaction(
    *,
    parent_id: str,
    student_id: str,
    relationship: str = "child",
    status: str = "active",
    source: str = "admin_repair",
    actor: str = "system",
    created_at: str,
    version: int = 1,
    expected_generation: int,
) -> list[TransactionOperation]:
    """Compose both formal rows and the profile projection behind one fence."""
    parent_id = _required_text(parent_id, "parent_id")
    student_id = _required_text(student_id, "student_id")
    relationship = _required_text(relationship, "relationship")
    status = _required_text(status, "status")
    source = _required_text(source, "source")
    actor = _required_text(actor, "actor")
    created_at = _required_text(created_at, "created_at")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")

    binding = {
        "entity_type": "parent_student_binding",
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": relationship,
        "status": status,
        "source": source,
        "actor": actor,
        "version": version,
        "created_at": created_at,
        "updated_at": created_at,
    }
    names = {
        "#entity_type": "entity_type",
        "#parent_id": "parent_id",
        "#student_id": "student_id",
        "#relationship": "relationship",
        "#status": "status",
        "#source": "source",
        "#actor": "actor",
        "#version": "version",
        "#created_at": "created_at",
        "#updated_at": "updated_at",
    }
    values = {f":{key}": value for key, value in binding.items()}
    condition = (
        "(attribute_not_exists(PK) AND attribute_not_exists(SK)) OR "
        "(#parent_id = :parent_id AND #student_id = :student_id AND "
        "#relationship = :relationship AND #version = :version)"
    )
    update = (
        "SET #entity_type = if_not_exists(#entity_type, :entity_type), "
        "#parent_id = if_not_exists(#parent_id, :parent_id), "
        "#student_id = if_not_exists(#student_id, :student_id), "
        "#relationship = if_not_exists(#relationship, :relationship), "
        "#status = :status, #source = :source, #actor = :actor, "
        "#version = if_not_exists(#version, :version), "
        "#created_at = if_not_exists(#created_at, :created_at), "
        "#updated_at = :updated_at"
    )

    def binding_update(pk: str, sk: str) -> TransactionOperation:
        return {
            "Update": {
                "Key": {"PK": pk, "SK": sk},
                "UpdateExpression": update,
                "ConditionExpression": condition,
                "ExpressionAttributeNames": dict(names),
                "ExpressionAttributeValues": dict(values),
            }
        }

    return [
        account_deletion_repo.active_fence_condition(student_id, expected_generation),
        binding_update(f"USER#{parent_id}", f"CHILD#{student_id}"),
        binding_update(f"USER#{student_id}", f"PARENT#{parent_id}"),
        {
            "Update": {
                "Key": {"PK": f"USER#{student_id}", "SK": "PROFILE"},
                "UpdateExpression": (
                    "SET #parent_id = :parent_id, #relationship = :relationship, "
                    "#parent_binding_status = :status"
                ),
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND "
                    "#user_id = :student_id AND #role = :student_role AND "
                    "(attribute_not_exists(#parent_id) OR #parent_id = :parent_id) AND "
                    "(attribute_not_exists(#relationship) OR #relationship = :relationship)"
                ),
                "ExpressionAttributeNames": {
                    "#parent_id": "parent_id",
                    "#relationship": "relationship",
                    "#parent_binding_status": "parent_binding_status",
                    "#user_id": "user_id",
                    "#role": "role",
                },
                "ExpressionAttributeValues": {
                    ":parent_id": parent_id,
                    ":student_id": student_id,
                    ":student_role": "student",
                    ":relationship": relationship,
                    ":status": status,
                },
            }
        },
    ]


def put_parent_student_relationship(
    *,
    parent_id: str,
    student_id: str,
    relationship: str = "child",
    status: str = "active",
    source: str = "admin_repair",
    actor: str = "system",
    created_at: str,
    version: int = 1,
) -> ParentBindingResult:
    """Commit or replay the exact relationship without choosing a conflict winner."""
    table = get_table()
    snapshot = _parent_binding_snapshot(parent_id, student_id)
    replay = _matching_parent_relationship(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        version=version,
    )
    if replay is not None:
        return ParentBindingResult(
            ParentBindingDisposition.REPLAYED,
            binding=replay,
            profile=snapshot.profile,
        )
    if _parent_relationship_conflicts(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        version=version,
    ):
        return ParentBindingResult(ParentBindingDisposition.CONFLICT)

    try:
        fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
        account_deletion_repo.transact(
            build_parent_binding_transaction(
                parent_id=parent_id,
                student_id=student_id,
                relationship=relationship,
                status=status,
                source=source,
                actor=actor,
                created_at=created_at,
                version=version,
                expected_generation=_required_positive_integer(fence.get("generation")),
            ),
            table=table,
        )
    except account_deletion_repo.AccountDeletionConflict:
        current = _parent_binding_snapshot(parent_id, student_id)
        replay = _matching_parent_relationship(
            current,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            status=status,
            version=version,
        )
        if replay is not None:
            return ParentBindingResult(
                ParentBindingDisposition.REPLAYED,
                binding=replay,
                profile=current.profile,
            )
        if _parent_relationship_conflicts(
            current,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            version=version,
        ):
            return ParentBindingResult(ParentBindingDisposition.CONFLICT)
        return ParentBindingResult(ParentBindingDisposition.RETRYABLE)

    current = _parent_binding_snapshot(parent_id, student_id)
    binding = _matching_parent_relationship(
        current,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        version=version,
    )
    if binding is None:
        if _parent_relationship_conflicts(
            current,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            version=version,
        ):
            return ParentBindingResult(ParentBindingDisposition.CONFLICT)
        return ParentBindingResult(ParentBindingDisposition.RETRYABLE)
    return ParentBindingResult(
        ParentBindingDisposition.CREATED,
        binding=binding,
        profile=current.profile,
    )


def put_parent_student_binding(
    *,
    parent_id: str,
    student_id: str,
    relationship: str = "child",
    status: str = "active",
    source: str = "admin_repair",
    actor: str = "system",
    created_at: str,
    version: int = 1,
) -> UserItem:
    """Compatibility wrapper over the atomic relationship primitive."""
    result = put_parent_student_relationship(
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        source=source,
        actor=actor,
        created_at=created_at,
        version=version,
    )
    if result.binding is None:
        raise account_deletion_repo.AccountDeletionConflict(
            f"parent binding {result.disposition.value}"
        )
    return result.binding


def _parent_binding_snapshot(
    parent_id: str, student_id: str
) -> _ParentBindingSnapshot:
    return _ParentBindingSnapshot(
        profile=get_user(student_id),
        forward=get_parent_student_binding(parent_id, student_id),
        reverse=get_student_parent_binding(student_id, parent_id),
        reverse_rows=tuple(list_student_parent_bindings(student_id)),
    )


def _matching_parent_relationship(
    snapshot: _ParentBindingSnapshot,
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    status: str,
    version: int,
) -> UserItem | None:
    rows = (snapshot.forward, snapshot.reverse)
    if any(
        not _binding_row_matches(
            row,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            version=version,
            status=status,
        )
        for row in rows
    ):
        return None
    profile = snapshot.profile
    if (
        profile is None
        or profile.get("user_id") != student_id
        or profile.get("role") != "student"
        or profile.get("parent_id") != parent_id
        or profile.get("relationship") != relationship
        or profile.get("parent_binding_status") != status
    ):
        return None
    return snapshot.forward


def _parent_relationship_conflicts(
    snapshot: _ParentBindingSnapshot,
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    version: int,
) -> bool:
    profile = snapshot.profile
    if (
        profile is None
        or profile.get("user_id") != student_id
        or profile.get("role") != "student"
    ):
        return True
    profile_parent = profile.get("parent_id")
    if profile_parent is not None and profile_parent != "" and profile_parent != parent_id:
        return True
    profile_relationship = profile.get("relationship")
    if (
        profile_relationship is not None
        and profile_relationship != ""
        and profile_relationship != relationship
    ):
        return True
    for row in (snapshot.forward, snapshot.reverse, *snapshot.reverse_rows):
        if row is not None and not _binding_row_matches(
            row,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            version=version,
        ):
            return True
    return False


def _binding_row_matches(
    row: Mapping[str, object] | None,
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    version: int,
    status: str | None = None,
) -> bool:
    if row is None:
        return False
    if (
        row.get("parent_id") != parent_id
        or row.get("student_id") != student_id
        or row.get("relationship") != relationship
        or row.get("version") != version
    ):
        return False
    return status is None or row.get("status") == status


def get_parent_student_binding(parent_id: str, student_id: str) -> UserItem | None:
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def get_student_parent_binding(student_id: str, parent_id: str) -> UserItem | None:
    """Read the exact reverse formal row; profile fields never substitute for it."""
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{student_id}", "SK": f"PARENT#{parent_id}"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def list_parent_student_bindings(parent_id: str) -> list[UserItem]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{parent_id}") & Key("SK").begins_with("CHILD#"),
        ConsistentRead=True,
    )
    return _items(resp.get("Items", []))


def list_student_parent_bindings(student_id: str) -> list[UserItem]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{student_id}") & Key("SK").begins_with("PARENT#"),
        ConsistentRead=True,
    )
    return _items(resp.get("Items", []))


def update_student_parent_link(student_id: str, parent_id: str, relationship: str = "child") -> None:
    update_profile_fields(
        student_id,
        update_expression=(
            "SET parent_id = :parent_id, relationship = :relationship, "
            "parent_binding_status = :status"
        ),
        expression_attribute_values={
            ":parent_id": parent_id,
            ":relationship": relationship,
            ":status": "active",
        },
    )


def _optional_item(value: object) -> UserItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("malformed user repository response")
    item: UserItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise ValueError("malformed user repository response")
        item[key] = member
    return item


def _items(value: object) -> list[UserItem]:
    if not isinstance(value, list):
        raise ValueError("malformed user repository response")
    items: list[UserItem] = []
    for member in value:
        item = _optional_item(member)
        if item is None:
            raise ValueError("malformed user repository response")
        items.append(item)
    return items


def _required_positive_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("malformed account fence generation")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise ValueError("malformed account fence generation")
    if parsed < 1:
        raise ValueError("malformed account fence generation")
    return parsed


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value
