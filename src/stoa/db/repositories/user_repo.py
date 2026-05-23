"""DynamoDB access patterns for the User entity."""
from boto3.dynamodb.conditions import Key
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
