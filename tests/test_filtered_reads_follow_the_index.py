"""A filtered read must follow the continuation key, everywhere.

DynamoDB applies `Limit` to rows read and the filter afterwards, so one call
returns whatever survived the filter on that page and a key to carry on with.
Trusting one page has produced the same defect four times in this codebase:

  * the account console listed no accounts at all, on a table of 5517 rows
  * `/admin/stats` counted a fraction of the platform and called it the total
  * a conversation list lost everything behind its first shared-index page
  * a parent's weekly report showed a child who had asked nothing

Every one of them was a read that filtered and stopped. The rule is not "use a
bigger limit", which agrees with itself until the table grows; it is that a read
which filters must either follow the key or be the kind of read that cannot
leave anything behind it.
"""

from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"

# A read whose own function never mentions the continuation key, and does not
# have to: these answer a question a page cannot truncate. Each is named rather
# than pattern-matched, so a new one has to be somebody's decision.
READS_THAT_CANNOT_TRUNCATE: frozenset[str] = frozenset()


def filtered_reads_that_stop_after_one_page() -> list[str]:
    """Every `query`/`scan` in a filtering function that ignores the key.

    The filter is looked for anywhere in the function, not only as a keyword on
    the call. The first version of this check read keywords alone, and every
    read fixed by building the request as a dict and passing `**request` became
    invisible to it - including the two this file was written for. A check that
    stops seeing a read the moment somebody rearranges the call is not a check.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dumped = ast.dump(node)
            if "FilterExpression" not in dumped:
                continue
            if "LastEvaluatedKey" in dumped or "ExclusiveStartKey" in dumped:
                continue
            for call in ast.walk(node):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                    continue
                if call.func.attr not in ("query", "scan"):
                    continue
                where = f"{path.relative_to(SRC.parent)}:{call.lineno} {node.name}"
                if node.name in READS_THAT_CANNOT_TRUNCATE:
                    continue
                offenders.append(where)
    return offenders


def test_no_filtered_read_stops_after_one_page() -> None:
    offenders = filtered_reads_that_stop_after_one_page()

    assert offenders == [], (
        "these reads filter and never follow the continuation key, so they "
        "report whatever survived one page as the whole answer:\n  "
        + "\n  ".join(offenders)
    )


def test_the_reader_finds_the_reads_it_claims_to_check() -> None:
    """Negative control: an empty answer has to mean "none", not "read nothing".

    Without this, deleting the walk above would pass the check for good.
    """
    def offenders_in(source: str) -> list[str]:
        module = ast.parse(source)
        found = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dumped = ast.dump(node)
            if "FilterExpression" not in dumped:
                continue
            if "LastEvaluatedKey" in dumped or "ExclusiveStartKey" in dumped:
                continue
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("query", "scan")
                ):
                    found.append(node.name)
        return found

    # As a keyword on the call...
    assert offenders_in(
        "def keyworded(table):\n"
        "    return table.query(FilterExpression='x', Limit=50)\n"
    ) == ["keyworded"]

    # ...and built into a dict and splatted, which is the shape every fix here
    # uses and the shape the first version of this check could not see.
    assert offenders_in(
        "def splatted(table):\n"
        "    request = {'FilterExpression': 'x', 'Limit': 50}\n"
        "    return table.query(**request)\n"
    ) == ["splatted"]


def test_a_read_that_follows_the_key_is_not_reported() -> None:
    """Second negative control: the check must not simply refuse every filter."""
    module = ast.parse(
        "from boto3.dynamodb.conditions import Attr\n"
        "def paged(table):\n"
        "    key = None\n"
        "    while True:\n"
        "        page = table.query(FilterExpression=Attr('x').eq('y'), ExclusiveStartKey=key)\n"
        "        key = page.get('LastEvaluatedKey')\n"
        "        if key is None:\n"
        "            return page\n"
    )
    reported = []
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        dumped = ast.dump(node)
        if "FilterExpression" not in dumped:
            continue
        if "LastEvaluatedKey" in dumped or "ExclusiveStartKey" in dumped:
            continue
        reported.append(node.name)

    assert reported == []
