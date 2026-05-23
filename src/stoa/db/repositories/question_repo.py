"""DynamoDB access patterns for the Question entity."""
from boto3.dynamodb.conditions import Key
from stoa.db.dynamodb import get_table


def put_question(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"QUESTION#{item['question_id']}", "SK": "META", **item})


def get_question(question_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"QUESTION#{question_id}", "SK": "META"})
    return resp.get("Item")


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
