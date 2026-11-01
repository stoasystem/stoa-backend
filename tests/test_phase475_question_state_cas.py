from __future__ import annotations

import ast
from pathlib import Path

from stoa.db.repositories import question_repo


ROOT = Path(__file__).resolve().parents[1]


def _question_repo_calls(path: str) -> list[tuple[str, str]]:
    tree = ast.parse((ROOT / path).read_text())
    calls: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            func = child.func if isinstance(child, ast.Call) else None
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "question_repo"
                and func.attr in {
                    "mutate_question",
                    "update_status",
                    "update_status_conditionally",
                }
            ):
                calls.append((node.name, func.attr))
    return calls


def _dict_value(node: ast.Dict, key: str) -> ast.expr | None:
    for candidate, value in zip(node.keys, node.values, strict=True):
        if isinstance(candidate, ast.Constant) and candidate.value == key:
            return value
    return None


def _is_question_partition_key(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.startswith("QUESTION#")
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.startswith("QUESTION#")
            for value in node.values
        )
    return False


def _direct_question_updates(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    updates: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Dict):
                continue
            update = _dict_value(node, "Update")
            if not isinstance(update, ast.Dict):
                continue
            key = _dict_value(update, "Key")
            if not isinstance(key, ast.Dict):
                continue
            if _is_question_partition_key(_dict_value(key, "PK")):
                updates.add(function.name)
    return updates


def test_production_question_writer_registry_is_closed_over_cas_calls():
    # The question routes that wrote here (submit, request-teacher, feedback)
    # were retired in #148, the teacher-side ones with the question lane (#188),
    # and the chat help request's queue row with #189: no question row is
    # mutated any more, so the compare-and-set machinery went too.
    for name in (
        "mutate_question",
        "initialize_legacy_question_version",
        "build_question_update_transaction",
        "update_status",
        "update_status_conditionally",
    ):
        assert not hasattr(question_repo, name), name
    callers = {
        path.relative_to(ROOT).as_posix(): calls
        for path in (ROOT / "src/stoa").rglob("*.py")
        if (calls := _question_repo_calls(path.relative_to(ROOT).as_posix()))
    }
    assert callers == {}

    direct_registry = {
        "src/stoa/db/repositories/question_submission_repo.py": {
            "reverse_terminal_question_admission",
        },
    }
    discovered: dict[str, set[str]] = {}
    for path in (ROOT / "src/stoa").rglob("*.py"):
        functions = _direct_question_updates(path)
        if functions:
            discovered[path.relative_to(ROOT).as_posix()] = functions
    assert discovered == direct_registry
