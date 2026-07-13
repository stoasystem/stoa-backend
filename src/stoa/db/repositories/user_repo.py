"""DynamoDB access patterns for the User entity."""
from boto3.dynamodb.conditions import Attr, Key
from stoa.db.dynamodb import get_table


def put_user(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"USER#{item['user_id']}", "SK": "PROFILE", **item})


def get_user(user_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"})
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
    table = get_table()
    resp = table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression=(
            "SET preferred_locale = :locale, preferredLocale = :locale, "
            "#language = :locale, locale_updated_at = :updated_at, updated_at = :updated_at"
        ),
        ExpressionAttributeNames={"#language": "language"},
        ExpressionAttributeValues={
            ":locale": locale,
            ":updated_at": updated_at,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes", {})


def update_tutor_availability(
    user_id: str,
    *,
    subjects: list[str],
    weekly_availability: list[dict],
    updated_at: str,
) -> dict:
    table = get_table()
    resp = table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression=(
            "SET subjects = :subjects, primary_subjects = :subjects, "
            "dispatch_subjects = :subjects, weekly_availability = :weekly_availability, "
            "weeklyAvailability = :weekly_availability, availability_status = :availability, "
            "dispatch_availability = :availability, updated_at = :updated_at"
        ),
        ExpressionAttributeValues={
            ":subjects": subjects,
            ":weekly_availability": weekly_availability,
            ":availability": "available",
            ":updated_at": updated_at,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes", {})


def update_email_verification_state(user_id: str, fields: dict) -> dict:
    """Update bounded email verification metadata on a user profile."""
    if not fields:
        return get_user(user_id) or {}
    table = get_table()
    update_parts = []
    attr_names: dict[str, str] = {}
    attr_values: dict[str, object] = {}
    for idx, (field, value) in enumerate(fields.items()):
        name_key = f"#f{idx}"
        value_key = f":v{idx}"
        attr_names[name_key] = field
        attr_values[value_key] = value
        update_parts.append(f"{name_key} = {value_key}")
    resp = table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes", {})


def put_parent_student_binding(
    *,
    parent_id: str,
    student_id: str,
    relationship: str = "child",
    status: str = "active",
    source: str = "admin_repair",
    actor: str = "system",
    created_at: str,
) -> dict:
    """Persist the formal parent/student binding and a reverse lookup row."""
    table = get_table()
    binding = {
        "entity_type": "parent_student_binding",
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": relationship,
        "status": status,
        "source": source,
        "actor": actor,
        "created_at": created_at,
        "updated_at": created_at,
    }
    table.put_item(
        Item={
            "PK": f"USER#{parent_id}",
            "SK": f"CHILD#{student_id}",
            **binding,
        }
    )
    table.put_item(
        Item={
            "PK": f"USER#{student_id}",
            "SK": f"PARENT#{parent_id}",
            **binding,
        }
    )
    return binding


def get_parent_student_binding(parent_id: str, student_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"USER#{parent_id}", "SK": f"CHILD#{student_id}"})
    return resp.get("Item")


def list_parent_student_bindings(parent_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{parent_id}") & Key("SK").begins_with("CHILD#"),
    )
    return resp.get("Items", [])


def list_student_parent_bindings(student_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{student_id}") & Key("SK").begins_with("PARENT#"),
    )
    return resp.get("Items", [])


def update_student_parent_link(student_id: str, parent_id: str, relationship: str = "child") -> None:
    table = get_table()
    table.update_item(
        Key={"PK": f"USER#{student_id}", "SK": "PROFILE"},
        UpdateExpression=(
            "SET parent_id = :parent_id, relationship = :relationship, "
            "parent_binding_status = :status"
        ),
        ExpressionAttributeValues={
            ":parent_id": parent_id,
            ":relationship": relationship,
            ":status": "active",
        },
    )
