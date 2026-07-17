"""DynamoDB access patterns for the User entity."""
from datetime import UTC, datetime

from boto3.dynamodb.conditions import Attr, Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


def put_user(item: dict) -> None:
    timestamp = str(item.get("created_at") or datetime.now(UTC).isoformat())
    account_deletion_repo.materialize_profile_with_fence(
        item, now_iso=timestamp, table=get_table()
    )


def get_user(user_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        ConsistentRead=True,
    )
    return resp.get("Item")


def get_user_by_email(email: str) -> dict | None:
    table = get_table()
    resp = table.query(
        IndexName="GSI-Email",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def list_children_by_parent_scan(parent_id: str) -> list[dict]:
    """Return student profiles that still use the legacy parent_id profile link."""
    table = get_table()
    scan_kwargs = {
        "FilterExpression": Attr("parent_id").eq(parent_id) & Attr("role").eq("student"),
    }
    children: list[dict] = []
    while True:
        resp = table.scan(**scan_kwargs)
        children.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return children
        scan_kwargs["ExclusiveStartKey"] = last_key


def update_locale_preference(user_id: str, locale: str, updated_at: str) -> dict:
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
    weekly_availability: list[dict],
    updated_at: str,
) -> dict:
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


def update_email_verification_state(user_id: str, fields: dict) -> dict:
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
    expression_attribute_values: dict,
    expression_attribute_names: dict | None = None,
    expected_generation: int,
) -> list[dict]:
    """Build one exact-generation profile update that cannot ghost-upsert."""
    return [
        account_deletion_repo.active_fence_condition(user_id, expected_generation),
        {
            "Update": {
                "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
                "UpdateExpression": update_expression,
                "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
                **(
                    {"ExpressionAttributeNames": expression_attribute_names}
                    if expression_attribute_names
                    else {}
                ),
                "ExpressionAttributeValues": expression_attribute_values,
            }
        },
    ]


def update_profile_fields(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: dict,
    expression_attribute_names: dict | None = None,
) -> dict:
    table = get_table()
    fence = account_deletion_repo.require_active_account_fence(user_id, table=table)
    account_deletion_repo.transact(
        build_profile_update_transaction(
            user_id,
            update_expression=update_expression,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            expected_generation=int(fence["generation"]),
        ),
        table=table,
    )
    return get_user(user_id) or {}


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
) -> dict:
    """Persist the formal parent/student binding and a reverse lookup row."""
    table = get_table()
    fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
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
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(
                student_id, int(fence["generation"])
            ),
            {"Put": {"Item": {
            "PK": f"USER#{parent_id}",
            "SK": f"CHILD#{student_id}",
            **binding,
            }}},
            {"Put": {"Item": {
            "PK": f"USER#{student_id}",
            "SK": f"PARENT#{parent_id}",
            **binding,
            }}},
        ],
        table=table,
    )
    return binding


def get_parent_student_binding(parent_id: str, student_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}"},
        ConsistentRead=True,
    )
    return resp.get("Item")


def get_student_parent_binding(student_id: str, parent_id: str) -> dict | None:
    """Read the exact reverse formal row; profile fields never substitute for it."""
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"USER#{student_id}", "SK": f"PARENT#{parent_id}"},
        ConsistentRead=True,
    )
    return resp.get("Item")


def list_parent_student_bindings(parent_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{parent_id}") & Key("SK").begins_with("CHILD#"),
        ConsistentRead=True,
    )
    return resp.get("Items", [])


def list_student_parent_bindings(student_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{student_id}") & Key("SK").begins_with("PARENT#"),
        ConsistentRead=True,
    )
    return resp.get("Items", [])


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
