"""Shared test doubles. The DynamoDB table double lives in `fakes.dynamodb`."""

from __future__ import annotations

from fakes.dynamodb import (
    ConditionEvaluator,
    FakeTable,
    IndexSchema,
    apply_update_expression,
    as_stored,
    condition_holds,
    conditional_check_failed,
)

__all__ = [
    "ConditionEvaluator",
    "FakeTable",
    "IndexSchema",
    "apply_update_expression",
    "as_stored",
    "condition_holds",
    "conditional_check_failed",
]
