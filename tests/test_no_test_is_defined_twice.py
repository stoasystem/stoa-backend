"""No test module may define the same top-level test function twice.

Python keeps the last definition of a name, so the first one is replaced
before pytest collects anything: it never runs, and nothing reports it. That
is how `stoa-infra/tests/test_release_topology.py` carried two copies of
`test_a_waiting_student_is_swept_back_to_a_teacher` with only one collected.
The copies were identical, so nothing was lost that time; the next pair need
not be.

Ruff's F811 catches this in this repository, but stoa-infra's CI runs ruff on
the CDK app only, never on its tests. This reads both, from the source.

Only top-level functions in one module are compared. A method repeated inside
a class is not looked at, and the same name in two modules is not a defect:
pytest tells those apart by module.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest


BACKEND_TESTS = Path(__file__).resolve().parent
# Beside a developer checkout the sibling is stoa-infra; the formal release gate
# lays the three repositories out as backend/, frontend/ and infra/. Accept
# either, as test_infra_workflow_contract does.
INFRA_TEST_CANDIDATES = tuple(
    Path(__file__).resolve().parents[2] / name / "tests" for name in ("stoa-infra", "infra")
)


def _names_defined_twice(source: str) -> list[str]:
    """Top-level `test*` functions this module defines more than once."""
    tree = ast.parse(source)
    names = Counter(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test")
    )
    return sorted(name for name, count in names.items() if count > 1)


def _duplicates_under(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for module in sorted(root.rglob("test_*.py")):
        names = _names_defined_twice(module.read_text(encoding="utf-8"))
        if names:
            found[str(module.relative_to(root.parent))] = names
    return found


def test_a_test_defined_twice_is_reported() -> None:
    source = "def test_a():\n    pass\n\n\ndef test_a():\n    pass\n"

    assert _names_defined_twice(source) == ["test_a"]


def test_an_async_test_defined_twice_is_reported() -> None:
    source = "async def test_a():\n    pass\n\n\nasync def test_a():\n    pass\n"

    assert _names_defined_twice(source) == ["test_a"]


def test_differently_named_tests_and_helpers_are_not_reported() -> None:
    source = (
        "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n\n\n"
        "def _helper():\n    pass\n\n\ndef _helper():\n    pass\n"
    )

    assert _names_defined_twice(source) == []


def test_no_backend_test_module_defines_a_test_twice() -> None:
    assert _duplicates_under(BACKEND_TESTS) == {}


def test_no_infra_test_module_defines_a_test_twice() -> None:
    found = [candidate for candidate in INFRA_TEST_CANDIDATES if candidate.is_dir()]
    if not found:
        # Backend CI and the formal gate both check the infra repository out
        # beside this one, so a missing sibling means this check is not
        # reading what it guards.
        tried = ", ".join(str(candidate) for candidate in INFRA_TEST_CANDIDATES)
        pytest.fail(f"infra tests are not beside this checkout; tried {tried}")

    assert _duplicates_under(found[0]) == {}
