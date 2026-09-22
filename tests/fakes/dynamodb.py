"""One DynamoDB double for the whole suite, faithful where hand-written ones were not.

Five times a hand-written table double has been looser than the real store, and each
time the suite stayed green while production was broken. The five, and the rule each
one of them broke:

1. `Limit` applied *after* the filter instead of before it, and `LastEvaluatedKey`
   never returned. A real `Limit` counts rows *read*, so a page can be spent entirely
   on rows the filter drops. Card 018: the admin account list was permanently empty.
2. Numbers handed back as `int`. The resource interface deserializes every stored
   number to `Decimal`, so roughly sixty guards written against `int` passed against
   the double and refused the real values.
3. Writes performed with `dict.__setitem__`, skipping the conditional write the
   production path depends on to be correct under concurrency.
4. Rows planted directly instead of created through the real path, so a path that
   never wrote the row at all looked healthy.
5. A filter judged by whether some placeholder happened to be bound rather than by
   evaluating `FilterExpression`, so a scan that had stopped naming a row kind still
   got that kind back.

`tests/test_fakes_dynamodb_fidelity.py` holds one test per rule below; those tests are
what make this file load-bearing rather than merely well intentioned.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
import threading
from typing import Any, NamedTuple

from botocore.exceptions import ClientError


class IndexSchema(NamedTuple):
    """A global secondary index: what partitions it and what orders it."""

    partition_key: str
    sort_key: str | None = None


# The indexes this table actually carries. A row reaches an index only when it holds
# every one of its key attributes - that sparseness is a real DynamoDB property and
# `parent_link_repo` depends on it: the link rows omit `created_at` on purpose so they
# stay out of GSI-StudentId.
DEFAULT_INDEXES: dict[str, IndexSchema] = {
    "GSI-Email": IndexSchema("email"),
    "GSI-StudentId": IndexSchema("student_id", "created_at"),
    "GSI-ParentId": IndexSchema("parent_id", "week_start"),
    "GSI-ReviewState": IndexSchema("review_state", "created_at"),
}


def conditional_check_failed(operation: str) -> ClientError:
    """The error botocore raises, in the shape production code matches on."""
    return ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            },
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation,
    )


def transaction_canceled(reasons: list[str], operation: str = "TransactWriteItems") -> ClientError:
    """`TransactionCanceledException`, carrying one cancellation reason per operation."""
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "Transaction cancelled, please refer cancellation reasons",
            },
            "CancellationReasons": [{"Code": reason} for reason in reasons],
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        operation,
    )


def as_stored(value: Any) -> Any:
    """Numbers as the table gives them back, which is never `int`.

    `bool` is left alone: `True` is an `int` in Python but a `BOOL` in DynamoDB, and
    turning it into `Decimal(1)` would invent a difference the real store does not have.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Mapping):
        return {key: as_stored(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_stored(item) for item in value]
    if isinstance(value, set):
        return {as_stored(item) for item in value}
    return value


def _split_top(expression: str, separator: str) -> list[str]:
    """Split on a separator that is not nested inside parentheses."""
    parts: list[str] = []
    depth = 0
    current = ""
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and expression[index : index + len(separator)] == separator:
            parts.append(current)
            current = ""
            index += len(separator)
            continue
        current += char
        index += 1
    parts.append(current)
    return parts


def _split_conjuncts(text: str) -> list[str]:
    """Split on AND, keeping `a BETWEEN :lo AND :hi` in one piece."""
    parts = _split_top(text, " AND ")
    merged: list[str] = []
    for part in parts:
        if merged and " BETWEEN " in merged[-1] and " AND " not in merged[-1]:
            merged[-1] = f"{merged[-1]} AND {part}"
            continue
        merged.append(part)
    return merged


def _fully_wrapped(text: str) -> bool:
    if not text.startswith("(") or not text.endswith(")"):
        return False
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


def _compare(operator: str, stored: Any, expected: Any) -> bool:
    if operator == "=":
        return stored == expected
    if operator == "<>":
        return stored != expected
    if stored is None:
        return False
    try:
        if operator == "<":
            return stored < expected
        if operator == ">":
            return stored > expected
        if operator == "<=":
            return stored <= expected
        return stored >= expected
    except TypeError:
        return False


class ConditionEvaluator:
    """The subset of DynamoDB expression syntax this codebase actually writes.

    Every term is evaluated against the stored row. Judging a condition by which
    placeholders happen to be bound - incident 5 above - is what this replaces.
    """

    OPERATORS = ("<>", ">=", "<=", "=", "<", ">")

    def __init__(
        self, names: dict[str, str] | None = None, values: dict[str, Any] | None = None
    ) -> None:
        self.names = names or {}
        self.values = values or {}

    def holds(self, expression: str | None, item: dict[str, Any] | None) -> bool:
        if not expression:
            return True
        return self._clause(str(expression), item or {})

    def _clause(self, expression: str, item: dict[str, Any]) -> bool:
        text = expression.strip()
        if _fully_wrapped(text):
            return self._clause(text[1:-1], item)
        parts = _split_top(text, " OR ")
        if len(parts) > 1:
            return any(self._clause(part, item) for part in parts)
        parts = _split_conjuncts(text)
        if len(parts) > 1:
            return all(self._clause(part, item) for part in parts)
        if text.upper().startswith("NOT "):
            return not self._clause(text[4:], item)
        return self._primary(text, item)

    def _primary(self, expression: str, item: dict[str, Any]) -> bool:
        text = expression.strip()
        for prefix, decide in (
            ("attribute_not_exists(", lambda path, _args: path not in item),
            ("attribute_exists(", lambda path, _args: path in item),
        ):
            if text.startswith(prefix):
                return bool(decide(self.path(text[len(prefix) : -1]), ()))
        if text.startswith("begins_with("):
            path, value = (part.strip() for part in text[len("begins_with(") : -1].split(",", 1))
            stored = item.get(self.path(path))
            return isinstance(stored, str) and stored.startswith(str(self.value(value)))
        if text.startswith("contains("):
            path, value = (part.strip() for part in text[len("contains(") : -1].split(",", 1))
            stored = item.get(self.path(path))
            return stored is not None and self.value(value) in stored
        if text.startswith("attribute_type("):
            path, kind = (part.strip() for part in text[len("attribute_type(") : -1].split(",", 1))
            return _matches_type(item.get(self.path(path)), str(self.value(kind)))
        if " BETWEEN " in text:
            path, bounds = text.split(" BETWEEN ", 1)
            low, high = (part.strip() for part in bounds.split(" AND ", 1))
            stored = item.get(self.path(path))
            if stored is None:
                return False
            return self.value(low) <= stored <= self.value(high)
        if " IN " in text:
            path, listed = text.split(" IN ", 1)
            candidates = [
                self.value(token.strip()) for token in listed.strip().strip("()").split(",")
            ]
            return item.get(self.path(path)) in candidates
        for operator in self.OPERATORS:
            if operator in text:
                left, right = text.split(operator, 1)
                return _compare(operator, item.get(self.path(left)), self.value(right))
        raise AssertionError(f"unsupported condition: {expression}")

    def path(self, token: str) -> str:
        name = token.strip()
        return self.names.get(name, name)

    def value(self, token: str) -> Any:
        name = token.strip()
        if name.startswith(":"):
            if name not in self.values:
                raise AssertionError(f"unbound value: {name}")
            return as_stored(self.values[name])
        if name.startswith("#"):
            return self.names.get(name, name)
        return name


_TYPE_CHECKS = {
    "S": str,
    "N": (Decimal, int, float),
    "BOOL": bool,
    "L": list,
    "M": dict,
    "SS": set,
}


def _matches_type(stored: Any, kind: str) -> bool:
    expected = _TYPE_CHECKS.get(kind)
    if expected is None:
        raise AssertionError(f"unsupported attribute_type: {kind}")
    if kind == "N" and isinstance(stored, bool):
        return False
    return isinstance(stored, expected)


def _object_condition_holds(condition: Any, item: dict[str, Any]) -> bool:
    """Evaluate one boto3 `Attr`/`Key` condition tree the way the store would."""
    built = condition.get_expression()
    operator = built["operator"]
    values = built["values"]
    if operator == "AND":
        return all(_object_condition_holds(value, item) for value in values)
    if operator == "OR":
        return any(_object_condition_holds(value, item) for value in values)
    if operator == "NOT":
        return not _object_condition_holds(values[0], item)
    name = values[0]
    stored = item.get(name.name)
    if operator == "attribute_exists":
        return name.name in item
    if operator == "attribute_not_exists":
        return name.name not in item
    if operator == "begins_with":
        return isinstance(stored, str) and stored.startswith(str(values[1]))
    if operator == "contains":
        return stored is not None and values[1] in stored
    if operator == "BETWEEN":
        low, high = as_stored(values[1]), as_stored(values[2])
        return stored is not None and low <= stored <= high
    if operator == "IN":
        return stored in [as_stored(value) for value in values[1:]]
    if operator == "attribute_type":
        return _matches_type(stored, str(values[1]))
    expected = as_stored(values[1])
    if operator in ("=", "<>", "<", ">", "<=", ">="):
        return _compare(operator, stored, expected)
    raise AssertionError(f"unsupported condition operator: {operator}")


def condition_holds(
    condition: Any,
    item: dict[str, Any] | None,
    *,
    names: dict[str, str] | None = None,
    values: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a condition given either as a string expression or as a boto3 object."""
    if condition is None:
        return True
    if isinstance(condition, str):
        return ConditionEvaluator(names, values).holds(condition, item)
    return _object_condition_holds(condition, item or {})


def _resolve_operand(token: str, evaluator: ConditionEvaluator, item: dict[str, Any]) -> Any:
    """One side of a SET assignment: a placeholder, a stored path, or a function."""
    text = token.strip()
    if text.startswith("if_not_exists("):
        path, fallback = (part.strip() for part in _split_top(text[len("if_not_exists(") : -1], ","))
        current = item.get(evaluator.path(path))
        return current if current is not None else _resolve_operand(fallback, evaluator, item)
    if text.startswith("list_append("):
        first, second = (part.strip() for part in _split_top(text[len("list_append(") : -1], ","))
        head = _resolve_operand(first, evaluator, item) or []
        tail = _resolve_operand(second, evaluator, item) or []
        return list(head) + list(tail)
    for operator in ("+", "-"):
        parts = _split_top(text, operator)
        if len(parts) > 1:
            left = _resolve_operand(parts[0], evaluator, item)
            right = _resolve_operand(operator.join(parts[1:]), evaluator, item)
            left = Decimal(0) if left is None else left
            return left + right if operator == "+" else left - right
    if text.startswith(":"):
        return evaluator.value(text)
    if text.startswith("#") or text in item:
        return item.get(evaluator.path(text))
    return evaluator.value(text)


def apply_update_expression(
    item: dict[str, Any],
    expression: str,
    names: dict[str, str] | None = None,
    values: dict[str, Any] | None = None,
) -> set[str]:
    """Apply SET / REMOVE / ADD / DELETE in place, returning the names it touched.

    The names matter: `ReturnValues="UPDATED_NEW"` hands back only those, and a double
    that hands back the whole row lets a caller read an attribute the real response
    would not carry.
    """
    evaluator = ConditionEvaluator(names, values)
    touched: set[str] = set()
    clauses: list[tuple[str, str]] = []
    current_verb = ""
    current_body = ""
    for token in expression.replace("\n", " ").split(" "):
        upper = token.strip().upper()
        if upper in ("SET", "REMOVE", "ADD", "DELETE"):
            if current_verb:
                clauses.append((current_verb, current_body))
            current_verb, current_body = upper, ""
            continue
        current_body = f"{current_body} {token}"
    if current_verb:
        clauses.append((current_verb, current_body))
    if not clauses:
        raise AssertionError(f"unsupported update expression: {expression}")

    for verb, body in clauses:
        for fragment in _split_top(body.strip(), ","):
            piece = fragment.strip()
            if not piece:
                continue
            if verb == "SET":
                target, source = piece.split("=", 1)
                name = evaluator.path(target)
                item[name] = as_stored(_resolve_operand(source, evaluator, item))
                touched.add(name)
            elif verb == "REMOVE":
                item.pop(evaluator.path(piece), None)
            elif verb == "ADD":
                target, source = piece.split(" ", 1)
                name = evaluator.path(target)
                addend = evaluator.value(source)
                if isinstance(addend, set):
                    item[name] = set(item.get(name) or set()) | addend
                else:
                    item[name] = as_stored((item.get(name) or Decimal(0)) + addend)
                touched.add(name)
            else:
                target, source = piece.split(" ", 1)
                name = evaluator.path(target)
                item[name] = set(item.get(name) or set()) - set(evaluator.value(source))
                touched.add(name)
    return touched


def _key_of(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item["PK"]), str(item["SK"]))


# One response is capped at a megabyte of rows read, `Limit` or no `Limit`. A double
# that answers an unlimited scan with the whole table cannot fail the way `/admin/stats`
# failed: it counted one sample of a 3.76 MB table and reported it as the total.
DEFAULT_PAGE_SIZE_BYTES = 1024 * 1024


def item_size_bytes(item: dict[str, Any]) -> int:
    """Roughly what the row costs against the response cap: names plus values."""
    total = 0
    for name, value in item.items():
        total += len(str(name)) + _value_size_bytes(value)
    return total


def _value_size_bytes(value: Any) -> int:
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float, Decimal)):
        return len(str(value))
    if isinstance(value, str):
        return len(value.encode())
    if isinstance(value, dict):
        return sum(len(str(key)) + _value_size_bytes(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return sum(_value_size_bytes(item) for item in value)
    if value is None:
        return 1
    return len(str(value).encode())


class FakeTable:
    """An in-memory single table that answers the way DynamoDB answers.

    Subclass it to add counting, barriers or repository-specific helpers; override a
    method only to add behaviour around `super()`, never to relax a rule below.
    """

    def __init__(
        self,
        *,
        indexes: dict[str, IndexSchema] | None = None,
        rows: dict[tuple[str, str], dict[str, Any]] | None = None,
        page_size_bytes: int = DEFAULT_PAGE_SIZE_BYTES,
        page_item_cap: int | None = None,
    ) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.indexes = dict(DEFAULT_INDEXES if indexes is None else indexes)
        self.page_size_bytes = page_size_bytes
        # Where the response cap falls, stated in rows instead of bytes. It only ever
        # makes a page shorter, so a test can put the boundary at a known row without
        # having to compute the size of its fixture.
        self.page_item_cap = page_item_cap
        self.calls: Counter[str] = Counter()
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.lock = threading.RLock()
        if rows:
            for item in rows.values():
                self.seed(item)

    # -- seeding -----------------------------------------------------------------

    def seed(self, *items: dict[str, Any]) -> None:
        """Plant rows without going through a write path, for arranging a fixture.

        Nothing here is free of `as_stored`: a row planted as `int` would reintroduce
        incident 2 through the back door.
        """
        for item in items:
            self.rows[_key_of(item)] = as_stored(deepcopy(item))

    def item_count(self) -> int:
        return len(self.rows)

    def _record(self, operation: str, request: dict[str, Any]) -> None:
        self.calls[operation] += 1
        self.requests.append((operation, request))

    # -- point operations --------------------------------------------------------

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record("get_item", kwargs)
            key = (str(kwargs["Key"]["PK"]), str(kwargs["Key"]["SK"]))
            item = self.rows.get(key)
            return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record("put_item", kwargs)
            item = kwargs["Item"]
            key = _key_of(item)
            if not condition_holds(
                kwargs.get("ConditionExpression"),
                self.rows.get(key),
                names=kwargs.get("ExpressionAttributeNames"),
                values=kwargs.get("ExpressionAttributeValues"),
            ):
                raise conditional_check_failed("PutItem")
            previous = self.rows.get(key)
            self.rows[key] = as_stored(deepcopy(item))
            return self._return_values(kwargs.get("ReturnValues"), previous, self.rows[key])

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record("update_item", kwargs)
            key = (str(kwargs["Key"]["PK"]), str(kwargs["Key"]["SK"]))
            current = self.rows.get(key)
            if not condition_holds(
                kwargs.get("ConditionExpression"),
                current,
                names=kwargs.get("ExpressionAttributeNames"),
                values=kwargs.get("ExpressionAttributeValues"),
            ):
                raise conditional_check_failed("UpdateItem")
            updated = deepcopy(current) if current is not None else dict(kwargs["Key"])
            touched = apply_update_expression(
                updated,
                str(kwargs["UpdateExpression"]),
                kwargs.get("ExpressionAttributeNames"),
                kwargs.get("ExpressionAttributeValues"),
            )
            self.rows[key] = as_stored(updated)
            return self._return_values(
                kwargs.get("ReturnValues"), current, self.rows[key], touched
            )

    def delete_item(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record("delete_item", kwargs)
            key = (str(kwargs["Key"]["PK"]), str(kwargs["Key"]["SK"]))
            current = self.rows.get(key)
            if not condition_holds(
                kwargs.get("ConditionExpression"),
                current,
                names=kwargs.get("ExpressionAttributeNames"),
                values=kwargs.get("ExpressionAttributeValues"),
            ):
                raise conditional_check_failed("DeleteItem")
            self.rows.pop(key, None)
            return self._return_values(kwargs.get("ReturnValues"), current, None)

    @staticmethod
    def _return_values(
        requested: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        touched: set[str] | None = None,
    ) -> dict[str, Any]:
        if requested in (None, "NONE"):
            return {}
        if requested == "ALL_OLD":
            return {"Attributes": deepcopy(before)} if before is not None else {}
        if requested == "ALL_NEW":
            return {"Attributes": deepcopy(after)} if after is not None else {}
        if requested == "UPDATED_NEW":
            if after is None:
                return {}
            names = touched if touched is not None else set(after)
            return {"Attributes": {name: deepcopy(after[name]) for name in sorted(names)}}
        raise AssertionError(f"unsupported ReturnValues: {requested}")

    # -- reads over many rows ----------------------------------------------------

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """Whole-table read. `Limit` counts rows read; the filter runs afterwards.

        This is incident 1. A double that filters first and truncates afterwards hands
        back a full page however the table is laid out, which no real table can do.
        """
        with self.lock:
            self._record("scan", kwargs)
            ordered = [deepcopy(row) for _, row in sorted(self.rows.items())]
        return self._page(ordered, kwargs, sort_key=None)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record("query", kwargs)
            index_name = kwargs.get("IndexName")
            if index_name is None:
                candidates, sort_key = self._base_candidates(kwargs)
            else:
                candidates, sort_key = self._index_candidates(index_name, kwargs)
        if not kwargs.get("ScanIndexForward", True):
            candidates = list(reversed(candidates))
        return self._page(candidates, kwargs, sort_key=sort_key)

    def _base_candidates(self, kwargs: dict[str, Any]) -> tuple[list[dict[str, Any]], None]:
        condition = kwargs.get("KeyConditionExpression")
        if condition is None:
            raise AssertionError("query requires a KeyConditionExpression")
        rows = [deepcopy(row) for _, row in sorted(self.rows.items())]
        if isinstance(condition, str):
            evaluator = ConditionEvaluator(
                kwargs.get("ExpressionAttributeNames"), kwargs.get("ExpressionAttributeValues")
            )
            return [row for row in rows if evaluator.holds(condition, row)], None
        return [row for row in rows if _object_condition_holds(condition, row)], None

    def _index_candidates(
        self, index_name: str, kwargs: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str | None]:
        schema = self.indexes.get(index_name)
        if schema is None:
            raise AssertionError(f"unknown index: {index_name}")
        projected = [
            deepcopy(row)
            for _, row in sorted(self.rows.items())
            if schema.partition_key in row
            and (schema.sort_key is None or schema.sort_key in row)
        ]
        projected.sort(
            key=lambda row: (
                str(row.get(schema.partition_key)),
                str(row.get(schema.sort_key)) if schema.sort_key else "",
                _key_of(row),
            )
        )
        condition = kwargs.get("KeyConditionExpression")
        if condition is None:
            raise AssertionError("query requires a KeyConditionExpression")
        if isinstance(condition, str):
            evaluator = ConditionEvaluator(
                kwargs.get("ExpressionAttributeNames"), kwargs.get("ExpressionAttributeValues")
            )
            matched = [row for row in projected if evaluator.holds(condition, row)]
        else:
            matched = [row for row in projected if _object_condition_holds(condition, row)]
        return matched, schema.sort_key

    def _page(
        self, candidates: list[dict[str, Any]], kwargs: dict[str, Any], *, sort_key: str | None
    ) -> dict[str, Any]:
        """Cut one page out of an ordered candidate list, DynamoDB's way round.

        `Limit` first, over rows *read*; `FilterExpression` second, over what the limit
        left; `LastEvaluatedKey` whenever the read stopped before the end, whether or
        not anything survived the filter.

        A read with no `Limit` still stops at the response cap. Answering it with the
        whole table is how a census written as one unlimited scan looks complete here
        and reports a sample in production.
        """
        start = 0
        resume = kwargs.get("ExclusiveStartKey")
        if resume:
            wanted = (str(resume["PK"]), str(resume["SK"]))
            positions = [
                index for index, row in enumerate(candidates) if _key_of(row) == wanted
            ]
            start = positions[0] + 1 if positions else len(candidates)
        remaining = candidates[start:]
        limit = len(remaining) if kwargs.get("Limit") is None else int(kwargs["Limit"])
        if self.page_item_cap is not None:
            limit = min(limit, self.page_item_cap)
        window: list[dict[str, Any]] = []
        budget = self.page_size_bytes
        for row in remaining[:limit]:
            if window and budget <= 0:
                break
            window.append(row)
            budget -= item_size_bytes(row)
        exhausted = len(window) == len(remaining)
        items = [
            row
            for row in window
            if condition_holds(
                kwargs.get("FilterExpression"),
                row,
                names=kwargs.get("ExpressionAttributeNames"),
                values=kwargs.get("ExpressionAttributeValues"),
            )
        ]
        response: dict[str, Any] = {"Items": items, "Count": len(items), "ScannedCount": len(window)}
        if not exhausted and window:
            last = window[-1]
            key = {"PK": last["PK"], "SK": last["SK"]}
            if sort_key:
                key[sort_key] = last[sort_key]
            response["LastEvaluatedKey"] = key
        return response

    # -- transactions ------------------------------------------------------------

    def transact_write_items(self, operations: list[dict[str, Any]]) -> None:
        """All conditions, then all effects, under one lock.

        The lock is the transaction: without it two callers can both pass their
        conditions before either writes, and a conditional claim the real store would
        refuse gets through the double.
        """
        with self.lock:
            self._record("transact_write_items", {"operations": operations})
            staged: list[tuple[tuple[str, str], dict[str, Any] | None]] = []
            reasons: list[str] = []
            for operation in operations:
                for kind, body in operation.items():
                    key = (
                        (str(body["Key"]["PK"]), str(body["Key"]["SK"]))
                        if "Key" in body
                        else _key_of(body["Item"])
                    )
                    current = self.rows.get(key)
                    if not condition_holds(
                        body.get("ConditionExpression"),
                        current,
                        names=body.get("ExpressionAttributeNames"),
                        values=body.get("ExpressionAttributeValues"),
                    ):
                        reasons.append("ConditionalCheckFailed")
                        continue
                    reasons.append("None")
                    if kind == "ConditionCheck":
                        continue
                    if kind == "Put":
                        staged.append((key, as_stored(deepcopy(body["Item"]))))
                        continue
                    if kind == "Delete":
                        staged.append((key, None))
                        continue
                    if kind != "Update":
                        raise AssertionError(f"unsupported transaction operation: {kind}")
                    updated = deepcopy(current) if current is not None else dict(body["Key"])
                    apply_update_expression(
                        updated,
                        str(body["UpdateExpression"]),
                        body.get("ExpressionAttributeNames"),
                        body.get("ExpressionAttributeValues"),
                    )
                    staged.append((key, as_stored(updated)))
            if any(reason != "None" for reason in reasons):
                raise transaction_canceled(reasons)
            for key, row in staged:
                if row is None:
                    self.rows.pop(key, None)
                else:
                    self.rows[key] = row
