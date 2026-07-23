"""DynamoDB access patterns for the User entity."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


type UserItem = dict[str, object]
type TransactionOperation = dict[str, Any]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def _dependency_mapping(value: object) -> UserItem:
    item = _optional_item(value)
    if item is None:
        raise ValueError("malformed user repository response")
    return item


def _get_item(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _GetTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.get_item(**kwargs))


def _query(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _QueryTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.query(**kwargs))


def _scan(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _ScanTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.scan(**kwargs))


PROFILE_WRITE_MAX_ATTEMPTS = 3
PROFILE_SCRUB_OWNED_FIELDS = frozenset(
    {
        "child_user_id",
        "student_id",
        "child_id",
        "children",
        "child_summaries",
        "student_summaries",
    }
)

# Closed source inventory for every production mutation of USER#*/PROFILE.  The
# source-backed test in Plan 475-08 requires additions to be reviewed here; row
# creation and deletion scrub remain special lifecycle primitives, while every
# ordinary update is built by profile_update_operation().
PROFILE_WRITER_REGISTRY = frozenset(
    {
        "src/stoa/db/repositories/account_deletion_repo.py:materialize_profile_with_fence",
        "src/stoa/db/repositories/account_deletion_repo.py:_parent_profile_scrub_operation",
        "src/stoa/db/repositories/user_repo.py:profile_update_operation",
    }
)


class ProfileWriteDisposition(StrEnum):
    """Closed outcomes for one bounded shared-profile CAS operation."""

    UPDATED = "updated"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ProfileWriteResult:
    disposition: ProfileWriteDisposition
    profile: UserItem | None = None
    attempts: int = 0


class ParentBindingDisposition(StrEnum):
    """Closed outcomes for one atomic parent/student relationship write."""

    CREATED = "created"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    RETRYABLE = "retryable"


class ParentBindingStatusDisposition(StrEnum):
    """Closed outcomes for one explicit relationship lifecycle transition."""

    TRANSITIONED = "transitioned"
    CONFLICT = "conflict"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ParentBindingResult:
    disposition: ParentBindingDisposition
    binding: UserItem | None = None
    profile: UserItem | None = None


@dataclass(frozen=True, slots=True)
class ParentBindingStatusResult:
    disposition: ParentBindingStatusDisposition
    status: str | None = None
    version: int | None = None


class ParentBindingRepairClassification(StrEnum):
    """Closed preview classifications for historical relationship repair."""

    CONSISTENT = "consistent"
    REPAIRABLE_MISSING_FORWARD = "repairable_missing_forward"
    REPAIRABLE_MISSING_REVERSE = "repairable_missing_reverse"
    REPAIRABLE_PROFILE_PROJECTION = "repairable_profile_projection"
    CONFLICT = "conflict"
    SKIPPED_INVALID = "skipped_invalid"


class ParentBindingRepairApplyDisposition(StrEnum):
    """Closed outcomes for one preview-bound repair attempt."""

    REPAIRED = "repaired"
    ALREADY_CONSISTENT = "already_consistent"
    SKIPPED_CHANGED = "skipped_changed"
    CONFLICT = "conflict"
    SKIPPED_INVALID = "skipped_invalid"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ParentBindingRepairObservation:
    coordinate: str
    version: int | None
    digest: str


@dataclass(frozen=True, slots=True)
class ParentBindingRepairPreview:
    pair_id: str
    preview_id: str
    classification: ParentBindingRepairClassification
    proposed_action: str | None
    relationship_version: int | None
    observations: tuple[ParentBindingRepairObservation, ...]


@dataclass(frozen=True, slots=True)
class ParentBindingRepairApplyResult:
    disposition: ParentBindingRepairApplyDisposition
    preview: ParentBindingRepairPreview
    mutated: bool = False


@dataclass(frozen=True, slots=True)
class _ParentBindingSnapshot:
    parent_profile: UserItem | None
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
    resp = _get_item(
        table,
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def get_user_by_email(email: str) -> UserItem | None:
    table = get_table()
    resp = _query(
        table,
        IndexName="GSI-Email",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    items = _items(resp.get("Items", []))
    return items[0] if items else None


def list_children_by_parent_scan(parent_id: str) -> list[UserItem]:
    """Return student profiles that still use the legacy parent_id profile link."""
    table = get_table()
    scan_kwargs: dict[str, object] = {
        "FilterExpression": Attr("parent_id").eq(parent_id) & Attr("role").eq("student"),
    }
    children: list[UserItem] = []
    while True:
        resp = _scan(table, **scan_kwargs)
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


def update_email_verification_state(user_id: str, fields: Mapping[str, object]) -> UserItem:
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
    expected_version: int | None = None,
) -> list[TransactionOperation]:
    """Build one exact-generation, exact-version profile update."""
    return [
        account_deletion_repo.active_fence_condition(user_id, expected_generation),
        profile_update_operation(
            user_id,
            update_expression=update_expression,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            expected_version=expected_version,
        ),
    ]


def profile_update_operation(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    expected_version: int | None,
    additional_condition_expression: str | None = None,
) -> TransactionOperation:
    """Build the sole ordinary PROFILE update shape: narrow CAS plus one increment."""
    expression = update_expression.strip()
    if not expression:
        raise ValueError("profile update expression is required")
    names = dict(expression_attribute_names or {})
    values = dict(expression_attribute_values)
    if ":next_profile_version" in values:
        raise ValueError("profile version aliases are repository-owned")
    if expected_version is None:
        condition = "attribute_not_exists(version)"
        next_version = 1
    else:
        expected_version = _required_profile_version(expected_version)
        condition = "version=:expected_profile_version"
        values[":expected_profile_version"] = expected_version
        next_version = expected_version + 1
    values[":next_profile_version"] = next_version

    if expression.upper().startswith("SET "):
        expression = "SET version=:next_profile_version, " + expression[4:].lstrip()
    else:
        expression = "SET version=:next_profile_version " + expression
    condition_expression = "attribute_exists(PK) AND attribute_exists(SK) AND " + condition
    if additional_condition_expression:
        condition_expression += f" AND ({additional_condition_expression})"
    return {
        "Update": {
            "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
            "UpdateExpression": expression,
            "ConditionExpression": condition_expression,
            **({"ExpressionAttributeNames": names} if names else {}),
            "ExpressionAttributeValues": values,
        }
    }


def update_profile_fields_versioned(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    owned_fields: frozenset[str] | None = None,
    max_attempts: int = PROFILE_WRITE_MAX_ATTEMPTS,
) -> ProfileWriteResult:
    """Strong-read and apply one bounded, narrow profile CAS operation."""
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    fields = owned_fields or _profile_update_fields(update_expression, expression_attribute_names)
    # A stale ordinary mutation of scrub-owned data is never replayed after a
    # scrub wins.  Unrelated writers retain bounded retry and convergence.
    attempt_limit = 1 if fields & PROFILE_SCRUB_OWNED_FIELDS else max_attempts
    table = get_table()
    for attempt in range(1, attempt_limit + 1):
        profile = get_user(user_id)
        if profile is None:
            return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt)
        expected_version = _optional_profile_version(profile.get("version"))
        try:
            fence = account_deletion_repo.require_active_account_fence(user_id, table=table)
            account_deletion_repo.transact(
                build_profile_update_transaction(
                    user_id,
                    update_expression=update_expression,
                    expression_attribute_values=expression_attribute_values,
                    expression_attribute_names=expression_attribute_names,
                    expected_generation=_required_positive_integer(fence.get("generation")),
                    expected_version=expected_version,
                ),
                table=table,
            )
        except account_deletion_repo.AccountDeletionConflict:
            continue
        current = get_user(user_id)
        if current is None:
            return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt)
        return ProfileWriteResult(
            ProfileWriteDisposition.UPDATED,
            profile=current,
            attempts=attempt,
        )
    return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt_limit)


def update_profile_fields(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    owned_fields: frozenset[str] | None = None,
) -> UserItem:
    """Compatibility projection over the typed, bounded profile writer."""
    result = update_profile_fields_versioned(
        user_id,
        update_expression=update_expression,
        expression_attribute_values=expression_attribute_values,
        expression_attribute_names=expression_attribute_names,
        owned_fields=owned_fields,
    )
    if result.disposition is not ProfileWriteDisposition.UPDATED or result.profile is None:
        raise account_deletion_repo.AccountDeletionConflict("profile write remains retryable")
    return result.profile


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
    expected_parent_generation: int,
    expected_student_generation: int,
    expected_parent_profile_version: int,
    expected_student_profile_version: int,
) -> list[TransactionOperation]:
    """Compose both formal rows and the profile projection behind both accounts."""
    parent_id = _required_text(parent_id, "parent_id")
    student_id = _required_text(student_id, "student_id")
    relationship = _required_text(relationship, "relationship")
    status = _required_text(status, "status")
    source = _required_text(source, "source")
    actor = _required_text(actor, "actor")
    created_at = _required_text(created_at, "created_at")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    expected_parent_generation = _required_positive_integer(expected_parent_generation)
    expected_student_generation = _required_positive_integer(expected_student_generation)
    expected_parent_profile_version = _required_profile_version(expected_parent_profile_version)
    expected_student_profile_version = _required_profile_version(expected_student_profile_version)

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
        "#relationship = :relationship AND #status = :status AND "
        "#version = :version)"
    )
    update = (
        "SET #entity_type = if_not_exists(#entity_type, :entity_type), "
        "#parent_id = if_not_exists(#parent_id, :parent_id), "
        "#student_id = if_not_exists(#student_id, :student_id), "
        "#relationship = if_not_exists(#relationship, :relationship), "
        "#status = if_not_exists(#status, :status), "
        "#source = :source, #actor = :actor, "
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
        account_deletion_repo.active_fence_condition(parent_id, expected_parent_generation),
        account_deletion_repo.active_fence_condition(student_id, expected_student_generation),
        _active_profile_observation_condition(
            parent_id,
            role="parent",
            profile_version=expected_parent_profile_version,
        ),
        binding_update(f"USER#{parent_id}", f"CHILD#{student_id}"),
        binding_update(f"USER#{student_id}", f"PARENT#{parent_id}"),
        profile_update_operation(
            student_id,
            update_expression=(
                "SET #parent_id = :parent_id, #relationship = :relationship, "
                "#parent_binding_status = :status"
            ),
            expression_attribute_names={
                "#parent_id": "parent_id",
                "#relationship": "relationship",
                "#parent_binding_status": "parent_binding_status",
                "#user_id": "user_id",
                "#role": "role",
                "#account_status": "account_status",
            },
            expression_attribute_values={
                ":parent_id": parent_id,
                ":student_id": student_id,
                ":student_role": "student",
                ":active": "active",
                ":relationship": relationship,
                ":status": status,
            },
            expected_version=expected_student_profile_version,
            additional_condition_expression=(
                "#user_id = :student_id AND #role = :student_role AND "
                "#account_status = :active AND "
                "(attribute_not_exists(#parent_id) OR #parent_id = :parent_id) AND "
                "(attribute_not_exists(#relationship) OR "
                "#relationship = :relationship)"
            ),
        ),
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
    if _parent_relationship_conflicts(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        version=version,
    ):
        return ParentBindingResult(ParentBindingDisposition.CONFLICT)
    observations = _parent_binding_authorization_observations(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        table=table,
    )
    if observations is None:
        return ParentBindingResult(ParentBindingDisposition.RETRYABLE)
    (
        expected_parent_generation,
        expected_student_generation,
        expected_parent_profile_version,
        expected_student_profile_version,
    ) = observations
    replay = _matching_parent_relationship(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        version=version,
    )
    if replay is not None:
        if status != "active":
            return ParentBindingResult(ParentBindingDisposition.CONFLICT)
        return ParentBindingResult(
            ParentBindingDisposition.REPLAYED,
            binding=replay,
            profile=snapshot.profile,
        )
    try:
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
                expected_parent_generation=expected_parent_generation,
                expected_student_generation=expected_student_generation,
                expected_parent_profile_version=expected_parent_profile_version,
                expected_student_profile_version=expected_student_profile_version,
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
            if status != "active":
                return ParentBindingResult(ParentBindingDisposition.CONFLICT)
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
            status=status,
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
            status=status,
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


def build_parent_binding_status_transition_transaction(
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    expected_status: str,
    expected_version: int,
    status: str,
    source: str,
    actor: str,
    updated_at: str,
    expected_parent_generation: int,
    expected_student_generation: int,
    expected_parent_profile_version: int,
    expected_student_profile_version: int,
) -> list[TransactionOperation]:
    """Build one exact-status/version transition across all relationship projections."""
    parent_id = _required_text(parent_id, "parent_id")
    student_id = _required_text(student_id, "student_id")
    relationship = _required_text(relationship, "relationship")
    expected_status = _required_relationship_status(expected_status)
    status = _required_relationship_status(status)
    if status == expected_status:
        raise ValueError("relationship status transition must change status")
    expected_version = _required_profile_version(expected_version)
    source = _required_text(source, "source")
    actor = _required_text(actor, "actor")
    updated_at = _required_text(updated_at, "updated_at")
    expected_parent_generation = _required_positive_integer(expected_parent_generation)
    expected_student_generation = _required_positive_integer(expected_student_generation)
    expected_parent_profile_version = _required_profile_version(expected_parent_profile_version)
    expected_student_profile_version = _required_profile_version(expected_student_profile_version)
    next_version = expected_version + 1
    names = {
        "#parent_id": "parent_id",
        "#student_id": "student_id",
        "#relationship": "relationship",
        "#status": "status",
        "#version": "version",
        "#source": "source",
        "#actor": "actor",
        "#updated_at": "updated_at",
    }
    values = {
        ":parent_id": parent_id,
        ":student_id": student_id,
        ":relationship": relationship,
        ":expected_status": expected_status,
        ":expected_version": expected_version,
        ":next_status": status,
        ":next_version": next_version,
        ":source": source,
        ":actor": actor,
        ":updated_at": updated_at,
    }
    condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND "
        "#parent_id=:parent_id AND #student_id=:student_id AND "
        "#relationship=:relationship AND #status=:expected_status AND "
        "#version=:expected_version"
    )
    update = (
        "SET #status=:next_status, #version=:next_version, #source=:source, "
        "#actor=:actor, #updated_at=:updated_at"
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
        account_deletion_repo.active_fence_condition(
            parent_id, expected_parent_generation
        ),
        account_deletion_repo.active_fence_condition(
            student_id, expected_student_generation
        ),
        _active_profile_observation_condition(
            parent_id,
            role="parent",
            profile_version=expected_parent_profile_version,
        ),
        binding_update(f"USER#{parent_id}", f"CHILD#{student_id}"),
        binding_update(f"USER#{student_id}", f"PARENT#{parent_id}"),
        profile_update_operation(
            student_id,
            update_expression="SET #parent_binding_status=:next_status",
            expression_attribute_names={
                "#parent_binding_status": "parent_binding_status",
                "#user_id": "user_id",
                "#parent_id": "parent_id",
                "#relationship": "relationship",
                "#role": "role",
                "#account_status": "account_status",
            },
            expression_attribute_values={
                ":student_id": student_id,
                ":parent_id": parent_id,
                ":relationship": relationship,
                ":student_role": "student",
                ":active": "active",
                ":expected_binding_status": expected_status,
                ":next_status": status,
            },
            expected_version=expected_student_profile_version,
            additional_condition_expression=(
                "#user_id=:student_id AND #parent_id=:parent_id AND "
                "#relationship=:relationship AND #role=:student_role AND "
                "#account_status=:active AND "
                "#parent_binding_status=:expected_binding_status"
            ),
        ),
    ]


def transition_parent_student_relationship_status(
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    expected_status: str,
    expected_version: int,
    status: str,
    source: str,
    actor: str,
    updated_at: str,
) -> ParentBindingStatusResult:
    """Apply one explicit lifecycle transition guarded by exact status and version."""
    expected_status = _required_relationship_status(expected_status)
    status = _required_relationship_status(status)
    if status == expected_status:
        raise ValueError("relationship status transition must change status")
    expected_version = _required_profile_version(expected_version)
    table = get_table()
    snapshot = _parent_binding_snapshot(parent_id, student_id)
    if not _parent_binding_status_snapshot_matches(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=expected_status,
        version=expected_version,
    ):
        return ParentBindingStatusResult(ParentBindingStatusDisposition.CONFLICT)
    profile = snapshot.profile
    assert profile is not None
    observations = _parent_binding_authorization_observations(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        table=table,
    )
    if observations is None:
        return ParentBindingStatusResult(ParentBindingStatusDisposition.CONFLICT)
    (
        expected_parent_generation,
        expected_student_generation,
        expected_parent_profile_version,
        expected_student_profile_version,
    ) = observations
    try:
        account_deletion_repo.transact(
            build_parent_binding_status_transition_transaction(
                parent_id=parent_id,
                student_id=student_id,
                relationship=relationship,
                expected_status=expected_status,
                expected_version=expected_version,
                status=status,
                source=source,
                actor=actor,
                updated_at=updated_at,
                expected_parent_generation=expected_parent_generation,
                expected_student_generation=expected_student_generation,
                expected_parent_profile_version=expected_parent_profile_version,
                expected_student_profile_version=expected_student_profile_version,
            ),
            table=table,
        )
    except (ValueError, account_deletion_repo.AccountDeletionConflict):
        current = _parent_binding_snapshot(parent_id, student_id)
        current_observations = _parent_binding_authorization_observations(
            current,
            parent_id=parent_id,
            student_id=student_id,
            table=table,
        )
        disposition = (
            ParentBindingStatusDisposition.RETRYABLE
            if current_observations is not None
            and _parent_binding_status_snapshot_matches(
                current,
                parent_id=parent_id,
                student_id=student_id,
                relationship=relationship,
                status=expected_status,
                version=expected_version,
            )
            else ParentBindingStatusDisposition.CONFLICT
        )
        return ParentBindingStatusResult(disposition)
    current = _parent_binding_snapshot(parent_id, student_id)
    next_version = expected_version + 1
    if not _parent_binding_status_snapshot_matches(
        current,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status=status,
        version=next_version,
    ):
        return ParentBindingStatusResult(ParentBindingStatusDisposition.RETRYABLE)
    return ParentBindingStatusResult(
        ParentBindingStatusDisposition.TRANSITIONED,
        status=status,
        version=next_version,
    )


def preview_parent_binding_repair(
    *,
    parent_id: str,
    student_id: str,
    relationship: str = "child",
) -> ParentBindingRepairPreview:
    """Strongly inspect one explicit pair without mutating relationship state."""
    parent_id = _required_text(parent_id, "parent_id")
    student_id = _required_text(student_id, "student_id")
    relationship = _required_text(relationship, "relationship")
    snapshot = _parent_binding_snapshot(parent_id, student_id)
    classification, proposed_action, relationship_version = _classify_parent_binding_repair(
        snapshot,
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
    )
    observations = _parent_binding_repair_observations(snapshot)
    pair_id = _parent_binding_repair_digest("pair", parent_id, student_id, relationship)
    preview_id = _parent_binding_repair_digest(
        "preview",
        parent_id,
        student_id,
        relationship,
        classification.value,
        proposed_action or "",
        str(relationship_version or ""),
        *(f"{item.coordinate}:{item.version}:{item.digest}" for item in observations),
    )
    return ParentBindingRepairPreview(
        pair_id=pair_id,
        preview_id=preview_id,
        classification=classification,
        proposed_action=proposed_action,
        relationship_version=relationship_version,
        observations=observations,
    )


def apply_parent_binding_repair(
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    preview_id: str,
    actor: str,
    created_at: str,
) -> ParentBindingRepairApplyResult:
    """Apply one unchanged, unambiguous preview through the atomic writer."""
    preview_id = _required_text(preview_id, "preview_id")
    current = preview_parent_binding_repair(
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
    )
    if current.classification is ParentBindingRepairClassification.CONFLICT:
        return ParentBindingRepairApplyResult(ParentBindingRepairApplyDisposition.CONFLICT, current)
    if current.classification is ParentBindingRepairClassification.CONSISTENT:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.ALREADY_CONSISTENT, current
        )
    if current.classification is ParentBindingRepairClassification.SKIPPED_INVALID:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.SKIPPED_INVALID, current
        )
    if current.preview_id != preview_id:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.SKIPPED_CHANGED, current
        )
    if current.relationship_version is None:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.SKIPPED_INVALID, current
        )

    result = put_parent_student_relationship(
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
        status="active",
        source="admin_reconciliation",
        actor=_required_text(actor, "actor"),
        created_at=_required_text(created_at, "created_at"),
        version=current.relationship_version,
    )
    refreshed = preview_parent_binding_repair(
        parent_id=parent_id,
        student_id=student_id,
        relationship=relationship,
    )
    if refreshed.classification is ParentBindingRepairClassification.CONSISTENT:
        disposition = (
            ParentBindingRepairApplyDisposition.REPAIRED
            if result.disposition is ParentBindingDisposition.CREATED
            else ParentBindingRepairApplyDisposition.ALREADY_CONSISTENT
        )
        return ParentBindingRepairApplyResult(
            disposition,
            refreshed,
            mutated=result.disposition is ParentBindingDisposition.CREATED,
        )
    if refreshed.classification is ParentBindingRepairClassification.CONFLICT:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.CONFLICT, refreshed
        )
    if refreshed.preview_id != current.preview_id:
        return ParentBindingRepairApplyResult(
            ParentBindingRepairApplyDisposition.SKIPPED_CHANGED, refreshed
        )
    return ParentBindingRepairApplyResult(ParentBindingRepairApplyDisposition.RETRYABLE, refreshed)


def _parent_binding_snapshot(parent_id: str, student_id: str) -> _ParentBindingSnapshot:
    return _ParentBindingSnapshot(
        parent_profile=get_user(parent_id),
        profile=get_user(student_id),
        forward=get_parent_student_binding(parent_id, student_id),
        reverse=get_student_parent_binding(student_id, parent_id),
        reverse_rows=tuple(list_student_parent_bindings(student_id)),
    )


def _classify_parent_binding_repair(
    snapshot: _ParentBindingSnapshot,
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
) -> tuple[ParentBindingRepairClassification, str | None, int | None]:
    parent = snapshot.parent_profile
    student = snapshot.profile
    if (
        parent is None
        or parent.get("user_id") != parent_id
        or parent.get("role") != "parent"
        or parent.get("account_status") != "active"
        or student is None
        or student.get("user_id") != student_id
        or student.get("role") != "student"
        or student.get("account_status") != "active"
    ):
        return ParentBindingRepairClassification.SKIPPED_INVALID, None, None

    profile_parent = student.get("parent_id")
    profile_relationship = student.get("relationship")
    if profile_parent not in (None, "", parent_id):
        return ParentBindingRepairClassification.CONFLICT, None, None
    if profile_relationship not in (None, "", relationship):
        return ParentBindingRepairClassification.CONFLICT, None, None

    rows = tuple(
        row
        for row in (snapshot.forward, snapshot.reverse, *snapshot.reverse_rows)
        if row is not None
    )
    for row in rows:
        if row.get("parent_id") != parent_id or row.get("student_id") != student_id:
            return ParentBindingRepairClassification.CONFLICT, None, None
        if row.get("relationship") != relationship:
            return ParentBindingRepairClassification.CONFLICT, None, None
        if row.get("status") != "active":
            return ParentBindingRepairClassification.SKIPPED_INVALID, None, None
        try:
            _required_profile_version(row.get("version"))
        except ValueError:
            return ParentBindingRepairClassification.SKIPPED_INVALID, None, None

    # The point read and the bounded reverse query are independent strong reads.
    # If the same exact row changed between them, do not derive an apply action.
    queried_exact = next(
        (
            row
            for row in snapshot.reverse_rows
            if row.get("PK") == f"USER#{student_id}" and row.get("SK") == f"PARENT#{parent_id}"
        ),
        None,
    )
    if snapshot.reverse is not None and (
        queried_exact is None
        or _parent_binding_row_digest(queried_exact) != _parent_binding_row_digest(snapshot.reverse)
    ):
        return ParentBindingRepairClassification.SKIPPED_INVALID, None, None
    if snapshot.reverse is None and queried_exact is not None:
        return ParentBindingRepairClassification.SKIPPED_INVALID, None, None

    forward_version = (
        _required_profile_version(snapshot.forward.get("version"))
        if snapshot.forward is not None
        else None
    )
    reverse_version = (
        _required_profile_version(snapshot.reverse.get("version"))
        if snapshot.reverse is not None
        else None
    )
    if (
        forward_version is not None
        and reverse_version is not None
        and forward_version != reverse_version
    ):
        return ParentBindingRepairClassification.CONFLICT, None, None
    relationship_version = forward_version or reverse_version
    profile_matches = (
        profile_parent == parent_id
        and profile_relationship == relationship
        and student.get("parent_binding_status") == "active"
    )
    if snapshot.forward is not None and snapshot.reverse is not None:
        if profile_matches:
            return (
                ParentBindingRepairClassification.CONSISTENT,
                None,
                relationship_version,
            )
        if (
            profile_parent in (None, "", parent_id)
            and profile_relationship in (None, "", relationship)
            and student.get("parent_binding_status") in (None, "", "active")
        ):
            return (
                ParentBindingRepairClassification.REPAIRABLE_PROFILE_PROJECTION,
                "repair_profile_projection",
                relationship_version,
            )
        return ParentBindingRepairClassification.SKIPPED_INVALID, None, relationship_version
    if snapshot.forward is None and snapshot.reverse is not None and profile_matches:
        return (
            ParentBindingRepairClassification.REPAIRABLE_MISSING_FORWARD,
            "create_missing_forward",
            relationship_version,
        )
    if snapshot.forward is not None and snapshot.reverse is None and profile_matches:
        return (
            ParentBindingRepairClassification.REPAIRABLE_MISSING_REVERSE,
            "create_missing_reverse",
            relationship_version,
        )
    return ParentBindingRepairClassification.SKIPPED_INVALID, None, relationship_version


def _parent_binding_repair_observations(
    snapshot: _ParentBindingSnapshot,
) -> tuple[ParentBindingRepairObservation, ...]:
    rows = [
        ("parent_profile", snapshot.parent_profile),
        ("student_profile", snapshot.profile),
        ("forward", snapshot.forward),
        ("reverse_target", snapshot.reverse),
    ]
    for index, row in enumerate(
        sorted(
            snapshot.reverse_rows,
            key=lambda item: (str(item.get("PK") or ""), str(item.get("SK") or "")),
        )
    ):
        rows.append((f"reverse_query_{index}", row))
    return tuple(
        ParentBindingRepairObservation(
            coordinate=coordinate,
            version=_repair_observed_version(row),
            digest=_parent_binding_row_digest(row),
        )
        for coordinate, row in rows
    )


def _repair_observed_version(row: Mapping[str, object] | None) -> int | None:
    if row is None or row.get("version") is None:
        return None
    try:
        return _required_profile_version(row.get("version"))
    except ValueError:
        return None


def _parent_binding_row_digest(row: Mapping[str, object] | None) -> str:
    canonical = json.dumps(
        _parent_binding_digest_value(row),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(
        b"stoa-parent-binding-repair-row-v1\x00" + canonical.encode("utf-8")
    ).hexdigest()


def _parent_binding_digest_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _parent_binding_digest_value(member)
            for key, member in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_parent_binding_digest_value(member) for member in value]
    if isinstance(value, (set, frozenset)):
        members = [_parent_binding_digest_value(member) for member in value]
        return sorted(members, key=lambda member: json.dumps(member, sort_keys=True))
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    return {"unsupported_type": type(value).__name__}


def _parent_binding_repair_digest(kind: str, *parts: str) -> str:
    material = b"stoa-parent-binding-repair-v1\x00" + kind.encode("utf-8") + b"\x00"
    for part in parts:
        encoded = part.encode("utf-8")
        material += len(encoded).to_bytes(8, "big") + encoded
    return hashlib.sha256(material).hexdigest()


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
            status=status,
            version=version,
        )
        for row in rows
    ):
        return None
    profile = snapshot.profile
    parent_profile = snapshot.parent_profile
    if (
        parent_profile is None
        or parent_profile.get("user_id") != parent_id
        or parent_profile.get("role") != "parent"
        or parent_profile.get("account_status") != "active"
        or profile is None
        or profile.get("user_id") != student_id
        or profile.get("role") != "student"
        or profile.get("account_status") != "active"
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
    status: str,
    version: int,
) -> bool:
    profile = snapshot.profile
    parent_profile = snapshot.parent_profile
    if (
        parent_profile is None
        or parent_profile.get("user_id") != parent_id
        or parent_profile.get("role") != "parent"
        or parent_profile.get("account_status") != "active"
        or profile is None
        or profile.get("user_id") != student_id
        or profile.get("role") != "student"
        or profile.get("account_status") != "active"
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
            status=status,
            version=version,
        ):
            return True
    return False


def _parent_binding_status_snapshot_matches(
    snapshot: _ParentBindingSnapshot,
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    status: str,
    version: int,
) -> bool:
    if any(
        not _binding_row_matches(
            row,
            parent_id=parent_id,
            student_id=student_id,
            relationship=relationship,
            status=status,
            version=version,
        )
        for row in (snapshot.forward, snapshot.reverse)
    ):
        return False
    profile = snapshot.profile
    return bool(
        profile is not None
        and profile.get("user_id") == student_id
        and profile.get("parent_id") == parent_id
        and profile.get("relationship") == relationship
        and profile.get("parent_binding_status") == status
    )


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
    resp = _get_item(
        table,
        Key={"PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def get_student_parent_binding(student_id: str, parent_id: str) -> UserItem | None:
    """Read the exact reverse formal row; profile fields never substitute for it."""
    table = get_table()
    resp = _get_item(
        table,
        Key={"PK": f"USER#{student_id}", "SK": f"PARENT#{parent_id}"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def list_parent_student_bindings(parent_id: str) -> list[UserItem]:
    table = get_table()
    resp = _query(
        table,
        KeyConditionExpression=Key("PK").eq(f"USER#{parent_id}") & Key("SK").begins_with("CHILD#"),
        ConsistentRead=True,
    )
    return _items(resp.get("Items", []))


def list_student_parent_bindings(student_id: str) -> list[UserItem]:
    table = get_table()
    resp = _query(
        table,
        KeyConditionExpression=Key("PK").eq(f"USER#{student_id}")
        & Key("SK").begins_with("PARENT#"),
        ConsistentRead=True,
    )
    return _items(resp.get("Items", []))


def update_student_parent_link(
    student_id: str, parent_id: str, relationship: str = "child"
) -> None:
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


def _required_profile_version(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("malformed profile version")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise ValueError("malformed profile version")
    if parsed < 1:
        raise ValueError("malformed profile version")
    return parsed


def _optional_profile_version(value: object) -> int | None:
    if value is None:
        return None
    return _required_profile_version(value)


def _profile_update_fields(
    update_expression: str, expression_attribute_names: Mapping[str, str] | None
) -> frozenset[str]:
    aliases = set((expression_attribute_names or {}).values())
    identifiers = set(re.findall(r"(?<![:#])[A-Za-z_][A-Za-z0-9_]*", update_expression))
    return frozenset(aliases | identifiers)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def _required_relationship_status(value: object) -> str:
    status = _required_text(value, "relationship status")
    if status not in {"active", "active_pending_verification", "inactive", "revoked"}:
        raise ValueError("unsupported relationship status")
    return status


def _active_profile_observation_condition(
    user_id: str,
    *,
    role: str,
    profile_version: int,
) -> TransactionOperation:
    """Bind one canonical active profile observation into a transaction."""
    return {
        "ConditionCheck": {
            "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
            "ConditionExpression": (
                "attribute_exists(PK) AND attribute_exists(SK) AND "
                "#user_id=:user_id AND #role=:role AND "
                "#account_status=:active AND #version=:profile_version"
            ),
            "ExpressionAttributeNames": {
                "#user_id": "user_id",
                "#role": "role",
                "#account_status": "account_status",
                "#version": "version",
            },
            "ExpressionAttributeValues": {
                ":user_id": user_id,
                ":role": role,
                ":active": "active",
                ":profile_version": profile_version,
            },
        }
    }


def _parent_binding_authorization_observations(
    snapshot: _ParentBindingSnapshot,
    *,
    parent_id: str,
    student_id: str,
    table: object,
) -> tuple[int, int, int, int] | None:
    """Load exact dual-account observations without a legacy-role fallback."""
    parent = snapshot.parent_profile
    student = snapshot.profile
    if (
        parent is None
        or parent.get("user_id") != parent_id
        or parent.get("role") != "parent"
        or parent.get("account_status") != "active"
        or student is None
        or student.get("user_id") != student_id
        or student.get("role") != "student"
        or student.get("account_status") != "active"
    ):
        return None
    try:
        parent_profile_version = _required_profile_version(parent.get("version"))
        student_profile_version = _required_profile_version(student.get("version"))
        parent_fence = account_deletion_repo.require_active_account_fence(parent_id, table=table)
        student_fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
        parent_generation = _required_positive_integer(parent_fence.get("generation"))
        student_generation = _required_positive_integer(student_fence.get("generation"))
    except (ValueError, account_deletion_repo.AccountDeletionConflict):
        return None
    return (
        parent_generation,
        student_generation,
        parent_profile_version,
        student_profile_version,
    )
