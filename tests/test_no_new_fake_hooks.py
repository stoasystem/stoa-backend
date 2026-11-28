"""No new `getattr(table|target|repository, ...)` hooks for test doubles (#629).

A hook such as `hook = getattr(target, "claim_delivery_intent", None)` lets a fake
table or fake repository stand in for one step. The real boto3 Table has no such
attribute, so production always takes the other branch, and a fake that lacks the
method silently skips the step: the old per-resource attachment release ran
without its retention fence for any repository lacking the method that opened
it (both gone with #655).

#629 removed the fifteen hooks no fake used any more. The ones listed below are
still in use. The account-deletion ones went with the old deletion branches (#642),
the attachment service's with its three leave actions (#653), the notification one
with #684.
A hook not listed may not appear, and a listed hook that is gone must be taken off.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = ROOT / "src" / "stoa" / "db" / "repositories"
ATTACHMENT_SERVICE = ROOT / "src" / "stoa" / "services" / "attachment_service.py"
SEAMS = {"table", "target", "repository"}

Hook = tuple[str, str, str]  # (file, enclosing function, attribute asked for)

ALLOWED: Counter[Hook] = Counter(
    {
        # Other repositories, as found when the gate was added.
        ("src/stoa/db/repositories/allowance_repo.py", "_strong_get", "'get_item'"): 1,
        ("src/stoa/db/repositories/identity_repo.py", "create_identity_binding", "'meta'"): 1,
        (
            "src/stoa/db/repositories/public_identity_repo.py",
            "create_or_get_public_identity_command",
            "'meta'",
        ): 1,
        ("src/stoa/db/repositories/public_identity_repo.py", "require_command_fence", "'meta'"): 1,
        ("src/stoa/db/repositories/weekly_counter.py", "read", "'get_item'"): 1,
    }
)


def _hooks_in(source: str, relative: str) -> Counter[Hook]:
    found: Counter[Hook] = Counter()

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            enclosing = (
                child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                else function
            )
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "getattr"
                and len(child.args) >= 2
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id in SEAMS
            ):
                found[(relative, enclosing, ast.unparse(child.args[1]))] += 1
            visit(child, enclosing)

    visit(ast.parse(source), "<module>")
    return found


def _hooks() -> Counter[Hook]:
    found: Counter[Hook] = Counter()
    for path in [*sorted(REPOSITORIES.rglob("*.py")), ATTACHMENT_SERVICE]:
        relative = path.relative_to(ROOT).as_posix()
        found += _hooks_in(path.read_text(encoding="utf-8"), relative)
    return found


def test_no_new_hook_lets_a_fake_replace_a_step():
    new = _hooks() - ALLOWED
    assert not new, (
        "call the real implementation and give the fake the method instead: "
        f"{sorted(new)}"
    )


def test_the_allowlist_names_only_hooks_that_are_still_there():
    stale = ALLOWED - _hooks()
    assert not stale, f"hook removed; take it off ALLOWED: {sorted(stale)}"


def test_the_gate_sees_what_it_guards():
    source = (
        "def step(target, repository, table):\n"
        "    hook = getattr(target, 'claim_delivery_intent', None)\n"
        "    probe = getattr(repository, name, None)\n"
        "    meta = getattr(table, 'meta')\n"
        "    read = getattr(body, 'read', None)\n"
    )
    assert _hooks_in(source, "f.py") == Counter(
        {
            ("f.py", "step", "'claim_delivery_intent'"): 1,
            ("f.py", "step", "name"): 1,
            ("f.py", "step", "'meta'"): 1,
        }
    )
