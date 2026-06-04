"""DynamoDB access patterns for the WeeklyReport entity."""
import base64
import json

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from stoa.db.dynamodb import get_table


def put_report(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item})


def try_claim_report_generation(item: dict) -> bool:
    table = get_table()
    try:
        table.put_item(
            Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_report_status(report_id: str, status: str, **fields) -> None:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    table.update_item(
        Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def try_start_generation_retry(report_id: str, *, operator: str, attempted_at: str) -> bool:
    """Atomically claim a generation-failed report for one admin retry."""
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :retrying, "
                "generation_retry_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            ConditionExpression="#status = :expected",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":retrying": "generation_retrying",
                ":expected": "generation_failed",
                ":attempted_at": attempted_at,
                ":operation": "retry_generation",
                ":operator": operator,
                ":in_progress": "in_progress",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_report_by_week(parent_id: str, week_start: str) -> dict | None:
    table = get_table()
    resp = table.query(
        IndexName="GSI-ParentId",
        KeyConditionExpression=Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_report_for_child_by_week(parent_id: str, student_id: str, week_start: str) -> dict | None:
    last_key = None
    while True:
        result = list_reports_for_parent_week(parent_id, week_start, last_key=last_key)
        for item in result.get("Items", []):
            if item.get("student_id") == student_id:
                return item
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return None


def encode_page_token(last_key: dict | None) -> str | None:
    """Encode a DynamoDB LastEvaluatedKey as an opaque API token."""
    if not last_key:
        return None
    raw = json.dumps(last_key, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_page_token(token: str | None) -> dict | None:
    """Decode an opaque API token into a DynamoDB ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Invalid pagination token")
    if not _is_valid_report_page_key(decoded):
        raise ValueError("Invalid pagination token")
    return decoded


def list_reports_for_admin(
    *,
    status: str | None = None,
    week_start: str | None = None,
    parent_id: str | None = None,
    student_id: str | None = None,
    limit: int = 50,
    last_key: dict | None = None,
) -> dict:
    """List report summary rows for admin operations.

    Parent-filtered access uses the existing parent/week GSI where possible.
    Cross-parent admin access uses a bounded scan for pilot volume; callers must
    pass a strict limit and preserve LastEvaluatedKey pagination.
    """
    if parent_id:
        return _list_reports_for_admin_parent_query(
            parent_id=parent_id,
            status=status,
            week_start=week_start,
            student_id=student_id,
            limit=limit,
            last_key=last_key,
        )
    return _list_reports_for_admin_scan(
        status=status,
        week_start=week_start,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
    )


def _list_reports_for_admin_parent_query(
    *,
    parent_id: str,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: dict | None,
) -> dict:
    table = get_table()
    key_expr = Key("parent_id").eq(parent_id)
    if week_start:
        key_expr = key_expr & Key("week_start").eq(week_start)

    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": key_expr,
        "Limit": limit,
        "ScanIndexForward": False,
    }
    filter_expr = _admin_report_filter_expression(status=status, student_id=student_id)
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def _list_reports_for_admin_scan(
    *,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: dict | None,
) -> dict:
    table = get_table()
    filter_expr = Attr("PK").begins_with("REPORT#") & Attr("SK").eq("SUMMARY")
    extra_filter = _admin_report_filter_expression(
        status=status,
        week_start=week_start,
        student_id=student_id,
    )
    if extra_filter is not None:
        filter_expr = filter_expr & extra_filter
    kwargs = {
        "FilterExpression": filter_expr,
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.scan(**kwargs)


def _admin_report_filter_expression(
    *,
    status: str | None = None,
    week_start: str | None = None,
    student_id: str | None = None,
):
    filter_expr = None
    if status:
        filter_expr = Attr("status").eq(status)
    if week_start:
        week_filter = Attr("week_start").eq(week_start)
        filter_expr = week_filter if filter_expr is None else filter_expr & week_filter
    if student_id:
        student_filter = Attr("student_id").eq(student_id)
        filter_expr = student_filter if filter_expr is None else filter_expr & student_filter
    return filter_expr


def _is_valid_report_page_key(decoded: dict) -> bool:
    pk = decoded.get("PK")
    sk = decoded.get("SK")
    return (
        isinstance(pk, str)
        and pk.startswith("REPORT#")
        and isinstance(sk, str)
        and sk == "SUMMARY"
    )


def list_reports_for_parent_week(
    parent_id: str,
    week_start: str,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def list_reports_for_parent(
    parent_id: str,
    limit: int = 25,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)
