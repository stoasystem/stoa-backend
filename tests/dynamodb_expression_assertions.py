"""DynamoDB expression-shape assertions shared by transaction test doubles."""

from __future__ import annotations

import re
from collections.abc import Mapping


_NAME_TOKEN = re.compile(r"#[A-Za-z0-9_]+")
_VALUE_TOKEN = re.compile(r":[A-Za-z0-9_]+")
_EXPRESSION_FIELDS = (
    "ConditionExpression",
    "FilterExpression",
    "KeyConditionExpression",
    "ProjectionExpression",
    "UpdateExpression",
)


def assert_expression_placeholders_closed(operation: Mapping[str, object]) -> None:
    """Require every expression placeholder to be defined and every definition used."""
    payload = next(
        (
            candidate
            for operation_type in ("ConditionCheck", "Delete", "Put", "Update")
            if isinstance(candidate := operation.get(operation_type), Mapping)
        ),
        None,
    )
    if payload is None:
        raise AssertionError(f"unsupported DynamoDB transaction operation: {operation!r}")

    expressions = " ".join(
        str(payload[field])
        for field in _EXPRESSION_FIELDS
        if isinstance(payload.get(field), str)
    )
    expected_names = set(_NAME_TOKEN.findall(expressions))
    expected_values = set(_VALUE_TOKEN.findall(expressions))
    actual_names = set(
        cast_mapping(payload.get("ExpressionAttributeNames"), "ExpressionAttributeNames")
    )
    actual_values = set(
        cast_mapping(payload.get("ExpressionAttributeValues"), "ExpressionAttributeValues")
    )

    assert actual_names == expected_names, (
        f"ExpressionAttributeNames must exactly close expressions: "
        f"expected={sorted(expected_names)!r}, actual={sorted(actual_names)!r}"
    )
    assert actual_values == expected_values, (
        f"ExpressionAttributeValues must exactly close expressions: "
        f"expected={sorted(expected_values)!r}, actual={sorted(actual_values)!r}"
    )


def cast_mapping(value: object, field: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AssertionError(f"{field} must be a mapping")
    return value
