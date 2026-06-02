"""DynamoDB access patterns for the WeeklyReport entity."""
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
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
