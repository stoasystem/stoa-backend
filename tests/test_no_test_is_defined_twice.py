"""No test module may define the same test twice in one scope.

Python keeps the last definition of a name, so the first one is replaced
before pytest collects anything: it never runs, and nothing reports it. That
is how `stoa-infra/tests/test_release_topology.py` carried two copies of
`test_a_waiting_student_is_swept_back_to_a_teacher` with only one collected.
The copies were identical, so nothing was lost that time; the next pair need
not be.

Ruff's F811 catches this in this repository, but stoa-infra's CI runs ruff on
the CDK app only, never on its tests. This reads both, from the source.

A scope is a module body or a class body: pytest collects `test*` functions
at the top of a module and `test*` methods of a class, and Python replaces a
repeated name within either. The same name in two classes, or in two
modules, is not a defect: pytest tells those apart. Both file patterns
pytest collects by default are read, `test_*.py` and `*_test.py`.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

from test_infra_workflow_contract import _resolve_infra_root


BACKEND_ROOT = Path(__file__).resolve().parents[1]
BACKEND_TESTS = BACKEND_ROOT / "tests"
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")


def _test_names(body: list[ast.stmt]) -> Counter[str]:
    return Counter(
        node.name
        for node in body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test")
    )


def _names_defined_twice(source: str) -> list[str]:
    """Tests this module defines more than once in one scope.

    A module-level test is named as is; a method as `Class.test`.
    """
    tree = ast.parse(source)
    repeated = [name for name, count in _test_names(tree.body).items() if count > 1]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            repeated.extend(
                f"{node.name}.{name}"
                for name, count in _test_names(node.body).items()
                if count > 1
            )
    return sorted(repeated)


def _test_modules(root: Path) -> list[Path]:
    return sorted({module for pattern in TEST_FILE_PATTERNS for module in root.rglob(pattern)})


def _duplicates_under(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for module in _test_modules(root):
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


def test_a_method_defined_twice_in_one_class_is_reported() -> None:
    source = (
        "class TestThing:\n"
        "    def test_a(self):\n        pass\n\n"
        "    def test_a(self):\n        pass\n"
    )

    assert _names_defined_twice(source) == ["TestThing.test_a"]


def test_the_same_name_in_two_classes_or_at_top_level_is_not_reported() -> None:
    source = (
        "def test_a():\n    pass\n\n\n"
        "class TestOne:\n    def test_a(self):\n        pass\n\n\n"
        "class TestTwo:\n    def test_a(self):\n        pass\n"
    )

    assert _names_defined_twice(source) == []


def test_differently_named_tests_and_helpers_are_not_reported() -> None:
    source = (
        "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n\n\n"
        "def _helper():\n    pass\n\n\ndef _helper():\n    pass\n"
    )

    assert _names_defined_twice(source) == []


def test_both_file_patterns_pytest_collects_are_read(tmp_path: Path) -> None:
    duplicated = "def test_a():\n    pass\n\n\ndef test_a():\n    pass\n"
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_one.py").write_text(duplicated, encoding="utf-8")
    (tmp_path / "tests" / "two_test.py").write_text(duplicated, encoding="utf-8")
    (tmp_path / "tests" / "helper.py").write_text(duplicated, encoding="utf-8")

    assert _duplicates_under(tmp_path / "tests") == {
        "tests/test_one.py": ["test_a"],
        "tests/two_test.py": ["test_a"],
    }


def test_no_backend_test_module_defines_a_test_twice() -> None:
    assert _duplicates_under(BACKEND_TESTS) == {}


def test_no_infra_test_module_defines_a_test_twice() -> None:
    # Backend CI and the formal gate both check the infra repository out
    # beside this one, so a missing sibling means this check is not reading
    # what it guards. The rule for finding it is the one the workflow
    # contract already uses.
    try:
        infra_root = _resolve_infra_root(BACKEND_ROOT)
    except RuntimeError as exc:
        pytest.fail(f"infra tests are not beside this checkout: {exc}")

    assert _duplicates_under(infra_root / "tests") == {}
