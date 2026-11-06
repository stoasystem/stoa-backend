"""Services and the data layer refuse with rule violations, not HTTP (#211).

A service that raises `HTTPException` decides the transport from inside the
domain, and its sentence reaches the client untranslated. The rule says what was
broken (`stoa.rule_violation.RuleViolation`) and the application renders it.

The files below still import FastAPI or raise `HTTPException`. Each step of
#211 that moves one off removes its line; a file not listed may not start, and a
listed file that no longer does must be taken off.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARDED = (ROOT / "src" / "stoa" / "services", ROOT / "src" / "stoa" / "db")

ALLOWED = {
    "src/stoa/services/curriculum_migration_service.py",
    "src/stoa/services/curriculum_ops_service.py",
    # Stays until payments are unfrozen and Stripe is split out.
    "src/stoa/services/subscription_service.py",
}


def _is_http_exception(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id == "HTTPException"
    return isinstance(node, ast.Attribute) and node.attr == "HTTPException"


def _reaches_http(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "fastapi":
            found.append(f"{node.lineno}: from {node.module} import")
        elif isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "fastapi" for alias in node.names
        ):
            found.append(f"{node.lineno}: import fastapi")
        elif isinstance(node, ast.Raise) and _is_http_exception(node.exc):
            found.append(f"{node.lineno}: raise HTTPException")
    return found


def _offenders() -> dict[str, list[str]]:
    offenders = {}
    for root in GUARDED:
        for path in sorted(root.rglob("*.py")):
            found = _reaches_http(ast.parse(path.read_text(encoding="utf-8"), str(path)))
            if found:
                offenders[path.relative_to(ROOT).as_posix()] = found
    return offenders


def test_no_new_service_or_data_module_reaches_for_http():
    offenders = _offenders()
    new = {path: lines[:3] for path, lines in offenders.items() if path not in ALLOWED}
    assert not new, f"raise a RuleViolation instead of answering HTTP: {new}"


def test_the_allowlist_names_only_files_that_still_need_it():
    stale = ALLOWED - set(_offenders())
    assert not stale, f"no longer reaches for HTTP; remove from ALLOWED: {sorted(stale)}"


def test_the_gate_sees_what_it_guards():
    tree = ast.parse(
        "from fastapi import HTTPException\n"
        "def f():\n"
        "    raise HTTPException(status_code=400)\n"
        "def g():\n"
        "    import fastapi.responses\n"
        "    raise errors.HTTPException(404)\n"
    )
    assert len(_reaches_http(tree)) == 4
