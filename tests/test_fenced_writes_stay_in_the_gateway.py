"""A write behind an account's fence goes through `db_table.fenced` (#297, #210).

Callers used to read the fence, build its condition, put it in front of their own
operations and judge the refusal themselves - in some thirty files, with a private
builder in several. `stoa.db.table.fenced` does all four now; a module that builds
`active_fence_condition(...)` itself has started a fenced write of its own.

Two modules keep it. The account deletion flow owns the fence and holds a closing
account's deletion fence beside an active one in the same transaction. And the
files below, until they move: the list is expected to stay empty, except for
`subscription_service.py` while payments are frozen.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "stoa"

OWNERS = {
    "src/stoa/db/table.py",
    "src/stoa/db/repositories/account_deletion_repo.py",
}

ALLOWED: set[str] = {"src/stoa/services/subscription_service.py"}

_CALL = re.compile(r"\bactive_fence_condition\(")


def _calls(text: str) -> list[str]:
    return [
        f"{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if _CALL.search(line)
    ]


def _offenders() -> dict[str, list[str]]:
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative in OWNERS:
            continue
        found = _calls(path.read_text(encoding="utf-8"))
        if found:
            offenders[relative] = found
    return offenders


def test_no_module_builds_the_fence_condition_itself():
    new = {path: lines[:3] for path, lines in _offenders().items() if path not in ALLOWED}
    assert not new, f"write it through stoa.db.table.fenced instead: {new}"


def test_the_allowlist_names_only_files_that_still_need_it():
    stale = ALLOWED - set(_offenders())
    assert not stale, f"no longer builds the fence condition; remove from ALLOWED: {sorted(stale)}"


def test_the_gateway_is_where_the_condition_is_added():
    assert _calls((ROOT / "src/stoa/db/table.py").read_text(encoding="utf-8"))


def test_the_gate_sees_what_it_guards():
    assert _calls("    account_deletion_repo.active_fence_condition(owner, generation),\n")
    assert _calls("[active_fence_condition(user_id), mutation]\n")
    assert not _calls('"active_fence_condition" is named, not called\n')
