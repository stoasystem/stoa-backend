"""DynamoDB access patterns for the Question entity."""
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from stoa.db.dynamodb import get_table


def put_question(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"QUESTION#{item['question_id']}", "SK": "META", **item})


def question_item(item: dict) -> dict:
    """Build the canonical question transaction item without persisting it."""
    return {"PK": f"QUESTION#{item['question_id']}", "SK": "META", **item}


def get_question(question_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(
        Key={"PK": f"QUESTION#{question_id}", "SK": "META"},
        ConsistentRead=True,
    )
    return resp.get("Item")


def get_teacher_session(session_id: str) -> dict | None:
    """Read a current teacher-session snapshot without changing its lifecycle."""
    if not session_id:
        return None
    response = get_table().get_item(
        Key={"PK": f"SESSION#{session_id}", "SK": "META"},
        ConsistentRead=True,
    )
    return response.get("Item")


def get_teacher_assignment(teacher_id: str, student_id: str) -> dict | None:
    """Read the existing scoped assignment row; Phase 475 owns its writes."""
    if not teacher_id or not student_id:
        return None
    response = get_table().get_item(
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": f"STUDENT#{student_id}",
        },
        ConsistentRead=True,
    )
    return response.get("Item")


def get_teacher_curriculum_assignment(teacher_id: str) -> dict | None:
    """Read the current teacher curriculum-scope projection consistently.

    Phase 475 owns assignment write consistency. This read deliberately uses one
    current projection and fails closed when it is absent or unavailable.
    """
    if not teacher_id:
        return None
    response = get_table().get_item(
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": "CURRICULUM#CURRENT",
        },
        ConsistentRead=True,
    )
    return response.get("Item")


def list_by_student(student_id: str, limit: int = 20, last_key: dict | None = None) -> dict:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": Key("student_id").eq(student_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def record_daily_question_usage(student_id: str, day: str, limit: int, expires_at: int) -> int | None:
    """Atomically record one question submission, returning None when quota is exhausted."""
    table = get_table()
    try:
        resp = table.update_item(
            Key={"PK": f"USAGE#{student_id}", "SK": f"QUESTION#{day}"},
            UpdateExpression=(
                "ADD #c :one SET #ttl = if_not_exists(#ttl, :exp), "
                "usage_type = if_not_exists(usage_type, :usage_type)"
            ),
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "expires_at"},
            ExpressionAttributeValues={
                ":one": 1,
                ":limit": limit,
                ":exp": expires_at,
                ":usage_type": "daily_question_submission",
            },
            ReturnValues="UPDATED_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return None
        raise
    return int(resp.get("Attributes", {}).get("count", 1))


def update_status(question_id: str, status: str, **extra_attrs) -> None:
    table = get_table()
    update_expr = "SET #s = :s"
    attr_names = {"#s": "status"}
    attr_values = {":s": status}
    for k, v in extra_attrs.items():
        update_expr += f", {k} = :{k}"
        attr_values[f":{k}"] = v
    table.update_item(
        Key={"PK": f"QUESTION#{question_id}", "SK": "META"},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def update_status_conditionally(
    question_id: str,
    status: str,
    *,
    condition_expression: str,
    condition_names: dict | None = None,
    condition_values: dict | None = None,
    **extra_attrs,
) -> bool:
    """Update a question row when a DynamoDB condition still holds."""
    table = get_table()
    update_expr = "SET #s = :s"
    attr_names = {"#s": "status", **(condition_names or {})}
    attr_values = {":s": status, **(condition_values or {})}
    for k, v in extra_attrs.items():
        update_expr += f", {k} = :{k}"
        attr_values[f":{k}"] = v

    try:
        table.update_item(
            Key={"PK": f"QUESTION#{question_id}", "SK": "META"},
            UpdateExpression=update_expr,
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True
