"""DynamoDB single-table client wrapper."""
import boto3
from collections.abc import Callable, Mapping
from decimal import Decimal
from functools import lru_cache
from stoa.config import settings

# Far more pages than this table has; a reader that needs more has a filter
# that is not doing its job, and should say so rather than read the account.
SCAN_PAGE_BUDGET = 200


def stored_int(value: object) -> int | None:
    """One number as it comes back from the table, or None when it is not a whole one.

    The resource interface returns every stored number as `Decimal`, so a guard
    written against `int` refuses the values it exists to check - and refuses them
    only in production, because in-memory doubles hand back the `int` that was put
    in. Booleans are not versions, and `True` is an `int`, so they are refused.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            return None
        return int(value)
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    return None


def omit_none_attributes(item: Mapping[str, object]) -> dict[str, object]:
    """`item` without the top-level attributes whose value is None.

    The resource interface serializes None as the NULL type, and the table refuses a
    NULL in an attribute one of its indexes keys on: on 2026-07-09 the usage ledger's
    `PutItem` was refused five times with "Type mismatch for Index Key parent_id
    Expected: S Actual: NULL IndexName: GSI-ParentId". Leaving the attribute out is
    what a sparse index expects, and it is what the transaction serializers already
    do with a Put's item. Nested None values stay: they are not index keys.
    """
    return {key: value for key, value in item.items() if value is not None}


@lru_cache
def get_table() -> object:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(settings.dynamodb_table_name)


def scan_every_page(
    scan: Callable[..., Mapping[str, object]],
    table: object,
    *,
    want: int | None = None,
    page_budget: int = SCAN_PAGE_BUDGET,
    **kwargs: object,
) -> dict[str, object]:
    """Every row a filtered scan admits, across the table's pages.

    `Limit` bounds the rows a scan *reads*, not the rows its filter keeps, so
    `_scan(table, FilterExpression=..., Limit=100)` answers from the first
    hundred rows of the table and returns whichever of them matched. On a table
    larger than the thing being looked for that is nothing, and nothing says so
    -- a teacher's help request was invisible in production for exactly this
    reason (#95). Pass `want` for a cap on matches, which is what those call
    sites meant.

    `Limit` is not forwarded: a page here is the service's own megabyte.
    """
    kwargs.pop("Limit", None)
    items: list[object] = []
    request = dict(kwargs)
    for _page in range(page_budget):
        result = scan(table, **request)
        rows = result.get("Items")
        if isinstance(rows, list):
            items.extend(rows)
        if want is not None and len(items) >= want:
            return {"Items": items[:want], "Count": want}
        cursor = result.get("LastEvaluatedKey")
        # No key, or an empty one, is the end of the table (DynamoDB's Scan
        # contract allows both).
        if not cursor:
            return {"Items": items, "Count": len(items)}
        if not isinstance(cursor, Mapping) or cursor == request.get("ExclusiveStartKey"):
            raise RuntimeError("the table's scan did not move forward")
        request["ExclusiveStartKey"] = cursor
    raise RuntimeError("a filtered scan did not reach the end of the table")
