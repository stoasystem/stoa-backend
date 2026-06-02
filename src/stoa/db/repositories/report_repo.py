"""DynamoDB access patterns for the WeeklyReport entity."""
from boto3.dynamodb.conditions import Key
from stoa.db.dynamodb import get_table


def put_report(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item})


def get_report_by_week(parent_id: str, week_start: str) -> dict | None:
    table = get_table()
    resp = table.query(
        IndexName="GSI-ParentId",
        KeyConditionExpression=Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


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
