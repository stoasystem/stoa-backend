"""An index key may not be written as an empty string.

DynamoDB refuses `TransactWriteItems` outright when an attribute that is a
secondary index key carries "": *A value specified for a secondary index key is
not supported.* It is not a condition failure that can be retried - the whole
transaction is invalid.

This cost a production 503 on 2026-09-24. An assigned teacher-support admission
has no parent, and the receipt was written with `parent_id=""`. `parent_id` is
the partition key of `GSI-ParentId`, so every attempt was refused, reported as a
retryable dependency failure and retried four times before the student was told
teacher support was "briefly unavailable".

The in-memory doubles have no indexes, so all of it passed locally - the sixth
time a double being more permissive than the table has hidden a defect here.
This reads what the writers write instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fakes.dynamodb import DEFAULT_INDEXES, IndexSchema
from test_infra_workflow_contract import _resolve_infra_root


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC = BACKEND_ROOT / "src"

# The key attributes of every secondary index on `stoa-main`, from
# `stoa-infra/stacks/database_stack.py`. The last test holds this list, and the
# double's index table, to what that file declares.
INDEX_KEY_ATTRIBUTES = frozenset(
    {
        "email",
        "student_id",
        "created_at",
        "parent_id",
        "week_start",
        "teacher_id",
        "started_at",
        "review_state",
    }
)


def _writes_empty_index_key(node: ast.Dict) -> list[str]:
    """Index-key attributes this literal sets to a literal empty string."""
    offenders: list[str] = []
    for key, value in zip(node.keys, node.values, strict=False):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        if key.value not in INDEX_KEY_ATTRIBUTES:
            continue
        if isinstance(value, ast.Constant) and value.value == "":
            offenders.append(key.value)
    return offenders


# A dictionary only reaches the table through one of these. A literal that is
# never handed to one is an in-memory stand-in - the invitation projection
# returned for a digest that is not on file, the placeholder profile used when a
# child has none - and DynamoDB never sees it.
WRITE_SINKS = frozenset({"Item", "put_item", "Put", "transact", "put_user"})


def _dictionaries_that_reach_the_table(tree: ast.AST) -> list[ast.Dict]:
    """Every literal a row is built from, by the name it is built under too.

    The first version read only literals passed straight to a write. Rows are
    not written that way here - they are assigned to `receipt`, `counter`,
    `item` and handed over later - so the poison that was meant to prove this
    check had teeth came back green, on the exact defect it was written for.
    A name assigned a dictionary and later given to a write counts as the row.
    """
    reaching: list[ast.Dict] = []
    assigned: dict[str, ast.Dict] = {}
    written_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[target.id] = node.value
        if isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if called in WRITE_SINKS:
                written_names.update(
                    argument.id for argument in node.args if isinstance(argument, ast.Name)
                )
            for keyword in node.keywords:
                if keyword.arg in WRITE_SINKS and isinstance(keyword.value, ast.Name):
                    written_names.add(keyword.value.id)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in WRITE_SINKS
                    and isinstance(value, ast.Name)
                ):
                    written_names.add(value.id)

    reaching.extend(assigned[name] for name in written_names if name in assigned)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if called in WRITE_SINKS:
                reaching.extend(
                    argument for argument in node.args if isinstance(argument, ast.Dict)
                )
            for keyword in node.keywords:
                if keyword.arg in WRITE_SINKS and isinstance(keyword.value, ast.Dict):
                    reaching.append(keyword.value)
        # `{"Item": {...}}` and `{"Put": {"Item": {...}}}`, the transaction shapes.
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if isinstance(key, ast.Constant) and key.value in WRITE_SINKS:
                    reaching.extend(_literals_behind(value, assigned))
    # One literal can be reached by more than one route - by its name and again
    # through the transaction shape it is nested in. Report the row once.
    return list({id(node): node for node in reaching}.values())


def _literals_behind(value: ast.AST, assigned: dict[str, ast.Dict]) -> list[ast.Dict]:
    """The literals a write sink is actually handed, through one builder call.

    `{"Item": question_repo.question_item({...})}` used to read as "not a
    literal" and the row inside it was never scanned - the gate went green on a
    shape the codebase uses, which is the failure this file warns about in its
    own docstring and then had.
    """
    if isinstance(value, ast.Dict):
        return [value]
    if isinstance(value, ast.Name):
        return [assigned[value.id]] if value.id in assigned else []
    if isinstance(value, ast.Call):
        found: list[ast.Dict] = []
        for argument in (*value.args, *(keyword.value for keyword in value.keywords)):
            found.extend(_literals_behind(argument, assigned))
        return found
    return []


def empty_index_key_literals() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in _dictionaries_that_reach_the_table(tree):
            for attribute in _writes_empty_index_key(node):
                found.append(f"{path.relative_to(SRC.parent)}:{node.lineno} {attribute}")
    return found


def test_no_writer_sets_an_index_key_to_an_empty_string() -> None:
    offenders = empty_index_key_literals()

    assert offenders == [], (
        "DynamoDB refuses the whole transaction when a secondary index key is "
        "an empty string; leave the attribute out instead:\n  "
        + "\n  ".join(offenders)
    )


def _offenders_in(source: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in _dictionaries_that_reach_the_table(tree):
        found.extend(_writes_empty_index_key(node))
    return found


def test_the_reader_finds_one_when_there_is_one() -> None:
    """Negative control, in each shape a row actually reaches the table by."""
    assert _offenders_in('table.put_item(Item={"parent_id": "", "note": "x"})\n') == [
        "parent_id"
    ]
    assert _offenders_in(
        'ops = [{"Put": {"Item": {"parent_id": "", "note": "x"}}}]\n'
    ) == ["parent_id"]
    assert _offenders_in('repo.put_user({"email": ""})\n') == ["email"]
    # And by the name a row is actually built under, which is how these are
    # written - the shape the first version of this check could not see.
    assert _offenders_in(
        'receipt = {"parent_id": "", "note": "x"}\n'
        'table.put_item(Item=receipt)\n'
    ) == ["parent_id"]
    assert _offenders_in(
        'counter = {"parent_id": "", "note": "x"}\n'
        'ops = [{"Put": {"Item": counter}}]\n'
    ) == ["parent_id"]
    # And through a row builder, which is how the escalated question row is
    # written. This shape read as "not a literal" and the row inside it was
    # never scanned at all.
    assert _offenders_in(
        'ops = [{"Put": {"Item": question_repo.question_item('
        '{"parent_id": "", "note": "x"})}}]\n'
    ) == ["parent_id"]


def test_a_literal_that_never_reaches_the_table_is_not_reported() -> None:
    """The stand-ins are why this narrowed: they are memory, not rows.

    `ABSENT_INVITATION` is a same-shaped answer for a digest that is not on
    file, returned so a miss and a hit cannot be told apart by timing. It has
    `email: ""` and always will. Reporting it would have made this check
    something to silence rather than something to fix.
    """
    assert _offenders_in('ABSENT = {"email": "", "role": ""}\n') == []


def test_a_non_index_attribute_set_to_empty_is_not_reported() -> None:
    """Only index keys are refused, so only they are checked."""
    assert _offenders_in('table.put_item(Item={"note": "", "parent_id": "p-1"})\n') == []


def _attribute_name(node: ast.AST) -> str:
    """The `name=` of a `dynamodb.Attribute(...)` call."""
    if isinstance(node, ast.Call):
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
    raise AssertionError(f"not a literal dynamodb.Attribute: {ast.dump(node)}")


def declared_indexes(stack_source: str) -> dict[str, IndexSchema]:
    """Every `add_global_secondary_index` in the CDK stack, as the double spells it.

    Read from the source, not from a list of names: the first version of this
    check filtered `INDEX_KEY_ATTRIBUTES` by whether each name appeared in the
    file, so it could only notice a removal. An index added to the table and not
    to the double came back `5 passed`, on the exact case it existed for.
    """
    declared: dict[str, IndexSchema] = {}
    for node in ast.walk(ast.parse(stack_source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_global_secondary_index"
        ):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        name = keywords["index_name"]
        assert isinstance(name, ast.Constant) and isinstance(name.value, str), ast.dump(name)
        assert name.value not in declared, f"{name.value} is declared twice"
        sort_key = keywords.get("sort_key")
        declared[name.value] = IndexSchema(
            _attribute_name(keywords["partition_key"]),
            None if sort_key is None else _attribute_name(sort_key),
        )
    return declared


def _database_stack_source() -> str:
    # Backend CI and the formal gate both check the infra repository out beside
    # this one, so a missing sibling means this check is not reading what it
    # guards. Fail, do not skip: skipping is how this gate went quiet before.
    try:
        infra_root = _resolve_infra_root(BACKEND_ROOT)
    except RuntimeError as exc:
        pytest.fail(f"the infra repository is not beside this checkout: {exc}")
    stack = infra_root / "stacks" / "database_stack.py"
    if not stack.is_file():
        pytest.fail(f"the table definition is not where this gate reads it: {stack}")
    return stack.read_text(encoding="utf-8")


def test_the_double_carries_exactly_the_indexes_the_table_declares() -> None:
    """Name, partition key and sort key, in both directions.

    Since card 036 the double enforces every index it knows about - a row with
    an empty or NULL key attribute is refused just as the table refuses it. An
    index the double does not know about is one it silently lets through, which
    is the gap this suite has been bitten by six times.
    """
    assert declared_indexes(_database_stack_source()) == DEFAULT_INDEXES


def test_the_index_key_list_matches_the_table_definition() -> None:
    """The list above is a copy of the infrastructure, so it has to still match."""
    declared = declared_indexes(_database_stack_source())
    key_attributes = {
        attribute
        for schema in declared.values()
        for attribute in (schema.partition_key, schema.sort_key)
        if attribute is not None
    }

    assert key_attributes == INDEX_KEY_ATTRIBUTES


STACK_FRAGMENT = """
self.table.add_global_secondary_index(
    index_name="GSI-Email",
    partition_key=dynamodb.Attribute(name="email", type=dynamodb.AttributeType.STRING),
    projection_type=dynamodb.ProjectionType.ALL,
)
self.table.add_global_secondary_index(
    index_name="GSI-Poison",
    partition_key=dynamodb.Attribute(
        name="poison_attr", type=dynamodb.AttributeType.STRING
    ),
    sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
    projection_type=dynamodb.ProjectionType.ALL,
)
"""


def test_the_stack_reader_sees_an_added_index_and_its_keys() -> None:
    """Negative control: the poison the card names has to come out of the reader."""
    assert declared_indexes(STACK_FRAGMENT) == {
        "GSI-Email": IndexSchema("email"),
        "GSI-Poison": IndexSchema("poison_attr", "created_at"),
    }
    assert declared_indexes("table = dynamodb.Table(self, 'T')\n") == {}
