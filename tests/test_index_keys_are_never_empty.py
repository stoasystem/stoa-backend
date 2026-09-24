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


SRC = Path(__file__).resolve().parents[1] / "src"

# The key attributes of every secondary index on `stoa-main`, from
# `stoa-infra/stacks/database_stack.py`.
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


def test_the_index_key_list_matches_the_table_definition() -> None:
    """The list above is a copy of the infrastructure, so it has to still match.

    If an index is added and this list is not, the check quietly stops covering
    it - which is the shape of every gate in this repository that went quiet.
    """
    stack = (
        Path(__file__).resolve().parents[2]
        / "stoa-infra"
        / "stacks"
        / "database_stack.py"
    )
    if not stack.exists():
        # The sibling checkout is not always present; the check above still runs.
        return
    source = stack.read_text(encoding="utf-8")
    declared = {
        literal
        for literal in INDEX_KEY_ATTRIBUTES
        if f'name="{literal}"' in source
    }

    assert declared == INDEX_KEY_ATTRIBUTES, (
        "these are listed here but no longer declared on the table: "
        f"{sorted(INDEX_KEY_ATTRIBUTES - declared)}"
    )
