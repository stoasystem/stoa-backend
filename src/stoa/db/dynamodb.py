"""DynamoDB single-table client wrapper."""
import boto3
from decimal import Decimal
from functools import lru_cache
from stoa.config import settings


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


@lru_cache
def get_table() -> object:
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(settings.dynamodb_table_name)
